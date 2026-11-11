"""Scheduled Federal Reserve (FOMC) announcement dates, read from the Fed's own pages (2026-11-10).

Why: signal E of the shortlist holds the index over the day of each **scheduled** announcement
(docs/research/2026-11-10-signals-e-b-f.md). The dates are public and fixed about a year ahead. They
are kept in the repository as config/calendars/fomc_scheduled.csv, built by
scripts/build_fomc_dates.py from two kinds of page on federalreserve.gov:
- one historical page per year (1994 to about five years ago), where each meeting is a heading such
  as "June 29-30 Meeting - 2005";
- the current calendar page (the last few years and the next), where each meeting is a month and a
  day range.

The announcement comes on a meeting's **last** day. Conference calls, unscheduled meetings, cancelled
meetings and notation votes are left out: the published effect is for scheduled meetings only, and an
unscheduled one cannot be traded in advance. Parsing is pure; only ``load`` reads a file.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

CSV = Path(__file__).resolve().parents[3] / "config" / "calendars" / "fomc_scheduled.csv"
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}  # fmt: skip
_SKIP = ("conference call", "unscheduled", "cancelled", "canceled", "notation vote")


def _month(text: str) -> int | None:
    t = text.strip().lower().rstrip(".")
    hits = [i for m, i in _MONTHS.items() if m.startswith(t) and len(t) >= 3]
    return hits[0] if len(hits) == 1 else None


def last_day(months: str, days: str, year: int) -> date | None:
    """The last day of a meeting from its month text and day text.

    Handles "June" + "29-30", "March" + "22", "June 30-July 1" given as ("June", "30-July 1"), and the
    Fed's short form for a meeting across a month end, "Jan/Feb" + "31-1"."""
    days = days.replace("*", "").strip()
    month_names = [m for m in re.split(r"[/\s]+", months.strip()) if m]
    nums = re.findall(r"\d+", days)
    inner = re.search(r"-\s*([A-Za-z]+)\s+(\d+)", days)  # "30-July 1"
    if not nums or not month_names:
        return None
    try:
        if inner:
            return date(year, _month(inner.group(1)), int(inner.group(2)))
        return date(year, _month(month_names[-1]), int(nums[-1]))
    except (TypeError, ValueError):
        return None


def parse_heading(text: str) -> date | None:
    """A historical page's heading, such as "January 31-February 1 Meeting - 1995". None for anything
    that is not a scheduled meeting."""
    t = re.sub(r"\s+", " ", text).strip()
    if any(w in t.lower() for w in _SKIP) or "meeting" not in t.lower():
        return None
    m = re.match(r"^([A-Za-z/]+)\s+(.+?)\s+Meeting\s*-\s*(\d{4})$", t)
    return last_day(m.group(1), m.group(2), int(m.group(3))) if m else None


def parse_historical_page(html: str) -> list[date]:
    found = (parse_heading(re.sub(r"<[^>]+>", "", h)) for h in re.findall(r"<h5[^>]*>.*?</h5>", html, flags=re.S))
    return sorted(d for d in found if d)


def parse_calendar_page(html: str) -> list[date]:
    """The current calendar page: a heading "YYYY FOMC Meetings", then one row per meeting holding a
    month and a day range. Rows marked unscheduled, cancelled or as a notation vote are left out."""
    out: list[date] = []
    parts = re.split(r"(\d{4}) FOMC Meetings", html)
    for year, block in zip(parts[1::2], parts[2::2], strict=False):
        rows = re.findall(
            r"fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>\s*</div>\s*"
            r'<div class="fomc-meeting__date[^>]*>([^<]+)<',
            block,
        )
        for months, days in rows:
            if any(w in days.lower() for w in _SKIP):
                continue
            d = last_day(months, days, int(year))
            if d:
                out.append(d)
    return sorted(set(out))


def load(path: Path | None = None) -> list[date]:
    """The saved dates, oldest first."""
    lines = (path or CSV).read_text().splitlines()
    return sorted(date.fromisoformat(x.strip()) for x in lines[1:] if x.strip())
