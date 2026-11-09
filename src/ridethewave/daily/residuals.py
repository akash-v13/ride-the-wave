"""Residual returns: what is left of a stock's move after its market and its sector are taken out.

Statistical arbitrage bets on residuals, not on raw returns: when a bank stock falls 3% on a day banks
fell 2.5% and the market 1%, the stock-specific part is the small piece that may revert. A raw-return
ranking would mostly be ranking sectors (docs/research/2026-11-02-statarb-stage1.md).

Two regressors, as in Avellaneda and Lee (2010), "Statistical arbitrage in the US equities market":

    r_i = a + b_m * r_SPY + b_s * (r_sector - r_SPY) + e_i

- **Sector.** Each stock's sector ETF is the one whose moves (beyond SPY's) correlated best with the
  stock's own over the previous year, re-chosen at each month start from prior data only. Alpaca has
  no sector field, and this also follows a company that changes business.
- **Betas.** From a rolling 60-session window that ends the day before, so a residual never uses its
  own day to estimate its betas. The intercept is fitted but not removed: over 60 days it is noise.

Pure functions on wide frames (rows = sessions, columns = symbols). No I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def assign_sectors(
    stock_rets: pd.DataFrame,
    market_ret: pd.Series,
    sector_rets: pd.DataFrame,
    window: int = 252,
    min_obs: int = 126,
) -> pd.DataFrame:
    """A frame like ``stock_rets`` holding each stock's sector ETF symbol per session (NaN until known).

    At the first session of each month, correlate every stock's return beyond SPY with every sector
    ETF's return beyond SPY over the previous ``window`` sessions; the best match holds for the month."""
    ex_stock = stock_rets.sub(market_ret, axis=0)
    ex_sector = sector_rets.sub(market_ret, axis=0)
    idx = stock_rets.index
    month_starts = idx[np.r_[True, idx.month[1:] != idx.month[:-1]]]
    labels = pd.DataFrame(np.nan, index=month_starts, columns=stock_rets.columns, dtype=object)
    for d in month_starts:
        i = idx.get_loc(d)
        if i < min_obs:
            continue
        hist_s = ex_stock.iloc[max(0, i - window) : i]
        hist_x = ex_sector.iloc[max(0, i - window) : i]
        enough_s = hist_s.notna().sum() >= min_obs
        enough_x = hist_x.columns[hist_x.notna().sum() >= min_obs]
        if not enough_s.any() or not len(enough_x):
            continue
        corr = pd.DataFrame({etf: hist_s.loc[:, enough_s].corrwith(hist_x[etf]) for etf in enough_x})
        best = corr.idxmax(axis=1)
        labels.loc[d, best.index] = best.values
    return labels.reindex(idx).ffill()


def sector_series(sectors: pd.DataFrame, sector_rets: pd.DataFrame) -> pd.DataFrame:
    """Each stock's own sector-ETF return per session, following its assignment."""
    code = {etf: k for k, etf in enumerate(sector_rets.columns)}
    codes = sectors.apply(lambda col: col.map(code)).to_numpy(dtype=float)
    etf_rets = sector_rets.reindex(sectors.index).to_numpy(dtype=float)
    out = np.full(sectors.shape, np.nan)
    r, c = np.nonzero(~np.isnan(codes))
    out[r, c] = etf_rets[r, codes[r, c].astype(int)]
    return pd.DataFrame(out, index=sectors.index, columns=sectors.columns)


def rolling_betas(
    stock_rets: pd.DataFrame,
    market_ret: pd.Series,
    stock_sector_rets: pd.DataFrame,
    window: int = 60,
    min_obs: int = 40,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Betas on the market (b_m) and on the sector beyond the market (b_s) from the ``window`` sessions
    ending at each row (inclusive). Shift by one before applying, so that day t uses betas up to t-1.
    Every moment uses the same sessions: the regressors are masked wherever the stock has no return."""
    y = stock_rets
    m = pd.DataFrame(np.repeat(market_ret.reindex(y.index).to_numpy()[:, None], y.shape[1], axis=1),
                     index=y.index, columns=y.columns).where(y.notna())  # fmt: skip
    x = (stock_sector_rets - m).where(y.notna())

    def mean(f: pd.DataFrame) -> pd.DataFrame:
        return f.rolling(window, min_periods=min_obs).mean()

    ey, em, ex = mean(y), mean(m), mean(x)
    cmm = mean(m * m) - em * em
    cxx = mean(x * x) - ex * ex
    cmx = mean(m * x) - em * ex
    cym = mean(y * m) - ey * em
    cyx = mean(y * x) - ey * ex
    det = cmm * cxx - cmx * cmx
    det = det.where(det.abs() > 1e-14)
    b_m = (cym * cxx - cyx * cmx) / det
    b_s = (cyx * cmm - cym * cmx) / det
    return b_m, b_s


def residuals(
    stock_rets: pd.DataFrame,
    market_ret: pd.Series,
    stock_sector_rets: pd.DataFrame,
    b_m: pd.DataFrame,
    b_s: pd.DataFrame,
) -> pd.DataFrame:
    """e = r - b_m * r_SPY - b_s * (r_sector - r_SPY), with the betas passed in already lagged."""
    m = market_ret.reindex(stock_rets.index)
    return stock_rets - b_m.mul(m, axis=0) - b_s * stock_sector_rets.sub(m, axis=0)
