"""Earnings report dates from the SEC's EDGAR filings (2026-11-10).

Why: signal B trades in the days before a company reports, so it needs each report's date and whether it
came before the open or after the close (docs/research/2026-11-11-signals-b-g.md). Alpaca has no earnings
calendar. A company that publishes results must furnish them to the SEC on form 8-K under item 2.02,
"Results of Operations and Financial Condition", and EDGAR records the minute it accepted the filing.
That is the official record, it is free, and it is open to scripts that say who they are.

- ``earnings_filings`` picks those filings out of one company's submissions file (pure).
- ``reaction_day`` turns an acceptance time into the first session that could trade on the news (pure).
- ``fetch_submissions`` is the only network call. The SEC asks every automated reader to identify itself
  in the User-Agent; the contact line comes from ``SEC_CONTACT`` in ``.env`` and is never written to
  code, logs or docs.

Limits: the filing can follow the press release by minutes or hours (rarely a day), so a reaction day
can be late, never early. Item 2.02 also covers preliminary results, so not every filing is a scheduled
quarterly report. Prices still come from Alpaca; this is reference data.
"""

from __future__ import annotations

import json
import time as _time
import urllib.request
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
SUBMISSIONS = "https://data.sec.gov/submissions/{name}"
CLOSE = time(16, 0)


def earnings_filings(recent: dict) -> list[datetime]:
    """Acceptance times (UTC) of the 8-K filings with item 2.02 in one block of a submissions file
    (``filings.recent``, or an older ``CIK...-submissions-NNN.json`` file, which has the same columns).
    Amendments (8-K/A) are left out: they correct a report already made."""
    out = []
    for form, items, accepted in zip(
        recent.get("form", []), recent.get("items", []), recent.get("acceptanceDateTime", []), strict=False
    ):
        if form == "8-K" and "2.02" in [x.strip() for x in (items or "").split(",")] and accepted:
            out.append(datetime.fromisoformat(accepted.replace("Z", "+00:00")).astimezone(timezone.utc))
    return out


def reaction_day(accepted: datetime, sessions: pd.DatetimeIndex) -> pd.Timestamp | None:
    """The first session whose trading could react to a filing accepted at ``accepted``.

    Accepted before 16:00 New York time on a session day: that day (a report before the open moves the
    open; one during the day moves the rest of it). At or after 16:00, or on a day the market is shut:
    the next session. None when that is beyond ``sessions``."""
    local = accepted.astimezone(ET)
    day = pd.Timestamp(local.date())
    i = sessions.searchsorted(day, side="left")
    if i < len(sessions) and sessions[i] == day and local.time() >= CLOSE:
        i += 1
    return sessions[i] if i < len(sessions) else None


def last_of_each_cluster(days: list[pd.Timestamp], gap_days: int = 45) -> list[pd.Timestamp]:
    """One report per quarter. When a company filed item 2.02 more than once within ``gap_days``, the
    last filing is kept: an earlier one is usually a preliminary announcement, which nobody could have
    traded ahead of. A company that files monthly figures this way chains into one long cluster and
    keeps a single date, which loses its reports but never invents one."""
    out: list[pd.Timestamp] = []
    for d in sorted(set(days)):
        if out and (d - out[-1]).days <= gap_days:
            out[-1] = d
        else:
            out.append(d)
    return out


def fetch_submissions(name: str, contact: str, tries: int = 4) -> dict | None:
    """One submissions file from data.sec.gov (``CIK0000320193.json`` or an older-filings file named in
    it). None when it does not exist or every try failed."""
    req = urllib.request.Request(
        SUBMISSIONS.format(name=name), headers={"User-Agent": f"RideTheWave research ({contact})"}
    )
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed https host
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            _time.sleep(2.0 * (k + 1))
        except Exception:  # noqa: BLE001
            _time.sleep(2.0 * (k + 1))
    return None
