"""Build the prospects dataset from cached history: one row per symbol per minute in the entry window."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from loguru import logger

from ridethewave.config import Settings
from ridethewave.data.market_data import regular_session_utc
from ridethewave.features.compute import compute_features
from ridethewave.features.labels import label
from ridethewave.models import Bar

ET = ZoneInfo("America/New_York")


@dataclass
class DatasetStats:
    days: int = 0
    symbols: int = 0
    rows: int = 0
    candidates: int = 0


def build_rows_for_day(
    day: date, bars: list[Bar], settings: Settings, horizon: int, target_pct: float, stop_pct: float
) -> list[dict]:
    """``bars`` is the full regular session for every symbol that day (SPY included), any order."""
    session_start, _ = regular_session_utc(day)
    by_sym: dict[str, list[Bar]] = {}
    for b in bars:
        by_sym.setdefault(b.symbol, []).append(b)
    for lst in by_sym.values():
        lst.sort(key=lambda b: b.ts)
    spy = by_sym.get("SPY", [])
    e = settings.entry
    rows: list[dict] = []
    for sym, lst in by_sym.items():
        if sym == "SPY":
            continue
        for i in range(len(lst)):
            b = lst[i]
            t = b.ts.astimezone(ET).time()
            if not (e.entry_start <= t < e.entry_end):
                continue
            f = compute_features(lst[: i + 1], spy, session_start)
            if f is None:
                continue
            future = lst[i + 1 :]
            if not future:
                continue
            entry_price = future[0].open * (1 + settings.backtest.slippage_pct / 100)
            o = label(future, entry_price, settings.exit, horizon, target_pct, stop_pct)
            if o is None:
                continue
            candidate = (
                f.streak >= e.green_streak_minutes
                and f.streak_gain_pct >= e.min_streak_gain_pct
                and f.streak_volume >= e.min_streak_volume
            )
            row = {"day": str(day), "candidate": candidate, **f.as_dict(), **o.as_dict()}
            rows.append(row)
    return rows


def build_dataset(
    settings: Settings,
    fetch_day: Callable[[date, list[str]], list[Bar]],
    universe_for: Callable[[date], list[str]],
    start: date,
    end: date,
    horizon: int = 60,
    target_pct: float = 1.0,
    stop_pct: float = 1.0,
) -> tuple[pd.DataFrame, DatasetStats]:
    stats = DatasetStats()
    frames: list[pd.DataFrame] = []
    seen: set[str] = set()
    day = start
    while day <= end:
        if day.weekday() < 5:
            syms = sorted(set(universe_for(day)) | {"SPY"})
            bars = fetch_day(day, syms)
            if bars:
                rows = build_rows_for_day(day, bars, settings, horizon, target_pct, stop_pct)
                if rows:
                    frames.append(pd.DataFrame(rows))
                    stats.days += 1
                    stats.rows += len(rows)
                    stats.candidates += sum(r["candidate"] for r in rows)
                    seen.update(syms)
                if stats.days % 10 == 0 and rows:
                    logger.info(
                        "{}: {} days, {:,} rows, {:,} candidates", day, stats.days, stats.rows, stats.candidates
                    )
        day += timedelta(days=1)
    stats.symbols = len(seen - {"SPY"})
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return df, stats
