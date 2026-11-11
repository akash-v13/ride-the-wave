"""Conditional signals from the 9 November 2026 shortlist: the pure parts (no I/O).

The owner's direction is to hunt for signals that repeat under stated conditions and to use each only
when its condition holds (docs/strategies/2026-11-09-signal-shortlist.md). This module holds the
conditions and rankings of the first three tested (docs/research/2026-11-10-signals-a-c-d.md):
- **Turn of the month** (signal D): which sessions are the last of a month or the first three of the next.
- **Sector stress** (signal A): which sector ETFs have moved unusually far from the market in a week.
- **Momentum for one night** (signal C): the twelve-month return, skipping the latest month, as known
  the day before.
``mean_difference`` is the test all calendar signals share: are the flagged days better than the rest?

Every function takes wide frames or a date index and looks only backwards, so a research script and a
live slot can use the same code.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def month_position(index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """Each session's place in its month: counted from the start (1 = first session) and from the end
    (1 = last session).

    The count from the end is NaN in the index's final month: from the dates alone there is no telling
    whether that month is over, and marking its last row as a month-end would be a guess."""
    idx = pd.DatetimeIndex(index)
    month = pd.Series(idx.year * 12 + idx.month, index=idx)
    from_start = month.groupby(month).cumcount() + 1
    from_end = (month.groupby(month).cumcount(ascending=False) + 1).astype(float)
    from_end[month == month.iloc[-1]] = np.nan
    return from_start, from_end


def turn_of_month(index: pd.DatetimeIndex, before: int = 1, after: int = 3) -> pd.Series:
    """True on the last ``before`` sessions of a month and the first ``after`` of the next
    (McConnell and Xu 2008 use 1 and 3).

    The index should begin at a month's first session; otherwise its first rows are counted as one."""
    from_start, from_end = month_position(index)
    return (from_start <= after) | (from_end <= before)


def sector_stress(
    sector_rets: pd.DataFrame,
    market_ret: pd.Series,
    k: int = 5,
    window: int = 252,
    min_obs: int = 200,
    quantile: float = 0.9,
) -> pd.DataFrame:
    """True where a sector's ``k``-session move beyond the market is unusually large for that sector.

    The size is the absolute sum of the sector's daily returns minus the market's over ``k`` sessions
    ending at the row. It is compared with the ``quantile`` of its own values over the ``window``
    sessions **before** the row, so the threshold never includes the day it judges. False until
    ``min_obs`` earlier values exist."""
    size = sector_rets.sub(market_ret, axis=0).rolling(k, min_periods=k).sum().abs()
    usual = size.rolling(window, min_periods=min_obs).quantile(quantile).shift(1)
    return (size >= usual) & usual.notna()


def momentum_12_1(close: pd.DataFrame, look: int = 252, skip: int = 21, lag: int = 1) -> pd.DataFrame:
    """Each stock's return from ``look`` to ``skip`` sessions ago, as known ``lag`` sessions before the
    row. With ``lag`` = 1 the row for day t uses closes up to t-1 only, which is what an order sent
    before today's close can know."""
    return close.shift(lag + skip) / close.shift(lag + look) - 1


def mean_difference(y: pd.Series, flag: pd.Series, lags: int = 5) -> dict[str, float]:
    """How much higher ``y`` averages on flagged rows than on the rest, with a t-statistic that allows
    for neighbouring rows moving together (Newey-West, ``lags`` lags).

    It is the slope b in y = a + b * flag + e. Returns the two averages, b and its t."""
    d = pd.DataFrame({"y": y, "f": flag.astype(float)}).dropna()
    n = len(d)
    f = d["f"].to_numpy()
    out = {"flagged": float("nan"), "rest": float("nan"), "difference": float("nan"), "t": float("nan"),
           "n_flagged": int(f.sum()), "n": n}  # fmt: skip
    if n < 10 or f.sum() < 2 or f.sum() > n - 2:
        return out
    x = np.column_stack([np.ones(n), f])
    yv = d["y"].to_numpy()
    xtx_inv = np.linalg.inv(x.T @ x)
    beta = xtx_inv @ x.T @ yv
    u = x * (yv - x @ beta)[:, None]  # each row's score
    s = u.T @ u
    for k in range(1, lags + 1):
        g = u[k:].T @ u[:-k]
        s += (1 - k / (lags + 1)) * (g + g.T)
    var_b = (xtx_inv @ s @ xtx_inv)[1, 1]
    out.update(
        flagged=float(yv[f == 1].mean()),
        rest=float(yv[f == 0].mean()),
        difference=float(beta[1]),
        t=float(beta[1] / math.sqrt(var_b)) if var_b > 0 else float("nan"),
    )
    return out


def price_at(minutes: np.ndarray, closes: np.ndarray, t: int) -> float:
    """The last traded price known at minute ``t`` of a session, from minute bars.

    ``minutes`` are the bars' start times in whole minutes since 09:30, oldest first, and ``closes``
    their closing prices. The bar that starts at minute k ends at k+1, so the price at ``t`` is the
    close of the latest bar starting before ``t``. NaN when nothing has traded yet."""
    k = int(np.searchsorted(minutes, t, side="left")) - 1
    return float(closes[k]) if k >= 0 else float("nan")


def news_move(
    minutes: np.ndarray,
    closes: np.ndarray,
    spy_minutes: np.ndarray,
    spy_closes: np.ndarray,
    t0: int,
    beta: float,
    before: int = 5,
    after: int = 5,
) -> float:
    """A stock's move around a headline published in minute ``t0``, with the market taken out: from
    ``before`` minutes earlier to ``after`` minutes later, less ``beta`` times SPY's move over the same
    minutes. Everything in it is known at ``t0 + after``. NaN when either price is missing."""
    a0, a1 = price_at(minutes, closes, t0 - before), price_at(minutes, closes, t0 + after)
    s0, s1 = price_at(spy_minutes, spy_closes, t0 - before), price_at(spy_minutes, spy_closes, t0 + after)
    if not (a0 > 0 and a1 > 0 and s0 > 0 and s1 > 0):
        return float("nan")
    return (a1 / a0 - 1) - beta * (s1 / s0 - 1)
