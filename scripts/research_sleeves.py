"""Do the sleeves make each other safer? (2026-11-02, the owner's question 2: a 10% volatility target and a
15% drawdown budget for the combined book.)

Combines daily return series that the two sleeve studies saved:
- the bull put spread, 1990-2026, priced from S&P 500 and VIX history
  (scripts/backtest_put_spread_history.py -> data/research/put_spread_history.parquet);
- trend following on US stocks and the 10-year Treasury, 1963-2026, and on the 21 ETFs, 2017-2026
  (scripts/research_trend.py -> data/research/trend/);
- US stocks held at constant volatility, a stand-in for the equity and momentum sleeves.

Each portfolio gives its sleeves equal risk (weights 1 / trailing one-year volatility) and scales the
whole to 10% volatility from the last 63 sessions, at most 2x, using only past data. Six portfolios,
fixed before the run.

    uv run python scripts/research_sleeves.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

from ridethewave.data.external import load as load_external

ROOT = Path(__file__).resolve().parents[1] / "data" / "research"
OUT = ROOT / "sleeves"
TARGET_VOL, MAX_LEV, VOL_DAYS, WEIGHT_DAYS = 0.10, 2.0, 63, 252
DD_BUDGET = -0.15

PORTFOLIOS = {
    "put spread alone": ["put_spread"],
    "trend alone": ["trend"],
    "stocks alone": ["stocks"],
    "put spread + trend": ["put_spread", "trend"],
    "put spread + stocks": ["put_spread", "stocks"],
    "put spread + trend + stocks": ["put_spread", "trend", "stocks"],
    # added after the first run, once the put spread had failed: the two sleeves that would remain
    "trend + stocks (added after the first run)": ["trend", "stocks"],
}
EPISODES = {
    "1998 LTCM": ("1998-07-17", "1998-10-08"),
    "2000-02": ("2000-03-24", "2002-10-09"),
    "2008-09": ("2007-10-09", "2009-03-09"),
    "Aug 2011": ("2011-07-22", "2011-10-03"),
    "Aug 2015": ("2015-08-17", "2016-02-11"),
    "Feb 2018": ("2018-01-26", "2018-02-08"),
    "Q4 2018": ("2018-09-20", "2018-12-24"),
    "Covid 2020": ("2020-02-19", "2020-03-23"),
    "2022": ("2022-01-03", "2022-10-12"),
    "Tariffs 2025": ("2025-02-19", "2025-04-08"),
}


def combine(rets: pd.DataFrame, rf: pd.Series, target_vol: float = TARGET_VOL) -> pd.Series:
    """Equal-risk sleeves scaled to TARGET_VOL, all from information before each day. Sleeves are excess
    returns over cash plus cash once, so leverage borrows at the cash rate."""
    ex = rets.sub(rf.reindex(rets.index).fillna(0.0), axis=0)
    inv = 1.0 / ex.rolling(WEIGHT_DAYS, min_periods=126).std()
    w = inv.div(inv.sum(axis=1), axis=0).shift(1)
    raw = (w * ex).sum(axis=1, min_count=1)
    lev = (target_vol / (raw.rolling(VOL_DAYS).std() * math.sqrt(252))).clip(upper=MAX_LEV).shift(1)
    return (lev * raw + rf.reindex(raw.index).fillna(0.0)).dropna()


def vol_for_dd_budget(rets: pd.DataFrame, rf: pd.Series) -> float:
    """The volatility target at which the portfolio's worst drawdown would just have stayed inside DD_BUDGET."""
    lo, hi = 0.005, 0.20
    for _ in range(30):
        mid = (lo + hi) / 2
        eq = (1 + combine(rets, rf, mid)).cumprod()
        lo, hi = (mid, hi) if float((eq / eq.cummax() - 1).min()) > DD_BUDGET else (lo, mid)
    return lo


def stats(r: pd.Series, rf: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    ex = r - rf.reindex(r.index).fillna(0.0)
    dd = eq / eq.cummax() - 1
    trough = dd.idxmin()
    monthly = (1 + r).resample("ME").prod() - 1
    return {
        "from": str(r.index[0].date()),
        "to": str(r.index[-1].date()),
        "cagr": float(eq.iloc[-1] ** (252 / len(r)) - 1),
        "vol": float(r.std() * math.sqrt(252)),
        "sharpe": float(ex.mean() / ex.std() * math.sqrt(252)),
        "max_dd": float(dd.min()),
        "dd_from": str(eq.loc[:trough].idxmax().date()),
        "dd_to": str(trough.date()),
        "worst_month": float(monthly.min()),
        "worst_month_at": str(monthly.idxmin().date()),
        "pct_months_up": float((monthly > 0).mean()),
        "days_below_dd_budget": int((dd < DD_BUDGET).sum()),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ff = load_external("ff_factors")
    rf = ff["RF"]
    stocks = ff["Mkt-RF"] + ff["RF"]
    ps = pd.read_parquet(ROOT / "put_spread_history.parquet")["ret"]
    hist = pd.read_parquet(ROOT / "trend" / "history_daily_returns.parquet")
    trend = hist["trend: stocks + 10y Treasury, 1963-2026"].dropna()
    days = ps.index.intersection(trend.index).intersection(stocks.index)
    sleeves = pd.DataFrame({"put_spread": ps, "trend": trend, "stocks": stocks}).loc[days]
    logger.info("common history {} to {}, {} sessions", days[0].date(), days[-1].date(), len(days))

    rows = []
    corr = sleeves.resample("ME").apply(lambda x: (1 + x).prod() - 1).corr()
    for label, cols in PORTFOLIOS.items():
        r = combine(sleeves[cols], rf)
        s = stats(r, rf)
        eps = {k: float((1 + r.loc[a:b]).prod() - 1) for k, (a, b) in EPISODES.items() if len(r.loc[a:b]) > 3}
        s["vol_target_for_15pct_dd"] = vol_for_dd_budget(sleeves[cols], rf)
        rows.append({"portfolio": label, **s, **{f"ep:{k}": v for k, v in eps.items()}})
        logger.info("{:30} CAGR {:+.1%} vol {:.1%} Sharpe {:.2f} DD {:.1%} worst month {:+.1%} vol for -15% DD {:.1%}",
                    label, s["cagr"], s["vol"], s["sharpe"], s["max_dd"], s["worst_month"],
                    s["vol_target_for_15pct_dd"])  # fmt: skip
    # the put spread's 20 worst months: what did trend do in them?
    m = sleeves.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    worst = m.nsmallest(20, "put_spread")
    hedge = {
        "put_spread_avg": float(worst["put_spread"].mean()),
        "trend_avg": float(worst["trend"].mean()),
        "trend_positive_share": float((worst["trend"] > 0).mean()),
        "months": {str(i.date()): {k: float(v) for k, v in row.items()} for i, row in worst.iterrows()},
    }
    (OUT / "results.json").write_text(
        json.dumps(
            {"portfolios": rows, "monthly_corr": corr.round(3).to_dict(), "put_spread_worst_20": hedge}, indent=1
        )  # fmt: skip
    )
    logger.info("monthly correlation:\n{}", corr.round(2))
    logger.info("in the put spread's 20 worst months: put spread {:+.1%}, trend {:+.1%}, trend up in {:.0%}",
                hedge["put_spread_avg"], hedge["trend_avg"], hedge["trend_positive_share"])  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
