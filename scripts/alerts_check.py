"""Health check for market hours. Scheduled every 5 minutes by launchd.

Notifies (macOS) only when something is wrong, and only once per distinct alert per day.
    uv run python scripts/alerts_check.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ridethewave.config import load_settings
from ridethewave.operator.notify import notify
from ridethewave.operator.reports import check_alerts
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")


def main() -> int:
    settings = load_settings()
    db = Database(settings.storage.resolved_db_path())
    alerts = check_alerts(db, settings)
    day = datetime.now(ET).strftime("%Y-%m-%d")
    seen = db.state.get("alerts_seen", {}) or {}
    todays = set(seen.get(day, []))
    new = [a for a in alerts if a.split(":")[0] not in todays]
    for a in new:
        print("ALERT:", a)
        notify("Ride The Wave ALERT", a, settings.operator.notify)
        todays.add(a.split(":")[0])
    db.state.set("alerts_seen", {day: sorted(todays)})
    db.state.set("last_health_check", {"at": datetime.now(timezone.utc).isoformat(), "alerts": alerts})
    if not alerts:
        print("healthy")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
