"""Daily portfolio slot: signed positions, overnight persistence, round trips, ledger."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

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


def test_dead_band_comes_from_the_spec_so_many_small_names_can_add(db):
    # sa_volrev, 2026-11-04: a name in a second cohort goes from 0.4% to 0.8% of $500k, a $2,000 add.
    # The 1% default ($5,000) skipped it while the hedge was sized for both cohorts.
    prices = {"AAA": 50.0}
    for band, expected in ((1.0, 40), (0.1, 80)):
        spec = PortfolioSpec(
            id=f"pf_band_{band}", kind="price_momentum", universe="AAA", dead_band_pct=band, slippage_bps=0
        )
        slot = DailySlot(spec, Fixed({}), db, "live", capital=500_000)
        slot.rebalance({"AAA": 0.004}, prices, NOW)
        slot.rebalance({"AAA": 0.008}, prices, NOW)
        assert slot.positions["AAA"].qty == expected


def test_fills_are_stored_with_the_quote_standing_at_the_time(db):
    spec = PortfolioSpec(id="pfq", kind="price_momentum", universe="AAA,BBB", slippage_bps=5)
    slot = DailySlot(spec, Fixed({"AAA": 0.5, "BBB": -0.5}), db, "live", capital=10_000)
    quotes = {"AAA": (109.95, 110.05)}  # the snapshot had no quote for BBB
    slot.decide(panel(), {"AAA": 110.0, "BBB": 45.0}, NOW, ["AAA", "BBB"], quotes=quotes)
    rows = {r["symbol"]: r for r in db.fills.for_day("pfq", "2026-09-18")}
    a, b = rows["AAA"], rows["BBB"]
    assert a["qty"] == 45 and a["last"] == 110.0 and a["price"] == pytest.approx(110 * 1.0005)
    assert (a["bid"], a["ask"]) == (109.95, 110.05) and a["target"] == 0.5
    assert b["qty"] == -111 and b["bid"] is None and b["ask"] is None  # kept, with no quote


def test_a_failed_fill_record_never_stops_the_decision(db):
    spec = PortfolioSpec(id="pfx", kind="price_momentum", universe="AAA")
    slot = DailySlot(spec, Fixed({"AAA": 1.0}), db, "live", capital=10_000)

    def broken(rows):
        raise RuntimeError("disk full")

    db.fills.insert_many = broken
    fills = slot.decide(panel(), {"AAA": 50.0}, NOW, ["AAA"], quotes={"AAA": (49.99, 50.01)})
    assert len(fills) == 1 and slot.positions["AAA"].qty == 200
    assert {r["symbol"] for r in db.positions.all_rows()} == {"AAA"} and slot.decided_on == "2026-09-18"


def test_settings_accept_portfolios_and_reject_duplicate_ids():
    s = Settings.model_validate(
        {"portfolios": [{"id": "pm", "kind": "price_momentum", "universe": "mega_caps_20", "weight": 0.5}]}
    )
    assert s.portfolios[0].decision_time.strftime("%H:%M") == "15:50" and s.portfolios[0].mode == "shadow"
    import pytest

    with pytest.raises(ValueError):
        Settings.model_validate({"portfolios": [{"id": "wave_rider", "kind": "price_momentum"}]})


def test_rebalance_days_trades_only_every_n_sessions_and_survives_a_restart(db):
    spec = PortfolioSpec(id="tf", kind="trend_following", universe="AAA,BBB", rebalance_days=5)
    prices = {"AAA": 110.0, "BBB": 45.0}
    full = panel(30)
    slot = DailySlot(spec, Fixed({"AAA": 0.5}), db, "live", capital=10_000)
    assert slot.decide(Panel(**{k: getattr(full, k).iloc[:26] for k in ("open", "high", "low", "close", "volume")}),
                       prices, NOW, ["AAA", "BBB"])  # fmt: skip
    first = slot.rebalanced_on
    # one to four sessions later: hold (no fills) even though the strategy now wants something else
    later = DailySlot(spec, Fixed({"BBB": -0.5}), db, "live", capital=10_000)
    later.load()
    assert later.rebalanced_on == first
    for n in (27, 28, 29, 30):
        sub = Panel(**{k: getattr(full, k).iloc[:n] for k in ("open", "high", "low", "close", "volume")})
        fills = later.decide(sub, prices, NOW, ["AAA", "BBB"])
        assert fills == [] and set(later.positions) == {"AAA"} and later.decided_on == str(sub.dates[-1].date())
    # the fifth session after the last trade rebalances
    nxt = pd.bdate_range(full.dates[-1], periods=2)[1:]
    ext = {
        k: pd.concat([getattr(full, k), getattr(full, k).iloc[-1:].set_axis(nxt)])
        for k in ("open", "high", "low", "close", "volume")
    }
    fills = later.decide(Panel(**ext), prices, NOW, ["AAA", "BBB"])
    assert fills and "BBB" in later.positions and later.rebalanced_on == str(nxt[0].date())


def test_rebalance_days_default_still_trades_every_day(db):
    spec = PortfolioSpec(id="pd", kind="price_momentum", universe="AAA,BBB")
    slot = DailySlot(spec, Fixed({"AAA": 0.5}), db, "live", capital=10_000)
    p = panel(30)
    slot.decide(Panel(**{k: getattr(p, k).iloc[:29] for k in ("open", "high", "low", "close", "volume")}),
                {"AAA": 110.0}, NOW, ["AAA"])  # fmt: skip
    slot.strategy = Fixed({"AAA": 0.2})
    assert slot.decide(p, {"AAA": 110.0}, NOW, ["AAA"])  # the next session trades again


def test_a_slot_can_fill_at_the_opening_auction_and_size_on_yesterdays_close(db):
    spec = PortfolioSpec(id="pfa", kind="price_momentum", universe="AAA,BBB", slippage_bps=1, fill_at="open_auction")
    slot = DailySlot(spec, Fixed({"AAA": 0.5, "BBB": -0.5}), db, "live", capital=10_000)
    now_prices = {"AAA": 110.0, "BBB": 45.0}  # at 09:35
    fills_at = {"AAA": (108.0, "auction")}  # BBB has no auction print: it falls back to its current price
    sizes_at = {"AAA": 100.0, "BBB": 50.0}  # yesterday's closes
    slot.decide(panel(), now_prices, NOW, ["AAA", "BBB"], fills_at=fills_at, sizes_at=sizes_at)
    rows = {r["symbol"]: r for r in db.fills.for_day("pfa", "2026-09-18")}
    a, b = rows["AAA"], rows["BBB"]
    assert a["qty"] == 50 and b["qty"] == -100  # $5,000 a side at yesterday's closes, not at 09:35 prices
    assert a["basis"] == "auction" and a["last"] == 108.0 and a["price"] == pytest.approx(108.0 * 1.0001)
    assert b["basis"] == "last" and b["last"] == 45.0 and b["price"] == pytest.approx(45.0 * 0.9999)
    # bought at the auction, worth the 09:35 price now: the position is marked there straight away
    assert slot.positions["AAA"].last_price == 110.0
    assert slot.last_equity == pytest.approx(10_000 + 50 * (110 - 108.0 * 1.0001) - 100 * (45 - 45.0 * 0.9999))
