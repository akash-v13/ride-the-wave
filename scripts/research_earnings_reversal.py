"""Signal B (2026-11-10): short-term reversal around earnings reports.

The test was fixed before running: docs/research/2026-11-10-signals-b-g.md, section 2. A stock about to
report is bought when its own move over the three sessions ending two before the report is in the
universe's lowest fifth, and shorted when in the highest fifth; held from the close two sessions before
the report to the close of the session after it, hedged, at 5 bp a trade. Report days come from SEC
8-K item 2.02 filings (scripts/download_earnings_dates.py).

    uv run python scripts/research_earnings_reversal.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from research_statarb_volgated import nw_t

from ridethewave.config import load_settings
from ridethewave.daily.residuals import sector_series
from ridethewave.daily.statarb import signal
from ridethewave.daily.statarb_data import load_inputs
from ridethewave.daily.universe import SECTOR_ETFS_11
from ridethewave.data.edgar import last_of_each_cluster, reaction_day
from ridethewave.storage import Database

ROOT = Path(__file__).resolve().parents[1]
DATES = ROOT / "data" / "reference" / "earnings_8k.parquet"
OUT = ROOT / "data" / "research" / "signals"
FRACTION, COST, MIN_TRADES, AWAY = 0.2, 0.0005, 1000, 10
START = "2017-01-03"
HALVES = {"2017-2021": ("2017-01-01", "2021-12-31"), "2022-2026": ("2022-01-01", "2026-12-31")}


def hedged(
    start: pd.DataFrame,
    end: pd.DataFrame,
    m0: pd.Series,
    m1: pd.Series,
    s0: pd.DataFrame,
    s1: pd.DataFrame,
    b_m: pd.DataFrame,
    b_s: pd.DataFrame,
    sectors: pd.DataFrame,
) -> pd.DataFrame:
    """Each stock's return from ``start`` to ``end`` after its market and sector hedge; the ETF frames
    give the same two prices for SPY (``m0``, ``m1``) and the sector ETFs (``s0``, ``s1``)."""
    m = m1 / m0 - 1
    sec = sector_series(sectors, s1 / s0 - 1)
    return (end / start - 1) - b_m.mul(m, axis=0) - b_s * sec.sub(m, axis=0)


def report_days(sessions: pd.DatetimeIndex, symbols: set[str]) -> pd.DataFrame:
    """(symbol, R): the first session that could trade on each report, one per quarter."""
    raw = pd.read_parquet(DATES)
    rows = []
    for sym, g in raw[raw["symbol"].isin(symbols)].groupby("symbol"):
        days = [reaction_day(t.to_pydatetime(), sessions) for t in g["accepted"]]
        rows += [(sym, d) for d in last_of_each_cluster([d for d in days if d is not None])]
    return pd.DataFrame(rows, columns=["symbol", "R"])


def trades(reports: pd.DataFrame, pct: pd.DataFrame, outcome: pd.DataFrame, back: int) -> pd.DataFrame:
    """One row per report whose stock is in an extreme fifth on the ranking row, ``back`` sessions
    before the report day. ``pct`` and ``outcome`` are indexed by that row."""
    pos = {d: i for i, d in enumerate(pct.index)}
    col = {s: j for j, s in enumerate(pct.columns)}
    p, o = pct.to_numpy(), outcome.to_numpy()
    rows = []
    for sym, r in zip(reports["symbol"], reports["R"], strict=True):
        i, j = pos[r] - back, col.get(sym)
        if i < 0 or j is None or np.isnan(p[i, j]) or np.isnan(o[i, j]):
            continue
        side = 1 if p[i, j] <= FRACTION else (-1 if p[i, j] > 1 - FRACTION else 0)
        if side:
            rows.append((sym, r, pct.index[i], side, side * o[i, j] - COST))
    return pd.DataFrame(rows, columns=["symbol", "R", "entry", "side", "net"])


def block(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0}
    daily = t.groupby("entry")["net"].mean()
    return {
        "trades": int(len(t)), "entry_days": int(len(daily)), "net_bp": float(t["net"].mean() * 1e4),
        "median_bp": float(t["net"].median() * 1e4), "t": nw_t(daily, 4), "won": float((t["net"] > 0).mean()),
        "bought_bp": float(t.loc[t["side"] > 0, "net"].mean() * 1e4),
        "shorted_bp": float(t.loc[t["side"] < 0, "net"].mean() * 1e4),
    }  # fmt: skip


def report(label: str, t: pd.DataFrame) -> dict:
    t = t[t["entry"] >= START]
    r = {"all": block(t), **{k: block(t[(t["entry"] >= a) & (t["entry"] <= b)]) for k, (a, b) in HALVES.items()}}
    a, h1, h2 = r["all"], *(r[k] for k in HALVES)
    logger.info(
        "{}: {} trades on {} days | net {:+.1f} bp (median {:+.1f}, t {:+.1f}, {:.0%} won) | bought {:+.1f}, shorted "
        "{:+.1f} | halves {:+.1f} / {:+.1f}",
        label, a["trades"], a["entry_days"], a["net_bp"], a["median_bp"], a["t"], a["won"], a["bought_bp"],
        a["shorted_bp"], h1["net_bp"], h2["net_bp"],
    )  # fmt: skip
    return r


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
    sessions = inp.close.index
    spy_c, spy_o = inp.etf_close["SPY"], inp.etf_open["SPY"]
    sec_c, sec_o = inp.etf_close[SECTOR_ETFS_11], inp.etf_open[SECTOR_ETFS_11]
    reports = report_days(sessions, set(inp.close.columns))
    reports = reports[reports["R"] >= sessions[5]]
    members = {(s, d) for s, d in zip(reports["symbol"], reports["R"], strict=True) if inp.member.at[d, s]}
    reports = reports[[x in members for x in zip(reports["symbol"], reports["R"], strict=True)]]
    per_year = reports.groupby(reports["R"].dt.year).size().to_dict()
    logger.info("{} reports by universe members, {} symbols; by year {}", len(reports), reports["symbol"].nunique(),
                per_year)  # fmt: skip

    # the test: rank on the three sessions ending at the row (R-2); close of the row to the close 3 later
    sig3 = inp.resid.rolling(3, min_periods=3).sum()
    pct3 = sig3.where(inp.member & sig3.notna()).rank(axis=1, pct=True)
    out3 = hedged(inp.close, inp.close.shift(-3), spy_c, spy_c.shift(-3), sec_c, sec_c.shift(-3),
                  inp.b_m, inp.b_s, inp.sectors)  # fmt: skip
    test = trades(reports, pct3, out3, back=2)
    results = {"reports": int(len(reports)), "reports_by_year": {str(k): int(v) for k, v in per_year.items()}}
    results["B through the report (the test)"] = r = report("B through the report (the test)", test)
    test.to_parquet(OUT / "earnings_reversal_trades.parquet", index=False)
    years = test[test["entry"] >= START].groupby(test["entry"].dt.year)["net"].agg(["size", "mean"])
    r["years"] = {str(y): {"trades": int(v["size"]), "net_bp": float(v["mean"] * 1e4)} for y, v in years.iterrows()}
    logger.info("years: {}", {y: (v["trades"], round(v["net_bp"])) for y, v in r["years"].items()})
    a, h1, h2 = r["all"], *(r[k] for k in HALVES)
    r["pass"] = {
        "at_least_1000_trades": bool(a["trades"] >= MIN_TRADES), "net_above_zero": bool(a["net_bp"] > 0),
        "t_at_least_2": bool(a["t"] >= 2), "both_halves": bool(h1["net_bp"] > 0 and h2["net_bp"] > 0),
    }  # fmt: skip
    r["pass"]["all"] = all(r["pass"].values())
    logger.info("pass: {}", r["pass"])

    # context 1: the same picks and holding period with no report within AWAY sessions
    pos = {d: i for i, d in enumerate(sessions)}
    col = {s: j for j, s in enumerate(inp.close.columns)}
    arr = np.zeros(inp.close.shape, dtype=bool)
    for sym, d in zip(reports["symbol"], reports["R"], strict=True):
        i = pos[d]
        arr[max(0, i - AWAY - 2) : i + AWAY - 1, col[sym]] = True  # ranking rows within AWAY of the row R-2
    far = ~pd.DataFrame(arr, index=sessions, columns=inp.close.columns)
    sides = []
    for side, mask in ((1, pct3 <= FRACTION), (-1, pct3 > 1 - FRACTION)):
        x = (side * out3 - COST).where(mask & far).loc[START:].stack().dropna().rename("net").reset_index()
        x.columns = ["entry", "symbol", "net"]
        sides.append(x.assign(side=side))
    control = pd.concat(sides, ignore_index=True)
    results["context: no report near"] = report("context: no report near", control)

    # context 2: the shortlist's version, out before the report
    sig5 = signal(inp.resid).shift(1)  # five sessions to yesterday's close, for an entry at today's open
    pct5 = sig5.where(inp.member & sig5.notna()).rank(axis=1, pct=True)
    before = hedged(inp.open, inp.close.shift(-2), spy_o, spy_c.shift(-2), sec_o, sec_c.shift(-2),
                    inp.b_m.shift(1), inp.b_s.shift(1), inp.sectors.shift(1))  # fmt: skip
    results["context: out before the report"] = report("context: out before the report",
                                                      trades(reports, pct5, before, back=3))  # fmt: skip
    (OUT / "earnings_reversal_results.json").write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
