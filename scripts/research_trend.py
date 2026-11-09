"""Trend-following sleeve study (2026-11-02): docs/research/2026-11-02-trend-following.md.

Part A replays ``trend_following`` on the 21-ETF universe (2017-2026, Alpaca adjusted daily bars)
through the daily engine: the pre-registered base configuration plus four labelled variants.
Part B runs the same weight function on a century of outside data: the US stock market from Ken
French's library (1927 on) and a 10-year Treasury rebuilt from FRED yields (1963 on), so the rule
is judged through 1929, the 1970s, 1987, 2000-02 and 2008 as well as Alpaca's one decade.

    uv run python scripts/download_daily.py --start 2015-06-01 --end 2026-11-02 --universe trend_etfs_21
    uv run python scripts/download_external.py
    uv run python scripts/research_trend.py

Writes daily return series to data/research/trend/ for the sleeve-combination study.
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
from ridethewave.daily import build_daily, load_panel, run_daily
from ridethewave.daily.strategies import TrendParams, trend_weights
from ridethewave.daily.universe import TREND_ETFS_21
from ridethewave.data.external import load as load_external
from ridethewave.data.external import tbill_daily_return, treasury_10y_total_return
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "trend"
START, END = date(2017, 1, 3), date(2026, 10, 30)
COST_BPS = 5.0
REBALANCE_DAYS = 5

# Pre-registered before any result (see the research page, section 2). Count every row: 5 configurations
# on the ETFs, 3 on the long history.
ETF_CONFIGS: dict[str, tuple[str, dict]] = {
    "base": ("trend_following", {}),
    "long_only": ("trend_following", {"allow_short": False}),
    "12m_only": ("trend_following", {"lookbacks": [252]}),
    "no_class_budget": ("trend_following", {"classes": {}}),
    "old_multi_asset_trend": ("multi_asset_trend", {}),  # September's long-only rule, for reference
}

EPISODES = {
    "1929-32 crash": ("1929-09-03", "1932-06-01"),
    "1937-38": ("1937-03-01", "1938-03-31"),
    "1973-74": ("1973-01-11", "1974-10-03"),
    "1987 crash": ("1987-08-25", "1987-12-04"),
    "2000-02": ("2000-03-24", "2002-10-09"),
    "2008-09": ("2007-10-09", "2009-03-09"),
    "Q4 2018": ("2018-09-20", "2018-12-24"),
    "Covid 2020": ("2020-02-19", "2020-03-23"),
    "2022": ("2022-01-03", "2022-10-12"),
    "Tariffs 2025": ("2025-02-19", "2025-04-08"),
}


def stats(r: pd.Series, rf: pd.Series | None = None) -> dict:
    """Curve statistics from daily returns. Sharpe is over cash when ``rf`` is given, else over zero."""
    r = r.dropna()
    eq = (1 + r).cumprod()
    years = len(r) / 252
    ex = r - (rf.reindex(r.index).fillna(0.0) if rf is not None else 0.0)
    dd = eq / eq.cummax() - 1
    trough = dd.idxmin()
    peak = eq.loc[:trough].idxmax()
    return {
        "cagr": float(eq.iloc[-1] ** (1 / years) - 1),
        "vol": float(r.std() * math.sqrt(252)),
        "sharpe": float(ex.mean() / ex.std() * math.sqrt(252)),
        "max_dd": float(dd.min()),
        "dd_from": str(peak.date()),
        "dd_to": str(trough.date()),
        "years": round(years, 1),
    }


def episode(r: pd.Series, a: str, b: str) -> float | None:
    seg = r.loc[a:b]
    return float((1 + seg).prod() - 1) if len(seg) > 5 else None


def corr_monthly(a: pd.Series, b: pd.Series) -> float:
    ma = (1 + a).resample("ME").prod() - 1
    mb = (1 + b).resample("ME").prod() - 1
    j = pd.concat([ma, mb], axis=1).dropna()
    return float(j.corr().iloc[0, 1])


def worst_months(r: pd.Series, market: pd.Series, q: float = 0.1) -> tuple[float, float]:
    """Average monthly return of ``r`` in the market's worst ``q`` of months, and the market's own."""
    mr = (1 + r).resample("ME").prod() - 1
    mm = (1 + market).resample("ME").prod() - 1
    j = pd.concat([mr.rename("r"), mm.rename("m")], axis=1).dropna()
    cut = j["m"].quantile(q)
    bad = j[j["m"] <= cut]
    return float(bad["r"].mean()), float(bad["m"].mean())


# ---------------------------------------------------------------- part A: ETFs through the daily engine
def part_a(db: Database) -> dict[str, pd.Series]:
    panel = load_panel(db, TREND_ETFS_21, date(2016, 1, 1), END)
    spy = panel.close["SPY"].pct_change()
    rf = tbill_daily_return()
    out: dict[str, pd.Series] = {}
    rows = []
    for label, (kind, params) in ETF_CONFIGS.items():
        res = run_daily(
            build_daily(kind, params),
            panel,
            START,
            END,
            universe=TREND_ETFS_21,
            slippage_bps=COST_BPS,
            rebalance_days=REBALANCE_DAYS,
            max_gross=2.0,
        )
        r = res.equity.pct_change().dropna()
        out[label] = r
        s = stats(r, rf)
        half1, half2 = stats(r.loc[:"2021-12-31"], rf), stats(r.loc["2022-01-01":], rf)
        gross = res.weights.abs().sum(axis=1)
        net = res.weights.sum(axis=1)
        # The engine pays no interest on cash. A futures account (how published trend records are kept)
        # earns T-bills on its net cash balance, 1 - net exposure; a retail stock account mostly does not.
        held = res.weights.fillna(0.0).reindex(r.index).ffill().shift(1).fillna(0.0)
        r_int = r + rf.reindex(r.index).fillna(0.0) * (1 - held.sum(axis=1))
        out[f"{label}+interest"] = r_int
        si = stats(r_int, rf)
        wm, mm = worst_months(r, spy.loc[r.index])
        if label == "base":
            rets = panel.close.pct_change().reindex(r.index)
            cls = TrendParams().classes
            contrib = (held * rets[held.columns]).fillna(0.0)
            by_class = {c: float(contrib[[x for x in contrib.columns if cls.get(x) == c]].sum(axis=1).mean() * 252)
                        for c in sorted(set(cls.values()))}  # fmt: skip
            (OUT / "etf_base_by_class.json").write_text(json.dumps(by_class, indent=1))
        rows.append(
            {
                "config": label,
                **{k: s[k] for k in ("cagr", "vol", "sharpe", "max_dd", "dd_from", "dd_to")},
                "cagr_with_interest": si["cagr"],
                "sharpe_with_interest": si["sharpe"],
                "max_dd_with_interest": si["max_dd"],
                "sharpe_2017_21": half1["sharpe"],
                "sharpe_2022_26": half2["sharpe"],
                "corr_spy_daily": float(r.corr(spy.loc[r.index])),
                "corr_spy_monthly": corr_monthly(r, spy.loc[r.index]),
                "worst10pct_months": wm,
                "spy_in_those": mm,
                "avg_gross": float(gross.mean()),
                "avg_net": float(net.mean()),
                **{f"ep:{k}": episode(r, a, b) for k, (a, b) in EPISODES.items() if a >= "2017"},
                "years": {str(y): float((1 + g).prod() - 1) for y, g in r.groupby(r.index.year)},
            }
        )
        logger.info(
            "A {:22} CAGR {:+.1%} vol {:.1%} Sharpe {:.2f} DD {:.1%}",
            label,
            s["cagr"],
            s["vol"],
            s["sharpe"],
            s["max_dd"],
        )
    spy_r = spy.loc[out["base"].index]
    rows.append(
        {
            "config": "SPY buy and hold",
            **{k: v for k, v in stats(spy_r, rf).items() if k != "years"},
            **{f"ep:{k}": episode(spy_r, a, b) for k, (a, b) in EPISODES.items() if a >= "2017"},
            "years": {str(y): float((1 + g).prod() - 1) for y, g in spy_r.groupby(spy_r.index.year)},
        }
    )
    out["SPY"] = spy_r
    (OUT / "etf_results.json").write_text(json.dumps(rows, indent=1, default=str))
    pd.DataFrame(out).to_parquet(OUT / "etf_daily_returns.parquet")
    return out


# ---------------------------------------------------------------- part B: a century on outside data
def run_on_returns(rets: pd.DataFrame, rf: pd.Series, p: TrendParams, start: str) -> tuple[pd.Series, pd.DataFrame]:
    """The engine's rule on return series: weights from ``trend_weights`` on the close every
    REBALANCE_DAYS sessions, applied from the next session; collateral earns cash; COST_BPS per unit
    of turnover. Close-to-close instead of next-open fills: the outside series have no opens."""
    px = (1 + rets.fillna(0.0)).cumprod()
    px[rets.isna()] = np.nan
    window = max(max(p.lookbacks) + 1, p.cov_days + 1, 4 * p.vol_com)
    idx = rets.index
    w = pd.Series(0.0, index=rets.columns)
    weights = {}
    first = idx.get_indexer([pd.Timestamp(start)], method="bfill")[0]
    for k, i in enumerate(range(first, len(idx))):
        if k % REBALANCE_DAYS == 0:
            tgt = trend_weights(px.iloc[max(0, i - window + 1) : i + 1], p)
            w = pd.Series(tgt, index=rets.columns).fillna(0.0)
        weights[idx[i]] = w
    W = pd.DataFrame(weights).T
    held = W.shift(1).fillna(0.0)
    cash = rf.reindex(idx).fillna(0.0).loc[W.index]
    excess = rets.loc[W.index].sub(cash, axis=0).fillna(0.0)
    turnover = W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
    r = (held * excess).sum(axis=1) + cash - turnover * COST_BPS / 10_000
    return r, W


def part_b() -> dict[str, pd.Series]:
    ff = load_external("ff_factors")
    rf = ff["RF"]
    market = (ff["Mkt-RF"] + ff["RF"]).rename("market")
    # The bond on the stock market's sessions: FRED has yields on days the exchange was shut (Wednesdays in
    # 1968, 9/11) and runs a month past Ken French's last update, so compound it onto the market's dates.
    bond_idx = (1 + treasury_10y_total_return()).cumprod()
    days = market.index[(market.index >= bond_idx.index[0]) & (market.index <= bond_idx.index[-1])]
    bond = bond_idx.reindex(bond_idx.index.union(days)).ffill().reindex(days).pct_change().dropna().rename("bond")
    classes = {"market": "equity", "bond": "bond"}
    rows, out = [], {}

    stock_only, _ = run_on_returns(market.to_frame(), rf, TrendParams(classes=classes, max_gross=2.0), "1927-07-01")
    rets2 = pd.concat([market, bond], axis=1, join="inner").loc["1962-01-01":]
    two, W2 = run_on_returns(rets2, rf, TrendParams(classes=classes, max_gross=2.0), "1963-01-02")
    two_lo, _ = run_on_returns(rets2, rf, TrendParams(classes=classes, max_gross=2.0, allow_short=False), "1963-01-02")
    mkt_bh = market.loc[stock_only.index]
    m6040 = (0.6 * market + 0.4 * bond).loc[two.index]  # rebalanced daily: close enough to monthly for this
    for label, r in [
        ("trend: US stocks only, 1927-2026", stock_only),
        ("US stocks buy and hold, 1927-2026", mkt_bh),
        ("trend: stocks + 10y Treasury, 1963-2026", two),
        ("trend: same, long-only", two_lo),
        ("60/40 stocks/10y Treasury, 1963-2026", m6040),
        ("US stocks buy and hold, 1963-2026", market.loc[two.index]),
    ]:
        s = stats(r, rf)
        mk = market.loc[r.index]
        wm, mm = worst_months(r, mk)
        rows.append(
            {
                "config": label,
                **{k: s[k] for k in ("cagr", "vol", "sharpe", "max_dd", "dd_from", "dd_to", "years")},
                "corr_market_monthly": corr_monthly(r, mk),
                "worst10pct_months": wm,
                "market_in_those": mm,
                **{f"ep:{k}": episode(r, a, b) for k, (a, b) in EPISODES.items()},
                "decades": {
                    f"{d}s": stats(g, rf)["sharpe"] for d, g in r.groupby((r.index.year // 10) * 10) if len(g) > 500
                },
                "decade_cagr": {
                    f"{d}s": float((1 + g).prod() ** (252 / len(g)) - 1)
                    for d, g in r.groupby((r.index.year // 10) * 10)
                    if len(g) > 500
                },
            }
        )
        out[label] = r
        logger.info(
            "B {:42} CAGR {:+.1%} vol {:.1%} Sharpe {:.2f} DD {:.1%}",
            label,
            s["cagr"],
            s["vol"],
            s["sharpe"],
            s["max_dd"],
        )
    # check the rebuilt Treasury against IEF over the years both exist (IEF is 7-10y, so shorter duration)
    rows.append(
        {"config": "bond proxy check", "bond_proxy_cagr_2017_26": stats(bond.loc["2017-01-03":"2026-10-30"])["cagr"]}
    )
    (OUT / "history_results.json").write_text(json.dumps(rows, indent=1, default=str))
    pd.DataFrame(out).to_parquet(OUT / "history_daily_returns.parquet")
    W2.to_parquet(OUT / "history_two_asset_weights.parquet")
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    s = load_settings()
    db = Database(s.storage.resolved_db_path())
    part_a(db)
    part_b()
    logger.info("results in {}", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
