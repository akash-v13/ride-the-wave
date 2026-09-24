"""Market-regime features and a rule-tree classifier, ported from TraderPro's selection layer.

Pure functions over daily closes. Every feature and every rule carries a plain-English reason so a
regime call can be audited. VIX is optional (Alpaca has no index symbols); when absent, the VIX rules
are skipped and the classifier leans on realised volatility, trend and breadth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

REGIMES = ("bull_trend", "bear_trend", "range_low_vol", "chop_high_vol", "crisis")
SECTOR_ETFS_11 = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLRE", "XLU", "XLC"]
TRADING_DAYS = 252


@dataclass
class RegimeFeatures:
    spy_close: float = math.nan
    spy_sma50: float = math.nan
    spy_sma200: float = math.nan
    spy_above_sma200: bool | None = None
    sma50_above_sma200: bool | None = None
    spy_return_3m: float = math.nan
    spy_drawdown_3m: float = math.nan
    realized_vol_20d: float = math.nan
    vix: float = math.nan
    vix_term_ratio: float = math.nan
    breadth_sectors_above_50d: float = math.nan
    credit_hyg_ief_trend: float = math.nan
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "notes"}
        return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in d.items()} | {
            "notes": self.notes
        }


@dataclass
class RegimeCall:
    regime: str
    confidence: float
    reasons: list[str]


def compute_features(
    close: pd.DataFrame,
    benchmark: str = "SPY",
    sectors: list[str] | None = None,
    vix: pd.Series | None = None,
    vix3m: pd.Series | None = None,
) -> RegimeFeatures:
    """``close``: wide frame of daily closes up to the decision day. Sector, HYG/IEF and VIX inputs are optional."""
    f = RegimeFeatures()
    sectors = sectors or SECTOR_ETFS_11
    if benchmark in close.columns:
        spy = close[benchmark].dropna()
        if len(spy) >= 200:
            f.spy_close = float(spy.iloc[-1])
            f.spy_sma50 = float(spy.tail(50).mean())
            f.spy_sma200 = float(spy.tail(200).mean())
            f.spy_above_sma200 = f.spy_close > f.spy_sma200
            f.sma50_above_sma200 = f.spy_sma50 > f.spy_sma200
        else:
            f.notes.append(f"{benchmark}: fewer than 200 closes, trend flags unset")
        if len(spy) >= 63:
            w = spy.tail(63)
            f.spy_return_3m = float(w.iloc[-1] / w.iloc[0] - 1)
            f.spy_drawdown_3m = float(w.iloc[-1] / w.max() - 1)
        if len(spy) >= 21:
            f.realized_vol_20d = float(spy.tail(21).pct_change().dropna().std() * math.sqrt(TRADING_DAYS))
    else:
        f.notes.append(f"{benchmark} missing")
    if vix is not None and len(vix.dropna()):
        f.vix = float(vix.dropna().iloc[-1])
        if vix3m is not None and len(vix3m.dropna()) and vix3m.dropna().iloc[-1] > 0:
            f.vix_term_ratio = f.vix / float(vix3m.dropna().iloc[-1])
    else:
        f.notes.append("no VIX series: VIX rules skipped")
    above = counted = 0
    for s in sectors:
        if s in close.columns:
            c = close[s].dropna()
            if len(c) >= 50:
                counted += 1
                above += int(c.iloc[-1] > c.tail(50).mean())
    if counted:
        f.breadth_sectors_above_50d = above / counted
    else:
        f.notes.append("no sector ETFs: breadth unset")
    if "HYG" in close.columns and "IEF" in close.columns:
        h, i = close["HYG"].dropna().tail(21), close["IEF"].dropna().tail(21)
        if len(h) == 21 and len(i) == 21:
            f.credit_hyg_ief_trend = float((h.iloc[-1] / h.iloc[0] - 1) - (i.iloc[-1] / i.iloc[0] - 1))
    return f


def _val(x: float) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


def classify(f: RegimeFeatures) -> RegimeCall:
    """TraderPro's ordered rules: crisis, bear trend, high-vol chop, bull trend, else low-vol range."""
    vix, ratio, dd = _val(f.vix), _val(f.vix_term_ratio), _val(f.spy_drawdown_3m)
    rv, breadth = _val(f.realized_vol_20d), _val(f.breadth_sectors_above_50d)
    reasons: list[str] = []
    crisis = 0
    if vix is not None and vix >= 30:
        crisis += 2
        reasons.append(f"VIX {vix:.0f} >= 30")
    if ratio is not None and ratio >= 1.0:
        crisis += 1
        reasons.append(f"VIX term ratio {ratio:.2f} >= 1 (backwardation)")
    if dd is not None and dd <= -0.12:
        crisis += 1
        reasons.append(f"3-month drawdown {dd:.0%} <= -12%")
    if vix is None and rv is not None and rv >= 0.35 and dd is not None and dd <= -0.12:
        crisis += 2  # no VIX available: a 35% realised vol with a deep drawdown stands in for VIX >= 30
        reasons.append(f"realised vol {rv:.0%} >= 35% with the drawdown (VIX proxy)")
    if crisis >= 2:
        return RegimeCall("crisis", min(0.6 + 0.15 * crisis, 0.95), reasons)
    reasons = []
    if f.spy_above_sma200 is False and f.sma50_above_sma200 is False:
        conf = 0.7
        reasons.append("SPY below its 200-day and the 50-day below the 200-day")
        if breadth is not None and breadth <= 0.3:
            conf += 0.15
            reasons.append(f"breadth {breadth:.0%} <= 30%")
        return RegimeCall("bear_trend", min(conf, 0.95), reasons)
    high_vol = (vix is not None and vix >= 22) or (rv is not None and rv >= 0.20)
    if high_vol:
        reasons.append(
            f"high vol: VIX {vix if vix is not None else 'n/a'}, realised {rv:.0%}" if rv is not None else "high vol"
        )
        uptrend = bool(f.spy_above_sma200 and f.sma50_above_sma200 and (breadth is None or breadth >= 0.5))
        return RegimeCall("chop_high_vol", 0.6 if uptrend else 0.7, reasons)
    if f.spy_above_sma200 and f.sma50_above_sma200:
        conf = 0.7
        reasons.append("SPY above its 200-day and the 50-day above the 200-day")
        if breadth is not None and breadth >= 0.6:
            conf += 0.15
            reasons.append(f"breadth {breadth:.0%} >= 60%")
        elif breadth is not None and breadth < 0.4:
            conf -= 0.1
            reasons.append(f"breadth {breadth:.0%} < 40%")
        return RegimeCall("bull_trend", max(0.5, min(conf, 0.95)), reasons)
    return RegimeCall("range_low_vol", 0.6, ["no trend signal and volatility is low"])


def regime_history(close: pd.DataFrame, every: int = 1, **kw) -> pd.DataFrame:
    """Classify each day (or every ``every`` days) from data up to that day only.

    Returns a frame with regime, confidence and the feature values."""
    rows = []
    for i in range(200, len(close), every):
        window = close.iloc[: i + 1]
        f = compute_features(window, **kw)
        call = classify(f)
        rows.append(
            {
                "day": close.index[i],
                "regime": call.regime,
                "confidence": call.confidence,
                **{k: v for k, v in f.as_dict().items() if k != "notes"},
            }
        )
    return pd.DataFrame(rows).set_index("day")
