"""Trend-following sleeve (time-series momentum, 2026-11-02) and the outside-data parsers it is tested on."""

import io
import math
import zipfile
from datetime import date

import numpy as np
import pandas as pd
import pytest

from ridethewave.daily.engine import run_daily
from ridethewave.daily.strategies import TrendParams, build_daily, trend_weights
from ridethewave.data import external
from tests.test_daily_engine import make_panel


def paths(spec: dict[str, tuple[float, float]], n: int = 400, seed: int = 3) -> pd.DataFrame:
    """Independent random walks: symbol -> (daily drift, daily volatility)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame(
        {s: 100 * np.cumprod(1 + mu + sd * rng.standard_normal(n)) for s, (mu, sd) in spec.items()}, index=days
    )


def test_long_rising_short_falling_and_long_only_drops_shorts():
    close = paths({"UP": (0.002, 0.01), "DOWN": (-0.002, 0.01)})
    p = TrendParams(classes={"UP": "a", "DOWN": "b"})
    w = trend_weights(close, p)
    assert w["UP"] > 0 > w["DOWN"]
    lo = trend_weights(close, TrendParams(classes={"UP": "a", "DOWN": "b"}, allow_short=False))
    assert "DOWN" not in lo and lo["UP"] > 0


def test_a_market_twice_as_volatile_gets_about_half_the_weight():
    close = paths({"CALM": (0.002, 0.005), "WILD": (0.004, 0.010)}, n=600)
    w = trend_weights(close, TrendParams(classes={"CALM": "a", "WILD": "b"}, max_weight=2, max_gross=4))
    assert w["WILD"] / w["CALM"] == pytest.approx(0.5, rel=0.25)


def test_each_class_gets_an_equal_share_of_risk():
    # three bond funds and one currency fund, all alike: the currency fund carries as much as all three bonds
    close = paths({s: (0.002, 0.008) for s in ("B1", "B2", "B3", "FX")}, n=600)
    classes = {"B1": "bond", "B2": "bond", "B3": "bond", "FX": "currency"}
    w = trend_weights(close, TrendParams(classes=classes, max_weight=2, max_gross=4))
    bonds = w["B1"] + w["B2"] + w["B3"]
    assert w["FX"] == pytest.approx(bonds, rel=0.35)
    assert w["FX"] > 2 * max(w["B1"], w["B2"], w["B3"])
    flat = trend_weights(close, TrendParams(classes={}, max_weight=2, max_gross=4))  # no classes: all equal
    assert flat["FX"] == pytest.approx(flat["B1"], rel=0.35)


def test_book_is_scaled_to_the_volatility_target_then_capped():
    close = paths({s: (0.002, 0.01) for s in ("A", "B", "C", "D")}, n=600)
    p = TrendParams(classes={}, target_vol=0.10, max_weight=2, max_gross=4)
    w = pd.Series(trend_weights(close, p))
    cov = close.pct_change().iloc[-p.cov_days :].cov() * 252
    assert math.sqrt(w @ cov.loc[w.index, w.index] @ w) == pytest.approx(0.10, rel=1e-6)
    capped = trend_weights(close, TrendParams(classes={}, target_vol=0.5, max_weight=0.3, max_gross=1.0))
    assert sum(abs(v) for v in capped.values()) <= 1.0 + 1e-9
    assert max(abs(v) for v in capped.values()) <= 0.3 + 1e-9


def test_markets_without_a_years_history_are_left_out():
    close = paths({"OLD": (0.002, 0.01), "NEW": (0.002, 0.01)})
    close.iloc[:200, 1] = np.nan
    assert set(trend_weights(close, TrendParams(classes={}))) == {"OLD"}


def test_strategy_runs_in_the_daily_engine_long_and_short():
    panel = make_panel(n=420)
    res = run_daily(build_daily("trend_following", {"classes": {}}), panel, date(2025, 1, 1), date(2025, 8, 1),
                    universe=["UP", "DOWN", "FLAT"], rebalance_days=5, max_gross=2.0)  # fmt: skip
    last = res.weights.iloc[-1]
    assert last["UP"] > 0 > last["DOWN"]


# ---------------------------------------------------------------- outside data parsers
def test_parse_french_reads_the_daily_block_in_decimals():
    text = (
        "This file was created by ...\n\n"
        ",Mkt-RF,SMB,HML,RF\n"
        "19260701,    0.09,   -0.25,   -0.27,    0.01\n"
        "19260702,    0.45,   -0.33,   -0.06,    0.01\n"
        "\nCopyright 2026 Eugene F. Fama and Kenneth R. French\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("F-F_Research_Data_Factors_daily.csv", text)
    df = external.parse_french(buf.getvalue())
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert df.index[0] == pd.Timestamp("1926-07-01") and len(df) == 2
    assert df.loc["1926-07-02", "Mkt-RF"] == pytest.approx(0.0045)


def test_parse_french_reads_a_monthly_file_and_stops_before_the_annual_block():
    text = (
        "The portfolios are constructed monthly.\n\n"
        ",ST_Rev\n192602,   -2.10\n192603,    3.05\n\n"
        " Annual Factors: January-December\n,ST_Rev\n1927,   12.00\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("F-F_ST_Reversal_Factor.csv", text)
    df = external.parse_french(buf.getvalue())
    assert list(df.index) == [pd.Timestamp("1926-02-28"), pd.Timestamp("1926-03-31")]
    assert df["ST_Rev"].iloc[1] == pytest.approx(0.0305)


def test_parse_cboe_handles_ohlc_and_single_value_files():
    ohlc = external.parse_cboe(b"DATE,OPEN,HIGH,LOW,CLOSE\n01/02/1990,17.24,17.24,17.24,17.24\n", "vix")
    one = external.parse_cboe(b"DATE,PUT\n03/04/1991,153.5\n08/07/1991,163.67\n", "put")
    assert ohlc["close"].iloc[0] == pytest.approx(17.24)
    assert list(one.columns) == ["close"] and one.index[1] == pd.Timestamp("1991-08-07")


def test_parse_fred_drops_missing_days():
    s = external.parse_fred(b"observation_date,DGS10\n1962-01-02,4.06\n1962-01-03,.\n1962-01-04,4.03\n", "dgs10")
    assert list(s.values) == [4.06, 4.03]


def test_treasury_proxy_earns_carry_and_loses_duration_on_a_rate_rise(tmp_path, monkeypatch):
    days = pd.bdate_range("2020-01-01", periods=4)
    (tmp_path / "fred").mkdir()
    yields = [4.0, 4.0, 4.01, 4.01]
    rows = "".join(f"{d.date()},{y}\n" for d, y in zip(days, yields, strict=True))
    (tmp_path / "fred" / "DGS10.csv").write_text("observation_date,DGS10\n" + rows)
    r = external.treasury_10y_total_return(root=tmp_path)
    carry = 0.04 / 365
    assert r.iloc[0] == pytest.approx(carry, rel=1e-6)  # flat yield: one day of coupon
    duration = (1 - 1.02**-20) / 0.04  # ~8.2 years for a 10-year par bond at 4%
    assert r.iloc[1] == pytest.approx(carry - duration * 0.0001, rel=0.01)  # a 1 bp rise costs ~0.08%
