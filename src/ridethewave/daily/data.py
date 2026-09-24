"""Wide daily frames from the SQLite bar cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")
ADJ_TAG = "sip-day-adj"


@dataclass
class Panel:
    """Daily OHLCV as wide frames: index = session date, columns = symbols. Adjusted prices."""

    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame

    @property
    def symbols(self) -> list[str]:
        return list(self.close.columns)

    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.close.index

    def dollar_volume(self, lookback: int = 20) -> pd.DataFrame:
        return (self.close * self.volume).rolling(lookback, min_periods=max(5, lookback // 2)).mean()


def load_panel(db: Database, symbols: list[str], start: date, end: date, feed: str = ADJ_TAG) -> Panel:
    """Load [start, end] for the symbols. Missing days for a symbol stay NaN (never forward-filled here)."""
    s_utc = datetime.combine(start, datetime.min.time(), timezone.utc) - timedelta(days=1)
    e_utc = datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(days=1)
    bars = db.bars.range_all(sorted(set(symbols)), s_utc, e_utc, feed)
    if not bars:
        raise ValueError(f"no daily bars with feed tag {feed!r}; run scripts/download_daily.py first")
    rows = [(b.symbol, b.ts.astimezone(ET).date(), b.open, b.high, b.low, b.close, b.volume) for b in bars]
    df = pd.DataFrame(rows, columns=["symbol", "day", "open", "high", "low", "close", "volume"])
    df = df[(df["day"] >= start) & (df["day"] <= end)]
    df["day"] = pd.to_datetime(df["day"])
    wide = {
        c: df.pivot(index="day", columns="symbol", values=c).sort_index()
        for c in ("open", "high", "low", "close", "volume")
    }
    return Panel(**wide)
