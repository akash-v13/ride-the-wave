"""The operator's five-minute tick: health check, then any scheduled task that is due (in Eastern time).

Scheduled by launchd as an interval job, so it is immune to launchd's timezone. Marks each task done
for the day in bot_state so nothing runs twice.
    uv run python scripts/operator_tick.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger

from ridethewave.config import load_settings
from ridethewave.operator.dispatch import due_tasks
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")
PROJECT = Path(__file__).resolve().parents[1]


def main() -> int:
    settings = load_settings()
    db = Database(settings.storage.resolved_db_path())
    now = datetime.now(timezone.utc)
    day = now.astimezone(ET).strftime("%Y-%m-%d")
    state = db.state.get("operator_done", {}) or {}
    done = set(state.get(day, []))
    # 1. health check every tick
    r = subprocess.run([sys.executable, "scripts/alerts_check.py"], cwd=PROJECT, capture_output=True, text=True)
    if r.returncode != 0:
        logger.warning("alerts_check failed: {}", (r.stderr or r.stdout)[-300:])
    # 2. due tasks
    for task in due_tasks(now, done, settings.operator.report_times_et):
        logger.info(
            "running {} (due {} ET, now {} ET)",
            task.name,
            task.at.strftime("%H:%M"),
            now.astimezone(ET).strftime("%H:%M"),
        )
        r = subprocess.run([sys.executable, *task.command], cwd=PROJECT, capture_output=True, text=True)
        tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
        logger.info("{} -> exit {} {}", task.name, r.returncode, tail[0][:160])
        done.add(task.name)
        db.state.set("operator_done", {day: sorted(done)})
    db.state.set("operator_tick", {"at": now.isoformat(), "done_today": sorted(done)})
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
