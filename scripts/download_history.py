"""Fill the local bar cache so backtests run offline and fast.

    uv run python scripts/download_history.py --start 2026-06-01 --end 2026-09-16 --pit-top 50
    uv run python scripts/download_history.py --start 2026-06-01 --end 2026-09-16 --symbols AAPL,TSLA --feeds sip,iex

Downloads regular-session minute bars (09:30 to 16:00 ET) per day, the same windows the replay
engine queries, so every later backtest over these dates is a cache hit. With --pit-top the
universe is recomputed per day from trailing dollar volume (no lookahead).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import HistoricalBars, regular_session_utc
from ridethewave.data.pit_universe import PointInTimeUniverse
from ridethewave.storage import Database


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--pit-top", type=int, default=None, help="point-in-time top N by trailing dollar volume")
    ap.add_argument("--feeds", default="sip", help="comma list: sip,iex")
    ap.add_argument("--settings", default=None)
    args = ap.parse_args()

    settings = load_settings(args.settings)
    clients = make_clients(load_secrets(), settings)
    db = Database(settings.storage.resolved_db_path())
    feeds = [f.strip() for f in args.feeds.split(",") if f.strip()]

    pit = None
    static: list[str] = []
    if args.symbols:
        static = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.pit_top:
        pit = PointInTimeUniverse(clients, db, settings.universe)
        pit.preload(args.start, args.end)
    else:
        sys.exit("give --symbols or --pit-top")

    fetchers = {f: HistoricalBars(clients.data, db, feed=f) for f in feeds}
    t0 = time.time()
    total = 0
    days = 0
    seen: set[str] = set()
    day = args.start
    while day <= args.end:
        if day.weekday() < 5:
            syms = static or pit.universe_for(day, args.pit_top)
            seen.update(syms)
            s, e = regular_session_utc(day)
            for h in fetchers.values():
                bars = h.fetch(syms, s, e)
                total += len(bars)
            days += 1
            if days % 5 == 0:
                calls = sum(h.calls for h in fetchers.values())
                logger.info(
                    "{}: {} days, {:,} bars, {} symbols seen, {} API calls, {:.0f}s",
                    day,
                    days,
                    total,
                    len(seen),
                    calls,
                    time.time() - t0,
                )
        day += timedelta(days=1)
    calls = sum(h.calls for h in fetchers.values())
    logger.info(
        "done: {} days, {:,} bars, {} distinct symbols, {} API calls in {:.0f}s",
        days,
        total,
        len(seen),
        calls,
        time.time() - t0,
    )
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
