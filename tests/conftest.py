from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ridethewave.models import Bar
from ridethewave.storage import Database


@pytest.fixture
def db() -> Database:
    d = Database.in_memory()
    yield d
    d.close()


def make_bars(symbol: str, closes: list[float], start: datetime | None = None, volume: int = 5000) -> list[Bar]:
    """Build consecutive one-minute bars from a list of closes. Open = previous close."""
    start = start or datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)
    bars = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        bars.append(
            Bar(
                symbol=symbol,
                ts=start + timedelta(minutes=i),
                open=o,
                high=max(o, c),
                low=min(o, c),
                close=c,
                volume=volume,
                trade_count=10,
                vwap=(o + c) / 2,
            )
        )
        prev = c
    return bars
