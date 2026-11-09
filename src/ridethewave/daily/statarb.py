"""Statistical arbitrage on residuals: the cohort rules, pure (no I/O).

Stage 1 (docs/research/2026-11-02-statarb-stage1.md) found that a stock's residual move (after SPY
and its sector ETF) reverses over about 5 sessions only when the market is stressed. Stage 2a
(docs/research/2026-11-02-statarb-volatility-gated.md) tests that as a rule:
- **Gate.** Form a cohort only when VIX closed at 20 or above the session before.
- **Positions.** Buy the fifth of stocks whose residuals fell most over the last 5 sessions and
  short the fifth that rose most.
- **Hedge.** Hedge their market and sector betas with SPY and the sector ETFs, and hold 5 sessions.

The research script and the live strategy (`statarb_vol_reversal` in strategies.py) both use these
functions. The data the studies share is loaded by ``statarb_data.py``.
"""

from __future__ import annotations

import math

import pandas as pd

from ridethewave.daily.residuals import assign_sectors, residuals, rolling_betas, sector_series


# ---------------------------------------------------------------- pure cohort rules
def signal(resid: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """The sum of each stock's last ``k`` residuals, up to and including the row."""
    return resid.rolling(k, min_periods=k).sum()


def not_a_jump(resid: pd.DataFrame, k: int = 5, vol_days: int = 60, threshold: float = 3.0) -> pd.DataFrame:
    """True where the k-session residual is within ``threshold`` times its normal size (the residual's
    ``vol_days`` volatility times sqrt(k)). Larger moves are usually news, which tends not to reverse."""
    normal = resid.rolling(vol_days, min_periods=40).std() * math.sqrt(k)
    return signal(resid, k).abs() <= threshold * normal


def pick(sig: pd.Series, eligible: pd.Series, fraction: float = 0.2) -> tuple[list[str], list[str]]:
    """Buy the ``fraction`` with the most negative signal, short the ``fraction`` with the most positive."""
    s = sig[eligible.reindex(sig.index, fill_value=False) & sig.notna()]
    if len(s) < 25:
        return [], []
    pct = s.rank(pct=True)
    return pct[pct <= fraction].index.tolist(), pct[pct > 1 - fraction].index.tolist()


def cohort_weights(longs: list[str], shorts: list[str], side: float = 0.2) -> dict[str, float]:
    """Equal weights, ``side`` of capital long and ``side`` short."""
    w = {s: side / len(longs) for s in longs} if longs else {}
    for s in shorts:
        w[s] = w.get(s, 0.0) - side / len(shorts)
    return w


def hedge(weights: dict[str, float], b_m: pd.Series, b_s: pd.Series, sectors: pd.Series) -> dict[str, float]:
    """ETF positions that cancel the stocks' market and sector betas. A stock's exposure is
    b_m * SPY + b_s * (sector - SPY), so the sector ETF takes -sum(w * b_s) and SPY takes
    -sum(w * b_m) + sum(w * b_s)."""
    out: dict[str, float] = {}
    for sym, w in weights.items():
        bm, bs, etf = b_m.get(sym), b_s.get(sym), sectors.get(sym)
        if bm is None or pd.isna(bm) or bs is None or pd.isna(bs) or not isinstance(etf, str):
            continue
        out["SPY"] = out.get("SPY", 0.0) - w * bm + w * bs
        out[etf] = out.get(etf, 0.0) - w * bs
    return {k: v for k, v in out.items() if abs(v) > 1e-9}


def cohort_targets(
    close: pd.DataFrame,
    universe: list[str],
    vix_close: pd.Series,
    sector_etfs: list[str],
    market: str = "SPY",
    k: int = 5,
    hold: int = 5,
    fraction: float = 0.2,
    side: float = 0.2,
    gate: float = 20.0,
) -> tuple[dict[str, float], list[str]]:
    """Target weights for the next session's open: the sum of every cohort still alive, with its hedge.

    ``close`` holds completed sessions only (oldest first) for the stocks, ``market`` and the sector
    ETFs. The cohort entering at session j used data to the close of j-1 and is formed only if VIX
    closed at ``gate`` or above that day. Cohorts live ``hold`` sessions, so the next session holds
    those entering at it and at the ``hold``-1 sessions before. Rebuilding them from history each
    day means the strategy keeps no state: a restart cannot lose a cohort. Returns the weights and
    one line per live cohort for the log."""
    rets = close.pct_change(fill_method=None)
    stocks = [s for s in universe if s in rets.columns and s != market and s not in sector_etfs]
    etfs = [e for e in sector_etfs if e in rets.columns]
    m = rets[market]
    sec_r = rets[etfs]
    sectors = assign_sectors(rets[stocks], m, sec_r)
    s_i = sector_series(sectors, sec_r)
    b_m, b_s = rolling_betas(rets[stocks], m, s_i)
    sig = signal(residuals(rets[stocks], m, s_i, b_m.shift(1), b_s.shift(1)), k)
    eligible = pd.Series(True, index=stocks)
    n = len(close)  # the next session is position n; the cohort entering at j uses row j - 1
    total: dict[str, float] = {}
    notes: list[str] = []
    for j in range(n - hold + 1, n + 1):
        row = j - 1
        if row < 0:
            continue
        day = close.index[row]
        v = vix_close.get(day)
        if v is None or pd.isna(v):
            notes.append(f"{day.date()}: no VIX close, no cohort")
            continue
        if v < gate:
            continue
        longs, shorts = pick(sig.iloc[row], eligible, fraction)
        if not longs or not shorts:
            notes.append(f"{day.date()}: VIX {v:.1f} but too few names, no cohort")
            continue
        w = cohort_weights(longs, shorts, side)
        for sym, x in w.items():
            total[sym] = total.get(sym, 0.0) + x
        for sym, x in hedge(w, b_m.iloc[row], b_s.iloc[row], sectors.iloc[row]).items():
            total[sym] = total.get(sym, 0.0) + x
        notes.append(f"cohort from {day.date()} (VIX {v:.1f}): {len(longs)} long, {len(shorts)} short")
    return {s: x for s, x in total.items() if abs(x) > 1e-9}, notes
