from datetime import datetime
from zoneinfo import ZoneInfo

from ridethewave.operator.dispatch import due_tasks

ET = ZoneInfo("America/New_York")
TIMES = ["09:00", "11:30", "14:00", "16:15", "21:00"]


def at(h, m, day=22):
    return datetime(2026, 9, day, h, m, tzinfo=ET)


def names(dt, done=frozenset()):
    return sorted(t.name for t in due_tasks(dt, set(done), TIMES))


def test_due_only_after_time_and_once():
    assert names(at(8, 59)) == []
    assert names(at(9, 2)) == ["report-premarket"]
    assert names(at(9, 2), {"report-premarket"}) == []
    # two hours late (Mac was asleep) still runs
    assert names(at(11, 0)) == ["report-premarket"]
    assert names(at(14, 30)) == ["report-midday", "report-morning"]


def test_stale_tasks_are_skipped():
    # at 22:00 the close report (16:15) is more than four hours old and is skipped; nightly and research run
    assert names(at(22, 0)) == ["nightly", "report-research"]
    assert names(at(1, 0, day=23)) == []


def test_weekend_runs_nothing():
    assert names(at(10, 0, day=26)) == []  # Saturday
