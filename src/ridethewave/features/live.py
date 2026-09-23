"""Record per-minute feature rows during a live session and label them after the close.

Why: every paper day is training data on the feed the bot actually trades (IEX), which the
SIP-based research dataset cannot provide. Recording never touches trading: every call is wrapped so
a failure is logged and skipped.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time
from zoneinfo import ZoneInfo

from loguru import logger

from ridethewave.config import Settings
from ridethewave.features.compute import compute_features
from ridethewave.features.labels import label
from ridethewave.models import Bar
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")
MARKET = "SPY"


class LiveFeatureRecorder:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        feed: str,
        horizon: int = 60,
        target_pct: float = 1.0,
        stop_pct: float = 1.0,
    ):
        self.db = db
        self.s = settings
        self.feed = feed
        self.horizon = horizon
        self.target_pct = target_pct
        self.stop_pct = stop_pct
        self.rows = 0
        self.candidates = 0
        self._buffer: list[tuple] = []

    # ---------- during the session ----------
    def on_bar(self, bar: Bar, history: Callable[[str], list[Bar]], now: datetime) -> None:
        if bar.symbol == MARKET:
            return
        try:
            t = bar.ts.astimezone(ET)
            if not (self.s.entry.entry_start <= t.time() < self.s.entry.entry_end):
                return
            session_start = t.replace(hour=9, minute=30, second=0, microsecond=0)
            bars = history(bar.symbol)
            if not bars or bars[-1].ts != bar.ts:
                bars = [*bars, bar]
            f = compute_features(bars, history(MARKET), session_start)
            if f is None:
                return
            e = self.s.entry
            cand = (
                f.streak >= e.green_streak_minutes
                and f.streak_gain_pct >= e.min_streak_gain_pct
                and f.streak_volume >= e.min_streak_volume
            )
            self._buffer.append((bar.symbol, bar.ts, self.feed, t.strftime("%Y-%m-%d"), cand, f.as_dict()))
            self.rows += 1
            self.candidates += int(cand)
            if len(self._buffer) >= 200:
                self.flush()
        except Exception as e:  # noqa: BLE001
            logger.warning("feature recording skipped for {}: {}", bar.symbol, e)

    def flush(self) -> None:
        if not self._buffer:
            return
        try:
            self.db.features.insert_many(self._buffer)
        except Exception as e:  # noqa: BLE001
            logger.warning("feature flush failed ({} rows): {}", len(self._buffer), e)
        self._buffer = []

    # ---------- after the close ----------
    def finalize(self, day: str, fetch_day_bars: Callable[[list[str]], list[Bar]]) -> int:
        """Label every unlabelled row for ``day`` using the full session's bars. Returns rows labelled."""
        self.flush()
        pending = self.db.features.unlabelled(day, self.feed)
        if not pending:
            return 0
        symbols = sorted({r["symbol"] for r in pending})
        try:
            bars = fetch_day_bars(symbols)
        except Exception as e:  # noqa: BLE001
            logger.warning("label fetch failed: {}", e)
            return 0
        by_sym: dict[str, list[Bar]] = {}
        for b in bars:
            by_sym.setdefault(b.symbol, []).append(b)
        for lst in by_sym.values():
            lst.sort(key=lambda b: b.ts)
        slip = self.s.backtest.slippage_pct / 100
        updates = []
        for r in pending:
            lst = by_sym.get(r["symbol"], [])
            ts = datetime.fromisoformat(r["ts"])
            future = [b for b in lst if b.ts > ts]
            if not future:
                continue
            entry_price = future[0].open * (1 + slip)
            o = label(future, entry_price, self.s.exit, self.horizon, self.target_pct, self.stop_pct)
            if o is not None:
                updates.append((r["symbol"], ts, self.feed, o.as_dict()))
        n = self.db.features.set_labels(updates)
        logger.info("labelled {} of {} live feature rows for {}", n, len(pending), day)
        return n


def session_bounds(day: datetime) -> tuple[time, time]:
    return time(9, 30), time(16, 0)
