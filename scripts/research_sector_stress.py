"""Signal A (2026-11-10): residual reversal inside stressed sectors, in calm markets.

The test was fixed before running: docs/research/2026-11-10-signals-a-c-d.md, section 2. A sector is
stressed when its five-session move beyond SPY is in the top tenth of its own last year. On sessions
after a VIX close below 20 (the days the VIX rule does not trade), the stocks of each stressed sector
are ranked on their five-session residual; the lowest fifth is bought and the highest fifth shorted,
hedged, from the open to the open five sessions later, at 10 bp of costs per cohort.

    uv run python scripts/research_sector_stress.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from loguru import logger
from research_statarb_volgated import HALVES, HOLD, START, VIX_GATE, summarise

from ridethewave.config import load_settings
from ridethewave.daily.residuals import sector_series
from ridethewave.daily.signals import sector_stress
from ridethewave.daily.statarb import signal
from ridethewave.daily.statarb_data import StatArbInputs, load_inputs
from ridethewave.daily.universe import SECTOR_ETFS_11
from ridethewave.data.external import load as load_external
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "signals"
FRACTION, MIN_SECTOR, MIN_SIDE = 0.2, 10, 4
COST = 0.0010  # 4 auction trades at 1 bp, 5 bp of hedges, 1 bp of borrowing


def hedged_outcome(inp: StatArbInputs) -> pd.DataFrame:
    """Each stock's return from today's open to the open HOLD sessions later, after its market and
    sector hedge, with betas and sectors as known at yesterday's close (as the VIX rule's backtest)."""
    bm, bs = inp.b_m.shift(1), inp.b_s.shift(1)
    oo = inp.open.shift(-HOLD) / inp.open - 1
    m_oo = inp.etf_open["SPY"].shift(-HOLD) / inp.etf_open["SPY"] - 1
    sec_oo = inp.etf_open[SECTOR_ETFS_11].shift(-HOLD) / inp.etf_open[SECTOR_ETFS_11] - 1
    s_oo = sector_series(inp.sectors.shift(1), sec_oo)
    return oo - bm.mul(m_oo, axis=0) - bs * s_oo.sub(m_oo, axis=0)


def sector_picks(inp: StatArbInputs, outcome: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Long and short masks from ranking each sector's stocks among themselves, and a mask of the stocks
    whose sector was stressed at yesterday's close. Rows are entry sessions."""
    sig = signal(inp.resid).shift(1)
    label = inp.sectors.shift(1)
    ok = inp.member & sig.notna() & outcome.notna()
    rets = inp.etf_close[SECTOR_ETFS_11].pct_change(fill_method=None)
    stress = sector_stress(rets, inp.etf_close["SPY"].pct_change(fill_method=None)).shift(1, fill_value=False)
    longs = pd.DataFrame(False, index=ok.index, columns=ok.columns)
    shorts, stressed = longs.copy(), longs.copy()
    for etf in SECTOR_ETFS_11:
        grp = ok & (label == etf)
        enough = grp.sum(axis=1) >= MIN_SECTOR
        pct = sig.where(grp).rank(axis=1, pct=True)
        longs |= (pct <= FRACTION).where(enough, False)
        shorts |= (pct > 1 - FRACTION).where(enough, False)
        stressed |= grp.where(stress[etf].astype(bool), False)
    return longs, shorts, stressed


def cohorts(outcome: pd.DataFrame, longs: pd.DataFrame, shorts: pd.DataFrame, days: pd.Series) -> pd.DataFrame:
    """One row per session in ``days`` with at least MIN_SIDE names a side: all picks pooled, equal weight."""
    out = pd.DataFrame(
        {
            "long": outcome.where(longs).mean(axis=1), "short": outcome.where(shorts).mean(axis=1),
            "n_long": longs.sum(axis=1), "n_short": shorts.sum(axis=1),
        }
    )  # fmt: skip
    out = out[days.reindex(out.index, fill_value=False) & (out["n_long"] >= MIN_SIDE) & (out["n_short"] >= MIN_SIDE)]
    out = out.copy()
    out["n"] = (out["n_long"] + out["n_short"]) / (2 * FRACTION)  # so that summarise reports names per side
    out["gross"] = out["long"] - out["short"]
    out["net"] = out["gross"] - COST
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
    idx = inp.close.index
    vix = load_external("vix")["close"].reindex(idx).ffill()
    calm = (vix.shift(1) < VIX_GATE).loc[START:]
    volatile = (vix.shift(1) >= VIX_GATE).loc[START:]
    outcome = hedged_outcome(inp)
    longs, shorts, stressed = sector_picks(inp, outcome)
    cases = {
        "A stressed sectors, VIX below 20 (the test)": (longs & stressed, shorts & stressed, calm),
        "context: other sectors, VIX below 20": (longs & ~stressed, shorts & ~stressed, calm),
        "context: stressed sectors, VIX 20 or above": (longs & stressed, shorts & stressed, volatile),
    }
    results: dict = {}
    for label, (lo, sh, days) in cases.items():
        c = cohorts(outcome, lo, sh, days).loc[START:]
        results[label] = r = summarise(c, idx)
        r["share_of_sessions"] = float(len(c) / len(idx[idx >= START]))
        a, h1, h2 = r["all"], *(r[k] for k in HALVES)
        logger.info(
            "{}: {} cohorts ({:.0%} of sessions), {:.1f} names a side | net {:+.1f} bp (gross {:+.1f}, t {:+.1f}, "
            "hit {:.0%}) | halves {:+.1f} / {:+.1f} bp | {:+.1%} a year on capital, vol {:.1%}, Sharpe {:.2f}, "
            "DD {:.1%}",
            label, a["cohorts"], r["share_of_sessions"], r["avg_names_per_side"], a["net_bp"], a["gross_bp"], a["t"],
            a["hit"], h1["net_bp"], h2["net_bp"], a["return_on_capital_a_year"], r["vol_a_year"], a["sharpe"],
            r["max_dd"],
        )  # fmt: skip
        if label.startswith("A "):
            c.to_parquet(OUT / "sector_stress_cohorts.parquet")
            logger.info("years: {}", {y: (v["cohorts"], round(v["net_bp"], 1)) for y, v in r["years"].items()})
            r["pass"] = {
                "net_t_at_least_2": bool(a["net_bp"] > 0 and a["t"] >= 2),
                "both_halves": bool(h1["net_bp"] > 0 and h2["net_bp"] > 0),
            }
            r["pass"]["all"] = all(r["pass"].values())
            logger.info("pass: {}", r["pass"])
    rets = inp.etf_close[SECTOR_ETFS_11].pct_change(fill_method=None)
    flags = sector_stress(rets, inp.etf_close["SPY"].pct_change(fill_method=None)).loc[START:]
    results["stress"] = {
        "share_of_sector_days": float(flags.mean().mean()),
        "share_of_sessions_with_any": float(flags.any(axis=1).mean()),
        "by_sector": {k: float(v) for k, v in flags.mean().items()},
    }
    logger.info("stress: {}", results["stress"])
    (OUT / "sector_stress_results.json").write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
