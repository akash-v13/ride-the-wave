"""An options slot: one structure template on one underlying, at most one open at a time, decided daily.

Each decision: value every open structure from live quotes and apply the exit rules; if nothing is
open (and the entry gate passes) take a chain snapshot, resolve the template, size it and open it.
``shadow`` fills every leg against the live quote paying a fraction of the half-spread and keeps the
books here; ``live`` sends the legs to the paper account as a multi-leg order (fills assumed at mid
for the books; the broker order id is kept on the structure). Cash and the open structures persist
across restarts, and so does each structure's last mark. Every closed structure is also booked as a
Trade (symbol "UNDERLYING:template") so ledgers, reports and the leaderboard see options P&L without
special cases.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from loguru import logger

from ridethewave.config import CapitalSettings, OptionsSpec
from ridethewave.models import DailyLedger, Trade
from ridethewave.options.chain import ChainSnapshot
from ridethewave.options.lifecycle import (
    CONTRACT_MULT,
    Structure,
    describe,
    exit_reason,
    fill_value,
    intrinsic_value,
    leg_dicts,
    leg_orders,
    size_structure,
    structure_value,
)
from ridethewave.options.resolver import ResolutionError, resolve
from ridethewave.options.structures import get_template
from ridethewave.portfolio.ledger import build_ledger

STATE_KEY = "options:{id}"


class OptionsSlot:
    def __init__(self, spec: OptionsSpec, db, run_id: str, capital: float, broker=None):
        self.spec = spec
        self.db = db
        self.run_id = run_id
        self.capital = capital
        self.cash = capital
        self.broker = broker  # AlpacaBroker for mode live; None in shadow
        self.template = get_template(spec.template)
        self.open: list[Structure] = []
        self.trades_today: list[Trade] = []
        self.decided_on: str | None = None
        self.skipped: dict | None = None  # {"day", "reason"} when the last due decision could not be made
        self.last_value: float = 0.0  # Σ V_now × 100 × qty over open structures
        self.last_note: str = ""

    # ---------- persistence ----------
    def load(self) -> None:
        if self.db is None:
            return
        self.open = [Structure.from_row(r) for r in self.db.structures.open_for(self.spec.id)]
        state = self.db.state.get(STATE_KEY.format(id=self.spec.id)) or {}
        if "cash" in state:
            self.cash = float(state["cash"])
            self.decided_on = state.get("decided_on")
        marks = state.get("marks") or {}
        for st in self.open:
            if st.id in marks:
                st.notes["value"] = float(marks[st.id])
        self.last_value = sum(st.notes["value"] * CONTRACT_MULT * st.qty for st in self.open if "value" in st.notes)
        if self.open:
            logger.info("[{}] resumed {} open structure(s), cash ${:,.2f}", self.spec.id, len(self.open), self.cash)

    def _save(self) -> None:
        if self.db is None:
            return
        self.db.state.set(
            STATE_KEY.format(id=self.spec.id),
            {
                "cash": self.cash,
                "capital": self.capital,
                "decided_on": self.decided_on,
                "open": [s.id for s in self.open],
                "marks": {s.id: s.notes["value"] for s in self.open if "value" in s.notes},
                "equity": self.equity(),
                "note": self.last_note,
                "updated_at": datetime.now().isoformat(),
            },
        )

    # ---------- valuation ----------
    def mark(self, option_quotes: dict[str, tuple[float, float]], stock_prices: dict[str, float]) -> float:
        total = 0.0
        for st in self.open:
            v = structure_value(st.legs, option_quotes, stock_prices)
            if v is not None:
                st.notes["value"] = v
                total += v * CONTRACT_MULT * st.qty
            elif "value" in st.notes:
                total += st.notes["value"] * CONTRACT_MULT * st.qty
        self.last_value = total
        self._save()  # a restart keeps the marks; a close with no quote falls back on them
        return self.equity()

    def equity(self) -> float:
        return self.cash + self.last_value

    def unrealized(self) -> float:
        return sum(st.unrealized(st.notes["value"]) for st in self.open if "value" in st.notes)

    # ---------- the daily decision ----------
    def decide(
        self,
        today: date,
        now: datetime,
        spot: float,
        option_quotes: dict[str, tuple[float, float]],
        stock_prices: dict[str, float],
        chain_fn,
        realized_vol: float | None = None,
    ) -> dict:
        """``chain_fn(dte_min, dte_max) -> ChainSnapshot`` is called only when an entry is possible."""
        actions: list[str] = []
        # 1. exits
        for st in list(self.open):
            value = structure_value(st.legs, option_quotes, stock_prices)
            reason = exit_reason(
                st, value, today, self.spec.profit_target_pct, self.spec.stop_mult, self.spec.close_dte
            )
            if reason:
                self._close(st, option_quotes, stock_prices, now, reason)
                actions.append(f"closed {st.template_id}: {reason}")
        # 2. entry
        if not self.open:
            ok, why = self._gate(chain_fn, spot, realized_vol)
            if ok:
                opened = self._open(chain_fn, spot, now, why)
                actions.append(opened)
            else:
                actions.append(f"no entry: {why}")
        self.mark(option_quotes, stock_prices)
        self.decided_on = str(today)
        self.last_note = "; ".join(actions)
        self._save()
        logger.info("[{}] decided {}: {}", self.spec.id, today, self.last_note)
        return {"actions": actions, "open": len(self.open), "equity": self.equity()}

    def _gate(self, chain_fn, spot: float, realized_vol: float | None) -> tuple[bool, str]:
        if self.spec.entry_gate == "none":
            return True, f"no open {self.spec.template}; entering at ~{self.spec.dte_target} DTE"
        chain = self._chain(chain_fn)
        iv = chain.atm_iv() if chain else None
        if iv is None or realized_vol is None:
            return False, "vrp gate: implied or realised volatility unavailable"
        spread = iv - realized_vol
        if spread >= self.spec.vrp_threshold:
            return (
                True,
                f"vrp gate open: IV {iv:.1%} - RV {realized_vol:.1%} = {spread:+.1%} >= {self.spec.vrp_threshold:.1%}",
            )
        return (
            False,
            f"vrp gate closed: IV {iv:.1%} - RV {realized_vol:.1%} = {spread:+.1%} < {self.spec.vrp_threshold:.1%}",
        )

    def _chain(self, chain_fn) -> ChainSnapshot | None:
        has_far = any(leg.expiry == "far" for leg in self.template.legs)
        dte_min = max(self.spec.dte_target - 15, 3)
        dte_max = self.spec.dte_target + (self.spec.far_dte_offset + 20 if has_far else 15)
        try:
            return chain_fn(dte_min, dte_max)
        except Exception as e:  # noqa: BLE001
            logger.warning("[{}] chain snapshot failed: {}", self.spec.id, e)
            return None

    def _open(self, chain_fn, spot: float, now: datetime, why: str) -> str:
        chain = self._chain(chain_fn)
        if chain is None or not chain.contracts:
            return "no entry: empty chain"
        try:
            resolved = resolve(
                self.template,
                chain,
                target_dte=self.spec.dte_target,
                far_dte_offset=self.spec.far_dte_offset,
                step_pct=self.spec.strike_step_pct,
            )
        except ResolutionError as e:
            return f"no entry: resolution failed ({e})"
        equity = self.equity()  # size from what is left, never from the starting capital
        if equity <= 0:
            return "no entry: equity exhausted"
        qty = size_structure(resolved, equity, self.spec.risk_fraction, self.spec.max_risk_pct)
        if qty is None:
            return f"no entry: one unit of {resolved.template_id} exceeds the capital (${self.capital:,.0f})"
        legs = leg_dicts(resolved)
        quotes = {c.symbol: (c.bid, c.ask) for c in chain.contracts}
        stock_prices = {chain.underlying: chain.spot}
        order_id = None
        if self.spec.mode == "live" and self.broker is not None:
            order_id = self.broker.submit_structure(leg_orders(legs), qty)
            v_entry = -resolved.net_per_unit  # books at mid until fills are reconciled
        else:
            v_entry = fill_value(legs, quotes, stock_prices, self.spec.spread_fraction)
            if v_entry is None:
                return "no entry: a leg had no two-sided quote"
        entry_net = -v_entry
        st = Structure(
            id=uuid.uuid4().hex[:12],
            strategy=self.spec.id,
            run_id=self.run_id,
            mode=self.spec.mode,
            template_id=resolved.template_id,
            underlying=resolved.underlying,
            qty=qty,
            legs=legs,
            entry_net=round(entry_net, 4),
            max_profit=resolved.max_profit,
            max_loss=resolved.max_loss,
            opened_at=now,
            broker_order_id=order_id,
        )
        self.cash -= v_entry * CONTRACT_MULT * qty  # a debit costs cash, a credit adds it
        st.notes["value"] = structure_value(legs, quotes, stock_prices) or -resolved.net_per_unit  # marked at mid
        self.open.append(st)
        if self.db is not None:
            self.db.structures.insert(st.to_row())
        msg = f"opened x{qty} {describe(resolved)} | {why}"
        logger.info("[{}] {}", self.spec.id, msg)
        return msg

    def _close(self, st: Structure, option_quotes, stock_prices, now: datetime, reason: str) -> None:
        if self.spec.mode == "live" and self.broker is not None:
            self.broker.submit_structure(leg_orders(st.legs, closing=True), st.qty)
            v_exit = structure_value(st.legs, option_quotes, stock_prices)
        else:
            v_exit = fill_value(st.legs, option_quotes, stock_prices, self.spec.spread_fraction, closing=True)
        if v_exit is None:
            v_exit, source = self._fallback_exit_value(st, option_quotes, stock_prices)
            reason = f"{reason} | priced from {source}"
        self.cash += v_exit * CONTRACT_MULT * st.qty
        pl = (st.entry_net + v_exit) * CONTRACT_MULT * st.qty
        st.status, st.closed_at, st.exit_net, st.realized_pl, st.close_reason = (
            "closed",
            now,
            v_exit,
            round(pl, 2),
            reason,
        )
        self.open = [x for x in self.open if x.id != st.id]
        t = Trade(
            symbol=f"{st.underlying}:{st.template_id}",
            qty=CONTRACT_MULT * st.qty,
            entry_price=-st.entry_net,
            entry_time=st.opened_at,
            exit_price=v_exit,
            exit_time=now,
            exit_reason=reason.split(" | ")[0],
            peak_price=max(-st.entry_net, v_exit),
            mode=self.spec.mode,
            run_id=self.run_id,
            strategy=self.spec.id,
        )
        self.trades_today.append(t)
        if self.db is not None:
            self.db.structures.close(st.id, now.isoformat(), v_exit, st.realized_pl, reason)
            self.db.trades.insert(t)
        logger.info("[{}] CLOSED {} x{}: {} (P&L {:+.2f})", self.spec.id, st.template_id, st.qty, reason, pl)

    def _fallback_exit_value(self, st: Structure, option_quotes, stock_prices) -> tuple[float, str]:
        """The price a close books when the fill price is missing, best source first. The source is
        logged and kept in the close reason. Before 2026-10-29 a missing price after a restart fell
        straight back to the entry value: cc_qqq, down about $1,890, was booked at $0.00."""
        v = structure_value(st.legs, option_quotes, stock_prices)
        if v is not None:
            source = "mid, a leg had a one-sided quote"
        elif "value" in st.notes:
            v, source = st.notes["value"], "the last mark"
        else:
            v = intrinsic_value(st.legs, stock_prices.get(st.underlying, 0.0), stock_prices)
            source = "intrinsic value, no quotes and no mark"
        if v is None:
            logger.error("[{}] {}: no price of any kind; booked at the entry value (P&L 0)", self.spec.id, st.id)
            return -st.entry_net, "the entry value, no price of any kind"
        logger.warning("[{}] {}: no fill price for the close; priced from {}", self.spec.id, st.id, source)
        return v, source

    # ---------- end of day ----------
    def ledger(self, today: str, prev: DailyLedger | None, cfg: CapitalSettings) -> DailyLedger:
        led = build_ledger(
            today,
            self.spec.mode,
            self.run_id,
            self.trades_today,
            [],
            prev,
            self.capital,
            cfg.model_copy(update={"base_allocation": self.capital}),
            equity_close=self.equity(),
        )
        led.strategy = self.spec.id
        led.unrealized_pnl = round(self.unrealized(), 2)
        led.extra["open_structures"] = [
            {
                "template": s.template_id,
                "qty": s.qty,
                "entry_net": s.entry_net,
                "dte": s.min_dte(date.fromisoformat(today)),
            }
            for s in self.open
        ]
        led.extra["note"] = self.last_note
        return led

    def skip(self, today: str, reason: str) -> None:
        """Mark today as handled without a decision (no retry every tick) and remember why, so the
        heartbeat and the operator's alert check can report it."""
        self.decided_on = str(today)
        self.skipped = {"day": str(today), "reason": reason}

    def snapshot(self) -> dict:
        return {
            "mode": self.spec.mode,
            "template": self.spec.template,
            "underlying": self.spec.underlying,
            "open": len(self.open),
            "equity": round(self.equity(), 2),
            "cash": round(self.cash, 2),
            "unrealized": round(self.unrealized(), 2),
            "decided_on": self.decided_on,
            "skipped": self.skipped,
            "note": self.last_note[:200],
        }
