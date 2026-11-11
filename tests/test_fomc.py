"""Scheduled Fed announcement dates parsed from the Fed's pages (signal E)."""

from datetime import date

from ridethewave.data.fomc import load, parse_calendar_page, parse_heading


def test_headings_give_the_meetings_last_day_and_skip_what_was_not_scheduled():
    assert parse_heading("June 29-30 Meeting - 2005") == date(2005, 6, 30)
    assert parse_heading("March 22 Meeting - 2005") == date(2005, 3, 22)
    assert parse_heading("January 31-February 1 Meeting - 1995") == date(1995, 2, 1)
    assert parse_heading("July 31-August 1  Meeting - 2012") == date(2012, 8, 1)
    assert parse_heading("Jan/Feb 31-1 Meeting - 2017") == date(2017, 2, 1)
    assert parse_heading("April/May 30-1 Meeting - 2013") == date(2013, 5, 1)
    for skipped in (
        "January 21 Conference Call - 2008",
        "March 15 (unscheduled) Meeting - 2020",
        "March 17-18 (cancelled) Meeting - 2020",
        "March 19 (notation vote) - 2020",
        "October 16 (unscheduled) - 2013",
    ):
        assert parse_heading(skipped) is None


def test_the_calendar_page_is_read_by_year_month_and_day_range():
    row = (
        '<div class="row fomc-meeting"><div class="fomc-meeting__month col-xs-5"><strong>{m}</strong></div>'
        '<div class="fomc-meeting__date col-xs-4">{d}</div></div>'
    )
    html = (
        "<h4>2026 FOMC Meetings</h4>" + row.format(m="January", d="27-28") + row.format(m="March", d="17-18*")
        + row.format(m="Apr/May", d="30-1") + row.format(m="August", d="22 (notation vote)")
        + "<h4>2025 FOMC Meetings</h4>" + row.format(m="December", d="9-10*")
    )  # fmt: skip
    assert parse_calendar_page(html) == [date(2025, 12, 10), date(2026, 1, 28), date(2026, 3, 18), date(2026, 5, 1)]


def test_the_saved_list_is_complete():
    dates = load()
    assert dates == sorted(set(dates)) and dates[0] == date(1994, 2, 4)
    per_year = {y: sum(d.year == y for d in dates) for y in range(1994, 2027)}
    assert {y: n for y, n in per_year.items() if n != 8} == {2020: 7}  # March 2020's meeting was cancelled
    assert date(2008, 10, 29) in dates and date(2003, 9, 16) in dates and date(2003, 9, 15) not in dates
    assert date(2008, 1, 22) not in dates and date(2020, 3, 15) not in dates  # emergency cuts
    assert all(d.weekday() < 5 for d in dates)
