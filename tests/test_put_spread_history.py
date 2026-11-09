"""The long-history put spread simulation (options/history_sim.py): skew curve, pricing, calendar,
payoffs and the vrp gate on small synthetic paths."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from ridethewave.options.history_sim import (
    SimConfig,
    SkewCurve,
    deflated_sharpe,
    fit_skew,
    monthly_expiries,
    put_implied_vol,
    put_price,
    simulate,
)

SKEW = SkewCurve(0.834, -0.254, 0.008, 0.844)


def _path(values: list[float], start: str = "2024-01-02") -> pd.Series:
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_skew_curve_levels_and_scaling():
    assert SKEW.ratio(0.0) == pytest.approx(0.834)
    # an out-of-the-money put (negative z) carries more implied vol than the money
    assert SKEW.iv(0.20, 100, 90, 35 / 365) > SKEW.iv(0.20, 100, 100, 35 / 365)
    steep = SKEW.scaled(1.25)
    assert steep.c0 == SKEW.c0 and steep.c1 == pytest.approx(SKEW.c1 * 1.25)
    assert steep.iv(0.20, 100, 90, 35 / 365) > SKEW.iv(0.20, 100, 90, 35 / 365)


def test_fit_skew_recovers_a_known_curve():
    z = np.linspace(-3, 0.5, 50)
    curve = fit_skew(z, 0.8 - 0.3 * z + 0.02 * z**2, atm_gate=0.85)
    assert (curve.c0, curve.c1, curve.c2) == pytest.approx((0.8, -0.3, 0.02), abs=1e-9)


def test_put_price_intrinsic_at_expiry_and_iv_round_trip():
    assert put_price(90, 100, 0, 0.3, 0.04, 0.018) == pytest.approx(10.0)
    assert put_price(110, 100, 0, 0.3, 0.04, 0.018) == 0.0
    p = put_price(100, 95, 35 / 365, 0.22, 0.045, 0.018)
    assert put_implied_vol(p, 100, 95, 35 / 365, 0.045, 0.018) == pytest.approx(0.22, abs=1e-5)


def test_monthly_expiries_third_friday_and_good_friday():
    days = pd.bdate_range("2025-03-01", "2025-05-31")
    days = days[days != pd.Timestamp("2025-04-18")]  # Good Friday: the market is shut
    exps = monthly_expiries(days)
    assert date(2025, 3, 21) in exps
    assert date(2025, 4, 17) in exps  # moved to the Thursday, as SPY's was
    assert date(2025, 5, 16) in exps


def test_flat_market_spreads_expire_worthless_and_earn_the_credit():
    spx = _path([100.0] * 160)
    vix = _path([20.0] * 160)
    res = simulate(spx, vix, _path([0.0] * 160), SKEW, SimConfig(capital=20_000.0))
    assert res.trades and all(t.reason == "dte_exit" and t.pnl > 0 for t in res.trades)
    assert res.equity.iloc[-1] > 20_000.0


def test_a_crash_loses_about_the_risk_fraction():
    # flat long enough for the 20-day realised vol to exist, then a 20% gap down that stays down
    vals = [100.0] * 30 + [80.0] * 60
    spx, vix = _path(vals), _path([20.0] * 30 + [45.0] * 60)
    cfg = SimConfig(capital=20_000.0, cash_interest=False)
    res = simulate(spx, vix, _path([0.0] * 90), SKEW, cfg)
    first = res.trades[0]
    assert first.k_short == pytest.approx(95.0) and first.k_long == pytest.approx(90.0)
    # both puts end deep in the money: the loss is the width less the credit on 20% of equity, plus costs
    assert -0.26 < first.pnl / 20_000.0 < -0.18


def test_vrp_gate_closed_when_implied_is_below_realised():
    # alternating +-2% days: realised vol ~32%, far above a modelled ATM IV of 0.844 x 10% = 8.4%
    vals = [100.0 * (1.02 if i % 2 else 1 / 1.02) for i in range(120)]
    spx, vix = _path(vals), _path([10.0] * 120)
    rates = _path([0.0] * 120)
    assert simulate(spx, vix, rates, SKEW, SimConfig()).trades == []
    assert simulate(spx, vix, rates, SKEW, replace(SimConfig(), gate="none")).trades


def test_deflated_sharpe_is_below_the_plain_probability():
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(0.0004, 0.01, 5000))
    out = deflated_sharpe(x, [0.03, 0.04, 0.05, 0.02, 0.035], 5)
    assert out["psr_vs_zero"] > 0.9
    assert out["dsr"] <= out["psr_vs_zero"]
    assert math.isclose(out["sharpe_annual"], out["sharpe_daily"] * math.sqrt(252))
