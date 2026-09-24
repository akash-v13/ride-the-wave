"""Daily bars for option contracts on monthly expiries (third Fridays), for the options backtester.

For each underlying and each monthly expiry, every call and put with a strike within --band of the
underlying's price range over the 80 days before expiry (strike step --step), with daily bars from 80
days before expiry to expiry. OCC symbols are built from the grid; symbols that never existed simply
return no bars. Also stores the underlying's raw (unadjusted) daily bars, since strikes are raw prices.
Alpaca's option bar history starts in January 2024 (verified 2026-09-24).

    uv run python scripts/download_option_history.py --underlyings SPY,QQQ,IWM
Output: data/options_history/<UNDERLYING>_<YYYYMMDD>.parquet and <UNDERLYING>_underlying.parquet
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from alpaca.data.requests import OptionBarsRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import DailyBars

OUT = Path("data/options_history")


def third_fridays(start: date, end: date) -> list[date]:
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        d = date(y, m, 15)  # the third Friday falls on the 15th to the 21st
        d += timedelta(days=(4 - d.weekday()) % 7)
        if start <= d <= end:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def occ(und: str, expiry: date, right: str, strike: float) -> str:
    return f"{und}{expiry:%y%m%d}{right}{round(strike * 1000):08d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlyings", default="SPY,QQQ,IWM")
    ap.add_argument("--start", type=date.fromisoformat, default=date(2024, 3, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 12, 31))
    ap.add_argument("--band", type=float, default=0.18, help="strikes within this fraction of the price range")
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--lookback", type=int, default=80, help="calendar days of bars before each expiry")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    s = load_settings()
    c = make_clients(load_secrets(), s)
    OUT.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    raw = DailyBars(c.data, None, adjustment="raw")
    for und in [x.strip().upper() for x in args.underlyings.split(",")]:
        ub = raw._fetch(
            [und], datetime(2023, 10, 1, tzinfo=timezone.utc), datetime.now(timezone.utc) - timedelta(minutes=20)
        )
        u = pd.DataFrame(
            [(b.ts.date(), b.open, b.high, b.low, b.close, b.volume) for b in ub],
            columns=["day", "open", "high", "low", "close", "volume"],
        )
        u["day"] = pd.to_datetime(u["day"])
        u = u.set_index("day").sort_index()
        u.to_parquet(OUT / f"{und}_underlying.parquet")
        for third in third_fridays(args.start, args.end):
            for exp in (third, third - timedelta(days=1)):  # a holiday Friday moves expiry to the Thursday
                path = OUT / f"{und}_{exp:%Y%m%d}.parquet"
                if (
                    exp != third
                    and (OUT / f"{und}_{third:%Y%m%d}.parquet").exists()
                    and len(pd.read_parquet(OUT / f"{und}_{third:%Y%m%d}.parquet"))
                ):
                    break
                if path.exists() and not args.force and exp < today:
                    continue
                lo_day = pd.Timestamp(exp - timedelta(days=args.lookback))
                win = u.loc[(u.index >= lo_day) & (u.index <= pd.Timestamp(min(exp, today)))]
                if win.empty:
                    continue
                lo, hi = win["low"].min() * (1 - args.band), win["high"].max() * (1 + args.band)
                k = (lo // args.step) * args.step
                syms = []
                while k <= hi:
                    syms += [occ(und, exp, "C", k), occ(und, exp, "P", k)]
                    k += args.step
                rows = []
                for i in range(0, len(syms), 100):
                    chunk = syms[i : i + 100]
                    try:
                        data = c.options.get_option_bars(
                            OptionBarsRequest(
                                symbol_or_symbols=chunk,
                                timeframe=TimeFrame.Day,
                                start=datetime.combine(lo_day.date(), datetime.min.time(), timezone.utc),
                                end=datetime.combine(exp + timedelta(days=1), datetime.min.time(), timezone.utc),
                                limit=None,
                            )
                        ).data
                    except Exception as e:  # noqa: BLE001
                        logger.warning("{} {}: {}", und, exp, e)
                        continue
                    for sym, lst in data.items():
                        rows += [
                            (sym, b.timestamp.date(), b.open, b.high, b.low, b.close, b.volume, b.trade_count)
                            for b in lst
                        ]
                df = pd.DataFrame(rows, columns=["symbol", "day", "open", "high", "low", "close", "volume", "trades"])
                if not len(df):
                    path.unlink(missing_ok=True)
                    logger.info("{} {}: no bars (holiday or not yet listed)", und, exp)
                    continue
                df.to_parquet(path, index=False)
                logger.info(
                    "{} {}: {} candidate symbols, {} with bars, {} bars",
                    und,
                    exp,
                    len(syms),
                    df["symbol"].nunique() if len(df) else 0,
                    len(df),
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
