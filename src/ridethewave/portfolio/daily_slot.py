"""A daily portfolio slot: one daily-bar strategy, decided once a day, holding overnight, long or short.

Shadow only for now. At ``decision_time`` the runner hands the slot a panel of adjusted daily history
(today's bar included) and current prices; the slot asks its strategy for target weights, turns them
into whole-share deltas, fills them at the current price plus slippage, books round trips as trades,
and persists positions and cash so the next bot start resumes where it left off. Nothing reaches Alpaca.

Same-side adjustments smaller than ``dead_band_pct`` of capital are skipped (TraderPro's rule) so a
portfolio does not churn on rounding.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from ridethewave.config import CapitalSettings, PortfolioSpec
from ridethewave.daily.data import Panel
from ridethewave.daily.strategies import DailyStrategy, Window
from ridethewave.models import DailyLedger, Position, Trade
from ridethewave.portfolio.ledger import build_ledger
from ridethewave.storage import Database

STATE_KEY = "portfolio:{id}"


class DailySlot:
    def __init__(
        self,
        spec: PortfolioSpec,
        strategy: DailyStrategy,
        db: Database | None,
        run_id: str,
        capital: float,
        dead_band_pct: float = 1.0,
    ):
        self.spec = spec
        self.strategy = strategy
        self.db = db
        self.run_id = run_id
        self.capital = capital
        self.cash = capital
        self.dead_band_pct = dead_band_pct
        self.positions: dict[str, Position] = {}
        self.trades_today: list[Trade] = []
        self.decided_on: str | None = None  # YYYY-MM-DD of the last decision
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
    def decide(self, panel: Panel, prices: dict[str, float], now: datetime, universe: list[str]) -> list[dict]:
        """Ask the strategy for targets on ``panel`` (history up to and including today) and rebalance."""
        today = str(panel.dates[-1].date())
        self.universe = [s for s in universe if s in panel.close.columns]
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
        fills = self.rebalance(targets, prices, now)
        self.decided_on = today
        self._save()
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

    def rebalance(self, targets: dict[str, float], prices: dict[str, float], now: datetime) -> list[dict]:
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
            target_qty = int(eq * w / px)
            cur = self.positions[sym].qty if sym in self.positions else 0.0
            delta = target_qty - cur
            if delta == 0:
                continue
            same_side = cur != 0 and target_qty != 0 and (cur > 0) == (target_qty > 0)
            if same_side and abs(delta) * px < self.capital * self.dead_band_pct / 100.0:
                continue
            fill_px = px * (1 + slip * (1 if delta > 0 else -1))
            self._execute(sym, delta, fill_px, now)
            fills.append({"symbol": sym, "qty": delta, "price": round(fill_px, 4), "target": w})
        self.last_equity = self.equity()
        return fills

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

    def snapshot(self) -> dict:
        return {
            "mode": self.spec.mode,
            "positions": len(self.positions),
            "shorts": sum(1 for p in self.positions.values() if p.qty < 0),
            "equity": round(self.last_equity, 2),
            "cash": round(self.cash, 2),
            "decided_on": self.decided_on,
            "trades": len(self.trades_today),
        }
