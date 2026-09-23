from datetime import datetime, timedelta, timezone

import pytest

from ridethewave.config import ExitSettings
from ridethewave.features import compute_features, forward_outcome, simulate_exit
from ridethewave.features.labels import label
from ridethewave.models import Bar
from tests.conftest import make_bars

T0 = datetime(2026, 9, 16, 13, 30, tzinfo=timezone.utc)


def test_compute_features_basic():
    # 25 flat bars at volume 1000, then a 3-bar streak at volume 3000
    closes = [100.0] * 25 + [100.5, 101.0, 101.5]
    bars = make_bars("AAPL", closes, start=T0, volume=1000)
    bars = bars[:25] + [Bar("AAPL", b.ts, b.open, b.high, b.low, b.close, 3000, 30, b.vwap) for b in bars[25:]]
    spy = make_bars("SPY", [500 + i * 0.1 for i in range(28)], start=T0, volume=1)
    f = compute_features(bars, spy, T0)
    assert f.streak == 3 and f.streak_gain_pct == pytest.approx(1.5)
    assert f.minutes_since_open == 27 and f.bars_in_session == 28
    assert f.rvol_20 == pytest.approx(3000 / (1000 * 18 + 3000 * 2) * 20)  # prior 20 bars include 2 streak bars
    assert f.streak_vol_ratio == pytest.approx(3.0) and f.trade_count_ratio == pytest.approx(3.0)
    assert f.session_ret_pct == pytest.approx(1.5)
    assert f.vwap_dist_pct is not None and f.vwap_dist_pct > 0
    assert f.spy_ret_5m_pct == pytest.approx((502.7 / 502.2 - 1) * 100, rel=1e-3)
    assert f.spy_ret_session_pct == pytest.approx((502.7 / 500 - 1) * 100, rel=1e-3)


def test_compute_features_ignores_previous_session_and_handles_short_history():
    prev = make_bars("AAPL", [90, 91, 92], start=T0 - timedelta(days=1))
    today = make_bars("AAPL", [100, 101], start=T0)
    f = compute_features(prev + today, None, T0)
    assert f.bars_in_session == 2 and f.streak == 1
    assert f.rvol_20 is None and f.range_pct_20 is None and f.spy_ret_5m_pct is None
    assert compute_features(prev, None, T0) is None


def test_forward_outcome_stop_wins_ties():
    fut = [Bar("A", T0, 100, 101.5, 98.5, 100, 1), Bar("A", T0 + timedelta(minutes=1), 100, 100, 100, 100, 1)]
    mfe, mae, ret_h, hit, n = forward_outcome(fut, 100.0, 60, 1.0, 1.0)
    assert hit is False and n == 1 and mfe == pytest.approx(1.5) and mae == pytest.approx(-1.5)
    fut = [Bar("A", T0, 100, 101.5, 99.5, 101, 1)]
    assert forward_outcome(fut, 100.0, 60, 1.0, 1.0)[3] is True


def test_simulate_exit_matches_strategy_rules():
    ex = ExitSettings(trail_pct=1.0, min_gain_pct=0.5, hard_stop_pct=1.0, max_hold_minutes=10)
    # run to 103 then close at 101.9 (below trigger 101.97, above floor 100.5) -> wave exit
    fut = make_bars("A", [101, 102, 103, 101.9], start=T0)
    pnl, reason, held = simulate_exit(fut, 100.0, ex, slippage_pct=0)
    assert reason == "wave_exit" and held == 4 and pnl == pytest.approx(1.9)
    # gap down through the stop fills at the open
    fut = [Bar("A", T0, 98.0, 98.5, 97.5, 98.2, 1)]
    pnl, reason, _ = simulate_exit(fut, 100.0, ex, slippage_pct=0)
    assert reason == "hard_stop" and pnl == pytest.approx(-2.0)
    # timeout only if profitable
    fut = make_bars("A", [100.2] * 12, start=T0)
    assert simulate_exit(fut, 100.0, ex, 0)[1] == "timeout"
    fut = make_bars("A", [99.8] * 12, start=T0)
    assert simulate_exit(fut, 100.0, ex, 0)[1] == "end_of_data"


def test_label_bundle():
    ex = ExitSettings()
    fut = make_bars("A", [100.5, 101, 101.5, 102, 102.5], start=T0)
    o = label(fut, 100.0, ex, horizon=60)
    assert o.mfe_pct == pytest.approx(2.5) and o.hit_target_first is True and o.strat_exit_reason == "end_of_data"
