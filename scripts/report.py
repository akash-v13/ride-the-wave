"""Write a check-in page. Scheduled by launchd; also fine by hand.

uv run python scripts/report.py premarket|morning|midday|close|research
-> data/reports/<date>/<HHMM>-<kind>.md and data/reports/latest.md
"""

from __future__ import annotations

import argparse
import sys

from ridethewave.config import load_settings
from ridethewave.operator.notify import notify
from ridethewave.operator.reports import check_alerts, write_report
from ridethewave.storage import Database


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["premarket", "morning", "midday", "close", "research"])
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args()
    settings = load_settings()
    db = Database(settings.storage.resolved_db_path())
    path = write_report(args.kind, db, settings)
    alerts = check_alerts(db, settings)
    print(f"wrote {path}")
    if alerts:
        print("ALERTS:", *alerts, sep="\n  ")
    if not args.no_notify:
        notify(
            "Ride The Wave",
            f"{args.kind} report ready" + (f" ({len(alerts)} alert(s))" if alerts else ""),
            settings.operator.notify,
        )
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
