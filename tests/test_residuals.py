"""Residual returns for statistical arbitrage: sector assignment, rolling betas, residuals (2026-11-02)."""

import numpy as np
import pandas as pd
import pytest

from ridethewave.daily.residuals import assign_sectors, residuals, rolling_betas, sector_series


def market_and_sectors(n: int = 400, seed: int = 7):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-01", periods=n)
    m = pd.Series(0.01 * rng.standard_normal(n), index=days)
    sec = pd.DataFrame(
        {"XLK": m + 0.008 * rng.standard_normal(n), "XLF": m + 0.008 * rng.standard_normal(n)}, index=days
    )
    return rng, days, m, sec


def test_each_stock_gets_the_sector_it_moves_with_and_only_from_prior_data():
    rng, days, m, sec = market_and_sectors()
    stocks = pd.DataFrame(
        {
            "TECH": 1.1 * m + 1.0 * (sec["XLK"] - m) + 0.005 * rng.standard_normal(len(days)),
            "BANK": 0.9 * m + 1.2 * (sec["XLF"] - m) + 0.005 * rng.standard_normal(len(days)),
        }
    )
    labels = assign_sectors(stocks, m, sec, window=252, min_obs=126)
    assert labels.iloc[:126].isna().all().all()  # nothing is known before enough history
    assert labels.iloc[-1]["TECH"] == "XLK" and labels.iloc[-1]["BANK"] == "XLF"
    # labels change only at month starts
    changes = labels["TECH"].ne(labels["TECH"].shift()) & labels["TECH"].notna()
    assert all(d.day <= 7 for d in labels.index[changes])


def test_rolling_betas_recover_known_exposures_and_residuals_strip_them():
    rng, days, m, sec = market_and_sectors(n=300)
    noise = 0.004 * rng.standard_normal(len(days))
    stocks = pd.DataFrame({"S": 1.3 * m + 0.7 * (sec["XLK"] - m) + noise})
    s_i = pd.DataFrame({"S": sec["XLK"]})
    b_m, b_s = rolling_betas(stocks, m, s_i, window=120, min_obs=60)
    assert b_m["S"].iloc[-1] == pytest.approx(1.3, abs=0.1)
    assert b_s["S"].iloc[-1] == pytest.approx(0.7, abs=0.1)
    e = residuals(stocks, m, s_i, b_m.shift(1), b_s.shift(1)).dropna()
    assert abs(np.corrcoef(e["S"], m.loc[e.index])[0, 1]) < 0.1  # no market left in the residual
    assert e["S"].std() == pytest.approx(0.004, rel=0.2)  # only the stock's own noise is left


def test_betas_for_a_day_do_not_use_that_day():
    _, days, m, sec = market_and_sectors(n=200)
    stocks = pd.DataFrame({"S": 1.0 * m + 0.5 * (sec["XLK"] - m)})
    s_i = pd.DataFrame({"S": sec["XLK"]})
    b_m, _ = rolling_betas(stocks, m, s_i, window=60, min_obs=40)
    shocked = stocks.copy()
    shocked.iloc[-1] = 0.5  # a huge move on the last day
    b_m2, _ = rolling_betas(shocked, m, s_i, window=60, min_obs=40)
    assert b_m.shift(1).iloc[-1, 0] == pytest.approx(b_m2.shift(1).iloc[-1, 0])  # lagged betas unchanged


def test_sector_series_follows_the_assignment():
    _, days, m, sec = market_and_sectors(n=10)
    labels = pd.DataFrame({"A": ["XLK"] * 5 + ["XLF"] * 5, "B": [np.nan] * 10}, index=days, dtype=object)
    s = sector_series(labels, sec)
    assert s["A"].iloc[2] == sec["XLK"].iloc[2] and s["A"].iloc[7] == sec["XLF"].iloc[7]
    assert s["B"].isna().all()
