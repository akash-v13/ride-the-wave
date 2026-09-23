"""Roll completed 1-minute bars into N-minute bars, per symbol, live or in replay.

Buckets are anchored at 09:30 ET so a 15-minute bar covers 09:30-09:44, 09:45-09:59, ... A bucket is
emitted when a 1-minute bar from a later bucket (or a later session) arrives, or on ``flush``. With
``bar_minutes == 1`` this is a passthrough.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

from ridethewave.models import Bar

ET = ZoneInfo("America/New_York")


def bucket_start(ts: datetime, minutes: int) -> datetime:
    et = ts.astimezone(ET)
    mins = et.hour * 60 + et.minute - (9 * 60 + 30)
    if mins < 0:
        return et.replace(hour=9, minute=30, second=0, microsecond=0).astimezone(ts.tzinfo)
    b = (mins // minutes) * minutes
    return (
        et.replace(hour=9, minute=30, second=0, microsecond=0)
        .replace(hour=(9 * 60 + 30 + b) // 60, minute=(9 * 60 + 30 + b) % 60)
        .astimezone(ts.tzinfo)
    )


class Resampler:
    def __init__(self, bar_minutes: int = 1, window: int = 240):
        self.minutes = bar_minutes
        self.window = window
        self._open: dict[str, Bar] = {}  # in-progress bucket per symbol
        self._hist: dict[str, deque[Bar]] = {}

    def on_bar(self, bar: Bar) -> Bar | None:
        """Feed one completed 1-minute bar; return a completed N-minute bar if this one closed a bucket."""
        if self.minutes <= 1:
            self._push(bar)
            return bar
        start = bucket_start(bar.ts, self.minutes)
        cur = self._open.get(bar.symbol)
        emitted = None
        if cur is not None and cur.ts != start:
            emitted = cur
            self._push(cur)
            cur = None
        if cur is None:
            self._open[bar.symbol] = Bar(
                bar.symbol, start, bar.open, bar.high, bar.low, bar.close, bar.volume, bar.trade_count, bar.vwap
            )
        else:
            tot = cur.volume + bar.volume
            vwap = ((cur.vwap * cur.volume + bar.vwap * bar.volume) / tot) if tot > 0 else bar.close
            self._open[bar.symbol] = Bar(
                bar.symbol,
                cur.ts,
                cur.open,
                max(cur.high, bar.high),
                min(cur.low, bar.low),
                bar.close,
                tot,
                cur.trade_count + bar.trade_count,
                vwap,
            )
        return emitted

    def flush(self, symbol: str | None = None) -> list[Bar]:
        """Close any in-progress bucket(s) (end of session)."""
        out = []
        for sym in [symbol] if symbol else list(self._open):
            b = self._open.pop(sym, None)
            if b is not None:
                self._push(b)
                out.append(b)
        return out

    def in_progress(self, symbol: str) -> Bar | None:
        return self._open.get(symbol)

    def history(self, symbol: str) -> list[Bar]:
        return list(self._hist.get(symbol, ()))

    def seed(self, bars: list[Bar]) -> int:
        """Warm-up: feed completed 1-minute bars in time order (any symbols)."""
        n = 0
        for b in sorted(bars, key=lambda x: (x.symbol, x.ts)):
            if self.on_bar(b) is not None:
                n += 1
        return n

    def _push(self, bar: Bar) -> None:
        dq = self._hist.setdefault(bar.symbol, deque(maxlen=self.window))
        if dq and dq[-1].ts >= bar.ts:
            return
        dq.append(bar)
