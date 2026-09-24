"""Daily portfolio engine and strategies (ported from TraderPro / 151 Trading Strategies)."""

from datetime import date

import numpy as np
import pandas as pd

from ridethewave.daily.data import Panel
from ridethewave.daily.engine import run_daily
from ridethewave.daily.strategies import (
    DailyStrategy,
    Window,
    build_daily,
)
from ridethewave.daily.universe import pit_top_fn


def make_panel(n: int = 400, seed: int = 1) -> Panel:
    """UP trends up 0.1%/day, DOWN drifts down 0.1%/day, FLAT wobbles, SPY rises slowly."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=n)
    paths = {
        "UP": 100 * np.cumprod(1 + 0.001 + 0.002 * rng.standard_normal(n)),
        "DOWN": 100 * np.cumprod(1 - 0.001 + 0.002 * rng.standard_normal(n)),
        "FLAT": 100 * np.cumprod(1 + 0.004 * rng.standard_normal(n)),
        "SPY": 100 * np.cumprod(1 + 0.0003 + 0.001 * rng.standard_normal(n)),
    }
    close = pd.DataFrame(paths, index=days)
    open_ = close.shift(1).fillna(close.iloc[0]) * (1 + 0.0005 * rng.standard_normal((n, 4)))
    high = pd.concat([open_, close], axis=1).T.groupby(level=0).max().T * 1.002
    low = pd.concat([open_, close], axis=1).T.groupby(level=0).min().T * 0.998
    vol = pd.DataFrame({"UP": 1e6, "DOWN": 5e5, "FLAT": 2e6, "SPY": 5e7}, index=days)
    return Panel(open=open_, high=high[close.columns], low=low[close.columns], close=close, volume=vol)


class LongUp(DailyStrategy):
    name = "long_up"

    def targets(self, w: Window):
        return {"UP": 1.0}


class ShortDown(DailyStrategy):
    name = "short_down"

    def targets(self, w: Window):
        return {"DOWN": -0.5}


def test_engine_fills_next_open_marks_closes_and_reports_benchmarks():
    panel = make_panel()
    res = run_daily(
        LongUp(), panel, date(2024, 3, 1), date(2025, 6, 1), universe=["UP", "DOWN", "FLAT"], capital=10_000
    )
    m = res.metrics
    assert m["total_return"] > 0.2 and m["benchmark_cagr"] > 0 and "equal_weight_cagr" in m
    assert res.fills[0]["day"] > pd.Timestamp("2024-03-01")  # first fill is the day after the first close
    first = res.fills[0]
    assert abs(first["price"] / float(panel.open.loc[first["day"], "UP"]) - 1.0005) < 1e-9  # 5 bp slippage on a buy
    assert m["trades"] == 0 and res.weights["UP"].iloc[-1] == 1.0  # never closed: no round trip yet
    assert m["ir_vs_benchmark"] > 0 and m["h1_cagr"] > 0 and m["h2_cagr"] > 0


def test_shorts_earn_on_a_falling_stock_and_close_as_round_trips():
    panel = make_panel()
    res = run_daily(ShortDown(), panel, date(2024, 3, 1), date(2025, 6, 1), universe=["UP", "DOWN"], capital=10_000)
    assert res.metrics["total_return"] > 0.05
    assert (
        res.fills[0]["qty"] < 0
        and abs(res.fills[0]["price"] / float(panel.open.loc[res.fills[0]["day"], "DOWN"]) - 0.9995) < 1e-9
    )

    # flip to flat at the end via a strategy that returns nothing -> engine closes on the next open
    class Flip(DailyStrategy):
        name = "flip"
        n = 0

        def targets(self, w):
            self.n += 1
            return {"DOWN": -0.5} if self.n < 50 else {}

    r2 = run_daily(Flip(), panel, date(2024, 3, 1), date(2024, 9, 1), universe=["DOWN"], capital=10_000)
    assert len(r2.trades) == 1 and r2.trades[0]["side"] == "short" and r2.trades[0]["pnl"] > 0
    assert r2.metrics["profit_factor"] == float("inf") and r2.metrics["win_rate"] == 1.0


def test_book_strategies_rank_as_documented():
    panel = make_panel()
    i = 350
    w = Window(
        close=panel.close.iloc[:i],
        open=panel.open.iloc[:i],
        high=panel.high.iloc[:i],
        low=panel.low.iloc[:i],
        volume=panel.volume.iloc[:i],
        today=panel.close.index[i - 1],
        symbols=["UP", "DOWN", "FLAT"],
    )
    mom = build_daily(
        "price_momentum", {"formation_days": 120, "skip_days": 5, "fraction": 0.34, "allow_short": True}
    ).targets(w)
    assert mom["UP"] > 0 and mom["DOWN"] < 0 and abs(sum(abs(v) for v in mom.values()) - 1) < 1e-9
    resid = build_daily("residual_momentum", {"formation_days": 120, "skip_days": 5, "fraction": 0.34}).targets(w)
    assert list(resid) == ["UP"]
    mr = build_daily("mean_reversion", {"lookback_days": 20, "fraction": 0.34}).targets(w)
    assert len(mr) == 1  # one laggard bought
    prop = build_daily(
        "mean_reversion", {"lookback_days": 20, "weighting": "proportional", "allow_short": True}
    ).targets(w)
    assert abs(sum(abs(v) for v in prop.values()) - 1) < 1e-9 and any(v < 0 for v in prop.values())
    lv = build_daily("low_volatility", {"vol_days": 60, "fraction": 0.34}).targets(w)
    assert len(lv) == 1 and list(lv)[0] in ("UP", "DOWN")  # FLAT is the noisiest name
    combo = build_daily(
        "alpha_combo", {"momentum_days": 120, "momentum_skip": 5, "vol_days": 60, "fraction": 0.34}
    ).targets(w)
    assert len(combo) == 1
    multi = build_daily(
        "mean_reversion_multi", {"clusters": {"a": ["UP", "DOWN"], "b": ["FLAT", "SPY"]}, "fraction": 0.5}
    ).targets(w)
    assert set(multi) <= {"UP", "DOWN", "FLAT"} and len(multi) == 1  # FLAT's cluster mate SPY is not in the universe
    ibs = build_daily("ibs_mean_reversion", {"fraction": 0.34}).targets(w)
    assert len(ibs) == 1
    vt = build_daily("vol_targeting", {"symbol": "SPY", "target_vol": 0.10, "vol_days": 20}).targets(w)
    assert 0 < vt["SPY"] <= 1.0
    ma = build_daily("ma_rule", {"symbol": "UP", "fast": 20, "slow": 50}).targets(w)
    assert ma == {"UP": 1.0}
    ma3 = build_daily("ma_rule", {"symbol": "DOWN", "fast": 3, "slow": 10, "third": 21, "allow_short": True}).targets(w)
    assert ma3 in ({"DOWN": -1.0}, {})
    sr = build_daily(
        "sector_rotation", {"formation_days": 60, "top_n": 1, "dual_momentum_days": 100, "defensive": "FLAT"}
    ).targets(w)
    assert sr in ({"UP": 1.0}, {"FLAT": 1.0})
    mat = build_daily("multi_asset_trend", {"formation_days": 60, "ma_filter_days": 50, "vol_days": 30}).targets(w)
    assert set(mat) <= {"UP", "FLAT", "DOWN"} and all(0 < v <= 0.4 + 1e-9 for v in mat.values())


def test_point_in_time_universe_ranks_by_prior_dollar_volume():
    panel = make_panel()
    fn = pit_top_fn(panel, top=2, lookback=10)
    day = panel.close.index[100].date()
    top = fn(day)
    assert top[0] == "SPY" and len(top) == 2
    assert fn(panel.close.index[0].date()) == []  # nothing before the first bar


def test_equal_weight_benchmark_is_point_in_time():
    """The universe benchmark must only hold names that were in the universe at the previous close:
    DOWN is in the universe for the first half only, UP for the second half only."""
    panel = make_panel()
    days = panel.close.index
    mid = days[200].date()

    def ufn(d):
        return ["DOWN", "FLAT"] if d < mid else ["UP", "FLAT"]

    res = run_daily(LongUp(), panel, days[50].date(), days[350].date(), universe_fn=ufn, capital=10_000)
    ew = res.equal_weight.pct_change().dropna()
    rets = panel.close.pct_change()
    first = ew.index[(ew.index > days[51]) & (ew.index < days[199])]
    second = ew.index[ew.index > days[202]]
    assert np.allclose(ew.loc[first], rets.loc[first, ["DOWN", "FLAT"]].mean(axis=1), atol=1e-12)
    assert np.allclose(ew.loc[second], rets.loc[second, ["UP", "FLAT"]].mean(axis=1), atol=1e-12)
