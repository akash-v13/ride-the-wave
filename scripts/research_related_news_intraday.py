"""Signal G inside the day (2026-11-10): after a stock moves on news, do its related stocks still have
room to follow before the close?

The test was fixed before any minute price was fetched: docs/research/2026-11-10-signal-g-intraday.md.
- **Event:** a material scored headline between 09:40 and 15:00 New York time, and a move by the stock,
  over the ten minutes around it and beyond the market, of at least half its usual daily own-move.
- **Trade:** the ten related stocks (as in research_related_news.py) in that direction, in during the
  minute five after the headline at that minute's average price, out at the close, hedged with SPY,
  7 bp of costs.

Two stages, each saved so a re-run does not fetch again:
1. ``events``: minute bars for the news stocks and SPY on every candidate day; which headlines trigger.
2. ``outcomes``: minute bars for each event's related stocks; what they did.

    uv run python scripts/research_related_news_intraday.py            # both stages, then the summary
    uv run python scripts/research_related_news_intraday.py --part summary
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger
from research_offering_bounce import NEWS
from research_related_news import HALVES, MATERIAL, related
from research_statarb_costs import WORKERS, at, client
from research_statarb_volgated import nw_t

from ridethewave.config import load_settings
from ridethewave.daily.signals import news_move, price_at
from ridethewave.daily.statarb_data import load_inputs
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "signals"
EVENTS, OUTCOMES = OUT / "related_intraday_events.parquet", OUT / "related_intraday_outcomes.parquet"
FIRST, LAST = 10, 330  # headline minutes since 09:30: 09:40 to 15:00
BEFORE, AFTER, TRIGGER, VOL_DAYS = 5, 5, 0.5, 60
COST, MIN_EVENTS, MIN_PRICED, SESSION = 0.0007, 300, 5, 390
Bars = dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]  # symbol -> bar start minutes, closes, average prices


def day_bars(day: pd.Timestamp, symbols: list[str]) -> Bars:
    """One session's regular-hours minute bars for ``symbols``."""
    start = at(day, time(9, 30))
    out: Bars = {}
    for i in range(0, len(symbols), 25):
        req = StockBarsRequest(
            symbol_or_symbols=symbols[i : i + 25],
            timeframe=TimeFrame.Minute,
            start=start,
            end=start + timedelta(minutes=SESSION) - timedelta(seconds=1),
            feed=DataFeed.SIP,
            limit=None,
        )
        for sym, rows in client().get_stock_bars(req).items():
            ts = pd.to_datetime([r["t"] for r in rows], utc=True)
            minute = ((ts - pd.Timestamp(start)).total_seconds() // 60).astype(int).to_numpy()
            keep = (minute >= 0) & (minute < SESSION)
            close = np.array([r["c"] for r in rows], dtype=float)[keep]
            vwap = np.array([r.get("vw") or r["c"] for r in rows], dtype=float)[keep]
            out[sym] = (minute[keep], close, vwap)
    return out


def headlines(sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Material headlines published between 09:40 and 15:00 New York time on a session: symbol, day, minute."""
    cols = ["key", "symbol", "error", "p_relevant", "p_stale", "materiality"]
    sc = pd.read_parquet(NEWS / "scores.parquet", columns=cols)
    sc = sc[sc["error"].isna() & (sc["p_relevant"] > 0.5) & (sc["p_stale"] < 0.5) & (sc["materiality"] >= MATERIAL)]
    sc = sc.join(pd.read_parquet(NEWS / "pairs.parquet").set_index("key")[["created_at"]], on="key")
    et = sc["created_at"].dt.tz_convert("America/New_York")
    out = pd.DataFrame({
        "symbol": sc["symbol"].to_numpy(), "day": pd.to_datetime(et.dt.date).to_numpy(),
        "t0": (et.dt.hour * 60 + et.dt.minute - 570).to_numpy(),
    })  # fmt: skip
    out = out[out["day"].isin(sessions) & (out["t0"] >= FIRST) & (out["t0"] <= LAST)]
    return out.drop_duplicates().sort_values(["day", "symbol", "t0"]).reset_index(drop=True)


def find_events(inp, heads: pd.DataFrame) -> pd.DataFrame:
    """Stage 1: each stock-day's first headline whose ten-minute move is at least TRIGGER x its usual day."""
    bm = inp.b_m.shift(1)
    usual = inp.resid.rolling(VOL_DAYS, min_periods=40).std().shift(1)
    heads = heads[heads["symbol"].isin(inp.close.columns)]

    def one_day(item) -> list[dict]:
        day, g = item
        bars = day_bars(day, sorted(set(g["symbol"]) | {"SPY"}))
        if "SPY" not in bars:
            return []
        spy_m, spy_c, _ = bars["SPY"]
        found = []
        for sym, hs in g.groupby("symbol"):
            beta, size = bm.at[day, sym], usual.at[day, sym]
            if sym not in bars or not (beta == beta and size > 0):
                continue
            m, c, _ = bars[sym]
            for t0 in hs["t0"]:
                move = news_move(m, c, spy_m, spy_c, int(t0), float(beta), BEFORE, AFTER)
                if move == move and abs(move) >= TRIGGER * size:
                    found.append({"symbol": sym, "day": day, "t0": int(t0), "move": move, "usual": float(size)})
                    break
        return found

    items = list(heads.groupby("day"))
    logger.info("stage 1: minute bars for {} stock-days on {} days", len(heads.drop_duplicates(["symbol", "day"])),
                len(items))  # fmt: skip
    with ThreadPoolExecutor(WORKERS) as pool:
        rows = [r for part in pool.map(one_day, items) for r in part]
    return pd.DataFrame(rows)


def find_outcomes(inp, events: pd.DataFrame) -> pd.DataFrame:
    """Stage 2: what each event's ten related stocks did, from minute bars."""
    sessions = inp.close.index
    pos = pd.Series(np.arange(len(sessions)), index=sessions)
    bm = inp.b_m.shift(1)
    spy_ret = inp.etf_close["SPY"].pct_change(fill_method=None)
    x = (inp.close.pct_change(fill_method=None) - bm.mul(spy_ret, axis=0)).to_numpy()
    member = inp.member.to_numpy()
    cols = np.array(inp.close.columns)
    col = {s: j for j, s in enumerate(cols)}
    baskets = {}
    for sym, day in zip(events["symbol"], events["day"], strict=True):
        i = int(pos[day])
        picked = related(x, member, i, col[sym]) if i >= 252 else None
        if picked is not None:
            baskets[(sym, day)] = list(cols[picked[0]])

    def hedged(bars: Bars, sym: str, beta: float, a: int, b: int | None, spy: tuple) -> float:
        """Market-hedged return of ``sym`` from the average price of minute ``a`` (or the price at ``a`` when
        ``b`` marks a window start) to the price at minute ``b``."""
        if sym not in bars or beta != beta:
            return float("nan")
        m, c, v = bars[sym]
        k = int(np.searchsorted(m, a, side="left"))
        if k >= len(m) or m[k] > a + 2:  # no trade within two minutes of the entry minute
            return float("nan")
        return (price_at(m, c, b) / v[k] - 1) - beta * (price_at(spy[0], spy[1], b) / spy[3] - 1)

    def one_day(item) -> list[dict]:
        day, g = item
        need = {"SPY"}
        for sym in g["symbol"]:
            need |= {sym, *baskets.get((sym, day), [])}
        bars = day_bars(day, sorted(need))
        if "SPY" not in bars:
            return []
        sm, sc_, sv = bars["SPY"]
        out = []
        for sym, t0, move in zip(g["symbol"], g["t0"], g["move"], strict=True):
            names = baskets.get((sym, day))
            if not names:
                continue
            e, side = t0 + AFTER, float(np.sign(move))
            k = int(np.searchsorted(sm, e, side="left"))
            if k >= len(sm) or sm[k] > e + 2:
                continue
            spy = (sm, sc_, sv, sv[k])
            row = {"symbol": sym, "day": day, "t0": t0, "side": side, "move": move}
            for label, b in (("close", SESSION), ("m30", e + 30), ("m60", e + 60)):
                r = [hedged(bars, s, bm.at[day, s], e, min(b, SESSION), spy) for s in names]
                row[label] = side * float(np.nanmean(r)) if np.sum(~np.isnan(r)) >= MIN_PRICED else float("nan")
                if label == "close":
                    row["priced"] = int(np.sum(~np.isnan(r)))
            # what the related stocks had already done inside the trigger window, beyond the market
            pre = []
            for s in names:
                if s in bars and bm.at[day, s] == bm.at[day, s]:
                    m, c, _ = bars[s]
                    p0, p1 = price_at(m, c, t0 - BEFORE), price_at(m, c, e)
                    s0, s1 = price_at(sm, sc_, t0 - BEFORE), price_at(sm, sc_, e)
                    if p0 > 0 and p1 > 0 and s0 > 0 and s1 > 0:
                        pre.append((p1 / p0 - 1) - bm.at[day, s] * (s1 / s0 - 1))
            row["already"] = side * float(np.mean(pre)) if len(pre) >= MIN_PRICED else float("nan")
            row["own"] = side * hedged(bars, sym, bm.at[day, sym], e, SESSION, spy)
            row["basket"] = ",".join(names)
            out.append(row)
        return out

    items = list(events.groupby("day"))
    logger.info("stage 2: minute bars for the related stocks of {} events on {} days", len(events), len(items))
    with ThreadPoolExecutor(WORKERS) as pool:
        rows = [r for part in pool.map(one_day, items) for r in part]
    return pd.DataFrame(rows)


def block(ev: pd.DataFrame) -> dict:
    ev = ev.dropna(subset=["close"])
    if ev.empty:
        return {"events": 0}
    net = ev["close"] - COST
    daily = net.groupby(ev["day"]).mean()
    return {
        "events": int(len(ev)), "days": int(len(daily)), "gross_bp": float(ev["close"].mean() * 1e4),
        "net_bp": float(net.mean() * 1e4), "median_net_bp": float(net.median() * 1e4),
        "t": nw_t(daily, 4) if len(daily) > 10 else float("nan"), "won": float((net > 0).mean()),
        "already_bp": float(ev["already"].mean() * 1e4), "m30_bp": float(ev["m30"].mean() * 1e4),
        "m60_bp": float(ev["m60"].mean() * 1e4), "own_bp": float(ev["own"].mean() * 1e4),
        "trigger_bp": float((ev["move"] * ev["side"]).mean() * 1e4),
    }  # fmt: skip


def summarise(ev: pd.DataFrame) -> dict:
    results: dict = {}
    cases = {"G inside the day (the test)": ev, "context: after a jump": ev[ev["side"] > 0],
             "context: after a fall": ev[ev["side"] < 0]}  # fmt: skip
    for label, e in cases.items():
        results[label] = r = {"all": block(e), **{k: block(e[(e["day"] >= a) & (e["day"] <= b)])
                                                  for k, (a, b) in HALVES.items()}}  # fmt: skip
        a, h1, h2 = r["all"], *(r[k] for k in HALVES)
        logger.info(
            "{}: {} events on {} days | news stock's move {:+.0f} bp | related stocks: already {:+.1f} bp in the "
            "window; after entry +30 min {:+.1f}, +60 min {:+.1f}, to the close {:+.1f} | net {:+.1f} bp (median "
            "{:+.1f}, t {:+.1f}, {:.0%} won) | halves {:+.1f} / {:+.1f} | the news stock itself to the close {:+.1f}",
            label, a["events"], a["days"], a["trigger_bp"], a["already_bp"], a["m30_bp"], a["m60_bp"], a["gross_bp"],
            a["net_bp"], a["median_net_bp"], a["t"], a["won"], h1.get("net_bp", float("nan")),
            h2.get("net_bp", float("nan")), a["own_bp"],
        )  # fmt: skip
    r = results["G inside the day (the test)"]
    a, h1, h2 = r["all"], *(r[k] for k in HALVES)
    done = ev.dropna(subset=["close"])
    years = (done["close"] - COST).groupby(done["day"].dt.year).agg(["size", "mean"])
    r["years"] = {str(y): {"events": int(v["size"]), "net_bp": float(v["mean"] * 1e4)} for y, v in years.iterrows()}
    r["breakeven_cost_bp"] = a["gross_bp"]
    r["pass"] = {
        "at_least_300_events": bool(a["events"] >= MIN_EVENTS), "net_above_zero": bool(a["net_bp"] > 0),
        "t_at_least_2": bool(a["t"] >= 2),
        "both_halves": bool(h1.get("net_bp", -1) > 0 and h2.get("net_bp", -1) > 0),
    }  # fmt: skip
    r["pass"]["all"] = all(r["pass"].values())
    logger.info("years: {}", {y: (v["events"], round(v["net_bp"], 1)) for y, v in r["years"].items()})
    logger.info("pass: {}", r["pass"])
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["all", "summary"], default="all")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.part == "all":
        inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
        if not EVENTS.exists():
            heads = headlines(inp.close.index)
            logger.info("{} headlines on {} stock-days", len(heads), len(heads.drop_duplicates(["symbol", "day"])))
            find_events(inp, heads).to_parquet(EVENTS, index=False)
        events = pd.read_parquet(EVENTS)
        logger.info("{} events (a headline and a move of at least {} of the usual day)", len(events), TRIGGER)
        if not OUTCOMES.exists():
            find_outcomes(inp, events).to_parquet(OUTCOMES, index=False)
    results = summarise(pd.read_parquet(OUTCOMES))
    (OUT / "related_intraday_results.json").write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
