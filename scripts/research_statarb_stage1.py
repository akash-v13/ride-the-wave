"""Statistical arbitrage, stage 1 (2026-11-02): do stocks' residual moves reverse over 1 to 5 days?

The design and the kill test were fixed before running: docs/research/2026-11-02-statarb-stage1.md,
section 2. Point-in-time top 300 company stocks by dollar volume from the survivorship-free panel;
residuals after SPY and each stock's best-matching sector ETF (``ridethewave.daily.residuals``);
signal = the last k sessions' residuals; outcome = the next h sessions' residual from the next open.

    uv run python scripts/research_statarb_stage1.py
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from ridethewave.config import load_settings
from ridethewave.daily.data import load_panel
from ridethewave.daily.panel_store import load_long, monthly_universes
from ridethewave.daily.residuals import assign_sectors, residuals, rolling_betas, sector_series
from ridethewave.daily.universe import SECTOR_ETFS_11
from ridethewave.data.external import load as load_external
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "statarb"
START, END = "2017-01-03", "2026-09-22"
HALVES = {"2017-2021": ("2017-01-01", "2021-12-31"), "2022-2026": ("2022-01-01", "2026-12-31")}
TOP, KS, HS = 300, (1, 3, 5), (1, 3, 5)


def nw_t(x: pd.Series, lags: int) -> float:
    """t-statistic of the mean with a Newey-West (Bartlett) correction for ``lags`` days of overlap."""
    x = x.dropna()
    n = len(x)
    if n < 30:
        return float("nan")
    d = (x - x.mean()).to_numpy()
    s = d @ d / n
    for k in range(1, lags + 1):
        s += 2 * (1 - k / (lags + 1)) * (d[k:] @ d[:-k]) / n
    return float(x.mean() / math.sqrt(s / n))


def cross_section(signal: pd.DataFrame, outcome: pd.DataFrame, member: pd.DataFrame) -> pd.DataFrame:
    """Per day: rank IC of minus the signal with the outcome, the quintile spread (most negative signal
    minus most positive), and the number of names."""
    ok = member & signal.notna() & outcome.notna()
    s = signal.where(ok)
    o = outcome.where(ok)
    n = ok.sum(axis=1)
    pct = s.rank(axis=1, pct=True)
    low = o.where(pct <= 0.2).mean(axis=1)
    high = o.where(pct > 0.8).mean(axis=1)
    rs = (-s).rank(axis=1)
    ro = o.rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0)
    ro = ro.sub(ro.mean(axis=1), axis=0)
    ic = (rs * ro).sum(axis=1) / np.sqrt((rs * rs).sum(axis=1) * (ro * ro).sum(axis=1))
    out = pd.DataFrame({"ic": ic, "spread": low - high, "n": n})
    return out[out["n"] >= 50]


def summarise(daily: pd.DataFrame, h: int, vix: pd.Series) -> dict:
    lags = max(h - 1, 0)

    def block(g: pd.DataFrame) -> dict:
        return {
            "days": int(len(g)),
            "ic": float(g["ic"].mean()),
            "ic_t": nw_t(g["ic"], lags),
            "spread_bp": float(g["spread"].mean() * 1e4),
            "spread_t": nw_t(g["spread"], lags),
            "breakeven_bp": float(g["spread"].mean() * 1e4 / 4),
            "hit": float((g["spread"] > 0).mean()),
        }

    v = vix.reindex(daily.index).ffill()
    return {
        "all": block(daily),
        **{k: block(daily.loc[a:b]) for k, (a, b) in HALVES.items()},
        "vix>=20": block(daily[v >= 20]),
        "vix<20": block(daily[v < 20]),
        # the lead, split by half (reported, not part of the kill test)
        **{f"vix>=20 {k}": block(daily[v >= 20].loc[a:b]) for k, (a, b) in HALVES.items()},
        "years": {str(y): float(g["spread"].mean() * 1e4) for y, g in daily.groupby(daily.index.year)},
        "avg_names": float(daily["n"].mean()),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    long = load_long(5.0, 2e6)
    universes = monthly_universes(long, TOP)
    chosen = sorted({s for lst in universes.values() for s in lst})
    sub = long[long["symbol"].isin(chosen)]
    close = sub.pivot(index="day", columns="symbol", values="close").sort_index()
    open_ = sub.pivot(index="day", columns="symbol", values="open").sort_index().reindex_like(close)
    logger.info("{} names ever in the top {}; {} sessions", len(chosen), TOP, len(close))

    db = Database(load_settings().storage.resolved_db_path())
    etf = load_panel(db, ["SPY", *SECTOR_ETFS_11], date(2016, 1, 1), date.fromisoformat(END))
    e_close = etf.close.reindex(close.index)
    e_open = etf.open.reindex(close.index)

    r = close.pct_change(fill_method=None)
    m = e_close["SPY"].pct_change(fill_method=None)
    sec_r = e_close[SECTOR_ETFS_11].pct_change(fill_method=None)
    sectors = assign_sectors(r, m, sec_r)
    s_i = sector_series(sectors, sec_r)
    b_m, b_s = rolling_betas(r, m, s_i)
    e = residuals(r, m, s_i, b_m.shift(1), b_s.shift(1))
    counts = sectors.loc[START:].iloc[-1].value_counts().to_dict()
    logger.info("sector assignment on the last day: {}", counts)

    days = close.index
    month = pd.Series(days.strftime("%Y-%m"), index=days)
    member = pd.DataFrame(False, index=days, columns=close.columns)
    for mo, names in universes.items():
        rows = month.index[month == mo]
        cols = [x for x in names if x in member.columns]
        if len(rows) and cols:
            member.loc[rows, cols] = True

    vix = load_external("vix")["close"]
    results: dict[str, dict] = {"residual": {}, "raw_control": {}}
    spreads: dict[str, pd.Series] = {}
    for h in HS:
        # outcome: from tomorrow's open to the close h sessions later, hedged with today's betas
        oc = close.shift(-h) / open_.shift(-1) - 1
        m_oc = e_close["SPY"].shift(-h) / e_open["SPY"].shift(-1) - 1
        sec_oc = e_close[SECTOR_ETFS_11].shift(-h) / e_open[SECTOR_ETFS_11].shift(-1) - 1
        s_oc = sector_series(sectors, sec_oc)
        fwd_resid = oc - b_m.mul(m_oc, axis=0) - b_s * s_oc.sub(m_oc, axis=0)
        for k in KS:
            sig = e.rolling(k, min_periods=k).sum()
            daily = cross_section(sig, fwd_resid, member).loc[START:END]
            results["residual"][f"k{k}_h{h}"] = cell = summarise(daily, h, vix)
            spreads[f"k{k}_h{h}"] = daily["spread"]
            raw_daily = cross_section(r.rolling(k, min_periods=k).sum(), oc, member).loc[START:END]
            results["raw_control"][f"k{k}_h{h}"] = summarise(raw_daily, h, vix)
            a, h1, h2 = cell["all"], cell["2017-2021"], cell["2022-2026"]
            logger.info(
                "k={} h={}: spread {:+.1f} bp (t {:+.1f}; halves {:+.1f} / {:+.1f}, t {:+.1f} / {:+.1f}) IC {:+.3f} "
                "break-even {:+.1f} bp | VIX>=20 {:+.1f} bp (t {:+.1f}) | raw {:+.1f} bp",
                k, h, a["spread_bp"], a["spread_t"], h1["spread_bp"], h2["spread_bp"], h1["spread_t"], h2["spread_t"],
                a["ic"], a["breakeven_bp"], cell["vix>=20"]["spread_bp"], cell["vix>=20"]["spread_t"],
                results["raw_control"][f"k{k}_h{h}"]["all"]["spread_bp"],
            )  # fmt: skip
    passing = [
        c
        for c, v in results["residual"].items()
        if v["2017-2021"]["spread_t"] >= 2 and v["2022-2026"]["spread_t"] >= 2 and v["all"]["breakeven_bp"] >= 5
    ]
    results["kill_test"] = {"passing_cells": passing, "verdict": "pass" if passing else "fail"}
    results["sectors_last_day"] = counts
    (OUT / "stage1_results.json").write_text(json.dumps(results, indent=1))
    pd.DataFrame(spreads).to_parquet(OUT / "stage1_daily_spreads.parquet")
    logger.info("kill test: {} (passing cells: {})", results["kill_test"]["verdict"], passing or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
