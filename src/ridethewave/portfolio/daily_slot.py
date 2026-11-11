"""A daily portfolio slot: one daily-bar strategy, decided once a day, holding overnight, long or short.

Shadow only for now. At ``decision_time`` the runner hands the slot a panel of adjusted daily history
(today's bar included) and current prices; the slot asks its strategy for target weights, turns them
into whole-share deltas, fills them at the current price plus slippage, books round trips as trades,
and persists positions and cash so the next bot start resumes where it left off. Nothing reaches Alpaca.

Same-side adjustments smaller than the spec's ``dead_band_pct`` of capital are skipped (TraderPro's
rule) so a portfolio does not churn on rounding. The band must sit well below one position's size:
at the 1% default, ``sa_volrev`` (0.4% a name) never added a name's second cohort while its hedges
were sized for both (found 2026-11-04), so that slot sets 0.1%. With ``rebalance_days`` above 1
the slot trades only every that many sessions and just marks its book in between (the setting
existed but was ignored until 2026-11-02).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from loguru import logger

from ridethewave.config import CapitalSettings, PortfolioSpec
from ridethewave.daily.data import Panel
from ridethewave.daily.strategies import DailyStrategy, Window
from ridethewave.models import DailyLedger, Position, Trade
from ridethewave.portfolio.ledger import build_ledger
from ridethewave.storage import Database

STATE_KEY = "portfolio:{id}"
ET = ZoneInfo("America/New_York")


def _session_day(ts: datetime) -> str:
    """The New York date of a fill time (stored in UTC; a time with no zone is taken as it stands)."""
    return str((ts.astimezone(ET) if ts.tzinfo else ts).date())


class DailySlot:
    def __init__(
        self,
        spec: PortfolioSpec,
        strategy: DailyStrategy,
        db: Database | None,
        run_id: str,
        capital: float,
    ):
        self.spec = spec
        self.strategy = strategy
        self.db = db
        self.run_id = run_id
        self.capital = capital
        self.cash = capital
        self.dead_band_pct = spec.dead_band_pct
        self.positions: dict[str, Position] = {}
        self.trades_today: list[Trade] = []
        self.decided_on: str | None = None  # YYYY-MM-DD of the last decision
        self.rebalanced_on: str | None = None  # YYYY-MM-DD of the last decision that traded (rebalance_days)
        self.flattened_on: str | None = None  # YYYY-MM-DD of the last morning sale (spec.flatten_time)
        self.skipped: dict | None = None  # {"day", "reason"} when the last due decision could not be made
        self.last_targets: dict[str, float] = {}
        self.last_equity: float = capital
        self.universe: list[str] = []

    # ---------- persistence ----------
    def load(self) -> None:
        """Resume positions and cash from the database (overnight holds survive restarts)."""
        if self.db is None:
            return
        for p in self.db.positions.all(self.spec.id):
            p.strategy = self.spec.id
            self.positions[p.symbol] = p
        state = self.db.state.get(STATE_KEY.format(id=self.spec.id)) or {}
        if "cash" in state:
            self.cash = float(state["cash"])
            self.decided_on = state.get("decided_on")
            self.rebalanced_on = state.get("rebalanced_on")
            self.flattened_on = state.get("flattened_on")
            self.last_targets = state.get("targets", {})
        if self.positions:
            logger.info("[{}] resumed {} positions, cash ${:,.2f}", self.spec.id, len(self.positions), self.cash)

    def _save(self) -> None:
        if self.db is None:
            return
        self.db.positions.clear(self.spec.id)
        for p in self.positions.values():
            self.db.positions.upsert(p, self.run_id)
        self.db.state.set(
            STATE_KEY.format(id=self.spec.id),
            {
                "cash": self.cash,
                "capital": self.capital,
                "decided_on": self.decided_on,
                "rebalanced_on": self.rebalanced_on,
                "flattened_on": self.flattened_on,
                "targets": self.last_targets,
                "equity": self.last_equity,
                "updated_at": datetime.now().isoformat(),
            },
        )

    # ---------- marks ----------
    def mark(self, prices: dict[str, float]) -> float:
        for sym, p in self.positions.items():
            px = prices.get(sym)
            if px:
                p.update_price(px)
        self.last_equity = self.equity()
        return self.last_equity

    def equity(self) -> float:
        return self.cash + sum(p.qty * p.last_price for p in self.positions.values())

    # ---------- the daily decision ----------
    def decide(
        self,
        panel: Panel,
        prices: dict[str, float],
        now: datetime,
        universe: list[str],
        external: dict | None = None,
        quotes: dict[str, tuple[float | None, float | None]] | None = None,
        fills_at: dict[str, tuple[float, str]] | None = None,
        sizes_at: dict[str, float] | None = None,
    ) -> list[dict]:
        """Ask the strategy for targets on ``panel`` (history up to and including today) and rebalance.
        ``external`` carries outside series the strategy asked for (``external_series``), such as VIX.
        ``quotes`` is each symbol's (bid, ask) from the same snapshot as ``prices``; it changes no fill
        and is stored beside each one, so the record can later be re-priced at the real spread.
        ``fills_at`` and ``sizes_at`` are for slots that fill at the opening auction (``rebalance``)."""
        today = str(panel.dates[-1].date())
        self.universe = [s for s in universe if s in panel.close.columns]
        if self.rebalanced_on is not None:
            sessions = int((panel.dates > pd.Timestamp(self.rebalanced_on)).sum())  # today's row included
            if sessions < self.spec.rebalance_days:
                self.mark(prices)
                self.decided_on = today
                self._save()
                logger.info(
                    "[{}] {}: holding, {} of {} sessions since the last rebalance; equity ${:,.2f}",
                    self.spec.id,
                    today,
                    sessions,
                    self.spec.rebalance_days,
                    self.last_equity,
                )
                return []
        window = Window(
            close=panel.close,
            open=panel.open,
            high=panel.high,
            low=panel.low,
            volume=panel.volume,
            today=panel.dates[-1],
            symbols=self.universe,
            held={s: p.qty for s, p in self.positions.items()},
            log=lambda m: logger.info("[{}] {}", self.spec.id, m),
            external=external or {},
        )
        try:
            targets = self.strategy.targets(window) or {}
        except Exception as e:  # noqa: BLE001
            logger.exception("[{}] strategy failed: {}", self.spec.id, e)
            targets = {}
        gross = sum(abs(v) for v in targets.values())
        if gross > self.spec.max_gross and gross > 0:
            targets = {s: v * self.spec.max_gross / gross for s, v in targets.items()}
        self.last_targets = {s: round(v, 4) for s, v in targets.items()}
        fills = self.rebalance(targets, prices, now, fills_at, sizes_at)
        self.decided_on = today
        self.rebalanced_on = today
        self._save()
        self._record_fills(fills, quotes or {}, today, now)
        logger.info(
            "[{}] decided {}: {} targets, {} fills, equity ${:,.2f}, cash ${:,.2f}, {} positions",
            self.spec.id,
            today,
            len(targets),
            len(fills),
            self.last_equity,
            self.cash,
            len(self.positions),
        )
        return fills

    def rebalance(
        self,
        targets: dict[str, float],
        prices: dict[str, float],
        now: datetime,
        fills_at: dict[str, tuple[float, str]] | None = None,
        sizes_at: dict[str, float] | None = None,
    ) -> list[dict]:
        """Trade to ``targets``. By default each fill is priced at the symbol's current price.

        A slot that fills at the opening auction (``fill_at: open_auction``) passes two more things:
        - ``fills_at``: per symbol, the price to fill at and what it is ("auction", or "open" when Alpaca
          has no auction print and the day's first trade stands in);
        - ``sizes_at``: yesterday's close, which is all an order sent before the open can size itself on.
        A symbol missing from either falls back to its current price."""
        self.mark(prices)
        eq = self.equity()
        slip = self.spec.slippage_bps / 10_000.0
        fills: list[dict] = []
        for sym in sorted(set(targets) | set(self.positions)):
            px = prices.get(sym)
            if not px or px <= 0:
                if sym in targets and targets[sym]:
                    logger.warning("[{}] no price for {}; target skipped", self.spec.id, sym)
                continue
            w = targets.get(sym, 0.0)
            ref, basis = (fills_at or {}).get(sym) or (px, "last")
            size_px = (sizes_at or {}).get(sym) or px
            target_qty = int(eq * w / size_px)
            cur = self.positions[sym].qty if sym in self.positions else 0.0
            delta = target_qty - cur
            if delta == 0:
                continue
            same_side = cur != 0 and target_qty != 0 and (cur > 0) == (target_qty > 0)
            if same_side and abs(delta) * size_px < self.capital * self.dead_band_pct / 100.0:
                continue
            fill_px = ref * (1 + slip * (1 if delta > 0 else -1))
            self._execute(sym, delta, fill_px, now)
            fill = {"symbol": sym, "qty": delta, "price": round(fill_px, 4), "target": w, "last": ref, "basis": basis}
            fills.append(fill)
        if fills_at:
            self.mark(prices)  # positions just filled at the open are worth the current price now
        self.last_equity = self.equity()
        return fills

    def sell_at_open(
        self,
        prices: dict[str, float],
        now: datetime,
        today: str,
        fills_at: dict[str, tuple[float, str]],
        closes: dict[str, float],
        close_day: str | None,
        quotes: dict | None = None,
    ) -> list[dict]:
        """The morning half of a book held overnight only (``flatten_time``): sell everything at the
        opening auction.

        Before selling, each position bought on ``close_day`` (the session before) is re-booked at that
        day's official close from ``closes``, plus the slot's allowance. It was bought at the price
        standing at the decision time because the close was not known yet; the rule being observed buys
        at the close (docs/research/2026-11-10-signals-a-c-d.md). A position bought on any other day
        (the bot missed a morning) is sold as it stands. Marks today as done even with nothing to sell,
        so the evening's purchases are not sold again the same day."""
        slip = self.spec.slippage_bps / 10_000.0
        rebooked, moves = [], []
        for sym, pos in self.positions.items():
            close = closes.get(sym)
            if not close or close <= 0 or close_day is None or _session_day(pos.entry_time) != close_day:
                continue
            new_entry = close * (1 + slip * (1 if pos.qty > 0 else -1))
            moves.append((new_entry / pos.entry_price - 1) * 1e4)
            self.cash += pos.qty * (pos.entry_price - new_entry)
            pos.entry_price = new_entry
            rebooked.append(
                {"symbol": sym, "qty": pos.qty, "price": round(new_entry, 4), "target": 0.0, "last": close,
                 "basis": "close"}
            )  # fmt: skip
        if rebooked:
            logger.info(
                "[{}] {} of {} purchases re-booked at the {} close: on average {:+.1f} bp against the "
                "decision-time price",
                self.spec.id, len(rebooked), len(self.positions), close_day, sum(moves) / len(moves),
            )  # fmt: skip
            if self.db is not None:
                self._record_fills(rebooked, {}, close_day, now)
        fills = self.rebalance({}, prices, now, fills_at) if self.positions else []
        self.flattened_on = today
        self._save()
        self._record_fills(fills, quotes or {}, today, now)
        kinds = [f["basis"] for f in fills]
        logger.info(
            "[{}] {}: sold {} positions at the open ({} at the auction price, {} at the day's first trade, {} at "
            "the last trade); equity ${:,.2f}",
            self.spec.id, today, len(fills), kinds.count("auction"), kinds.count("open"), kinds.count("last"),
            self.last_equity,
        )  # fmt: skip
        return fills

    def _record_fills(self, fills: list[dict], quotes: dict, today: str, now: datetime) -> None:
        """Store each fill with the bid and ask standing when it was made (table ``portfolio_fills``).

        The slot fills at the last trade plus ``slippage_bps``; a real market order pays half the quoted
        spread. Keeping the quote lets the two be compared for every fill
        (docs/research/2026-11-09-statarb-costs.md). A failure here is logged and never stops a decision."""
        if self.db is None or not fills:
            return
        try:
            rows, halves = [], []
            for f in fills:
                bid, ask = quotes.get(f["symbol"]) or (None, None)
                if bid and ask and ask > bid:
                    halves.append((ask - bid) / (ask + bid) * 1e4)
                rows.append(
                    {
                        "strategy": self.spec.id,
                        "run_id": self.run_id,
                        "day": today,
                        "ts": now.isoformat(),
                        "symbol": f["symbol"],
                        "qty": f["qty"],
                        "price": f["price"],
                        "last": f["last"],
                        "basis": f.get("basis", "last"),
                        "bid": bid,
                        "ask": ask,
                        "target": f["target"],
                    }
                )
            self.db.fills.insert_many(rows)
            if halves:
                halves.sort()
                logger.info(
                    "[{}] quoted half-spread at the fills: mean {:.1f} bp, median {:.1f} bp ({} of {} quoted; "
                    "the book charges itself {:.1f} bp)",
                    self.spec.id,
                    sum(halves) / len(halves),
                    halves[len(halves) // 2],
                    len(halves),
                    len(fills),
                    self.spec.slippage_bps,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("[{}] fills not recorded: {}: {}", self.spec.id, type(e).__name__, e)

    def _execute(self, sym: str, delta: float, price: float, now: datetime) -> None:
        pos = self.positions.get(sym)
        old = pos.qty if pos else 0.0
        new = old + delta
        self.cash -= delta * price
        if pos is not None and (new == 0 or (old > 0) != (new > 0)):
            closed_qty = old
            t = Trade(
                symbol=sym,
                qty=closed_qty,
                entry_price=pos.entry_price,
                entry_time=pos.entry_time,
                exit_price=price,
                exit_time=now,
                exit_reason="rebalance",
                peak_price=pos.peak_price,
                mode=self.spec.mode,
                run_id=self.run_id,
                strategy=self.spec.id,
            )
            self.trades_today.append(t)
            if self.db is not None:
                self.db.trades.insert(t)
            logger.info("[{}] CLOSE {} x{} @ {:.2f} pnl {:+.2f}", self.spec.id, sym, closed_qty, price, t.pnl)
            self.positions.pop(sym, None)
            pos = None
            old = 0.0
            remaining = new  # a flip re-opens on the other side
            if remaining == 0:
                return
            delta = remaining
            new = remaining
        if pos is None:
            self.positions[sym] = Position(
                symbol=sym,
                qty=new,
                entry_price=price,
                entry_time=now,
                peak_price=price,
                last_price=price,
                strategy=self.spec.id,
            )
            logger.info("[{}] OPEN {} x{} @ {:.2f}", self.spec.id, sym, new, price)
            return
        if abs(new) > abs(old):  # adding: weighted average entry
            pos.entry_price = (pos.entry_price * abs(old) + price * abs(delta)) / abs(new)
        pos.qty = new
        pos.last_price = price

    # ---------- end of day ----------
    def ledger(self, today: str, prev: DailyLedger | None, cfg: CapitalSettings) -> DailyLedger:
        led = build_ledger(
            today,
            self.spec.mode,
            self.run_id,
            self.trades_today,
            list(self.positions.values()),
            prev,
            self.capital,
            cfg.model_copy(update={"base_allocation": self.capital}),
            equity_close=self.last_equity,
        )
        led.strategy = self.spec.id
        led.extra["gross"] = round(sum(abs(p.qty * p.last_price) for p in self.positions.values()), 2)
        led.extra["positions"] = len(self.positions)
        led.extra["targets"] = self.last_targets
        return led

    def skip(self, today: str, reason: str) -> None:
        """Mark today as handled without a decision (no retry every tick) and remember why, so the
        heartbeat and the operator's alert check can report it."""
        self.decided_on = str(today)
        self.skipped = {"day": str(today), "reason": reason}

    def snapshot(self) -> dict:
        return {
            "mode": self.spec.mode,
            "positions": len(self.positions),
            "shorts": sum(1 for p in self.positions.values() if p.qty < 0),
            "equity": round(self.last_equity, 2),
            "cash": round(self.cash, 2),
            "decided_on": self.decided_on,
            "skipped": self.skipped,
            "trades": len(self.trades_today),
        }
