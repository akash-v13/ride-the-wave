"""Survivorship-free daily history: every US equity Alpaca has ever listed (active AND delisted), adjusted
daily bars from 2016, written as parquet chunks under data/daily_panel/. This is the pool a point-in-time
universe must be drawn from if a backtest "started in 2017" is to mean anything: the names that went to
zero are in it. Alpaca lists ~19k inactive assets and serves their history (verified 2026-09-23).

    uv run python scripts/download_universe_history.py --start 2016-01-01 --end 2026-09-22
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest
from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import DailyBars
from ridethewave.data.universe import is_fund

OUT = Path("data/daily_panel")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=date(2016, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--chunk", type=int, default=100, help="symbols per API call")
    ap.add_argument("--include-funds", action="store_true")
    ap.add_argument("--resume", action="store_true", help="skip chunks whose parquet exists")
    args = ap.parse_args()
    settings = load_settings()
    clients = make_clients(load_secrets(), settings)
    allowed = {e.upper() for e in settings.universe.exchanges}
    assets = []
    for status in (AssetStatus.ACTIVE, AssetStatus.INACTIVE):
        assets += clients.trading.get_all_assets(GetAssetsRequest(status=status, asset_class=AssetClass.US_EQUITY))
    rows = []
    for a in assets:
        exch = str(getattr(a.exchange, "value", a.exchange)).upper()
        if exch not in allowed or not a.symbol.isalpha():
            continue
        fund = is_fund(getattr(a, "name", None))
        if fund and not args.include_funds:
            continue
        rows.append(
            {
                "symbol": a.symbol,
                "name": a.name,
                "exchange": exch,
                "status": str(getattr(a.status, "value", a.status)),
                "fund": fund,
            }
        )
    meta = pd.DataFrame(rows).drop_duplicates("symbol").sort_values("symbol")
    OUT.mkdir(parents=True, exist_ok=True)
    meta.to_parquet(OUT / "assets.parquet")
    symbols = meta["symbol"].tolist()
    logger.info(
        "{} symbols ({} active, {} inactive) after exchange/fund filters",
        len(symbols),
        (meta["status"] == "active").sum(),
        (meta["status"] == "inactive").sum(),
    )
    daily = DailyBars(clients.data, None, adjustment="all")
    s_utc = datetime.combine(args.start, datetime.min.time(), timezone.utc)
    e_utc = datetime.combine(args.end + timedelta(days=1), datetime.min.time(), timezone.utc) - timedelta(seconds=1)
    total = 0
    for i in range(0, len(symbols), args.chunk):
        path = OUT / f"bars_{i // args.chunk:04d}.parquet"
        if args.resume and path.exists():
            continue
        chunk = symbols[i : i + args.chunk]
        try:
            bars = daily._fetch(chunk, s_utc, e_utc)
        except Exception as e:  # noqa: BLE001
            logger.warning("chunk {} failed: {}", i // args.chunk, e)
            continue
        if bars:
            df = pd.DataFrame(
                [(b.symbol, b.ts.date(), b.open, b.high, b.low, b.close, b.volume) for b in bars],
                columns=["symbol", "day", "open", "high", "low", "close", "volume"],
            )
            df.to_parquet(path)
            total += len(df)
        if (i // args.chunk) % 20 == 0:
            logger.info(
                "chunk {}/{}: {} bars so far, {} API calls",
                i // args.chunk,
                len(symbols) // args.chunk,
                total,
                daily.calls,
            )
    logger.info("done: {} bars for {} symbols in {}", total, len(symbols), OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
