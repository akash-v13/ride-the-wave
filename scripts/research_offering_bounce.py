"""Signal F (2026-11-10): the bounce after a share offering.

The test was fixed before running: docs/research/2026-11-10-signals-e-b-f.md, section 3. An event is a
stock-day with a headline our news scoring called an offering (relevant, not stale) on which the stock
closed at least 5% down. The trade buys at the next open and sells at the open five sessions later,
hedged with SPY and the sector ETF, at 7 bp of costs.

    uv run python scripts/research_offering_bounce.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from research_sector_stress import hedged_outcome
from research_statarb_volgated import HOLD, nw_t

from ridethewave.config import load_settings
from ridethewave.daily.statarb_data import load_inputs
from ridethewave.storage import Database

ROOT = Path(__file__).resolve().parents[1]
NEWS = ROOT / "data" / "research" / "news_daily"
OUT = ROOT / "data" / "research" / "signals"
FALL, COST, MIN_EVENTS = -0.05, 0.0007, 100
HALVES = {"2019-2022": ("2019-01-01", "2022-12-31"), "2023-2026": ("2023-01-01", "2026-12-31")}


def headline_days(sc: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """(symbol, day) for the scored headlines in ``sc``. A headline after 16:00 New York time belongs to
    the next session, as in the September news study."""
    sc = sc.join(pd.read_parquet(NEWS / "pairs.parquet").set_index("key")[["created_at"]], on="key")
    et = sc["created_at"].dt.tz_convert("America/New_York")
    local = pd.to_datetime(et.dt.date).to_numpy()
    idx = sessions.searchsorted(local, side="left")
    same = sessions[idx.clip(max=len(sessions) - 1)] == local
    idx = idx + (same & (et.dt.hour >= 16).to_numpy())
    keep = idx < len(sessions)
    out = pd.DataFrame({"symbol": sc["symbol"].to_numpy()[keep], "day": sessions[idx[keep]]})
    return out.drop_duplicates().reset_index(drop=True)


def offering_days(sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """(symbol, day) with at least one offering headline that is relevant and not stale."""
    sc = pd.read_parquet(NEWS / "scores.parquet", columns=["key", "symbol", "error", "event", "p_relevant", "p_stale"])
    sc = sc[sc["error"].isna() & (sc["event"] == "offering_or_dilution") & (sc["p_relevant"] > 0.5)]
    return headline_days(sc[sc["p_stale"] < 0.5], sessions)


def spaced(events: pd.DataFrame, sessions: pd.DatetimeIndex, gap: int = HOLD) -> pd.DataFrame:
    """Drop a stock's event when it comes within ``gap`` sessions of the one kept before it."""
    pos = pd.Series(np.arange(len(sessions)), index=sessions)
    rows = []
    for sym, g in events.sort_values("day").groupby("symbol"):
        last = -10_000
        for d in g["day"]:
            p = int(pos[d])
            if p - last > gap:
                rows.append((sym, d))
                last = p
    return pd.DataFrame(rows, columns=["symbol", "day"])


def outcomes(events: pd.DataFrame, hedged: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Each event's hedged and unhedged return from the next session's open to the open HOLD later."""
    sessions = hedged.index
    nxt = pd.Series(sessions[1:], index=sessions[:-1])
    ev = events[events["day"].isin(nxt.index) & events["symbol"].isin(hedged.columns)].copy()
    ev["entry"] = ev["day"].map(nxt)
    ev["hedged"] = [hedged.at[e, s] for e, s in zip(ev["entry"], ev["symbol"], strict=True)]
    ev["raw"] = [raw.at[e, s] for e, s in zip(ev["entry"], ev["symbol"], strict=True)]
    ev = ev.dropna(subset=["hedged"])
    ev["net"] = ev["hedged"] - COST
    return ev


def block(ev: pd.DataFrame) -> dict:
    if ev.empty:
        return {"events": 0}
    daily = ev.groupby("entry")["net"].mean()
    return {
        "events": int(len(ev)), "entry_days": int(len(daily)), "net_bp": float(ev["net"].mean() * 1e4),
        "median_bp": float(ev["net"].median() * 1e4), "t": nw_t(daily, HOLD - 1) if len(daily) > 10 else float("nan"),
        "won": float((ev["net"] > 0).mean()), "unhedged_bp": float(ev["raw"].mean() * 1e4),
        "worst_bp": float(ev["net"].min() * 1e4), "best_bp": float(ev["net"].max() * 1e4),
    }  # fmt: skip


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
    sessions = inp.close.index
    hedged = hedged_outcome(inp)
    raw = inp.open.shift(-HOLD) / inp.open - 1
    ret = inp.close.pct_change(fill_method=None)

    news = offering_days(sessions)
    news = news[news["symbol"].isin(ret.columns)]
    news["move"] = [ret.at[d, s] for d, s in zip(news["day"], news["symbol"], strict=True)]
    fell = spaced(news[news["move"] <= FALL][["symbol", "day"]], sessions)
    every = spaced(news[["symbol", "day"]], sessions)

    # control: falls of 5% or more in the scored universe with no offering headline that day
    universes = json.loads((NEWS / "universes.json").read_text())
    month = pd.Series(sessions.strftime("%Y-%m"), index=sessions)
    drops = []
    offered = set(zip(news["symbol"], news["day"], strict=True))
    for mo, names in universes.items():
        rows = month.index[month == mo]
        cols = [s for s in names if s in ret.columns]
        sub = ret.loc[rows, cols]
        for d, s in zip(*np.nonzero((sub <= FALL).to_numpy()), strict=True):
            if (cols[s], rows[d]) not in offered:
                drops.append((cols[s], rows[d]))
    plain = spaced(pd.DataFrame(drops, columns=["symbol", "day"]), sessions)

    results: dict = {"offering_symbol_days": int(len(news)), "with_a_fall_of_5pct": int((news["move"] <= FALL).sum())}
    cases = {"F offering and a fall of 5% or more (the test)": fell, "context: every offering day": every,
             "context: a fall of 5% or more, no offering headline": plain}  # fmt: skip
    for label, events in cases.items():
        ev = outcomes(events, hedged, raw)
        results[label] = r = {"all": block(ev), **{k: block(ev[(ev["entry"] >= a) & (ev["entry"] <= b)])
                                                   for k, (a, b) in HALVES.items()}}  # fmt: skip
        a, h1, h2 = r["all"], *(r[k] for k in HALVES)
        logger.info(
            "{}: {} events on {} days | net {:+.1f} bp (median {:+.1f}, t {:+.1f}, {:.0%} won; unhedged {:+.1f}) | "
            "halves {:+.1f} ({} events) / {:+.1f} ({})",
            label, a["events"], a["entry_days"], a["net_bp"], a["median_bp"], a["t"], a["won"], a["unhedged_bp"],
            h1.get("net_bp", float("nan")), h1["events"], h2.get("net_bp", float("nan")), h2["events"],
        )  # fmt: skip
        if label.startswith("F "):
            ev.to_parquet(OUT / "offering_bounce_events.parquet", index=False)
            by_year = ev.groupby(ev["entry"].dt.year)["net"].agg(["size", "mean"])
            r["years"] = {
                str(y): {"events": int(v["size"]), "net_bp": float(v["mean"] * 1e4)} for y, v in by_year.iterrows()
            }
            logger.info("years: {}", {y: (v["events"], round(v["net_bp"])) for y, v in r["years"].items()})
            r["pass"] = {
                "at_least_100_events": bool(a["events"] >= MIN_EVENTS),
                "net_above_zero": bool(a["net_bp"] > 0),
                "t_at_least_2": bool(a["t"] >= 2),
                "both_halves": bool(h1.get("net_bp", -1) > 0 and h2.get("net_bp", -1) > 0),
            }
            r["pass"]["all"] = all(r["pass"].values())
            logger.info("pass: {}", r["pass"])
    (OUT / "offering_bounce_results.json").write_text(json.dumps(results, indent=1))
    logger.info("offering stock-days {}, of which fell 5% or more: {}", results["offering_symbol_days"],
                results["with_a_fall_of_5pct"])  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
