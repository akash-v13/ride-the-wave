"""Nightly maintenance. Scheduled after the close by launchd.

1. Cache today's SIP session bars for the universe the bot used (so tomorrow's research is offline).
2. Export live feature rows to parquet.
3. Write the research digest page.

    uv run python scripts/nightly.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date

from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import HistoricalBars, regular_session_utc
from ridethewave.storage import Database


def main() -> int:
    settings = load_settings()
    db = Database(settings.storage.resolved_db_path())
    universe = db.state.get("universe", []) or []
    today = date.today()
    if universe and today.weekday() < 5:
        clients = make_clients(load_secrets(), settings)
        h = HistoricalBars(clients.data, db, feed="sip")
        s, e = regular_session_utc(today)
        bars = h.fetch(sorted(set(universe) | {"SPY"}), s, e)
        logger.info("cached {} SIP bars for {} symbols for {}", len(bars), len(universe) + 1, today)
    db.close()
    for cmd in (["scripts/export_live_features.py"], ["scripts/report.py", "research"]):
        r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
        logger.info(
            "{} -> {}",
            cmd[0],
            (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else r.returncode,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
