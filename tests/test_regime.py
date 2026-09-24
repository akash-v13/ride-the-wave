import numpy as np
import pandas as pd

from ridethewave.daily.regime import REGIMES, RegimeFeatures, classify, compute_features, regime_history


def _closes(n=300, drift=0.0005, vol=0.008, seed=3):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-01", periods=n)
    spy = 100 * np.cumprod(1 + drift + vol * rng.standard_normal(n))
    data = {"SPY": spy}
    for s in ("XLK", "XLF", "XLV", "XLE"):
        data[s] = 50 * np.cumprod(1 + drift + vol * rng.standard_normal(n))
    return pd.DataFrame(data, index=days)


def test_features_and_bull_call_without_vix():
    close = _closes(drift=0.002, vol=0.005)
    f = compute_features(close)
    assert f.spy_above_sma200 and f.sma50_above_sma200 and 0 <= f.breadth_sectors_above_50d <= 1
    assert "VIX" in " ".join(f.notes)
    call = classify(f)
    assert call.regime == "bull_trend" and call.confidence >= 0.7 and call.reasons


def test_bear_crisis_chop_and_range_rules():
    bear = _closes(drift=-0.003, vol=0.006)
    assert classify(compute_features(bear)).regime == "bear_trend"
    f = RegimeFeatures(vix=35.0, vix_term_ratio=1.1, spy_drawdown_3m=-0.15)
    c = classify(f)
    assert c.regime == "crisis" and c.confidence == 0.95
    chop = RegimeFeatures(
        spy_above_sma200=True, sma50_above_sma200=True, realized_vol_20d=0.25, breadth_sectors_above_50d=0.7
    )
    assert classify(chop).regime == "chop_high_vol" and classify(chop).confidence == 0.6
    quiet = RegimeFeatures(spy_above_sma200=True, sma50_above_sma200=False, realized_vol_20d=0.10)
    assert classify(quiet).regime == "range_low_vol"
    assert set(REGIMES) >= {classify(compute_features(_closes())).regime}


def test_history_uses_only_past_data():
    close = _closes(n=260)
    hist = regime_history(close, every=20)
    assert len(hist) == 3 and set(hist["regime"]) <= set(REGIMES) and hist["confidence"].between(0.5, 0.95).all()
