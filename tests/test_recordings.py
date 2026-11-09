"""Daily recordings (feature 25): which expiries, what a row holds, files never half-written or replaced."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pandas as pd

from ridethewave.data.assets import AssetInfo
from ridethewave.data.recordings import (
    asset_frame,
    contract_rows,
    fetch_chain,
    monthly_expiries,
    option_frame,
    third_friday,
    write_day,
)

TS = datetime(2026, 11, 9, 20, 45, tzinfo=timezone.utc)


def snap(bid=1.0, ask=1.2, iv=0.3, delta=0.5):
    quote = SimpleNamespace(bid_price=bid, ask_price=ask, bid_size=10, ask_size=12, timestamp=TS)
    greeks = None if delta is None else SimpleNamespace(delta=delta, gamma=0.01, theta=-0.02, vega=0.1, rho=0.03)
    return SimpleNamespace(latest_quote=quote, latest_trade=None, implied_volatility=iv, greeks=greeks)


class FakeOptions:
    """Answers a chain request from a table keyed by (underlying, expiry)."""

    def __init__(self, chains: dict):
        self.chains = chains
        self.asked: list[tuple[str, date]] = []

    def get_option_chain(self, req):
        self.asked.append((req.underlying_symbol, req.expiration_date))
        if req.underlying_symbol == "BAD":
            raise RuntimeError("boom")
        return self.chains.get((req.underlying_symbol, req.expiration_date), {})


def test_the_next_two_monthly_expiries_at_least_a_week_away():
    assert third_friday(2026, 11) == date(2026, 11, 20) and third_friday(2027, 1) == date(2027, 1, 15)
    assert monthly_expiries(date(2026, 11, 9)) == [date(2026, 11, 20), date(2026, 12, 18)]
    # six days before the November expiry it is skipped; the pair runs over the year end
    assert monthly_expiries(date(2026, 11, 14)) == [date(2026, 12, 18), date(2027, 1, 15)]


def test_a_row_keeps_what_the_feed_sent_and_leaves_gaps_empty():
    raw = {
        "AAPL261218C00350000": snap(),
        "AAPL261218P00300000": snap(bid=0.0, iv=None, delta=None),  # no bid, no implied volatility, no greeks
        "not-an-option": snap(),
    }
    rows = {r["symbol"]: r for r in contract_rows("AAPL", 347.2, raw)}
    assert set(rows) == {"AAPL261218C00350000", "AAPL261218P00300000"}
    call, put = rows["AAPL261218C00350000"], rows["AAPL261218P00300000"]
    assert (call["expiry"], call["right"], call["strike"], call["spot"]) == ("2026-12-18", "C", 350.0, 347.2)
    assert (call["bid"], call["ask"], call["iv"], call["delta"], call["quote_ts"]) == (1.0, 1.2, 0.3, 0.5, TS)
    assert put["bid"] == 0.0 and put["iv"] is None and put["delta"] is None and put["last"] is None


def test_a_holiday_friday_falls_back_to_the_thursday():
    thursday = {"XYZ270325C00050000": snap()}  # Good Friday 2027 is 26 March: not a third Friday, but the same rule
    client = FakeOptions({("XYZ", date(2027, 3, 25)): thursday})
    assert fetch_chain(client, "XYZ", 50.0, date(2027, 3, 26)) == thursday
    assert client.asked == [("XYZ", date(2027, 3, 26)), ("XYZ", date(2027, 3, 25))]
    assert fetch_chain(client, "NONE", 50.0, date(2027, 3, 26)) == {}


def test_one_failing_name_does_not_lose_the_others():
    today = date(2026, 11, 9)
    client = FakeOptions(
        {
            ("AAA", date(2026, 11, 20)): {"AAA261120C00010000": snap()},
            ("AAA", date(2026, 12, 18)): {"AAA261218P00010000": snap(iv=None)},
            ("NOIV", date(2026, 11, 20)): {"NOIV261120C00010000": snap(iv=None)},
        }
    )
    frame, stats = option_frame(client, {"AAA": 10.0, "BAD": 5.0, "NOIV": 10.0, "EMPTY": 7.0}, today, market_open=True)
    assert stats["asked"] == 4 and stats["failed"] == 1 and stats["with_contracts"] == 2 and stats["with_iv"] == 1
    assert stats["contracts"] == 3 and stats["expiries"] == ["2026-11-20", "2026-12-18"]
    assert (
        set(frame["underlying"]) == {"AAA", "NOIV"}
        and frame["market_open"].all()
        and (frame["day"] == "2026-11-09").all()
    )


def test_a_recorded_day_is_not_replaced_unless_forced(tmp_path):
    first = pd.DataFrame({"symbol": ["A"], "iv": [0.2]})
    path = write_day(first, "options", "2026-11-09", root=tmp_path)
    assert path == tmp_path / "options" / "2026-11-09.parquet" and not path.with_suffix(".tmp").exists()
    later = pd.DataFrame({"symbol": ["A"], "iv": [9.9]})  # a late re-run with stale quotes
    assert write_day(later, "options", "2026-11-09", root=tmp_path) is None
    assert pd.read_parquet(path)["iv"].tolist() == [0.2]
    assert write_day(later, "options", "2026-11-09", root=tmp_path, force=True) == path
    assert pd.read_parquet(path)["iv"].tolist() == [9.9]


def test_borrow_flags_one_row_per_symbol():
    def asset(sym, shortable, etb):
        return AssetInfo(sym, None, "NASDAQ", "active", "us_equity", True, True, shortable, etb, False)

    frame = asset_frame([asset("ZZZ", True, True), asset("ONDS", False, False)], "2026-11-09")
    assert frame["symbol"].tolist() == ["ONDS", "ZZZ"] and frame["day"].eq("2026-11-09").all()
    assert frame.set_index("symbol").loc["ONDS", ["shortable", "easy_to_borrow"]].tolist() == [False, False]


def test_opening_auction_prices_come_from_the_largest_print_and_a_failure_loses_nothing_else():
    from ridethewave.data.market_data import opening_auctions

    class Client:
        def __init__(self):
            self.asked = []

        def get(self, path, params):
            self.asked.append((path, params["symbols"], params["start"], params["end"]))
            if "BAD" in params["symbols"]:
                raise RuntimeError("boom")
            return {"auctions": {"F": [{"d": "2025-04-09", "o": [{"p": 8.54, "s": 1}, {"p": 8.5, "s": 1888347}]}],
                                 "SPY": [{"d": "2025-04-09", "o": None}], "NONE": []}}  # fmt: skip

    client = Client()
    assert opening_auctions(client, ["F", "SPY", "NONE"], date(2025, 4, 9)) == {"F": 8.5}  # no print: left out
    assert client.asked == [("/stocks/auctions", "F,NONE,SPY", "2025-04-09", "2025-04-09")]
    assert opening_auctions(Client(), ["BAD"], date(2025, 4, 9)) == {}
