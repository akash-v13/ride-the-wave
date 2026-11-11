"""Earnings report days from SEC 8-K item 2.02 filings (signal B)."""

from datetime import datetime, timezone

import pandas as pd

from ridethewave.data.edgar import earnings_filings, last_of_each_cluster, reaction_day

SESSIONS = pd.bdate_range("2026-10-26", "2026-11-13")  # weekdays stand in for sessions


def test_only_8k_filings_with_item_2_02_are_kept():
    recent = {
        "form": ["8-K", "8-K", "10-Q", "8-K/A", "8-K"],
        "items": ["2.02,9.01", "5.02", "", "2.02", "7.01, 2.02"],
        "acceptanceDateTime": ["2026-11-02T21:30:23.000Z", "2026-10-01T12:00:00.000Z", "2026-11-03T10:00:00.000Z",
                               "2026-11-05T21:00:00.000Z", "2026-07-30T20:30:36.000Z"],
    }  # fmt: skip
    got = earnings_filings(recent)
    assert got == [
        datetime(2026, 11, 2, 21, 30, 23, tzinfo=timezone.utc),
        datetime(2026, 7, 30, 20, 30, 36, tzinfo=timezone.utc),
    ]
    assert earnings_filings({}) == []


def test_the_reaction_day_depends_on_the_new_york_time_of_the_filing():
    def day(utc):
        return reaction_day(datetime.fromisoformat(utc).replace(tzinfo=timezone.utc), SESSIONS)

    assert day("2026-11-02T21:30:23") == pd.Timestamp("2026-11-03")  # 16:30 Monday: Tuesday reacts
    assert day("2026-11-03T12:00:00") == pd.Timestamp("2026-11-03")  # 07:00 Tuesday, before the open
    assert day("2026-11-03T19:00:00") == pd.Timestamp("2026-11-03")  # 14:00 Tuesday, during the day
    assert day("2026-10-30T20:05:00") == pd.Timestamp("2026-11-02")  # 16:05 on a Friday in summer time
    assert day("2026-11-07T15:00:00") == pd.Timestamp("2026-11-09")  # a Saturday
    assert day("2026-11-13T22:00:00") is None  # after the last session we have


def test_one_report_per_quarter_keeps_the_last_filing_of_a_cluster():
    d = [pd.Timestamp(x) for x in ("2026-01-12", "2026-02-03", "2026-05-05", "2026-07-20", "2026-08-04", "2026-11-03")]
    assert last_of_each_cluster(d) == [
        pd.Timestamp(x) for x in ("2026-02-03", "2026-05-05", "2026-08-04", "2026-11-03")
    ]
    assert last_of_each_cluster([]) == []
