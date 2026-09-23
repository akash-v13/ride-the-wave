"""The glue between market data, strategy and execution. Shared by the live bot and the backtester.

The engine does not know where bars come from (snapshots or history) or where orders go
(Alpaca or the simulator). It only knows: a completed bar arrived, a tick arrived, ask the
strategy, hand signals to the order manager, keep the database's view of positions fresh.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ridethewave.config import Settings
from ridethewave.data.bars import BarAggregator
from ridethewave.data.resample import Resampler
from ridethewave.execution import OrderManager, PositionBook
from ridethewave.models import Bar, Signal, Tick, Trade
from ridethewave.storage import Database
from ridethewave.strategy import Strategy, StrategyContext


class TradingEngine:
    def __init__(
        self,
        settings: Settings,
        strategy: Strategy,
        book: PositionBook,
        orders: OrderManager,
        aggregator: BarAggregator,
        db: Database | None,
        run_id: str,
    ):
        self.settings = settings
        self.strategy = strategy
        self.book = book
        self.orders = orders
        self.agg = aggregator
        self.db = db
        self.run_id = run_id
        self.halted = False  # set by the risk monitor; exits keep working, entries stop
        self.signal_filter: Callable[[Signal], bool] | None = None  # e.g. symbol exclusivity across strategies
        self.resampler = Resampler(strategy.bar_minutes) if strategy.bar_minutes > 1 else None

    def bars(self, symbol: str) -> list[Bar]:
        return self.resampler.history(symbol) if self.resampler else self.agg.history(symbol)

    def context(self, now: datetime) -> StrategyContext:
        return StrategyContext(
            now=now,
            bars=self.bars,
            positions=self.book.positions,
            pending_entries=set(self.book.pending_entries),
            entries_today=self.book.entries_today,
            open_slots=0 if self.halted else self.book.open_slots(self.settings.entry.max_positions),
        )

    def _dispatch(self, signals: list[Signal], now: datetime) -> None:
        if self.signal_filter is not None:
            signals = [s for s in signals if self.signal_filter(s)]
        if signals:
            self.orders.handle(signals, now)

    def on_completed_bar(self, bar: Bar, now: datetime) -> None:
        """Feed a completed 1-minute bar; strategies on larger bars only see their own completed buckets."""
        if self.resampler:
            big = self.resampler.on_bar(bar)
            if big is None:
                return
            bar = big
        self._dispatch(self.strategy.on_bar(bar, self.context(now)), now)

    def seed(self, bars: list[Bar]) -> None:
        if self.resampler:
            self.resampler.seed(bars)

    def end_of_session(self, now: datetime) -> None:
        if self.resampler:
            for big in self.resampler.flush():
                self._dispatch(self.strategy.on_bar(big, self.context(now)), now)

    def on_tick(self, tick: Tick, now: datetime) -> None:
        if tick.symbol not in self.book.positions:
            return
        self._dispatch(self.strategy.on_tick(tick, self.context(now)), now)

    def poll_orders(self, now: datetime) -> list[Trade]:
        return self.orders.poll(now)

    def persist_positions(self) -> None:
        if self.db is None:
            return
        self.db.positions.clear()
        for pos in self.book.positions.values():
            self.db.positions.upsert(pos, self.run_id, exit_trigger=self.strategy.exit_trigger(pos))
