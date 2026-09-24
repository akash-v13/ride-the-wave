"""Fill the daily-bar cache (feed tag ``sip-day``) for a symbol list over a long range.

Unlike DailyBars.fetch, this always asks Alpaca for the whole range and upserts, so a symbol that
already has a few recent daily bars cached still gets its full history.

    uv run python scripts/download_daily.py --start 2015-06-01 --end 2026-09-22 --symbols SPY,QQQ,AAPL
    uv run python scripts/download_daily.py --start 2015-06-01 --end 2026-09-22 --universe traderpro
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone

from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import DailyBars
from ridethewave.storage import Database

# The universes TraderPro backtested on (docs/research/2026-09-23-traderpro-extraction.md) plus the
# broad-market and defensive instruments its strategies reference.
UNIVERSES: dict[str, list[str]] = {
    "mega_caps_20": [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "NVDA",
        "META",
        "TSLA",
        "AVGO",
        "BRK.B",
        "JPM",
        "V",
        "UNH",
        "XOM",
        "MA",
        "HD",
        "PG",
        "COST",
        "JNJ",
        "ABBV",
        "WMT",
    ],
    "sector_etfs_11": ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLRE", "XLU", "XLC"],
    "multi_asset_8": ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"],
    "broad_and_defensive": ["SPY", "QQQ", "IWM", "IEF", "TLT", "GLD", "SHY", "BIL"],
}
UNIVERSES["traderpro"] = sorted({s for lst in UNIVERSES.values() for s in lst})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--symbols", default=None, help="comma-separated")
    ap.add_argument("--universe", default=None, choices=sorted(UNIVERSES))
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument(
        "--adjust", default="all", choices=["raw", "split", "dividend", "all"], help="all -> tag sip-day-adj"
    )
    args = ap.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else []
    if args.universe:
        symbols += UNIVERSES[args.universe]
    symbols = sorted(set(symbols))
    if not symbols:
        sys.exit("give --symbols or --universe")
    settings = load_settings()
    clients = make_clients(load_secrets(), settings)
    db = Database(settings.storage.resolved_db_path())
    daily = DailyBars(clients.data, db, adjustment=args.adjust)
    s_utc = datetime.combine(args.start, datetime.min.time(), timezone.utc)
    e_utc = datetime.combine(args.end + timedelta(days=1), datetime.min.time(), timezone.utc) - timedelta(seconds=1)
    total = 0
    for i in range(0, len(symbols), args.batch):
        chunk = symbols[i : i + args.batch]
        bars = daily._fetch(chunk, s_utc, e_utc)
        if bars:
            db.bars.upsert_many(bars, feed=daily.feed_tag)
        got = {b.symbol for b in bars}
        missing = sorted(set(chunk) - got)
        total += len(bars)
        logger.info("{} symbols -> {} daily bars{}", len(chunk), len(bars), f"; none for {missing}" if missing else "")
    logger.info(
        "done: {} bars for {} symbols, {} API calls, feed tag {}", total, len(symbols), daily.calls, daily.feed_tag
    )
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
