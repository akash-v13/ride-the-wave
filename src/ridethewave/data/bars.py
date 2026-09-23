"""Turn snapshot polls into completed one-minute bars and keep a rolling history per symbol.

How live bars work on the free plan: every poll we receive, per symbol, the latest trade and the
latest *minute bar* Alpaca has (which may be the minute in progress). A bar is treated as
completed once its start time is older than the current minute. Minutes with no IEX trades
produce no bar at all, so "consecutive bars" can span a gap; the strategy works on bar sequence,
not wall-clock minutes, and this is documented in docs/strategy.md.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import datetime, timezone

from ridethewave.models import Bar, Tick


def floor_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


class BarAggregator:
    def __init__(self, window: int = 240):
        self.window = window
        self._history: dict[str, deque[Bar]] = {}
        self._last_emitted: dict[str, datetime] = {}
        self._last_tick: dict[str, Tick] = {}
        self._in_progress: dict[str, Bar] = {}

    # ----- history -----
    def seed(self, bars: Iterable[Bar]) -> int:
        """Load completed historical bars (warm-up). Returns number accepted."""
        n = 0
        for b in sorted(bars, key=lambda x: (x.symbol, x.ts)):
            if self._accept(b):
                n += 1
        return n

    def on_completed_bar(self, bar: Bar) -> Bar | None:
        """A bar known to be complete (backtest replay or websocket). Returns it if new."""
        return bar if self._accept(bar) else None

    def _accept(self, b: Bar) -> bool:
        last = self._last_emitted.get(b.symbol)
        if last is not None and b.ts <= last:
            return False
        dq = self._history.setdefault(b.symbol, deque(maxlen=self.window))
        dq.append(b)
        self._last_emitted[b.symbol] = b.ts
        self._in_progress.pop(b.symbol, None)
        return True

    # ----- live polling -----
    def on_snapshot(self, tick: Tick, minute_bar: Bar | None, now: datetime | None = None) -> Bar | None:
        """Feed one symbol's snapshot. Returns a newly completed bar, if any."""
        self._last_tick[tick.symbol] = tick
        if minute_bar is None:
            return None
        now = now or datetime.now(timezone.utc)
        current_minute = floor_minute(now)
        if minute_bar.ts < current_minute:
            return minute_bar if self._accept(minute_bar) else None
        self._in_progress[tick.symbol] = minute_bar
        return None

    # ----- reads -----
    def history(self, symbol: str) -> list[Bar]:
        return list(self._history.get(symbol, ()))

    def last_bar(self, symbol: str) -> Bar | None:
        dq = self._history.get(symbol)
        return dq[-1] if dq else None

    def in_progress(self, symbol: str) -> Bar | None:
        return self._in_progress.get(symbol)

    def last_price(self, symbol: str) -> float | None:
        t = self._last_tick.get(symbol)
        if t:
            return t.price
        b = self.last_bar(symbol)
        return b.close if b else None

    def last_tick(self, symbol: str) -> Tick | None:
        return self._last_tick.get(symbol)

    def symbols(self) -> list[str]:
        return list(self._history.keys())
