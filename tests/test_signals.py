"""Conditions and rankings of the shortlist signals (docs/research/2026-11-10-signals-a-c-d.md)."""

import numpy as np
import pandas as pd

from ridethewave.daily.signals import mean_difference, momentum_12_1, month_position, sector_stress, turn_of_month


def test_turn_of_month_is_the_last_session_and_the_first_three():
    idx = pd.bdate_range("2024-01-01", "2024-03-29")  # Jan, Feb, Mar 2024; weekdays stand in for sessions
    turn = turn_of_month(idx)
    on = [d.strftime("%m-%d") for d in idx[turn]]
    assert on == ["01-01", "01-02", "01-03", "01-31", "02-01", "02-02", "02-05", "02-29", "03-01", "03-04", "03-05"]


def test_the_final_months_end_is_not_guessed():
    idx = pd.bdate_range("2024-01-01", "2024-02-14")  # February is not over
    from_start, from_end = month_position(idx)
    assert from_start.loc["2024-02-01"] == 1 and from_end.loc["2024-01-31"] == 1
    assert from_end.loc["2024-02-14":].isna().all()
    assert not turn_of_month(idx).loc["2024-02-14"]


def test_sector_stress_judges_a_day_against_earlier_days_only():
    idx = pd.bdate_range("2020-01-01", periods=300)
    rng = np.random.default_rng(3)
    market = pd.Series(rng.normal(0, 0.01, 300), index=idx)
    calm = market + pd.Series(rng.normal(0, 0.002, 300), index=idx)
    hit = calm.copy()
    hit.iloc[-1] -= 0.10  # one sector falls 10% beyond the market on the last day
    flags = sector_stress(pd.DataFrame({"CALM": calm, "HIT": hit}), market)
    assert flags["HIT"].iloc[-1] and not flags["CALM"].iloc[-1]
    assert not flags.iloc[:204].any().any()  # 5 sessions for the first sum, then 200 earlier values
    # the threshold on the day before is the same with or without the shock: nothing looks ahead
    assert flags["HIT"].iloc[:-1].equals(sector_stress(pd.DataFrame({"HIT": calm}), market)["HIT"].iloc[:-1])
    # about a tenth of days qualify by construction
    assert 0.03 < flags["CALM"].iloc[205:].mean() < 0.25


def test_momentum_uses_prices_up_to_yesterday():
    idx = pd.bdate_range("2020-01-01", periods=300)
    close = pd.DataFrame({"A": np.arange(1.0, 301.0)}, index=idx)
    m = momentum_12_1(close)
    assert m["A"].iloc[:253].isna().all()
    t = 280
    assert m["A"].iloc[t] == close["A"].iloc[t - 22] / close["A"].iloc[t - 253] - 1
    changed = close.copy()
    changed.iloc[t - 21 :] = 999.0  # the latest month and today do not matter
    assert momentum_12_1(changed)["A"].iloc[t] == m["A"].iloc[t]


def test_mean_difference_matches_the_plain_difference_and_finds_a_real_one():
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2000-01-03", periods=5000)
    flag = turn_of_month(idx)
    noise = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    with_edge = noise + 0.002 * flag
    r = mean_difference(with_edge, flag)
    assert abs(r["difference"] - (with_edge[flag].mean() - with_edge[~flag].mean())) < 1e-12
    assert r["t"] > 4 and r["n_flagged"] == int(flag.sum())
    assert abs(mean_difference(noise, flag)["t"]) < 3
    assert np.isnan(mean_difference(noise.iloc[:5], flag.iloc[:5])["t"])  # too little to say anything
