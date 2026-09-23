"""Replay historical minute bars through the live code path."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger

from ridethewave.backtest.sim_broker import SimBroker
from ridethewave.config import Settings
from ridethewave.data.bars import BarAggregator
from ridethewave.data.market_data import HistoricalBars, regular_session_utc
from ridethewave.engine import TradingEngine
from ridethewave.execution import OrderManager, PositionBook
from ridethewave.models import Bar, DailyLedger, Trade
from ridethewave.portfolio import CapitalAllocator, build_ledger
from ridethewave.storage import Database
from ridethewave.strategy import Strategy, WaveRider

ET = ZoneInfo("America/New_York")


@dataclass
class BacktestResult:
    run_id: str
    start: date
    end: date
    feed: str
    universe: list[str]
    trades: list[Trade] = field(default_factory=list)
    ledgers: list[DailyLedger] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float, float]] = field(default_factory=list)
    bars_replayed: int = 0
    days: int = 0
    api_calls: int = 0


class ReplayEngine:
    def __init__(
        self,
        settings: Settings,
        db: Database | None,
        history: HistoricalBars,
        universe: list[str],
        start: date,
        end: date,
        strategy: Strategy | None = None,
        starting_cash: float | None = None,
        run_id: str | None = None,
        universe_fn: Callable[[date], list[str]] | None = None,
        daily_provider: Callable[[list[str], date], dict[str, list[Bar]]] | None = None,
    ):
        self.s = settings
        self.db = db
        self.history = history
        self.universe = universe
        self.universe_fn = universe_fn  # point-in-time universe per day; overrides self.universe when set
        self.daily_provider = daily_provider  # symbols, day -> recent daily bars per symbol (before that day)
        self.start = start
        self.end = end
        self.strategy = strategy or WaveRider(settings.entry, settings.exit)
        self.starting_cash = starting_cash or settings.capital.base_allocation * 10  # cash is not the constraint
        self.run_id = run_id or f"bt-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"

    def run(self) -> BacktestResult:
        res = BacktestResult(self.run_id, self.start, self.end, self.history.feed, self.universe)
        sim = SimBroker(cash=self.starting_cash, slippage_pct=self.s.backtest.slippage_pct)
        book = PositionBook()
        allocation = self.s.capital.base_allocation
        allocator = CapitalAllocator(self.s.capital, self.s.entry, allocation)
        orders = OrderManager(
            sim,
            book,
            allocator,
            self.db,
            self.s.entry,
            self.s.exit,
            run_id=self.run_id,
            mode="backtest",
            strategy=self.strategy.name,
            protective_stop=self.strategy.uses_protective_stop,
        )
        agg = BarAggregator()
        engine = TradingEngine(self.s, self.strategy, book, orders, agg, None, self.run_id)
        if self.db is not None:
            self.db.backtests.insert_run(
                id=self.run_id,
                start_date=str(self.start),
                end_date=str(self.end),
                feed=self.history.feed,
                params=self.s.model_dump(mode="json"),
                universe=self.universe,
            )

        prev_ledger: DailyLedger | None = None
        day = self.start
        while day <= self.end:
            if day.weekday() >= 5:
                day += timedelta(days=1)
                continue
            day_start, day_end = regular_session_utc(day)
            todays_universe = self.universe_fn(day) if self.universe_fn else self.universe
            if self.universe_fn:
                for sym in todays_universe:
                    if sym not in self.universe:
                        self.universe.append(sym)
            # keep polling anything still held even if it dropped out of today's universe
            symbols = sorted(set(todays_universe) | set(book.positions) | {"SPY"})
            bars = self.history.fetch(symbols, day_start, day_end)
            if not bars:
                logger.info("{}: no bars (holiday?)", day)
                day += timedelta(days=1)
                continue
            res.days += 1
            book.entries_today = {}
            allocator.allocation = allocation
            if self.daily_provider is not None:
                try:
                    self.strategy.on_session_start(str(day), self.daily_provider(symbols, day))
                except Exception as e:  # noqa: BLE001
                    logger.warning("{}: on_session_start failed: {}", day, e)
            trades_today = self._replay_day(bars, sim, book, orders, agg, engine, res)
            # end of day bookkeeping
            engine.end_of_session(day_end)
            last_prices = {s: p.last for s, p in sim.positions_.items()}
            if self.s.exit.flatten_at_close and self.strategy.flatten_at_close and book.positions:
                orders.flatten_all(day_end)
                sim.force_close_all(last_prices, day_end)
                trades_today += engine.poll_orders(day_end)
            orders.cancel_pending_entries()
            ledger = build_ledger(
                str(day),
                "backtest",
                self.run_id,
                trades_today,
                list(book.positions.values()),
                prev_ledger,
                allocation,
                self.s.capital,
                equity_close=sim.equity(),
            )
            res.ledgers.append(ledger)
            if self.db is not None:
                self.db.ledger.upsert(ledger)
            prev_ledger = ledger
            allocation = ledger.next_allocation
            logger.info(
                "{}: {} trades, realized {:+.2f}, equity {:,.2f}, next alloc {:,.0f}",
                day,
                ledger.trades,
                ledger.realized_pnl,
                sim.equity(),
                allocation,
            )
            day += timedelta(days=1)

        res.trades = list(orders.trades)
        res.api_calls = self.history.calls
        if self.db is not None:
            self.db.backtests.add_equity_points(self.run_id, res.equity_curve)
        return res

    def _replay_day(
        self,
        bars: list[Bar],
        sim: SimBroker,
        book: PositionBook,
        orders: OrderManager,
        agg: BarAggregator,
        engine: TradingEngine,
        res: BacktestResult,
    ) -> list[Trade]:
        trades: list[Trade] = []
        by_minute: dict[datetime, list[Bar]] = {}
        for b in bars:
            by_minute.setdefault(b.ts, []).append(b)
        for ts in sorted(by_minute):
            minute_bars = by_minute[ts]
            now = ts + timedelta(minutes=1)  # the bar is complete at the end of its minute
            # 1. orders placed on earlier bars get a chance to fill on this bar
            for b in minute_bars:
                sim.process_bar(b)
            trades += engine.poll_orders(now)
            # 2. strategy sees the completed bars
            for b in minute_bars:
                pos = book.positions.get(b.symbol)
                if pos is not None and not pos.exit_pending:
                    pos.update_price(b.high)  # live bot would have seen intra-minute highs via ticks
                if agg.on_completed_bar(b) is not None:
                    engine.on_completed_bar(b, now)
                res.bars_replayed += 1
            res.equity_curve.append((now, sim.equity(), sim.cash))
        return trades
