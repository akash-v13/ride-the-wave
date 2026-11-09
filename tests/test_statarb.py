"""Stat arb stage 2a: cohort rules, the live rebuild of cohorts, and the slot passing VIX through (2026-11-02)."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from ridethewave.config import PortfolioSpec
from ridethewave.daily.data import Panel
from ridethewave.daily.statarb import cohort_targets, cohort_weights, hedge, pick
from ridethewave.daily.strategies import DailyStrategy, Window, build_daily
from ridethewave.portfolio.daily_slot import DailySlot

SECTORS = ["XLK", "XLF"]


def market(n: int = 400, names: int = 40, seed: int = 11) -> pd.DataFrame:
    """Closes for SPY, two sector ETFs and ``names`` stocks, half in each sector."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=n)
    m = 0.01 * rng.standard_normal(n)
    sec = {e: m + 0.006 * rng.standard_normal(n) for e in SECTORS}
    rets = {"SPY": m, **sec}
    for i in range(names):
        e = SECTORS[i % 2]
        rets[f"S{i:02d}"] = m + (sec[e] - m) + 0.012 * rng.standard_normal(n)
    return 100 * (1 + pd.DataFrame(rets, index=days)).cumprod()


def test_pick_buys_the_most_negative_fifth_and_shorts_the_most_positive():
    sig = pd.Series(np.arange(50, dtype=float), index=[f"S{i}" for i in range(50)])
    longs, shorts = pick(sig, pd.Series(True, index=sig.index), 0.2)
    assert longs == [f"S{i}" for i in range(10)] and shorts == [f"S{i}" for i in range(40, 50)]
    assert pick(sig.iloc[:20], pd.Series(True, index=sig.index[:20])) == ([], [])  # too few names


def test_cohort_is_dollar_neutral_and_hedge_cancels_the_betas():
    w = cohort_weights(["A", "B"], ["C", "D"], side=0.2)
    assert sum(w.values()) == pytest.approx(0) and sum(abs(x) for x in w.values()) == pytest.approx(0.4)
    h = hedge({"A": 0.1}, pd.Series({"A": 1.2}), pd.Series({"A": 0.5}), pd.Series({"A": "XLK"}))
    # A's exposure is 1.2 SPY + 0.5 (XLK - SPY) = 0.7 SPY + 0.5 XLK; the hedge holds the opposite
    assert h["SPY"] == pytest.approx(-0.07) and h["XLK"] == pytest.approx(-0.05)


def test_cohorts_form_only_after_a_volatile_close_and_live_for_the_holding_period():
    close = market()
    names = [c for c in close.columns if c not in ("SPY", *SECTORS)]
    days = close.index
    vix = pd.Series(15.0, index=days)
    vix.iloc[-3] = 25.0  # one stressed close, three sessions before the end
    w, notes = cohort_targets(close, names, vix, SECTORS, hold=5)
    assert len([x for x in notes if x.startswith("cohort")]) == 1
    stocks = {s: x for s, x in w.items() if s in names}
    assert len(stocks) == 16 and sum(stocks.values()) == pytest.approx(0)  # 8 long, 8 short of 40
    assert set(w) - set(names) <= {"SPY", *SECTORS}  # everything else is the hedge
    # the stressed close was three sessions back: a two-session holding period has already let it go
    assert cohort_targets(close, names, vix, SECTORS, hold=2)[0] == {}
    assert days[-3] in {pd.Timestamp(x.split()[2]) for x in notes}


def test_no_cohort_when_vix_is_calm_and_the_strategy_goes_to_cash_without_vix():
    close = market()
    names = [c for c in close.columns if c not in ("SPY", *SECTORS)]
    w, _ = cohort_targets(close, names, pd.Series(15.0, index=close.index), SECTORS)
    assert w == {}
    strat = build_daily("statarb_vol_reversal", {"sector_etfs": SECTORS})
    panel = {k: close for k in ("close", "open", "high", "low", "volume")}
    win = Window(**panel, today=close.index[-1], symbols=names)
    assert strat.targets(win) == {}  # no VIX given: no cohorts


def test_strategy_uses_completed_sessions_only_when_deciding_at_the_open():
    close = market()
    names = [c for c in close.columns if c not in ("SPY", *SECTORS)]
    vix = pd.Series(15.0, index=close.index)
    vix.iloc[-1] = 30.0  # stressed close on the last row: that row is today's unfinished bar at 09:35
    strat = build_daily("statarb_vol_reversal", {"sector_etfs": SECTORS})
    win = Window(**{k: close for k in ("close", "open", "high", "low", "volume")}, today=close.index[-1],
                 symbols=names, external={"vix": vix})  # fmt: skip
    assert strat.targets(win) == {}  # today's VIX is not known yet, so it cannot open a cohort
    vix.iloc[-2] = 30.0  # yesterday's close was stressed: a cohort enters today
    assert any(s in names for s in strat.targets(win))
    assert strat.extra_symbols == ["SPY", *SECTORS] and strat.external_series == ["vix"]


class Echo(DailyStrategy):
    name = "echo"

    def __init__(self):
        super().__init__({})
        self.seen = None

    def targets(self, w: Window):
        self.seen = w.external
        return {}


def test_daily_slot_hands_external_series_to_the_strategy(db):
    days = pd.bdate_range("2026-08-10", periods=5)
    c = pd.DataFrame({"AAA": [10.0] * 5}, index=days)
    slot = DailySlot(PortfolioSpec(id="e", kind="price_momentum", universe="AAA"), Echo(), db, "live", 1000)
    slot.decide(Panel(open=c, high=c, low=c, close=c, volume=c), {"AAA": 10.0},
                datetime(2026, 8, 14, tzinfo=timezone.utc), ["AAA"], {"vix": pd.Series([20.0])})  # fmt: skip
    assert list(slot.strategy.seen) == ["vix"]
