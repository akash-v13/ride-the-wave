"""The live (paper) trading loop, running several strategies side by side.

Each enabled entry under ``strategies:`` in settings becomes a *slot*: its own strategy object,
position book, order manager, allocation and ledger. Live slots share the real Alpaca broker; shadow
slots get a ShadowBroker that fills against live ticks without sending orders. One symbol can be
held by only one live slot at a time.
"""

from __future__ import annotations

import signal as os_signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from loguru import logger

from ridethewave.clients import AlpacaClients
from ridethewave.config import Settings, StrategySpec
from ridethewave.data.bars import BarAggregator
from ridethewave.data.market_data import DailyBars, HistoricalBars, SnapshotPoller
from ridethewave.data.universe import UniverseBuilder
from ridethewave.engine import TradingEngine
from ridethewave.execution import OrderManager, PositionBook
from ridethewave.execution.broker import AlpacaBroker, Broker
from ridethewave.execution.shadow_broker import ShadowBroker
from ridethewave.features.live import LiveFeatureRecorder
from ridethewave.models import Signal, SignalType
from ridethewave.operator.risk import RiskMonitor
from ridethewave.portfolio import CapitalAllocator, build_ledger
from ridethewave.storage import Database
from ridethewave.strategy import Strategy, build

ET = ZoneInfo("America/New_York")
LIVE_RUN_ID = "live"
MARKET = "SPY"


@dataclass
class Slot:
    spec: StrategySpec
    strategy: Strategy
    broker: Broker
    book: PositionBook
    allocator: CapitalAllocator
    orders: OrderManager
    engine: TradingEngine
    symbols: list[str]
    allocation: float
    base_share: float
    realized_today: float = 0.0
    trades_today: list = field(default_factory=list)

    @property
    def live(self) -> bool:
        return self.spec.mode == "live"

    @property
    def mode(self) -> str:
        return "live" if self.live else "shadow"


class BotRunner:
    def __init__(self, settings: Settings, clients: AlpacaClients, db: Database, wait_for_open: bool = True):
        self.s = settings
        self.clients = clients
        self.db = db
        self.wait_for_open = wait_for_open
        self.broker = AlpacaBroker(clients.trading)
        self.poller = SnapshotPoller(clients.data, settings.alpaca.data_feed)
        self.history = HistoricalBars(clients.data, db, feed=settings.alpaca.data_feed)
        self.daily = DailyBars(clients.data, db)
        self.universe_builder = UniverseBuilder(clients, settings.universe, settings.alpaca.data_feed)
        self.agg = BarAggregator(window=420)
        self.recorder = LiveFeatureRecorder(db, settings, feed=settings.alpaca.data_feed)
        self.slots: list[Slot] = []
        self.universe: list[str] = []
        self.tick_no = 0
        self._stop = False
        self.risk: RiskMonitor | None = None

    # ------------------------------------------------------------------ lifecycle
    def run(self, dry_run: bool = False) -> None:
        os_signal.signal(os_signal.SIGINT, self._on_sigint)
        os_signal.signal(os_signal.SIGTERM, self._on_sigint)

        open_at: datetime | None = None
        if not dry_run:
            clock = self.broker.clock()
            if not clock.is_open:
                if not self.wait_for_open:
                    logger.info("market closed (next open {}); exiting because --no-wait", clock.next_open)
                    return
                open_at = clock.next_open
                self._wait_until(open_at - timedelta(minutes=2))
                if self._stop:
                    return

        today = datetime.now(ET).strftime("%Y-%m-%d")
        self._keep_awake()
        self._rebuild_universe()
        self._build_slots(today)
        self._reconcile()
        self._warmup()
        self._session_start(today)
        live_alloc = sum(sl.allocation for sl in self.slots if sl.live)
        self.risk = RiskMonitor(self.s.risk, live_alloc)
        self._apply_risk(
            self.risk.check_winrate(self.db.trades.recent(self.s.risk.winrate_lookback_trades, "live")[::-1])
        )
        self.db.state.set("allocation", live_alloc)
        self.db.state.set(
            "strategies",
            [
                {
                    "id": sl.spec.id,
                    "kind": sl.spec.kind,
                    "mode": sl.mode,
                    "allocation": sl.allocation,
                    "symbols": len(sl.symbols),
                }
                for sl in self.slots
            ],
        )
        self.db.state.set(
            "run",
            {
                "date": today,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "strategy": ", ".join(f"{sl.spec.id}({sl.mode})" for sl in self.slots),
                "universe_size": len(self.universe),
            },
        )
        logger.info(
            "bot running: live allocation=${:,.0f} universe={} slots={}",
            live_alloc,
            len(self.universe),
            [f"{sl.spec.id}:{sl.mode}:{len(sl.symbols)}sym:${sl.allocation:,.0f}" for sl in self.slots],
        )

        if dry_run:
            self._tick(datetime.now(timezone.utc))
            logger.info(
                "dry run complete: {} snapshots, {} bars in aggregator, positions {}",
                self.poller.calls,
                sum(len(self.agg.history(s)) for s in self.agg.symbols()),
                {sl.spec.id: len(sl.book.positions) for sl in self.slots},
            )
            return

        if open_at is not None:
            # setup took a few seconds; now wait for the bell itself so the first clock check cannot end the day
            self._wait_until(open_at)
            if self._stop:
                return
        last_clock_check = time.monotonic()
        last_universe_refresh = time.monotonic()
        market_open = True
        flattened = False
        while not self._stop and market_open:
            t_start = time.monotonic()
            now = datetime.now(timezone.utc)
            try:
                self._tick(now)
                if self.s.exit.flatten_at_close and not flattened:
                    if now.astimezone(ET).time() >= self._plus_minute(self.s.exit.flatten_time):
                        logger.info("flatten time passed; closing positions of strategies that flatten at close")
                        for sl in self.slots:
                            if sl.strategy.flatten_at_close:
                                sl.orders.flatten_all(now)
                            sl.orders.cancel_pending_entries()
                        flattened = True
                if time.monotonic() - last_clock_check > 60:
                    clk = self.broker.clock()
                    # closed is only believed after the open has passed (guards a stale or early clock read)
                    market_open = clk.is_open or (open_at is not None and now < open_at + timedelta(minutes=2))
                    last_clock_check = time.monotonic()
                if (
                    self.s.universe.refresh_minutes > 0
                    and time.monotonic() - last_universe_refresh > self.s.universe.refresh_minutes * 60
                ):
                    self._rebuild_universe()
                    for sl in self.slots:
                        sl.symbols = self._symbols_for(sl.strategy)
                    last_universe_refresh = time.monotonic()
            except Exception as e:  # noqa: BLE001
                logger.exception("tick failed: {}", e)
            elapsed = time.monotonic() - t_start
            for _ in range(int(max(0.0, self.s.scan.poll_interval_seconds - elapsed))):
                if self._stop:
                    break
                time.sleep(1)

        self._shutdown(today)

    def _keep_awake(self) -> None:
        """Prevent idle/system sleep while the session runs (macOS `caffeinate`, tied to our pid; no sudo).
        Waking a sleeping Mac before the open is a separate, one-time `pmset repeat` setting (docs)."""
        import os
        import platform
        import subprocess

        if platform.system() != "Darwin":
            return
        try:
            subprocess.Popen(
                ["caffeinate", "-i", "-s", "-w", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logger.info("caffeinate: sleep prevented for the session")
        except Exception as e:  # noqa: BLE001
            logger.warning("caffeinate unavailable: {}", e)

    def _on_sigint(self, *_):
        logger.warning("stop requested; finishing current tick")
        self._stop = True

    # ------------------------------------------------------------------ setup
    def _build_slots(self, today: str) -> None:
        specs = [x for x in self.s.strategies if x.enabled]
        live_weight = sum(x.weight for x in specs if x.mode == "live") or 1.0
        for spec in specs:
            strategy = build(spec.kind, self.s, spec.params)
            share = spec.weight / live_weight if spec.mode == "live" else spec.weight
            base_share = self.s.capital.base_allocation * share
            prev = self.db.ledger.latest_before(today, LIVE_RUN_ID, spec.id)
            allocation = prev.next_allocation if prev else base_share
            allocator = CapitalAllocator(self.s.capital, self.s.entry, allocation)
            broker: Broker = (
                self.broker
                if spec.mode == "live"
                else ShadowBroker(cash=allocation * 10, slippage_pct=self.s.backtest.slippage_pct)
            )
            book = PositionBook()
            orders = OrderManager(
                broker,
                book,
                allocator,
                self.db,
                self.s.entry,
                self.s.exit,
                run_id=LIVE_RUN_ID,
                mode="live" if spec.mode == "live" else "shadow",
                ask_lookup=self._ask,
                strategy=spec.id,
                protective_stop=strategy.uses_protective_stop,
                strategy_obj=strategy,  # sizing (qty_for) and stop (stops) hooks
            )
            engine = TradingEngine(self.s, strategy, book, orders, self.agg, self.db, LIVE_RUN_ID)
            if spec.mode == "live":
                engine.signal_filter = self._exclusive(spec.id)
            self.slots.append(
                Slot(
                    spec,
                    strategy,
                    broker,
                    book,
                    allocator,
                    orders,
                    engine,
                    self._symbols_for(strategy),
                    allocation,
                    base_share,
                )
            )

    def _symbols_for(self, strategy) -> list[str]:
        """The strategy's own view of the universe; strategies with ``stocks_only`` do not see funds."""
        syms = strategy.symbols(self.universe)
        if getattr(strategy, "stocks_only", False):
            try:
                funds = self.universe_builder.fund_symbols(syms)
            except Exception as e:  # noqa: BLE001
                logger.warning("fund lookup failed, keeping funds in the universe: {}", e)
                funds = set()
            syms = [x for x in syms if x not in funds]
        return syms

    def _exclusive(self, my_id: str):
        """A symbol held or pending in another live slot is off limits for a BUY."""

        def ok(sig: Signal) -> bool:
            if sig.type != SignalType.BUY:
                return True
            for sl in self.slots:
                if (
                    sl.live
                    and sl.spec.id != my_id
                    and (sig.symbol in sl.book.positions or sig.symbol in sl.book.pending_entries)
                ):
                    return False
            return True

        return ok

    def _reconcile(self) -> None:
        """Hand each broker position to the live slot that recorded it; leftovers go to the first live slot."""
        broker_positions = self.broker.positions()
        now = datetime.now(timezone.utc)
        unassigned = {bp.symbol: bp for bp in broker_positions}
        for sl in self.slots:
            if not sl.live:
                continue
            mine = {p.symbol for p in self.db.positions.all(sl.spec.id)}
            owned = [unassigned.pop(sym) for sym in list(unassigned) if sym in mine]
            sl.book.reconcile(owned, now, strategy=sl.spec.id)
        live_slots = [sl for sl in self.slots if sl.live]
        if unassigned and live_slots:
            logger.warning("adopting {} untracked broker positions into {}", len(unassigned), live_slots[0].spec.id)
            live_slots[0].book.reconcile(list(unassigned.values()), now, strategy=live_slots[0].spec.id)
            for p in live_slots[0].book.positions.values():
                p.strategy = live_slots[0].spec.id

    def _all_symbols(self) -> list[str]:
        out: set[str] = {MARKET}
        for sl in self.slots:
            out.update(sl.symbols)
            out.update(sl.book.positions)
            out.update(sl.book.pending_entries)
        return sorted(out)

    # ------------------------------------------------------------------ one tick
    def _tick(self, now: datetime) -> None:
        self.tick_no += 1
        self._apply_controls(now)
        snaps = self.poller.poll(self._all_symbols())
        completed = 0
        for sym, r in snaps.items():
            bar = self.agg.on_snapshot(r.tick, r.minute_bar, now=now)
            if bar is not None:
                completed += 1
                self.recorder.on_bar(bar, self.agg.history, now)
            for sl in self.slots:
                if sym not in sl.symbols and sym not in sl.book.positions and sym not in sl.book.pending_entries:
                    continue
                if not sl.live:
                    sl.broker.on_tick(r.tick)  # fills yesterday's-tick orders before new decisions
                if bar is not None:
                    sl.engine.on_completed_bar(bar, now)
                if sym in sl.book.positions:
                    sl.engine.on_tick(r.tick, now)
        realized_live = 0.0
        unrealized_live = 0.0
        for sl in self.slots:
            trades = sl.engine.poll_orders(now)
            if trades:
                sl.realized_today += sum(t.pnl for t in trades)
                sl.trades_today.extend(trades)
                for t in trades:
                    logger.info("[{}] trade done: {} {:+.2f}", sl.spec.id, t.symbol, t.pnl)
                if sl.live and self.risk:
                    self._apply_risk(
                        self.risk.check_winrate(
                            self.db.trades.recent(self.s.risk.winrate_lookback_trades, "live")[::-1]
                        )
                    )
            sl.engine.persist_positions()
            if sl.live:
                realized_live += sl.realized_today
                unrealized_live += sl.book.unrealized_pnl()
        if self.risk:
            self._apply_risk(self.risk.check_pnl(realized_live, unrealized_live))
        acct = self.broker.account() if self.tick_no % 4 == 1 else None
        if acct:
            self.db.state.set("account", {"equity": acct.equity, "cash": acct.cash, "buying_power": acct.buying_power})
        self.db.state.set(
            "heartbeat",
            {
                "ts": now.isoformat(),
                "tick": self.tick_no,
                "universe": len(self.universe),
                "snapshots": len(snaps),
                "completed_bars": completed,
                "api_calls": self.poller.calls + self.broker.calls,
                "positions": sum(len(sl.book.positions) for sl in self.slots if sl.live),
                "pending_entries": sum(len(sl.book.pending_entries) for sl in self.slots if sl.live),
                "feature_rows": self.recorder.rows,
                "feature_candidates": self.recorder.candidates,
                "halted": self.risk.halted_reason if self.risk else None,
                "realized_today": round(realized_live, 2),
                "unrealized": round(unrealized_live, 2),
                "slots": {
                    sl.spec.id: {
                        "mode": sl.mode,
                        "positions": len(sl.book.positions),
                        "pending": len(sl.book.pending_entries),
                        "realized": round(sl.realized_today, 2),
                        "trades": len(sl.trades_today),
                    }
                    for sl in self.slots
                },
            },
        )
        if self.tick_no % 20 == 0:
            logger.info(
                "tick {}: {} snaps, {} new bars, {}",
                self.tick_no,
                len(snaps),
                completed,
                {sl.spec.id: f"{len(sl.book.positions)}pos/{sl.realized_today:+.0f}" for sl in self.slots},
            )

    def _ask(self, symbol: str) -> float | None:
        t = self.agg.last_tick(symbol)
        return t.ask if t and t.ask else None

    # ------------------------------------------------------------------ helpers
    def _apply_controls(self, now: datetime) -> None:
        """Pause / resume / flatten / halt requests from the API, applied per strategy slot."""
        try:
            pending = self.db.control.pending()
        except Exception as e:  # noqa: BLE001
            logger.debug("control poll failed: {}", e)
            return
        for req in pending:
            cmd, target = req["command"], (req["strategy"] or "all")
            slots = [sl for sl in self.slots if target == "all" or sl.spec.id == target]
            if not slots:
                self.db.control.finish(req["id"], "rejected", f"unknown strategy {target}")
                continue
            try:
                for sl in slots:
                    if cmd == "pause":
                        sl.engine.halted = True
                        sl.orders.cancel_pending_entries()
                    elif cmd == "resume":
                        sl.engine.halted = False
                    elif cmd == "flatten":
                        sl.orders.cancel_pending_entries()
                        if sl.book.positions:
                            sl.orders.flatten_all(now, reason="manual_flatten")
                    elif cmd == "halt":
                        sl.engine.halted = True
                        sl.orders.cancel_pending_entries()
                        if sl.book.positions:
                            sl.orders.flatten_all(now, reason="manual_halt")
                    else:
                        raise ValueError(f"unknown command {cmd}")
                self.db.control.finish(req["id"], "done", f"{cmd} applied to {[sl.spec.id for sl in slots]}")
                logger.warning("CONTROL {} {} (from {})", cmd, target, req["source"])
            except Exception as e:  # noqa: BLE001
                self.db.control.finish(req["id"], "rejected", str(e)[:200])

    def _apply_risk(self, decision) -> None:
        if not decision.halt_entries:
            return
        live = [sl for sl in self.slots if sl.live]
        if not any(sl.engine.halted for sl in live):
            logger.warning("RISK HALT: {}", decision.reason)
            self.db.state.set("risk", {"halted": decision.reason, "at": datetime.now(timezone.utc).isoformat()})
        for sl in live:
            sl.engine.halted = True
            sl.orders.cancel_pending_entries()
            if decision.flatten and sl.book.positions:
                logger.warning("RISK FLATTEN [{}]: closing {} positions", sl.spec.id, len(sl.book.positions))
                sl.orders.flatten_all(datetime.now(timezone.utc), reason="risk_flatten")

    def _rebuild_universe(self) -> None:
        try:
            self.universe = self.universe_builder.build()
            self.db.state.set("universe", self.universe)
        except Exception as e:  # noqa: BLE001
            logger.error("universe build failed: {} (keeping {} symbols)", e, len(self.universe))

    def _warmup(self) -> None:
        if self.s.scan.warmup_minutes <= 0:
            return
        symbols = self._all_symbols()
        bars = self.history.warmup(symbols, self.s.scan.warmup_minutes)
        n = self.agg.seed(bars)
        for sl in self.slots:
            sl.engine.seed(bars)
        logger.info("warm-up: seeded {} bars for {} symbols", n, len({b.symbol for b in bars}))

    def _session_start(self, today: str) -> None:
        """Hand each strategy its symbols' recent daily bars (previous sessions only)."""
        from datetime import date as _date

        d = _date.fromisoformat(today)
        try:
            symbols = self._all_symbols()
            bars = self.daily.fetch(symbols, d - timedelta(days=40), d - timedelta(days=1))
        except Exception as e:  # noqa: BLE001
            logger.warning("daily bars for session start failed: {}", e)
            bars = []
        by: dict[str, list] = {}
        for b in bars:
            by.setdefault(b.symbol, []).append(b)
        for lst in by.values():
            lst.sort(key=lambda b: b.ts)
        for sl in self.slots:
            try:
                sl.strategy.on_session_start(today, {s: by.get(s, []) for s in sl.symbols})
            except Exception as e:  # noqa: BLE001
                logger.warning("[{}] on_session_start failed: {}", sl.spec.id, e)

    def _wait_until(self, when: datetime) -> None:
        logger.info("market closed; waiting until {} ET", when.astimezone(ET).strftime("%Y-%m-%d %H:%M"))
        while not self._stop:
            remaining = (when - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                return
            self.db.state.set(
                "heartbeat", {"ts": datetime.now(timezone.utc).isoformat(), "tick": 0, "waiting_for": when.isoformat()}
            )
            for _ in range(int(min(60, remaining))):
                if self._stop:
                    return
                time.sleep(1)

    @staticmethod
    def _plus_minute(t):
        return (datetime.combine(datetime.today(), t) + timedelta(minutes=1)).time()

    @staticmethod
    def _day_start_utc() -> datetime:
        return datetime.now(ET).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    def _shutdown(self, today: str) -> None:
        logger.info("shutting down: cancelling pending entries, final order poll")
        now = datetime.now(timezone.utc)
        try:
            for sl in self.slots:
                sl.engine.end_of_session(now)
                sl.orders.cancel_pending_entries()
                if not sl.live and sl.book.positions:
                    last = {sym: (self.agg.last_price(sym) or p.last_price) for sym, p in sl.book.positions.items()}
                    sl.orders.flatten_all(now, reason="shadow_eod")
                    sl.broker.force_close_all(last, now)
            for _ in range(3):
                pending = 0
                for sl in self.slots:
                    sl.trades_today.extend(sl.engine.poll_orders(datetime.now(timezone.utc)))
                    pending += len(sl.book.pending_exits)
                if not pending:
                    break
                time.sleep(2)
            acct = self.broker.account()
            for sl in self.slots:
                sl.engine.persist_positions()
                trades = self.db.trades.between(
                    self._day_start_utc(),
                    datetime.now(timezone.utc) + timedelta(minutes=1),
                    mode=sl.mode,
                    strategy=sl.spec.id,
                )
                prev = self.db.ledger.latest_before(today, LIVE_RUN_ID, sl.spec.id)
                cap = self.s.capital.model_copy(update={"base_allocation": sl.base_share})
                ledger = build_ledger(
                    today,
                    sl.mode,
                    LIVE_RUN_ID,
                    trades,
                    list(sl.book.positions.values()),
                    prev,
                    sl.allocation,
                    cap,
                    equity_close=acct.equity if sl.live else sl.broker.equity(),
                )
                ledger.strategy = sl.spec.id
                self.db.ledger.upsert(ledger)
                logger.info(
                    "ledger {} [{}/{}]: realized {:+.2f} on {} trades ({} wins), next allocation ${:,.0f}",
                    today,
                    sl.spec.id,
                    sl.mode,
                    ledger.realized_pnl,
                    ledger.trades,
                    ledger.wins,
                    ledger.next_allocation,
                )
            self._label_features(today)
        except Exception as e:  # noqa: BLE001
            logger.exception("shutdown bookkeeping failed: {}", e)

    def _label_features(self, today: str) -> None:
        try:
            from datetime import date as _date

            from ridethewave.data.market_data import regular_session_utc

            start, end = regular_session_utc(_date.fromisoformat(today))
            n = self.recorder.finalize(today, lambda syms: self.history.fetch(syms, start, end, use_cache=False))
            logger.info(
                "live features: {} rows recorded, {} candidates, {} labelled",
                self.recorder.rows,
                self.recorder.candidates,
                n,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("feature labelling failed: {}", e)
