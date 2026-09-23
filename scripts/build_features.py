"""Build the prospects/candidates feature dataset from cached history.

    uv run python scripts/build_features.py --start 2026-06-01 --end 2026-09-16 --pit-top 50
    -> data/features/features-<start>-<end>.parquet

Requires the bar cache (scripts/download_history.py) for the same range. SPY bars are fetched too.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import HistoricalBars, regular_session_utc
from ridethewave.data.pit_universe import PointInTimeUniverse
from ridethewave.features.dataset import build_dataset
from ridethewave.storage import Database


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--pit-top", type=int, default=50)
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    ap.add_argument("--horizon", type=int, default=60, help="bars for forward-outcome labels")
    ap.add_argument("--target", type=float, default=1.0)
    ap.add_argument("--stop", type=float, default=1.0)
    ap.add_argument("--settings", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    settings = load_settings(args.settings)
    clients = make_clients(load_secrets(), settings)
    db = Database(settings.storage.resolved_db_path())
    history = HistoricalBars(clients.data, db, feed=args.feed)
    pit = PointInTimeUniverse(clients, db, settings.universe)
    pit.preload(args.start, args.end)
    cache: dict[date, list[str]] = {}

    def universe_for(d: date) -> list[str]:
        if d not in cache:
            cache[d] = pit.universe_for(d, args.pit_top)
        return cache[d]

    def fetch_day(d: date, syms: list[str]):
        s, e = regular_session_utc(d)
        return history.fetch(syms, s, e)

    t0 = time.time()
    df, stats = build_dataset(
        settings, fetch_day, universe_for, args.start, args.end, args.horizon, args.target, args.stop
    )
    out = (
        Path(args.out)
        if args.out
        else settings.storage.resolved_db_path().parent
        / "features"
        / (f"features-{args.start}-{args.end}-{args.feed}.parquet")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    logger.info(
        "wrote {} rows ({} candidates) for {} days, {} symbols to {} in {:.0f}s",
        f"{stats.rows:,}",
        f"{stats.candidates:,}",
        stats.days,
        stats.symbols,
        out,
        time.time() - t0,
    )
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
