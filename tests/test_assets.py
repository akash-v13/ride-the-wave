"""Alpaca's asset list must load even when it carries an exchange code the SDK does not know."""

import pytest

from ridethewave.config import UniverseSettings
from ridethewave.data.assets import KNOWN_EXCHANGES, fetch_assets, parse_assets
from ridethewave.data.universe import UniverseBuilder

RAW = [
    {
        "symbol": "AAPL",
        "name": "Apple Inc. Common Stock",
        "exchange": "NASDAQ",
        "class": "us_equity",
        "status": "active",
        "tradable": True,
        "shortable": True,
        "easy_to_borrow": True,
        "fractionable": True,
        "marginable": True,
    },
    {
        "symbol": "TXS",
        "name": "Texas Capital Texas Equity Index ETF",
        "exchange": "TXSE",
        "class": "us_equity",
        "status": "active",
        "tradable": True,
    },
    {
        "symbol": "SOXL",
        "name": "Direxion Daily Semiconductor Bull 3X Shares",
        "exchange": "ARCA",
        "class": "us_equity",
        "status": "active",
        "tradable": True,
    },
    {
        "symbol": "HALT",
        "name": "Halted Corp",
        "exchange": "NYSE",
        "class": "us_equity",
        "status": "active",
        "tradable": False,
    },
    {"name": "row without a symbol"},
    "not even a dict",
]


class _Trading:
    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    def get(self, path, data=None):
        self.calls.append((path, data))
        return self.raw


def test_unknown_exchange_is_kept_and_bad_rows_are_skipped():
    assert "TXSE" not in KNOWN_EXCHANGES  # the reason this module exists (alpaca-py 0.44.0)
    assets = parse_assets(RAW)
    assert [a.symbol for a in assets] == ["AAPL", "TXS", "SOXL", "HALT"]
    txs = assets[1]
    assert txs.exchange == "TXSE" and txs.asset_class == "us_equity" and txs.shortable is False


def test_fetch_asks_the_assets_endpoint_with_filters():
    t = _Trading(RAW)
    assert len(fetch_assets(t, status="inactive")) == 4
    assert t.calls == [("/assets", {"status": "inactive", "asset_class": "us_equity"})]
    with pytest.raises(ValueError):
        parse_assets({"message": "forbidden"})


def test_universe_filters_work_on_the_raw_assets():
    clients = type("C", (), {"trading": _Trading(RAW)})()
    b = UniverseBuilder(clients, UniverseSettings(exchanges=["NASDAQ", "NYSE", "ARCA"]))
    assert b.filter_tradable(["AAPL", "TXS", "SOXL", "HALT", "MISSING"]) == ["AAPL", "SOXL"]
    assert b.fund_symbols(["AAPL", "SOXL", "TXS"]) == {"SOXL", "TXS"}
