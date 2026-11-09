"""Statistical arbitrage, stage 2a (2026-11-02): residual reversal traded only in volatile markets.

The rule and the pass test were fixed before running: docs/research/2026-11-02-statarb-volatility-gated.md.
On each session d with VIX >= 20 at the previous close, rank the point-in-time top 300 on their
residuals over the 5 sessions to yesterday's close; buy the most negative fifth, short the most
positive fifth (20% of capital a side), hedge betas with SPY and sector ETFs, enter at d's open,
exit at the open five sessions later, 26 bp of costs per round trip. Configuration B first drops
stocks whose 5-day residual is a jump (over 3 times its normal size).

    uv run python scripts/research_statarb_volgated.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

from ridethewave.config import load_settings
from ridethewave.daily.residuals import sector_series
from ridethewave.daily.statarb import not_a_jump, signal
from ridethewave.daily.statarb_data import load_inputs
from ridethewave.daily.universe import SECTOR_ETFS_11
from ridethewave.data.external import load as load_external
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "statarb"
START = "2017-01-03"
HOLD, SIDE, FRACTION, COST, VIX_GATE = 5, 0.2, 0.2, 0.0026, 20.0
HALVES = {"2017-2021": ("2017-01-01", "2021-12-31"), "2022-2026": ("2022-01-01", "2026-12-31")}


def nw_t(x: pd.Series, lags: int) -> float:
    x = x.dropna()
    d = (x - x.mean()).to_numpy()
    n = len(d)
    s = d @ d / n
    for k in range(1, lags + 1):
        s += 2 * (1 - k / (lags + 1)) * (d[k:] @ d[:-k]) / n
    return float(x.mean() / math.sqrt(s / n))


def cohorts(sig: pd.DataFrame, outcome: pd.DataFrame, eligible: pd.DataFrame, gate: pd.Series) -> pd.DataFrame:
    """One row per gated session: the long fifth's and short fifth's mean hedged return, net of costs."""
    ok = eligible & sig.notna() & outcome.notna()
    ok = ok.where(gate.reindex(ok.index, fill_value=False), False)
    s = sig.where(ok)
    o = outcome.where(ok)
    pct = s.rank(axis=1, pct=True)
    n = ok.sum(axis=1)
    longs = o.where(pct <= FRACTION).mean(axis=1)
    shorts = o.where(pct > 1 - FRACTION).mean(axis=1)
    out = pd.DataFrame({"long": longs, "short": shorts, "n": n})
    out = out[out["n"] >= 25].copy()
    out["gross"] = out["long"] - out["short"]
    out["net"] = out["gross"] - COST
    return out


def summarise(c: pd.DataFrame, index: pd.DatetimeIndex) -> dict:
    # each cohort earns SIDE x its net return; book it at its exit, five sessions after entry
    pos = index.get_indexer(c.index)
    exits = index[[min(p + HOLD, len(index) - 1) for p in pos]]
    pnl = pd.Series((SIDE * c["net"]).to_numpy(), index=exits).groupby(level=0).sum()
    monthly = pnl.resample("ME").sum().reindex(pd.date_range(index[0], index[-1], freq="ME"), fill_value=0.0)
    eq = (1 + monthly).cumprod()

    def block(g: pd.DataFrame, mon: pd.Series) -> dict:
        return {
            "cohorts": int(len(g)),
            "net_bp": float(g["net"].mean() * 1e4),
            "gross_bp": float(g["gross"].mean() * 1e4),
            "t": nw_t(g["net"], HOLD - 1),
            "hit": float((g["net"] > 0).mean()),
            "return_on_capital_a_year": float(mon.mean() * 12),
            "sharpe": float(mon.mean() / mon.std() * math.sqrt(12)) if mon.std() > 0 else 0.0,
        }

    active = pd.Series(0, index=index)
    for p in pos:
        active.iloc[p : p + HOLD] = 1
    return {
        "all": block(c, monthly),
        **{k: block(c.loc[a:b], monthly.loc[a:b]) for k, (a, b) in HALVES.items()},
        "vol_a_year": float(monthly.std() * math.sqrt(12)),
        "max_dd": float((eq / eq.cummax() - 1).min()),
        "worst_month": float(monthly.min()),
        "worst_month_at": str(monthly.idxmin().date()),
        "worst_cohort_bp": float(c["net"].min() * 1e4),
        "worst_cohort_at": str(c["net"].idxmin().date()),
        "time_invested": float(active.loc[START:].mean()),
        "avg_names_per_side": float(c["n"].mean() * FRACTION),
        "years": {
            str(y): {
                "cohorts": int(len(g)),
                "net_bp": float(g["net"].mean() * 1e4),
                "on_capital": float(SIDE * g["net"].sum()),
            }
            for y, g in c.groupby(c.index.year)
        },  # fmt: skip
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
    idx = inp.close.index
    vix = load_external("vix")["close"].reindex(idx).ffill()
    gate = (vix.shift(1) >= VIX_GATE).loc[START:]  # yesterday's close, published after the market shut

    sig_prev = signal(inp.resid).shift(1)  # residuals to yesterday's close
    keep_prev = not_a_jump(inp.resid).shift(1)
    bm, bs = inp.b_m.shift(1), inp.b_s.shift(1)  # betas known at yesterday's close
    oo = inp.open.shift(-HOLD) / inp.open - 1  # today's open to the open HOLD sessions later
    m_oo = inp.etf_open["SPY"].shift(-HOLD) / inp.etf_open["SPY"] - 1
    sec_oo = inp.etf_open[SECTOR_ETFS_11].shift(-HOLD) / inp.etf_open[SECTOR_ETFS_11] - 1
    s_oo = sector_series(inp.sectors.shift(1), sec_oo)
    hedged = oo - bm.mul(m_oo, axis=0) - bs * s_oo.sub(m_oo, axis=0)

    results = {}
    for label, eligible in (("A base", inp.member), ("B news-jump filter", inp.member & keep_prev.fillna(False))):
        c = cohorts(sig_prev, hedged, eligible, gate).loc[START:]
        results[label] = r = summarise(c, idx)
        c.to_parquet(OUT / f"volgated_cohorts_{label.split()[0]}.parquet")
        a, h1, h2 = r["all"], r["2017-2021"], r["2022-2026"]
        logger.info(
            "{}: {} cohorts, net {:+.1f} bp (gross {:+.1f}, t {:+.1f}, hit {:.0%}) | halves {:+.1f} / {:+.1f} bp "
            "| {:+.1%} a year on capital, vol {:.1%}, Sharpe {:.2f}, DD {:.1%}, invested {:.0%}",
            label, a["cohorts"], a["net_bp"], a["gross_bp"], a["t"], a["hit"], h1["net_bp"], h2["net_bp"],
            a["return_on_capital_a_year"], r["vol_a_year"], a["sharpe"], r["max_dd"], r["time_invested"],
        )  # fmt: skip
        r["pass"] = bool(h1["net_bp"] > 0 and h2["net_bp"] > 0)
    (OUT / "volgated_results.json").write_text(json.dumps(results, indent=1))
    logger.info("pass (net positive in both halves): A {}, B {}", results["A base"]["pass"],
                results["B news-jump filter"]["pass"])  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
