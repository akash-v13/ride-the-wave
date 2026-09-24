"""Daily-bar portfolio strategies from *151 Trading Strategies* (Kakushadze & Serur, 2018), as first
implemented in the owner's TraderPro project and re-implemented here on wide frames.

Each strategy sees a ``Window`` (all history up to today's close) and returns target weights: fraction
of equity per symbol, negative for short. Pure: no I/O. Defaults follow TraderPro where it had them,
the book otherwise; the section numbers are the book's.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


@dataclass
class Window:
    close: pd.DataFrame
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    volume: pd.DataFrame
    today: pd.Timestamp
    symbols: list[str]
    benchmark: str = "SPY"
    held: dict[str, float] = field(default_factory=dict)
    log: Callable[[str], None] = lambda _: None

    def closes(self, n: int, symbols: list[str] | None = None) -> pd.DataFrame:
        cols = [s for s in (symbols or self.symbols) if s in self.close.columns]
        return self.close[cols].iloc[-n:]

    def series(self, symbol: str, n: int) -> pd.Series:
        return self.close[symbol].iloc[-n:].dropna() if symbol in self.close.columns else pd.Series(dtype=float)


class NoParams(BaseModel):
    model_config = {"extra": "forbid"}


class DailyStrategy:
    name: str = "daily"
    params_model: type[BaseModel] = NoParams
    warmup: int = 0

    def __init__(self, params: dict | None = None):
        self.p = self.params_model.model_validate(params or {})

    def params_dict(self) -> dict:
        return self.p.model_dump(mode="json")

    def targets(self, w: Window) -> dict[str, float]:  # pragma: no cover - interface
        raise NotImplementedError


# ---------------------------------------------------------------- helpers
def _long_short(ranked: list[str], fraction: float, allow_short: bool, min_names: int = 3) -> dict[str, float]:
    """Equal weights: long the top of ``ranked`` (best first), short the bottom when allowed."""
    if len(ranked) < min_names:
        return {}
    n = max(1, int(len(ranked) * fraction))
    longs, shorts = ranked[:n], (ranked[-n:] if allow_short else [])
    w = 1.0 / (len(longs) + len(shorts))
    out = {s: w for s in longs}
    out.update({s: -w for s in shorts if s not in out})
    return out


def _window_returns(close: pd.DataFrame, lookback: int) -> pd.Series:
    """close[-1] / close[-lookback] - 1 per column, NaN where the window is incomplete."""
    if len(close) < lookback:
        return pd.Series(dtype=float)
    return (close.iloc[-1] / close.iloc[-lookback] - 1.0).dropna()


def _zscore(s: pd.Series) -> pd.Series:
    if len(s) < 2 or s.std(ddof=0) < 1e-12:
        return s * 0.0
    return (s - s.mean()) / s.std(ddof=0)


def _sma(s: pd.Series, n: int) -> float:
    return float(s.iloc[-n:].mean()) if len(s) >= n else float("nan")


def _above_ma(s: pd.Series, n: int) -> bool:
    return len(s) >= n and float(s.iloc[-1]) > _sma(s, n)


# ---------------------------------------------------------------- §3.1 price momentum
class PriceMomentumParams(BaseModel):
    formation_days: int = Field(231, ge=20, le=504)
    skip_days: int = Field(21, ge=0, le=63)
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class PriceMomentum(DailyStrategy):
    name = "price_momentum"
    params_model = PriceMomentumParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = self.p.formation_days + self.p.skip_days + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        c = w.closes(p.formation_days + p.skip_days)
        if len(c) < p.formation_days + p.skip_days:
            return {}
        end = c.iloc[-(p.skip_days + 1)] if p.skip_days else c.iloc[-1]
        mom = (end / c.iloc[0] - 1.0).dropna()
        ranked = mom.sort_values(ascending=False).index.tolist()
        return _long_short(ranked, p.fraction, p.allow_short)


# ---------------------------------------------------------------- §3.7 residual momentum
class ResidualMomentumParams(BaseModel):
    formation_days: int = Field(126, ge=40, le=504)
    skip_days: int = Field(10, ge=0, le=63)
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class ResidualMomentum(DailyStrategy):
    """Regress each stock's daily returns on the benchmark's over the formation window; the momentum
    score is the sum of residuals (intercept left in, as TraderPro did) excluding the skip days."""

    name = "residual_momentum"
    params_model = ResidualMomentumParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = self.p.formation_days + self.p.skip_days + 3

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        n = p.formation_days + 1
        if w.benchmark not in w.close.columns:
            w.log("residual momentum: benchmark missing")
            return {}
        c = w.closes(n)
        b = w.close[w.benchmark].iloc[-n:]
        rets = c.pct_change().iloc[1:]
        brets = b.pct_change().iloc[1:]
        scores = {}
        for s in rets.columns:
            j = pd.concat([rets[s], brets], axis=1, keys=["s", "b"]).dropna()
            if len(j) < p.formation_days:
                continue
            x, y = j["b"].to_numpy(), j["s"].to_numpy()
            beta = float(np.polyfit(x, y, 1)[0])
            resid = y - beta * x
            used = resid[: -p.skip_days] if p.skip_days else resid
            scores[s] = float(used.sum())
        ranked = sorted(scores, key=scores.get, reverse=True)
        return _long_short(ranked, p.fraction, p.allow_short)


# ---------------------------------------------------------------- §3.9 mean reversion, single cluster
class MeanReversionParams(BaseModel):
    lookback_days: int = Field(20, ge=2, le=252)
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    weighting: str = Field("equal", pattern="^(equal|proportional)$")  # proportional: D_i ∝ −deviation (book eq. 297)
    model_config = {"extra": "forbid"}


class MeanReversion(DailyStrategy):
    name = "mean_reversion"
    params_model = MeanReversionParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = self.p.lookback_days + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        r = _window_returns(w.closes(p.lookback_days), p.lookback_days)
        if len(r) < 3:
            return {}
        dev = r - r.mean()
        if p.weighting == "proportional":
            longs = -dev[dev < 0]
            shorts = dev[dev > 0] if p.allow_short else pd.Series(dtype=float)
            total = longs.sum() + shorts.sum()
            if total <= 0:
                return {}
            out = {s: float(v / total) for s, v in longs.items()}
            out.update({s: -float(v / total) for s, v in shorts.items()})
            return out
        ranked = dev.sort_values().index.tolist()  # biggest laggard first
        return _long_short(ranked, p.fraction, p.allow_short)


# ---------------------------------------------------------------- §3.9.1 mean reversion, multiple clusters
def _default_clusters() -> dict[str, list[str]]:
    return {
        "tech": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AVGO"],
        "consumer": ["AMZN", "TSLA", "HD", "COST", "WMT", "PG"],
        "health": ["LLY", "UNH", "JNJ", "ABBV"],
        "fin_energy": ["JPM", "V", "MA", "XOM"],
    }


class MeanReversionMultiParams(BaseModel):
    lookback_days: int = Field(20, ge=2, le=252)
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    clusters: dict[str, list[str]] = Field(default_factory=_default_clusters)
    model_config = {"extra": "forbid"}


class MeanReversionMulti(DailyStrategy):
    name = "mean_reversion_multi"
    params_model = MeanReversionMultiParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = self.p.lookback_days + 2

    def _cluster(self, s: str) -> str:
        for name, members in self.p.clusters.items():
            if s in members:
                return name
        return "other"

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        r = _window_returns(w.closes(p.lookback_days), p.lookback_days)
        if len(r) < 3:
            return {}
        groups: dict[str, list[str]] = {}
        for s in r.index:
            groups.setdefault(self._cluster(s), []).append(s)
        longs: list[str] = []
        shorts: list[str] = []
        for members in groups.values():
            if len(members) < 2:
                continue
            dev = (r[members] - r[members].mean()).sort_values()
            n = max(1, int(len(members) * p.fraction))
            longs += dev.index[:n].tolist()
            if p.allow_short:
                shorts += [s for s in dev.index[-n:].tolist() if s not in dev.index[:n]]
        if not longs and not shorts:
            return {}
        wgt = 1.0 / (len(longs) + len(shorts))
        out = {s: wgt for s in longs}
        out.update({s: -wgt for s in shorts})
        return out


# ---------------------------------------------------------------- §3.10 mean reversion, weighted by 1/σ
class MeanReversionWeightedParams(BaseModel):
    lookback_days: int = Field(20, ge=2, le=252)
    vol_days: int = Field(63, ge=5, le=252)
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class MeanReversionWeighted(DailyStrategy):
    name = "mean_reversion_weighted"
    params_model = MeanReversionWeightedParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = max(self.p.lookback_days, self.p.vol_days) + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        c = w.closes(max(p.lookback_days, p.vol_days) + 1)
        r = _window_returns(c.iloc[-p.lookback_days :], p.lookback_days)
        vol = c.iloc[-(p.vol_days + 1) :].pct_change().std() * math.sqrt(252)
        ok = r.index[(vol[r.index] > 0) & vol[r.index].notna()]
        r = r[ok]
        if len(r) < 3:
            return {}
        wdev = ((r - r.mean()) / vol[r.index]).sort_values()  # most negative first
        n = max(1, int(len(wdev) * p.fraction))
        longs = wdev.index[:n].tolist()
        shorts = [s for s in wdev.index[-n:].tolist() if s not in longs] if p.allow_short else []
        inv = {s: 1.0 / vol[s] for s in longs + shorts}
        total = sum(inv.values())
        out = {s: inv[s] / total for s in longs}
        out.update({s: -inv[s] / total for s in shorts})
        return out


# ---------------------------------------------------------------- §3.20 alpha combo (momentum + reversal + low vol)
class AlphaComboParams(BaseModel):
    momentum_days: int = Field(252, ge=20, le=504)
    momentum_skip: int = Field(21, ge=0, le=63)
    reversal_days: int = Field(5, ge=2, le=21)
    vol_days: int = Field(63, ge=20, le=252)
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class AlphaCombo(DailyStrategy):
    name = "alpha_combo"
    params_model = AlphaComboParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = max(self.p.momentum_days + self.p.momentum_skip, self.p.vol_days, self.p.reversal_days) + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        c = w.closes(self.warmup)
        zs = []
        if len(c) >= p.momentum_days + p.momentum_skip:
            end = c.iloc[-(p.momentum_skip + 1)] if p.momentum_skip else c.iloc[-1]
            zs.append(_zscore((end / c.iloc[-(p.momentum_days + p.momentum_skip)] - 1).dropna()))
        if len(c) >= p.reversal_days + 1:
            zs.append(_zscore(-(c.iloc[-1] / c.iloc[-(p.reversal_days + 1)] - 1).dropna()))
        if len(c) >= p.vol_days:
            zs.append(_zscore(-(c.iloc[-p.vol_days :].pct_change().std() * math.sqrt(252)).dropna()))
        if not zs:
            return {}
        composite = pd.concat(zs, axis=1).mean(axis=1).dropna()
        ranked = composite.sort_values(ascending=False).index.tolist()
        return _long_short(ranked, p.fraction, p.allow_short)


# ---------------------------------------------------------------- §3.4 low volatility
class LowVolParams(BaseModel):
    vol_days: int = Field(126, ge=20, le=504)
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class LowVolatility(DailyStrategy):
    name = "low_volatility"
    params_model = LowVolParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = self.p.vol_days + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        c = w.closes(p.vol_days + 1)
        if len(c) < p.vol_days:
            return {}
        vol = (c.pct_change().std() * math.sqrt(252)).dropna()
        vol = vol[vol > 0]
        ranked = vol.sort_values().index.tolist()  # lowest volatility first = buy
        return _long_short(ranked, p.fraction, p.allow_short)


# ---------------------------------------------------------------- §3.6 multifactor: average demeaned ranks
class MultifactorParams(BaseModel):
    formation_days: int = Field(231, ge=20, le=504)
    skip_days: int = Field(21, ge=0, le=63)
    vol_days: int = Field(126, ge=20, le=504)
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class Multifactor(DailyStrategy):
    name = "multifactor"
    params_model = MultifactorParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = max(self.p.formation_days + self.p.skip_days, self.p.vol_days) + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        c = w.closes(self.warmup)
        if len(c) < self.warmup - 2:
            return {}
        end = c.iloc[-(p.skip_days + 1)] if p.skip_days else c.iloc[-1]
        mom = (end / c.iloc[-(p.formation_days + p.skip_days)] - 1).dropna()
        vol = (c.iloc[-p.vol_days :].pct_change().std() * math.sqrt(252)).dropna()
        common = mom.index.intersection(vol.index)
        if len(common) < 3:
            return {}
        score = (mom[common].rank() - mom[common].rank().mean()) + (
            (-vol[common]).rank() - (-vol[common]).rank().mean()
        )
        ranked = score.sort_values(ascending=False).index.tolist()
        return _long_short(ranked, p.fraction, p.allow_short)


# ------------------------------------------------ §4.1 sector rotation (4.1.1 MA filter, 4.1.2 dual momentum)
class SectorRotationParams(BaseModel):
    formation_days: int = Field(126, ge=20, le=504)
    top_n: int = Field(3, ge=1)
    ma_filter_days: int = Field(0, ge=0)  # 4.1.1: buy only if price > its own MA; 0 = off
    dual_momentum_days: int = Field(0, ge=0)  # 4.1.2: need benchmark > its MA, else hold the defensive ETF; 0 = off
    defensive: str = "IEF"
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class SectorRotation(DailyStrategy):
    name = "sector_rotation"
    params_model = SectorRotationParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = max(self.p.formation_days, self.p.ma_filter_days, self.p.dual_momentum_days) + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        if p.dual_momentum_days:
            b = w.series(w.benchmark, p.dual_momentum_days)
            if len(b) < p.dual_momentum_days or b.iloc[-1] <= _sma(b, p.dual_momentum_days):
                return {p.defensive: 1.0} if p.defensive in w.close.columns else {}
        mom = _window_returns(w.closes(p.formation_days), p.formation_days)
        if len(mom) < 2:
            return {}
        ranked = mom.sort_values(ascending=False).index.tolist()
        longs = ranked[: p.top_n]
        if p.ma_filter_days:
            longs = [s for s in longs if _above_ma(w.series(s, p.ma_filter_days), p.ma_filter_days)]
        shorts = ranked[-p.top_n :] if p.allow_short else []
        shorts = [s for s in shorts if s not in longs]
        if not longs and not shorts:
            return {}
        wgt = 1.0 / (len(longs) + len(shorts))
        out = {s: wgt for s in longs}
        out.update({s: -wgt for s in shorts})
        return out


# ---------------------------------------------------------------- §4.6 multi-asset trend following
class MultiAssetTrendParams(BaseModel):
    formation_days: int = Field(126, ge=20, le=504)
    ma_filter_days: int = Field(200, ge=0)
    vol_days: int = Field(63, ge=10, le=252)
    weighting: str = Field("mom_over_var", pattern="^(mom|mom_over_vol|mom_over_var|equal)$")  # book eqs. 371-373
    max_weight: float = Field(0.4, gt=0, le=1)
    model_config = {"extra": "forbid"}


class MultiAssetTrend(DailyStrategy):
    name = "multi_asset_trend"
    params_model = MultiAssetTrendParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = max(self.p.formation_days, self.p.ma_filter_days, self.p.vol_days) + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        mom = _window_returns(w.closes(p.formation_days), p.formation_days)
        keep = mom[mom > 0]
        if p.ma_filter_days:
            keep = keep[[s for s in keep.index if _above_ma(w.series(s, p.ma_filter_days), p.ma_filter_days)]]
        if keep.empty:
            return {}
        vol = w.closes(p.vol_days + 1, keep.index.tolist()).pct_change().std() * math.sqrt(252)
        if p.weighting == "equal":
            raw = pd.Series(1.0, index=keep.index)
        elif p.weighting == "mom":
            raw = keep
        elif p.weighting == "mom_over_vol":
            raw = keep / vol[keep.index]
        else:
            raw = keep / vol[keep.index] ** 2
        raw = raw.replace([np.inf, -np.inf], np.nan).dropna()
        if raw.empty or raw.sum() <= 0:
            return {}
        wts = (raw / raw.sum()).clip(upper=p.max_weight)
        return {s: float(v) for s, v in wts.items()}


# ---------------------------------------------------------------- §4.4 ETF mean reversion on internal bar strength
class IbsParams(BaseModel):
    fraction: float = Field(0.3, gt=0, le=0.5)
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class IbsMeanReversion(DailyStrategy):
    """IBS = (close − low) / (high − low) of the last bar; buy the lowest (cheap), short the highest."""

    name = "ibs_mean_reversion"
    params_model = IbsParams
    warmup = 2

    def targets(self, w: Window) -> dict[str, float]:
        cols = [s for s in w.symbols if s in w.close.columns]
        h, lo, c = w.high[cols].iloc[-1], w.low[cols].iloc[-1], w.close[cols].iloc[-1]
        rng = h - lo
        ibs = ((c - lo) / rng).where(rng > 0).dropna()
        ranked = ibs.sort_values().index.tolist()  # lowest IBS first = buy
        return _long_short(ranked, self.p.fraction, self.p.allow_short)


# ---------------------------------------------------------------- §6.5 volatility targeting
class VolTargetParams(BaseModel):
    symbol: str = "SPY"
    target_vol: float = Field(0.15, gt=0)
    vol_days: int = Field(20, ge=5, le=252)
    max_leverage: float = Field(1.0, gt=0, le=3)
    rebalance_threshold: float = Field(0.05, ge=0)  # only move when |Δw|/w exceeds this
    model_config = {"extra": "forbid"}


class VolTargeting(DailyStrategy):
    name = "vol_targeting"
    params_model = VolTargetParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = self.p.vol_days + 2
        self._last_w: float | None = None

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        s = w.series(p.symbol, p.vol_days + 1)
        if len(s) < p.vol_days + 1:
            return {}
        vol = float(s.pct_change().std() * math.sqrt(252))
        if not vol or math.isnan(vol):
            return {}
        target = min(p.max_leverage, p.target_vol / vol)
        if (
            self._last_w is not None
            and self._last_w > 0
            and abs(target - self._last_w) / self._last_w < p.rebalance_threshold
        ):
            target = self._last_w
        self._last_w = target
        return {p.symbol: target}


# ---------------------------------------------------------------- §3.11-3.13 moving-average rules on one symbol
class MaRuleParams(BaseModel):
    symbol: str = "SPY"
    fast: int = Field(20, ge=1)
    slow: int = Field(50, ge=2)
    third: int = Field(0, ge=0)  # 3.13: fast < mid < slow uses fast, slow=mid, third=slow
    allow_short: bool = False
    model_config = {"extra": "forbid"}


class MovingAverageRule(DailyStrategy):
    """fast=1 gives the single-MA rule (price vs MA); fast<slow gives two MAs; third>0 the three-MA rule."""

    name = "ma_rule"
    params_model = MaRuleParams

    def __init__(self, params=None):
        super().__init__(params)
        self.warmup = max(self.p.slow, self.p.third) + 2

    def targets(self, w: Window) -> dict[str, float]:
        p = self.p
        s = w.series(p.symbol, self.warmup)
        if len(s) < max(p.slow, p.third):
            return {}
        fast = _sma(s, p.fast) if p.fast > 1 else float(s.iloc[-1])
        slow = _sma(s, p.slow)
        if p.third:
            third = _sma(s, p.third)
            long = fast > slow > third
            short = fast < slow < third
        else:
            long, short = fast > slow, fast < slow
        if long:
            return {p.symbol: 1.0}
        if short and p.allow_short:
            return {p.symbol: -1.0}
        return {}


# ---------------------------------------------------------------- registry
DAILY_REGISTRY: dict[str, type[DailyStrategy]] = {
    c.name: c
    for c in (
        PriceMomentum,
        ResidualMomentum,
        MeanReversion,
        MeanReversionMulti,
        MeanReversionWeighted,
        AlphaCombo,
        LowVolatility,
        Multifactor,
        SectorRotation,
        MultiAssetTrend,
        IbsMeanReversion,
        VolTargeting,
        MovingAverageRule,
    )
}


def build_daily(kind: str, params: dict | None = None) -> DailyStrategy:
    if kind not in DAILY_REGISTRY:
        raise KeyError(f"unknown daily strategy {kind!r}; known: {sorted(DAILY_REGISTRY)}")
    return DAILY_REGISTRY[kind](params)
