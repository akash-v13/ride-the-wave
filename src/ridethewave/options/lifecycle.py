"""Structure lifecycle rules: sizing, valuation and exits. Pure functions (from TraderPro's lifecycle).

Value convention: V(legs) = Σ (buy: +1 / sell: −1) · mid · ratio per structure unit, in per-share terms.
At entry V_entry = −entry_net (a credit received makes the held package worth a negative amount).
P&L per unit = entry_net + V_now: a credit structure reaches its max profit as V_now → 0, a debit
structure profits as V_now grows past the debit paid. Dollar P&L = per unit × 100 × qty.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from ridethewave.options.resolver import ResolvedLeg, ResolvedStructure

CONTRACT_MULT = 100


@dataclass
class Structure:
    id: str
    strategy: str
    run_id: str
    mode: str
    template_id: str
    underlying: str
    qty: int
    legs: list[dict]  # {symbol, instrument, side, ratio, strike, expiry (iso), mid}
    entry_net: float
    max_profit: float | None
    max_loss: float | None
    opened_at: datetime
    status: str = "open"
    closed_at: datetime | None = None
    exit_net: float | None = None
    realized_pl: float | None = None
    close_reason: str | None = None
    broker_order_id: str | None = None
    notes: dict = field(default_factory=dict)

    def min_dte(self, today: date) -> int | None:
        exps = [date.fromisoformat(x["expiry"]) for x in self.legs if x.get("expiry")]
        return min((e - today).days for e in exps) if exps else None

    def unrealized(self, value: float) -> float:
        return (self.entry_net + value) * CONTRACT_MULT * self.qty

    @property
    def option_symbols(self) -> list[str]:
        return [x["symbol"] for x in self.legs if x["instrument"] != "stock"]

    @property
    def stock_symbols(self) -> list[str]:
        return [x["symbol"] for x in self.legs if x["instrument"] == "stock"]

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "strategy": self.strategy,
            "run_id": self.run_id,
            "mode": self.mode,
            "template_id": self.template_id,
            "underlying": self.underlying,
            "qty": self.qty,
            "legs_json": json.dumps(self.legs),
            "entry_net": self.entry_net,
            "max_profit": self.max_profit,
            "max_loss": self.max_loss,
            "status": self.status,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "exit_net": self.exit_net,
            "realized_pl": self.realized_pl,
            "close_reason": self.close_reason,
            "broker_order_id": self.broker_order_id,
        }

    @classmethod
    def from_row(cls, r) -> Structure:
        return cls(
            id=r["id"],
            strategy=r["strategy"],
            run_id=r["run_id"],
            mode=r["mode"],
            template_id=r["template_id"],
            underlying=r["underlying"],
            qty=int(r["qty"]),
            legs=json.loads(r["legs_json"]),
            entry_net=r["entry_net"],
            max_profit=r["max_profit"],
            max_loss=r["max_loss"],
            opened_at=datetime.fromisoformat(r["opened_at"]),
            status=r["status"],
            closed_at=datetime.fromisoformat(r["closed_at"]) if r["closed_at"] else None,
            exit_net=r["exit_net"],
            realized_pl=r["realized_pl"],
            close_reason=r["close_reason"],
            broker_order_id=r["broker_order_id"],
        )


def leg_dicts(resolved: ResolvedStructure) -> list[dict]:
    out = []
    for leg in resolved.legs:
        d = asdict(leg)
        d["expiry"] = leg.expiry.isoformat() if leg.expiry else None
        out.append(d)
    return out


def size_structure(
    resolved: ResolvedStructure, capital: float, risk_fraction: float, max_risk_pct: float
) -> int | None:
    """Units so that the estimated max loss (or the debit) is ``risk_fraction`` of capital, capped at
    ``max_risk_pct``; None when even one unit costs more than the capital allows (TraderPro's rule)."""
    stock_cost = sum(leg.mid * leg.ratio for leg in resolved.legs if leg.instrument == "stock" and leg.side == "buy")
    # the option legs' own net (the structure net includes the stock leg, which must not be counted twice)
    net_options = sum(
        (1 if leg.side == "sell" else -1) * leg.mid * leg.ratio for leg in resolved.legs if leg.instrument != "stock"
    )
    unit_risk = (resolved.max_loss or abs(net_options) or 1.0) * CONTRACT_MULT
    unit_outlay = unit_risk + stock_cost
    if unit_outlay <= 0:
        return 1
    qty = max(1, int(capital * risk_fraction / unit_outlay))
    if unit_outlay * qty > capital * max_risk_pct + stock_cost * qty:
        qty = max(1, int(capital * max_risk_pct / unit_outlay))
    if unit_outlay * qty > capital * 1.05:
        return None
    return qty


def structure_value(
    legs: list[dict], option_quotes: dict[str, tuple[float, float]], stock_prices: dict[str, float]
) -> float | None:
    """V_now per unit at mid; None if any leg lacks a usable price."""
    total = 0.0
    for leg in legs:
        if leg["instrument"] == "stock":
            mid = stock_prices.get(leg["symbol"], 0.0)
            units = leg["ratio"] / CONTRACT_MULT
        else:
            bid, ask = option_quotes.get(leg["symbol"], (0.0, 0.0))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else (bid or ask)
            units = leg["ratio"]
        if not mid or mid <= 0:
            return None
        total += (1 if leg["side"] == "buy" else -1) * mid * units
    return total


def fill_value(
    legs: list[dict],
    option_quotes: dict[str, tuple[float, float]],
    stock_prices: dict[str, float],
    spread_fraction: float,
    closing: bool = False,
) -> float | None:
    """Like ``structure_value`` but each leg pays ``spread_fraction`` of its half-spread against you:
    buying pays above mid, selling receives below mid. ``closing`` reverses every leg's side."""
    total = 0.0
    for leg in legs:
        side = leg["side"] if not closing else ("sell" if leg["side"] == "buy" else "buy")
        if leg["instrument"] == "stock":
            px = stock_prices.get(leg["symbol"], 0.0)
            if not px:
                return None
            units = leg["ratio"] / CONTRACT_MULT
            half = px * 0.0002  # 2 bp half-spread for the stock leg
        else:
            bid, ask = option_quotes.get(leg["symbol"], (0.0, 0.0))
            if bid <= 0 or ask <= 0:
                return None
            px = (bid + ask) / 2
            units = leg["ratio"]
            half = (ask - bid) / 2
        px += spread_fraction * half * (1 if side == "buy" else -1)
        # value is always from the holder's view (buy legs positive) so entry/exit compare directly
        total += (1 if leg["side"] == "buy" else -1) * px * units
    return total


def exit_reason(
    st: Structure,
    value: float | None,
    today: date,
    profit_target_pct: float,
    stop_mult: float,
    close_dte: int,
) -> str | None:
    """DTE first, then profit target, then stop. Reason codes before ' | ' are stable for reports."""
    dte = st.min_dte(today)
    if dte is not None and dte <= close_dte:
        return f"dte_exit | {dte} days to expiry <= {close_dte}"
    if value is None:
        return None
    pl = st.entry_net + value
    if st.max_profit and pl >= profit_target_pct * st.max_profit:
        max_p = st.max_profit * CONTRACT_MULT
        return f"profit_target | P&L ${pl * CONTRACT_MULT:,.0f}/unit >= {profit_target_pct:.0%} of max ${max_p:,.0f}"
    baseline = st.max_profit if st.max_profit else (abs(st.entry_net) or 0.01)
    if pl <= -stop_mult * baseline:
        return (
            f"stop | P&L ${pl * CONTRACT_MULT:,.0f}/unit <= -{stop_mult:g}x baseline ${baseline * CONTRACT_MULT:,.0f}"
        )
    return None


def describe(resolved: ResolvedStructure) -> str:
    legs = ", ".join(
        f"{x.side} {x.ratio}x {x.instrument}"
        + (f" {x.strike:g} {x.expiry.isoformat()}" if x.strike else "")
        + f" @ {x.mid:.2f}"
        for x in resolved.legs
    )
    kind = "credit" if resolved.net_per_unit > 0 else "debit"
    net = abs(resolved.net_per_unit) * CONTRACT_MULT
    return (
        f"{resolved.template_id} on {resolved.underlying}: {legs}; net {kind} ${net:,.0f}/unit, "
        f"max profit {resolved.max_profit}, max loss {resolved.max_loss}"
    )


def leg_orders(legs: list[dict], closing: bool = False) -> list[dict]:
    out = []
    for leg in legs:
        side = leg["side"] if not closing else ("sell" if leg["side"] == "buy" else "buy")
        out.append({"symbol": leg["symbol"], "instrument": leg["instrument"], "side": side, "ratio": leg["ratio"]})
    return out


__all__ = [
    "CONTRACT_MULT",
    "ResolvedLeg",
    "Structure",
    "describe",
    "exit_reason",
    "fill_value",
    "leg_dicts",
    "leg_orders",
    "size_structure",
    "structure_value",
]
