"""Build config/calendars/fomc_scheduled.csv: every scheduled Fed announcement date from 1994 on.

Read from the Fed's own pages (see ridethewave.data.fomc for what is kept and why). Run it once a year,
when the Fed publishes the next year's meetings, or whenever the list looks short.

    uv run python scripts/build_fomc_dates.py                 # fetch from federalreserve.gov
    uv run python scripts/build_fomc_dates.py --pages DIR     # parse pages already saved in DIR
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from loguru import logger

from ridethewave.data.fomc import CSV, parse_calendar_page, parse_historical_page

BASE = "https://www.federalreserve.gov/monetarypolicy/"
FIRST_YEAR = 1994


def get(name: str, pages: Path | None) -> str | None:
    """One page's HTML, from ``pages`` when given (files named h1994.htm ... and cal.htm), else from the site."""
    if pages is not None:
        f = pages / ("cal.htm" if name == "fomccalendars.htm" else f"h{name[len('fomchistorical') : -4]}.htm")
        return f.read_text(encoding="utf-8", errors="replace") if f.exists() else None
    try:
        req = urllib.request.Request(BASE + name, headers={"User-Agent": "ridethewave-research/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed https URL
            time.sleep(1.0)
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 - a year with no historical page yet is expected
        logger.debug("{}: {}", name, e)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=Path, default=None)
    args = ap.parse_args()
    dates: set[date] = set()
    cal = get("fomccalendars.htm", args.pages)
    if cal is None:
        raise SystemExit("the calendar page could not be read")
    dates.update(parse_calendar_page(cal))
    first_on_calendar = min(d.year for d in dates)
    for year in range(FIRST_YEAR, first_on_calendar):
        html = get(f"fomchistorical{year}.htm", args.pages)
        if html is None or "Page not found" in html[:3000]:
            raise SystemExit(f"no page for {year}; the list would have a hole")
        got = [d for d in parse_historical_page(html) if d.year == year]
        dates.update(got)
    # 2003 lists a one-day session on 15 September before the scheduled meeting of the 16th: where two
    # dates are a day apart, the announcement came on the second.
    dates = {d for d in dates if d + timedelta(days=1) not in dates}
    per_year = Counter(d.year for d in dates)
    odd = {y: n for y, n in sorted(per_year.items()) if n != 8}
    logger.info("{} scheduled announcements, {} to {}", len(dates), min(dates), max(dates))
    if odd:
        logger.warning("years without exactly eight: {}", odd)
    CSV.parent.mkdir(parents=True, exist_ok=True)
    CSV.write_text("date\n" + "\n".join(d.isoformat() for d in sorted(dates)) + "\n")
    logger.info("saved to {}", CSV)
    return 0


if __name__ == "__main__":
    sys.exit(main())
