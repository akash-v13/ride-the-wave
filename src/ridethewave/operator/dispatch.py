"""Time-of-day dispatch that does not trust the scheduler's clock.

launchd fires calendar jobs in the timezone it booted with; on this machine that was two hours off
after a timezone change. An interval job runs this every five minutes; it reads Eastern time itself
and runs whichever scheduled tasks are due and not yet done today. Pure decision logic here; the
script does the running.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
LATE_WINDOW = timedelta(hours=4)  # a task missed by more than this (Mac asleep) is skipped, not run late


@dataclass(frozen=True, slots=True)
class Task:
    name: str  # key recorded in bot_state
    at: time  # ET
    command: list[str]  # relative to the project root, run with the venv python


def daily_tasks(report_times: list[str]) -> list[Task]:
    kinds = ["premarket", "morning", "midday", "close", "research"]
    tasks = []
    for kind, hhmm in zip(kinds, report_times, strict=True):
        hh, mm = hhmm.split(":")
        tasks.append(Task(f"report-{kind}", time(int(hh), int(mm)), ["scripts/report.py", kind]))
    tasks.append(Task("nightly", time(20, 30), ["scripts/nightly.py"]))
    return tasks


def due_tasks(now_utc: datetime, done_today: set[str], report_times: list[str]) -> list[Task]:
    et = now_utc.astimezone(ET)
    if et.weekday() >= 5:
        return []
    out = []
    for t in daily_tasks(report_times):
        if t.name in done_today:
            continue
        scheduled = et.replace(hour=t.at.hour, minute=t.at.minute, second=0, microsecond=0)
        if scheduled <= et <= scheduled + LATE_WINDOW:
            out.append(t)
    return out
