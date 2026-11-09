"""The delisting record: Massive's list read once, our own record from daily asset lists, and renames."""

import pandas as pd

from ridethewave.data import delistings
from ridethewave.data.delistings import left_the_list, massive_delisted, renamed


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        assert self.status_code == 200


class FakeSession:
    """Two pages for common stocks (the second after one refusal for going too fast), none for ADRs."""

    def __init__(self):
        self.headers, self.calls = {}, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if params and params["type"] == "ADRC":
            return FakeResponse(200, {"results": []})
        if params:
            first = {"ticker": "TWTR", "name": "Twitter, Inc.", "type": "CS", "primary_exchange": "XNYS",
                     "delisted_utc": "2022-10-31T04:00:00Z", "composite_figi": "BBG1", "cik": "1"}  # fmt: skip
            return FakeResponse(200, {"results": [first], "next_url": "https://api.massive.com/next?cursor=abc"})
        if sum(1 for u, _ in self.calls if "cursor" in u) == 1:
            return FakeResponse(429, {})
        second = {"ticker": "LNKD", "name": "LinkedIn", "type": "CS", "primary_exchange": "XNYS",
                  "delisted_utc": "2016-12-08T05:00:00Z"}  # fmt: skip
        return FakeResponse(200, {"results": [second]})


def test_massive_list_follows_pages_waits_out_a_refusal_and_keeps_the_key_in_a_header(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(delistings.requests, "Session", lambda: session)
    monkeypatch.setattr(delistings.time, "sleep", lambda s: None)
    frame = massive_delisted("secret-key")
    assert session.headers["Authorization"] == "Bearer secret-key"
    assert all("secret-key" not in u and "secret-key" not in str(p) for u, p in session.calls)
    assert frame["ticker"].tolist() == ["LNKD", "TWTR"] and frame["exchange"].tolist() == ["NYSE", "NYSE"]
    assert [str(d) for d in frame["delisted"]] == ["2016-12-08", "2022-10-31"]
    assert len(session.calls) == 4  # first page, the refused second page, the second page again, ADRs


def test_our_own_record_is_what_left_the_saved_asset_list():
    before = pd.DataFrame(
        {"symbol": ["AAA", "KVUE", "HALT"], "exchange": ["NYSE"] * 3, "tradable": [True, True, False]}
    )
    after = pd.DataFrame({"symbol": ["AAA", "NEW"], "exchange": ["NYSE"] * 2, "tradable": [True, True]})
    gone = left_the_list(before, after, "2026-11-10")
    # HALT was already untradable the day before, so it did not leave today
    assert gone.to_dict("records") == [{"symbol": "KVUE", "exchange": "NYSE", "gone_by": "2026-11-10"}]


def test_an_old_name_is_matched_to_the_company_the_panel_already_holds():
    days = pd.bdate_range("2022-06-01", periods=6)
    volume = [101, 202, 303, 404, 505, 606]
    panel = pd.DataFrame({"symbol": "META", "day": days, "volume": volume})
    other = pd.DataFrame({"symbol": "XYZ", "day": days, "volume": [7, 8, 9, 10, 11, 12]})
    panel = pd.concat([panel, other], ignore_index=True)
    old_name = pd.DataFrame({"symbol": "FB", "day": days, "volume": volume})
    different = pd.DataFrame({"symbol": "TWTR", "day": days, "volume": [1, 2, 3, 404, 5, 6]})  # one chance match
    short = pd.DataFrame({"symbol": "FEW", "day": days[:3], "volume": volume[:3]})  # too few days to judge
    cands = pd.concat([old_name, different, short], ignore_index=True)
    assert renamed(cands, panel) == {"FB": "META"}
