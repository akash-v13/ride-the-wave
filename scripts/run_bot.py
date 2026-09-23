"""Run the paper-trading bot for one session.

uv run python scripts/run_bot.py            # waits for the open if the market is closed
uv run python scripts/run_bot.py --no-wait  # exit immediately if the market is closed
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.runner import BotRunner
from ridethewave.storage import Database


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", default=None, help="path to settings.yaml")
    ap.add_argument("--no-wait", action="store_true", help="exit if the market is closed instead of waiting")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="start everything, run one tick, exit; no waiting, no ledger. Validates a deploy",
    )
    args = ap.parse_args()

    settings = load_settings(args.settings)
    log_dir = settings.storage.resolved_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(log_dir / f"bot-{datetime.now():%Y%m%d}.log", rotation="1 day", retention="30 days", level="DEBUG")

    clients = make_clients(load_secrets(), settings)
    db = Database(settings.storage.resolved_db_path())
    try:
        BotRunner(settings, clients, db, wait_for_open=not args.no_wait).run(dry_run=args.dry_run)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
