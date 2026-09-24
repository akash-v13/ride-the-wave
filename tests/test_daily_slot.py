"""Daily portfolio slot: signed positions, overnight persistence, round trips, ledger."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ridethewave.config import PortfolioSpec, Settings
from ridethewave.daily.data import Panel
from ridethewave.daily.strategies import DailyStrategy, Window
from ridethewave.portfolio.daily_slot import DailySlot

NOW = datetime(2026, 9, 24, 19, 50, tzinfo=timezone.utc)


class Fixed(DailyStrategy):
    name = "fixed"

    def __init__(self, targets):
        super().__init__({})
        self._t = targets

    def targets(self, w: Window):
        return dict(self._t)


def panel(n=30):
    days = pd.bdate_range("2026-08-10", periods=n)
    c = pd.DataFrame(
        {"AAA": np.linspace(100, 110, n), "BBB": np.linspace(50, 45, n), "SPY": np.linspace(500, 505, n)}, index=days
    )
    return Panel(open=c, high=c * 1.01, low=c * 0.99, close=c, volume=c * 0 + 1e6)


def test_long_short_fills_persist_and_flip(db):
    spec = PortfolioSpec(id="pf", kind="price_momentum", universe="AAA,BBB", slippage_bps=10)
    slot = DailySlot(spec, Fixed({"AAA": 0.5, "BBB": -0.5}), db, "live", capital=10_000)
    fills = slot.decide(panel(), {"AAA": 110.0, "BBB": 45.0, "SPY": 505.0}, NOW, ["AAA", "BBB"])
    assert {f["symbol"]: f["qty"] for f in fills} == {"AAA": 45, "BBB": -111}
    assert slot.positions["BBB"].qty == -111 and abs(slot.positions["BBB"].entry_price - 45 * 0.999) < 1e-9
    assert abs(slot.positions["AAA"].entry_price - 110 * 1.001) < 1e-9
    assert abs(slot.mark({"AAA": 110.0, "BBB": 45.0}) - (10_000 - 45 * 0.11 - 111 * 0.045)) < 0.05  # only slippage lost
    rows = {r["symbol"]: r["qty"] for r in db.positions.all_rows()}
    assert rows == {"AAA": 45.0, "BBB": -111.0}
    # a new slot resumes from the database
    again = DailySlot(spec, Fixed({}), db, "live", capital=10_000)
    again.load()
    assert (
        set(again.positions) == {"AAA", "BBB"}
        and abs(again.cash - slot.cash) < 1e-9
        and again.decided_on == "2026-09-18"
    )
    # prices move: the short gains, then flip both sides -> two closed trades with correctly signed P&L
    slot2 = DailySlot(spec, Fixed({"AAA": -0.3, "BBB": 0.3}), db, "live", capital=10_000)
    slot2.load()
    fills2 = slot2.rebalance({"AAA": -0.3, "BBB": 0.3}, {"AAA": 100.0, "BBB": 40.0}, NOW)
    closed = {t.symbol: t for t in slot2.trades_today}
    assert closed["BBB"].pnl > 0 and closed["BBB"].pnl_pct > 0 and closed["AAA"].pnl < 0 and closed["AAA"].pnl_pct < 0
    assert slot2.positions["AAA"].qty < 0 and slot2.positions["BBB"].qty > 0
    assert len(db.trades.recent(10, "shadow", "pf")) == 2
    assert any(f["symbol"] == "AAA" and f["qty"] < -45 for f in fills2)


def test_dead_band_and_ledger(db):
    spec = PortfolioSpec(id="pf2", kind="price_momentum", universe="AAA")
    slot = DailySlot(spec, Fixed({"AAA": 1.0}), db, "live", capital=10_000)
    slot.decide(panel(), {"AAA": 50.0}, NOW, ["AAA"])
    n = slot.positions["AAA"].qty
    assert n == 200
    # a 0.5% drift in price changes the target by one share ($50): below the 1% dead band ($100) -> no fill
    assert slot.rebalance({"AAA": 1.0}, {"AAA": 50.25}, NOW) == []
    assert slot.positions["AAA"].qty == n
    # closing entirely always goes through
    assert slot.rebalance({}, {"AAA": 51.0}, NOW)[0]["qty"] == -n
    led = slot.ledger("2026-09-24", None, Settings().capital)
    assert led.strategy == "pf2" and led.mode == "shadow" and led.trades == 1 and led.realized_pnl > 0
    assert led.extra["positions"] == 0 and led.next_allocation > 0


def test_settings_accept_portfolios_and_reject_duplicate_ids():
    s = Settings.model_validate(
        {"portfolios": [{"id": "pm", "kind": "price_momentum", "universe": "mega_caps_20", "weight": 0.5}]}
    )
    assert s.portfolios[0].decision_time.strftime("%H:%M") == "15:50" and s.portfolios[0].mode == "shadow"
    import pytest

    with pytest.raises(ValueError):
        Settings.model_validate({"portfolios": [{"id": "wave_rider", "kind": "price_momentum"}]})
