"""Statistical arbitrage on residuals: the data the studies share (I/O). The rules are in ``statarb.py``.

Stage 1 (docs/research/2026-11-02-statarb-stage1.md) found that a stock's residual move (after SPY
and its sector ETF) reverses over about 5 sessions only when the market is stressed. Stage 2a
(docs/research/2026-11-02-statarb-volatility-gated.md) tests that as a rule:
- **Gate.** Form a cohort only when VIX closed at 20 or above the session before.
- **Positions.** Buy the fifth of stocks whose residuals fell most over the last 5 sessions and
  short the fifth that rose most.
- **Hedge.** Hedge their market and sector betas with SPY and the sector ETFs, and hold 5 sessions.

``load_inputs`` reads the survivorship-free panel and the ETF bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ridethewave.daily.data import load_panel
from ridethewave.daily.panel_store import load_long, monthly_universes
from ridethewave.daily.residuals import assign_sectors, residuals, rolling_betas, sector_series
from ridethewave.daily.universe import SECTOR_ETFS_11
from ridethewave.storage import Database


@dataclass
class StatArbInputs:
    close: pd.DataFrame  # stocks, adjusted
    open: pd.DataFrame
    etf_close: pd.DataFrame  # SPY and the 11 sector ETFs
    etf_open: pd.DataFrame
    member: pd.DataFrame  # True where the stock is in that month's point-in-time universe
    sectors: pd.DataFrame  # each stock's sector ETF per session
    b_m: pd.DataFrame  # betas from the 60 sessions ending at the row (lag before use)
    b_s: pd.DataFrame
    resid: pd.DataFrame  # close-to-close residuals, computed with the previous session's betas


def load_inputs(db: Database, top: int = 300, end: date = date(2026, 9, 22)) -> StatArbInputs:
    """The point-in-time top ``top`` company stocks from the survivorship-free panel (price at least $5,
    median dollar volume at least $2m), with residuals after SPY and each stock's sector ETF."""
    long = load_long(5.0, 2e6)
    universes = monthly_universes(long, top)
    chosen = sorted({s for lst in universes.values() for s in lst})
    sub = long[long["symbol"].isin(chosen)]
    close = sub.pivot(index="day", columns="symbol", values="close").sort_index()
    open_ = sub.pivot(index="day", columns="symbol", values="open").sort_index().reindex_like(close)
    etf = load_panel(db, ["SPY", *SECTOR_ETFS_11], date(2016, 1, 1), end)
    e_close, e_open = etf.close.reindex(close.index), etf.open.reindex(close.index)

    r = close.pct_change(fill_method=None)
    m = e_close["SPY"].pct_change(fill_method=None)
    sec_r = e_close[SECTOR_ETFS_11].pct_change(fill_method=None)
    sectors = assign_sectors(r, m, sec_r)
    s_i = sector_series(sectors, sec_r)
    b_m, b_s = rolling_betas(r, m, s_i)
    resid = residuals(r, m, s_i, b_m.shift(1), b_s.shift(1))

    month = pd.Series(close.index.strftime("%Y-%m"), index=close.index)
    member = pd.DataFrame(False, index=close.index, columns=close.columns)
    for mo, names in universes.items():
        rows = month.index[month == mo]
        cols = [x for x in names if x in member.columns]
        if len(rows) and cols:
            member.loc[rows, cols] = True
    return StatArbInputs(close, open_, e_close, e_open, member, sectors, b_m, b_s, resid)
