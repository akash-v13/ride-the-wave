"""Small, pure helpers over lists of bars."""

from __future__ import annotations

from ridethewave.models import Bar


def green_streak(bars: list[Bar]) -> int:
    """Number of consecutive bars, ending at the last, whose close beat the previous close."""
    n = 0
    for i in range(len(bars) - 1, 0, -1):
        if bars[i].close > bars[i - 1].close:
            n += 1
        else:
            break
    return n


def streak_gain_pct(bars: list[Bar], streak: int) -> float:
    """Percent rise from the close just before the streak began to the latest close."""
    if streak <= 0 or len(bars) <= streak:
        return 0.0
    base = bars[-streak - 1].close
    if base <= 0:
        return 0.0
    return (bars[-1].close / base - 1.0) * 100.0


def streak_volume(bars: list[Bar], streak: int) -> int:
    if streak <= 0:
        return 0
    return sum(b.volume for b in bars[-streak:])
