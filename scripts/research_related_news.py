"""Signal G (2026-11-10): news about one stock carrying its related stocks.

The test was fixed before running: docs/research/2026-11-10-signals-b-g.md, section 3. An event is a
stock with a material scored headline and a move of at least twice its usual size that day. The ten
stocks whose returns beyond the market followed it most closely over the year before are bought (after a
jump) or shorted (after a fall) at the next open and closed three sessions later, hedged with SPY.

    uv run python scripts/research_related_news.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from research_offering_bounce import NEWS, headline_days, spaced
from research_statarb_volgated import nw_t

from ridethewave.config import load_settings
from ridethewave.daily.statarb_data import load_inputs
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "signals"
RELATED, LOOK, MIN_OBS, HOLD, SHOCK, VOL_DAYS, GAP = 10, 252, 126, 3, 2.0, 60, 3
MATERIAL, COST, MIN_EVENTS = 1.0, 0.0007, 500
HALVES = {"2019-2022": ("2019-01-01", "2022-12-31"), "2023-2026": ("2023-01-01", "2026-12-31")}


def material_days(sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """(symbol, day) with at least one headline scored relevant, not stale and material."""
    cols = ["key", "symbol", "error", "p_relevant", "p_stale", "materiality"]
    sc = pd.read_parquet(NEWS / "scores.parquet", columns=cols)
    sc = sc[sc["error"].isna() & (sc["p_relevant"] > 0.5) & (sc["p_stale"] < 0.5) & (sc["materiality"] >= MATERIAL)]
    return headline_days(sc, sessions)


def block(ev: pd.DataFrame) -> dict:
    if ev.empty:
        return {"events": 0}
    daily = ev.groupby("entry")["net"].mean()
    out = {"events": int(len(ev)), "entry_days": int(len(daily)), "t": nw_t(daily, 4),
           "won": float((ev["net"] > 0).mean())}  # fmt: skip
    for k in ("net", "same_day", "first_day", "own"):
        out[f"{k}_bp"] = float(ev[k].mean() * 1e4)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
    sessions = inp.close.index
    pos = pd.Series(np.arange(len(sessions)), index=sessions)
    spy_c, spy_o = inp.etf_close["SPY"], inp.etf_open["SPY"]
    bm = inp.b_m.shift(1)  # market beta known the day before
    beyond = inp.close.pct_change(fill_method=None) - bm.mul(spy_c.pct_change(fill_method=None), axis=0)
    usual = inp.resid.rolling(VOL_DAYS, min_periods=40).std().shift(1)
    big = inp.resid.abs() >= SHOCK * usual
    # market-hedged returns indexed by the entry session: open to the open HOLD later, and open to that day's close
    held = inp.open.shift(-HOLD) / inp.open - 1 - bm.mul(spy_o.shift(-HOLD) / spy_o - 1, axis=0)
    first = inp.close / inp.open - 1 - bm.mul(spy_c / spy_o - 1, axis=0)

    news = material_days(sessions)
    news = news[news["symbol"].isin(inp.close.columns)]
    hit = [bool(big.at[d, s]) for d, s in zip(news["day"], news["symbol"], strict=True)]
    events = spaced(news[hit][["symbol", "day"]], sessions, GAP)
    logger.info("{} stock-days with material news, {} with a move of {}x the usual size, {} after spacing",
                len(news), sum(hit), SHOCK, len(events))  # fmt: skip

    rows = []
    x = beyond.to_numpy()
    member = inp.member.to_numpy()
    cols = np.array(inp.close.columns)
    col = {s: j for j, s in enumerate(cols)}
    for sym, d in zip(events["symbol"], events["day"], strict=True):
        i, a = int(pos[d]), col[sym]
        if i < LOOK or i + 1 + HOLD >= len(sessions):
            continue
        win = x[i - LOOK : i]  # the year before the event day
        cand = np.nonzero(member[i])[0]
        cand = cand[cand != a]
        own = win[:, a]
        ok = ~np.isnan(own)
        corr = np.full(len(cand), np.nan)
        for k, j in enumerate(cand):
            both = ok & ~np.isnan(win[:, j])
            if both.sum() >= MIN_OBS:
                corr[k] = np.corrcoef(own[both], win[both, j])[0, 1]
        if np.isfinite(corr).sum() < RELATED:
            continue
        basket = cols[cand[np.argsort(-np.nan_to_num(corr, nan=-2))[:RELATED]]]
        side = float(np.sign(inp.resid.iat[i, a]))
        entry = sessions[i + 1]
        r = held.loc[entry, basket].mean()
        if side == 0 or np.isnan(r):
            continue
        rows.append({
            "symbol": sym, "day": d, "entry": entry, "side": side, "net": side * r - COST,
            "same_day": side * np.nanmean(x[i, [col[b] for b in basket]]),
            "first_day": side * first.loc[entry, basket].mean(), "own": side * held.at[entry, sym],
            "avg_corr": float(np.sort(corr[np.isfinite(corr)])[-RELATED:].mean()), "basket": ",".join(basket),
        })  # fmt: skip
    ev = pd.DataFrame(rows)
    ev.to_parquet(OUT / "related_news_events.parquet", index=False)
    results: dict = {"material_stock_days": int(len(news)), "big_moves": int(sum(hit))}
    cases = {"G all events (the test)": ev, "context: after a jump": ev[ev["side"] > 0],
             "context: after a fall": ev[ev["side"] < 0]}  # fmt: skip
    for label, e in cases.items():
        results[label] = r = {"all": block(e), **{k: block(e[(e["entry"] >= a) & (e["entry"] <= b)])
                                                  for k, (a, b) in HALVES.items()}}  # fmt: skip
        a, h1, h2 = r["all"], *(r[k] for k in HALVES)
        logger.info(
            "{}: {} events on {} days | net {:+.1f} bp (t {:+.1f}, {:.0%} won) | halves {:+.1f} / {:+.1f} | related "
            "stocks on the news day {:+.1f} bp, first day after {:+.1f}, the stock itself afterwards {:+.1f}",
            label, a["events"], a["entry_days"], a["net_bp"], a["t"], a["won"], h1["net_bp"], h2["net_bp"],
            a["same_day_bp"], a["first_day_bp"], a["own_bp"],
        )  # fmt: skip
    r = results["G all events (the test)"]
    a, h1, h2 = r["all"], *(r[k] for k in HALVES)
    years = ev.groupby(ev["entry"].dt.year)["net"].agg(["size", "mean"])
    r["years"] = {str(y): {"events": int(v["size"]), "net_bp": float(v["mean"] * 1e4)} for y, v in years.iterrows()}
    r["average_correlation"] = float(ev["avg_corr"].mean())
    r["pass"] = {
        "at_least_500_events": bool(a["events"] >= MIN_EVENTS), "net_above_zero": bool(a["net_bp"] > 0),
        "t_at_least_2": bool(a["t"] >= 2), "both_halves": bool(h1["net_bp"] > 0 and h2["net_bp"] > 0),
    }  # fmt: skip
    r["pass"]["all"] = all(r["pass"].values())
    logger.info("years: {}", {y: (v["events"], round(v["net_bp"], 1)) for y, v in r["years"].items()})
    logger.info("average correlation of the related stocks {:.2f}; pass: {}", r["average_correlation"], r["pass"])
    (OUT / "related_news_results.json").write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
