"""Momentum and short-term reversal over a century, from Ken French's data library (2026-11-02).

docs/research/2026-11-02-momentum-and-reversal-century.md, section 2, fixes the six series run here
before any result: M1 momentum long-short, M2 long-only winners against the market, M3 and M4 the
same scaled by their own volatility, R1 short-term reversal, R2 large-cap reversal. Writes
data/research/ken_french/results.json and the daily series.

R1 and R2 come from Ken French's MONTHLY files. The daily files re-sort every day on days -20 to -1,
so they include yesterday's bid-ask bounce, which no one can trade. That was found on the first run
and is recorded on the research page; the daily versions are still reported, labelled as such.

    uv run python scripts/download_external.py   # ff_* datasets, including the monthly reversal files
    uv run python scripts/research_ken_french.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

from ridethewave.data.external import load as load_external

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "ken_french"
VOL_DAYS, MAX_LEV = 126, 2.0
PERIODS = {
    "1927-2026": ("1927-01-01", "2026-12-31"),
    "1927-1976": ("1927-01-01", "1976-12-31"),
    "1977-2026": ("1977-01-01", "2026-12-31"),
    "2000-2026": ("2000-01-01", "2026-12-31"),
    "2010-2026": ("2010-01-01", "2026-12-31"),
}
EPISODES = {
    "1932 rebound": ("1932-06-01", "1932-08-31"),
    "1933 rebound": ("1933-04-01", "1933-07-31"),
    "2009 rebound": ("2009-03-09", "2009-05-29"),
    "Nov 2020 rotation": ("2020-11-06", "2020-11-13"),
}


def scaled(r: pd.Series, target: float) -> pd.Series:
    """Exposure = target / realised volatility of the previous VOL_DAYS sessions, capped, known a day ahead."""
    lev = (target / (r.rolling(VOL_DAYS).std() * math.sqrt(252))).clip(upper=MAX_LEV).shift(1)
    return (lev * r).dropna()


def describe(r: pd.Series) -> dict:
    """Statistics for an excess-return series (long-short or active): no cash is subtracted."""
    r = r.dropna()
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    trough = dd.idxmin()
    months = (1 + r).resample("ME").prod() - 1
    out = {
        "from": str(r.index[0].date()),
        "ann_return": float(r.mean() * 252),
        "vol": float(r.std() * math.sqrt(252)),
        "sharpe": float(r.mean() / r.std() * math.sqrt(252)),
        "t": float(r.mean() / r.std() * math.sqrt(len(r))),
        "max_dd": float(dd.min()),
        "dd_from": str(eq.loc[:trough].idxmax().date()),
        "dd_to": str(trough.date()),
        "worst_month": float(months.min()),
        "worst_month_at": str(months.idxmin().date()),
        # one-way cost per dollar traded that eats the average return if both legs turn over fully monthly
        "breakeven_bp_full_turnover": float(r.mean() * 21 / 4 * 10_000),
    }
    out["periods"] = {
        k: {
            "sharpe": float(g.mean() / g.std() * math.sqrt(252)),
            "ann_return": float(g.mean() * 252),
            "t": float(g.mean() / g.std() * math.sqrt(len(g))),
            "breakeven_bp": float(g.mean() * 21 / 4 * 10_000),
        }
        for k, (a, b) in PERIODS.items()
        if len(g := r.loc[a:b]) > 500
    }
    out["decades"] = {
        f"{d}s": {"sharpe": float(g.mean() / g.std() * math.sqrt(252)), "breakeven_bp": float(g.mean() * 21 / 4 * 1e4)}
        for d, g in r.groupby((r.index.year // 10) * 10)
        if len(g) > 500
    }
    out["episodes"] = {k: float((1 + r.loc[a:b]).prod() - 1) for k, (a, b) in EPISODES.items() if len(r.loc[a:b]) > 2}
    return out


def describe_monthly(r: pd.Series) -> dict:
    """Statistics for a monthly excess-return series; break-even as in ``describe``."""
    r = r.dropna()
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    trough = dd.idxmin()

    def block(g: pd.Series) -> dict:
        return {
            "sharpe": float(g.mean() / g.std() * math.sqrt(12)),
            "ann_return": float(g.mean() * 12),
            "t": float(g.mean() / g.std() * math.sqrt(len(g))),
            "breakeven_bp": float(g.mean() / 4 * 10_000),
            "pct_months_up": float((g > 0).mean()),
        }

    return {
        "from": str(r.index[0].date()),
        **block(r),
        "vol": float(r.std() * math.sqrt(12)),
        "max_dd": float(dd.min()),
        "dd_from": str(eq.loc[:trough].idxmax().date()),
        "dd_to": str(trough.date()),
        "worst_month": float(r.min()),
        "worst_month_at": str(r.idxmin().date()),
        "breakeven_bp_full_turnover": float(r.mean() / 4 * 10_000),
        "periods": {k: block(g) for k, (a, b) in PERIODS.items() if len(g := r.loc[a:b]) > 24},
        "decades": {f"{d}s": block(g) for d, g in r.groupby((r.index.year // 10) * 10) if len(g) > 24},
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ff = load_external("ff_factors")
    market = ff["Mkt-RF"] + ff["RF"]
    umd = load_external("ff_momentum").iloc[:, 0].rename("UMD")
    st_rev_daily = load_external("ff_st_reversal").iloc[:, 0].rename("ST_Rev_daily")
    st_rev = load_external("ff_st_reversal_monthly").iloc[:, 0].rename("ST_Rev")
    mom = load_external("ff_mom_deciles")
    rev_daily = load_external("ff_rev_deciles")
    rev = load_external("ff_rev_deciles_monthly")

    winners = mom[["Hi PRIOR", "PRIOR 9", "PRIOR 8"]].mean(axis=1)
    days = winners.index.intersection(market.index)
    m2 = (winners.loc[days] - market.loc[days]).rename("winners_minus_market")
    series = {
        "M1 momentum long-short": umd,
        "M2 long-only winners minus market": m2,
        "M3 momentum, volatility-scaled (12%)": scaled(umd, 0.12),
        "M4 winners minus market, volatility-scaled (6%)": scaled(m2, 0.06),
    }
    monthly = {
        "R1 short-term reversal (ST_Rev, monthly re-sort)": st_rev,
        "R2 large-cap reversal (VW bottom minus top decile, monthly re-sort)": rev["Lo PRIOR"] - rev["Hi PRIOR"],
    }
    invalid = {  # daily re-sort including yesterday's close: bid-ask bounce, not a tradable return
        "not valid: ST_Rev daily re-sort": st_rev_daily,
        "not valid: VW decile spread daily re-sort": rev_daily["Lo PRIOR"] - rev_daily["Hi PRIOR"],
    }
    rows = {}
    for label, r in series.items():
        rows[label] = d = describe(r)
        logger.info(
            "{:52} Sharpe {:.2f} (t {:.1f}) ann {:+.1%} vol {:.1%} DD {:.0%} 2000-26 Sharpe {:.2f} b/e {:.1f} bp",
            label, d["sharpe"], d["t"], d["ann_return"], d["vol"], d["max_dd"],
            d["periods"].get("2000-2026", {}).get("sharpe", float("nan")),
            d["periods"].get("2000-2026", {}).get("breakeven_bp", float("nan")),
        )  # fmt: skip
    for label, r in monthly.items():
        rows[label] = d = describe_monthly(r)
        logger.info(
            "{:52} Sharpe {:.2f} (t {:.1f}) ann {:+.1%} vol {:.1%} DD {:.0%} 2000-26 Sharpe {:.2f} b/e {:.1f} bp",
            label, d["sharpe"], d["t"], d["ann_return"], d["vol"], d["max_dd"],
            d["periods"]["2000-2026"]["sharpe"], d["periods"]["2000-2026"]["breakeven_bp"],
        )  # fmt: skip
    for label, r in invalid.items():
        rows[label] = describe(r)
    # context: the winners and the market on their own (long-only absolute returns)
    rows["context: winners (top 30%) absolute"] = describe(winners.loc[days])
    rows["context: market absolute"] = describe(market.loc[days])
    (OUT / "results.json").write_text(json.dumps(rows, indent=1))
    pd.DataFrame(series).to_parquet(OUT / "daily_series.parquet")
    logger.info("results in {}", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
