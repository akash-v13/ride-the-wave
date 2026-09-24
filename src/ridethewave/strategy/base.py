"""Strategy interface. Pure: no network, no database.

The runner (live or backtest) builds a ``StrategyContext`` before each call so the strategy can see
bar history, open positions and capacity without touching any I/O itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from ridethewave.models import Bar, Position, Signal, Tick


@dataclass(slots=True)
class StrategyContext:
    now: datetime  # timezone-aware
    bars: Callable[[str], list[Bar]]  # completed bar history for a symbol, oldest first
    positions: dict[str, Position] = field(default_factory=dict)
    pending_entries: set[str] = field(default_factory=set)
    entries_today: dict[str, int] = field(default_factory=dict)
    open_slots: int = 0

    def position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)


class Strategy(ABC):
    """A signal strategy: sees bars and ticks for its symbols, emits buy/sell signals.

    ``symbols(universe)`` tells the runner which symbols to route to it: the scanned universe by
    default, or a fixed list for market-timing strategies. ``flatten_at_close`` lets a strategy
    opt out of the global end-of-day flatten (it must then close its own positions).
    ``uses_protective_stop`` controls whether entries carry a server-side stop leg.
    """

    name: str = "base"
    flatten_at_close: bool = True
    uses_protective_stop: bool = True
    bar_minutes: int = 1  # the bar size on_bar receives; the runner and engine resample for it
    stocks_only: bool = False  # True: the runner and backtester drop ETFs, ETNs and trusts from this strategy's symbols

    def symbols(self, universe: list[str]) -> list[str]:
        return list(universe)

    def on_session_start(self, day: str, daily: dict[str, list[Bar]]) -> None:  # pragma: no cover - default
        """Called once per session with each symbol's recent daily bars (oldest first, about 20). Optional."""
        return None

    @abstractmethod
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Signal]:
        """Called once per completed bar per symbol."""

    @abstractmethod
    def on_tick(self, tick: Tick, ctx: StrategyContext) -> list[Signal]:
        """Called on every price update for symbols we hold (between bars)."""

    def exit_trigger(self, pos: Position) -> float | None:  # pragma: no cover - default
        """Optional: the price at which the strategy would currently sell, for the dashboard."""
        return None
