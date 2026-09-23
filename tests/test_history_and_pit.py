from datetime import date, datetime, timedelta, timezone

import pandas as pd

from ridethewave.config import UniverseSettings
from ridethewave.data.market_data import HistoricalBars, regular_session_utc
from ridethewave.data.pit_universe import PointInTimeUniverse


class _Bar:
    def __init__(self, ts, c, v):
        self.timestamp, self.open, self.high, self.low, self.close, self.volume = ts, c, c, c, c, v
        self.trade_count, self.vwap = 1, c


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeDataClient:
    def __init__(self):
        self.requests = []

    def get_stock_bars(self, req):
        self.requests.append(req)
        t0 = datetime(2026, 9, 16, 13, 30, tzinfo=timezone.utc)
        return _Resp(
            {s: [_Bar(t0 + timedelta(minutes=i), 100 + i, 10) for i in range(3)] for s in req.symbol_or_symbols}
        )


def test_historical_bars_requests_unlimited_pages_and_caches(db):
    client = _FakeDataClient()
    h = HistoricalBars(client, db, feed="sip")
    s, e = regular_session_utc(date(2026, 9, 16))
    assert s.hour == 13 and s.minute == 30 and (e - s) == timedelta(hours=6, minutes=30)
    bars = h.fetch(["AAPL", "MSFT"], s, e)
    assert len(bars) == 6
    assert client.requests[0].limit is None  # a number would silently truncate multi-symbol days
    sent_end = client.requests[0].end.replace(tzinfo=timezone.utc)  # SDK stores naive UTC
    assert sent_end == e - timedelta(seconds=1)  # Alpaca's end is inclusive
    again = h.fetch(["AAPL", "MSFT"], s, e)
    assert len(again) == 6 and len(client.requests) == 1  # served from cache


def test_pit_universe_ranks_by_trailing_dollar_volume():
    pit = PointInTimeUniverse.__new__(PointInTimeUniverse)
    pit.cfg = UniverseSettings(min_price=5, max_price=500)
    pit.lookback = 3
    days = [date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15), date(2026, 9, 16)]
    rows = []
    for d in days:
        rows += [
            ("BIG", d, 100.0, 1_000_000),
            ("MID", d, 50.0, 500_000),
            ("PENNY", d, 1.0, 900_000_000),
            ("PRICEY", d, 900.0, 1_000_000),
        ]
    rows += [("NEWLISTING", date(2026, 9, 16), 20.0, 50_000_000)]  # only one session: excluded
    pit._frame = pd.DataFrame(rows, columns=["symbol", "day", "close", "volume"])
    pit._frame["dollar_volume"] = pit._frame["close"] * pit._frame["volume"]
    pit._loaded = (days[0], days[-1])
    # universe for 9/16 must only use sessions before 9/16 and rank BIG (100M) above MID (25M)
    assert pit.universe_for(date(2026, 9, 16), top=5) == ["BIG", "MID"]
    assert pit.universe_for(date(2026, 9, 16), top=1) == ["BIG"]
