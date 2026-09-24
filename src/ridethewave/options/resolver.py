"""Resolve a StructureTemplate against a chain snapshot into concrete legs (from TraderPro).

Selection: expiry nearest the target DTE (far bucket = target + offset);
strikes per rule on the actual strike grid; liquidity filter (two-sided
quote, sane spread). Returns entry pricing (net debit/credit at mid) and
defined-risk max profit/loss where computable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ridethewave.options.chain import ChainSnapshot, OptionContract
from ridethewave.options.structures import Leg, StructureTemplate

MAX_SPREAD_PCT_OF_MID = 0.25  # reject contracts quoted wider than 25% of mid
MIN_MID = 0.05  # skip near-worthless contracts


@dataclass
class ResolvedLeg:
    symbol: str  # OCC symbol, or the underlying ticker for stock
    instrument: str  # call | put | stock
    side: str  # buy | sell
    ratio: int
    strike: float | None
    expiry: date | None
    mid: float  # option mid (per share) or stock price


@dataclass
class ResolvedStructure:
    template_id: str
    underlying: str
    legs: list[ResolvedLeg]
    net_per_unit: float  # negative = debit, positive = credit (per 1x, x100 for options)
    max_profit: float | None  # per unit, None if unlimited/unknown
    max_loss: float | None


class ResolutionError(Exception):
    pass


def _pick_expiry(chain: ChainSnapshot, target_dte: int) -> date:
    expiries = chain.expiries()
    if not expiries:
        raise ResolutionError("empty chain")
    today = chain.today  # the snapshot's own date, never the wall clock (replayable)
    return min(expiries, key=lambda e: abs((e - today).days - target_dte))


def _liquid(c: OptionContract) -> bool:
    if c.bid <= 0 or c.ask <= 0:
        return False
    mid = c.mid
    return mid >= MIN_MID and (c.ask - c.bid) <= max(MAX_SPREAD_PCT_OF_MID * mid, 0.10)


def _strike_grid(chain: ChainSnapshot, expiry: date, right: str) -> list[OptionContract]:
    contracts = [c for c in chain.slice(expiry, right) if _liquid(c)]
    if not contracts:
        raise ResolutionError(f"no liquid {right} contracts for {expiry}")
    return contracts


def _nearest(contracts: list[OptionContract], strike: float) -> OptionContract:
    return min(contracts, key=lambda c: abs(c.strike - strike))


def _atm_index(contracts: list[OptionContract], spot: float) -> int:
    return min(range(len(contracts)), key=lambda i: abs(contracts[i].strike - spot))


def resolve(
    template: StructureTemplate,
    chain: ChainSnapshot,
    target_dte: int = 30,
    far_dte_offset: int = 30,
) -> ResolvedStructure:
    near_expiry = _pick_expiry(chain, target_dte)
    far_expiry = _pick_expiry(chain, target_dte + far_dte_offset)
    if any(leg.expiry == "far" for leg in template.legs) and far_expiry == near_expiry:
        raise ResolutionError("chain window has no distinct far expiry for calendar/diagonal")

    resolved: list[ResolvedLeg] = []
    for leg in template.legs:
        if leg.instrument == "stock":
            resolved.append(
                ResolvedLeg(
                    symbol=chain.underlying,
                    instrument="stock",
                    side=leg.side,
                    ratio=leg.ratio * 100,  # 100 shares per option unit
                    strike=None,
                    expiry=None,
                    mid=chain.spot,
                )
            )
            continue

        expiry = far_expiry if leg.expiry == "far" else near_expiry
        right = "C" if leg.instrument == "call" else "P"
        grid = _strike_grid(chain, expiry, right)
        contract = _resolve_strike(leg, grid, chain.spot, resolved)
        resolved.append(
            ResolvedLeg(
                symbol=contract.symbol,
                instrument=leg.instrument,
                side=leg.side,
                ratio=leg.ratio,
                strike=contract.strike,
                expiry=contract.expiry,
                mid=contract.mid,
            )
        )

    net = 0.0
    for rleg in resolved:
        sign = -1 if rleg.side == "buy" else 1
        qty = rleg.ratio if rleg.instrument != "stock" else rleg.ratio / 100
        net += sign * rleg.mid * qty
    max_profit, max_loss = _payoff_bounds(template, resolved, net)

    return ResolvedStructure(
        template_id=template.id,
        underlying=chain.underlying,
        legs=resolved,
        net_per_unit=round(net, 4),
        max_profit=max_profit,
        max_loss=max_loss,
    )


# One "step" of moneyness ≈ 1% of spot. Dense strike grids (SPY: $1 on a $700
# underlying) make raw grid-index stepping meaninglessly narrow; percent-based
# steps keep structures sensibly proportioned on any underlying.
STEP_PCT = 0.01


def _resolve_strike(leg: Leg, grid: list[OptionContract], spot: float, resolved: list[ResolvedLeg]) -> OptionContract:
    rule = leg.strike
    if rule is None:
        raise ResolutionError("option leg missing strike rule")
    if rule.kind == "same":
        ref = resolved[rule.n]
        if ref.strike is None:
            raise ResolutionError(f"same({rule.n}) references a stock leg")
        return _nearest(grid, ref.strike)

    atm_i = _atm_index(grid, spot)
    if rule.kind == "atm":
        return grid[atm_i]

    is_call = grid[0].right == "C"
    # OTM: calls above spot, puts below. ITM: the reverse.
    direction = 1 if (rule.kind == "otm") == is_call else -1
    target = spot * (1 + direction * rule.n * STEP_PCT)
    contract = _nearest(grid, target)
    if contract.strike == grid[atm_i].strike and rule.n != 0:
        # target collapsed onto ATM (coarse grid) — take one grid step outward
        index = atm_i + direction
        if not 0 <= index < len(grid):
            raise ResolutionError("strike grid too narrow for requested offset")
        contract = grid[index]
    return contract


def _payoff_bounds(
    template: StructureTemplate, legs: list[ResolvedLeg], net: float
) -> tuple[float | None, float | None]:
    """Exact bounds via payoff evaluation on a spot grid (options-only,
    single-expiry, defined-risk structures). None = unlimited/unknown."""
    if template.has_stock_leg or not template.defined_risk:
        return None, None
    expiries = {leg.expiry for leg in legs}
    if len(expiries) > 1:
        return None, None  # calendars: payoff at near expiry isn't terminal

    strikes = [leg.strike for leg in legs if leg.strike]
    lo, hi = min(strikes) * 0.5, max(strikes) * 1.5
    grid = [lo + (hi - lo) * i / 400 for i in range(401)]
    payoffs = []
    for s in grid:
        value = net  # entry cashflow per unit
        for leg in legs:
            intrinsic = max(s - leg.strike, 0) if leg.instrument == "call" else max(leg.strike - s, 0)
            value += (1 if leg.side == "buy" else -1) * intrinsic * leg.ratio
        payoffs.append(value)
    return round(max(payoffs), 4), round(-min(payoffs), 4)
