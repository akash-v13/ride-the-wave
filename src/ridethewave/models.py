"""Plain data objects shared by every layer.

These are deliberately free of any Alpaca or SQLite types so the strategy and
backtester can use them without importing either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Bar:
    """One completed time bar (one minute in this project) for one symbol."""

    symbol: str
    ts: datetime  # bar start, timezone-aware UTC
    open: float
    high: float
    low: float
    close: float
    volume: int
    trade_count: int = 0
    vwap: float = 0.0


@dataclass(frozen=True, slots=True)
class Tick:
    """The latest price observation for a symbol, used between bar closes."""

    symbol: str
    ts: datetime
    price: float
    bid: float | None = None
    ask: float | None = None


class SignalType(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class Signal:
    """What the strategy wants done. Execution decides how."""

    type: SignalType
    symbol: str
    ts: datetime
    reason: str
    reference_price: float  # price the strategy saw when it decided
    qty: float | None = None  # None on BUY means "size it for me"
    noise_pct: float | None = None  # per-minute range at entry, for volatility-scaled exits


@dataclass(slots=True)
class Position:
    """The bot's own record of an open long position."""

    symbol: str
    qty: float
    entry_price: float
    entry_time: datetime
    peak_price: float
    last_price: float
    entry_order_id: str | None = None
    stop_order_id: str | None = None
    exit_pending: bool = False
    noise_pct: float | None = None
    strategy: str = "wave_rider"

    def update_price(self, price: float) -> None:
        self.last_price = price
        if price > self.peak_price:
            self.peak_price = price

    @property
    def unrealized_pnl(self) -> float:
        return (self.last_price - self.entry_price) * self.qty

    @property
    def unrealized_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.last_price / self.entry_price - 1.0) * 100.0


@dataclass(slots=True)
class Trade:
    """A completed round trip."""

    symbol: str
    qty: float
    entry_price: float
    entry_time: datetime
    exit_price: float
    exit_time: datetime
    exit_reason: str
    peak_price: float
    mode: str = "live"  # live | backtest | shadow
    run_id: str = ""
    entry_order_id: str | None = None
    exit_order_id: str | None = None
    strategy: str = "wave_rider"

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.qty

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.exit_price / self.entry_price - 1.0) * 100.0


@dataclass(slots=True)
class PendingEntry:
    """A buy order that has been submitted but not yet filled."""

    symbol: str
    order_id: str
    client_order_id: str
    submitted_at: datetime
    limit_price: float
    qty: float
    noise_pct: float | None = None


@dataclass(slots=True)
class DailyLedger:
    date: str  # YYYY-MM-DD in US/Eastern
    mode: str  # live | backtest | shadow
    run_id: str  # 'live' or the backtest run id
    base_allocation: float
    allocation: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    cumulative_realized: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    next_allocation: float = 0.0
    equity_close: float | None = None
    extra: dict = field(default_factory=dict)
    strategy: str = "wave_rider"
