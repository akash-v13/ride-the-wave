"""The operator's five-minute tick: watchdog, health check, then any scheduled task that is due (Eastern time).

The watchdog starts the bot if the Mac restarted during a trading day or the 06:30 ET morning start did not run
(src/ridethewave/operator/watchdog.py), and sends a phone alert when it does.

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
from ridethewave.operator.notify import notify, ntfy_topic
from ridethewave.operator.watchdog import RESTARTED, run_watchdog
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
    # 1. watchdog: start the bot after a reboot or a missed morning start on a trading day. Never breaks the tick.
    restarted = False
    try:
        msg = run_watchdog(db, settings, now)
        if msg:
            logger.warning(msg)
            restarted = msg.startswith(RESTARTED)
            notify(
                "Ride The Wave",
                msg,
                settings.operator.notify,
                topic=ntfy_topic(),
                server=settings.operator.ntfy_server,
                tags="arrows_counterclockwise" if restarted else "warning",
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("watchdog failed: {}: {}", type(e).__name__, e)
    # 2. health check every tick, except right after a restart: the heartbeat is stale by definition then, and the
    # alert is sent only once a day, so raising it now would silence a real stale heartbeat later today.
    if restarted:
        logger.info("health check skipped this tick: the bot was just restarted")
    else:
        r = subprocess.run([sys.executable, "scripts/alerts_check.py"], cwd=PROJECT, capture_output=True, text=True)
        if r.returncode != 0:
            logger.warning("alerts_check failed: {}", (r.stderr or r.stdout)[-300:])
    # 3. due tasks
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
