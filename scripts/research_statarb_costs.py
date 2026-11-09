"""Statistical arbitrage, costs (2026-11-09): what the VIX-gated reversal really pays to trade.

The design was fixed before running: docs/research/2026-11-09-statarb-costs.md. Two measurements on
the backtest's own picks (scripts/research_statarb_volgated.py, configuration A):

1. **The wait.** The backtest enters and exits at the open; the shadow slot fills at about 09:35.
   On every gated session, the picks' hedged move from the opening trade to 09:35, long minus
   short, on the entry day and on the exit day five sessions later. From minute bars.
2. **The spread.** On 60 gated and 30 calm sessions drawn at random (seed fixed), the time-weighted
   quoted half-spread of each pick at 09:35:15-09:35:45, when the slot trades, and at
   09:30:30-09:31:00, just after the open. From quote history.

    uv run python scripts/research_statarb_costs.py              # both parts, then the summary
    uv run python scripts/research_statarb_costs.py --part wait   # or: spread, summary
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockQuotesRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger

from ridethewave.clients import with_retries, with_timeouts
from ridethewave.config import load_secrets, load_settings
from ridethewave.daily.costs import half_spread_bp, long_short_gap, open_to_later
from ridethewave.daily.residuals import sector_series
from ridethewave.daily.statarb import signal
from ridethewave.daily.statarb_data import StatArbInputs, load_inputs
from ridethewave.daily.universe import SECTOR_ETFS_11
from ridethewave.data.external import load as load_external
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "statarb"
ET = ZoneInfo("America/New_York")
START = "2017-01-03"
HOLD, FRACTION, VIX_GATE = 5, 0.2, 20.0
ETFS = ["SPY", *SECTOR_ETFS_11]
SEED, N_GATED, N_CALM = 20261109, 60, 30
CAP_BP = 100.0  # a name quoted wider than this counts as this: nobody sends a market order into a 2% spread
WINDOWS = {"09:35": (time(9, 35, 15), time(9, 35, 45)), "open": (time(9, 30, 30), time(9, 31, 0))}
HEDGE_BP, BORROW_BP, ASSUMED_BP = 5.0, 1.0, 5.0  # per cohort round trip; per stock trade (the backtest's)
HALVES = {"2017-2021": ("2017-01-01", "2021-12-31"), "2022-2026": ("2022-01-01", "2026-12-31")}
WORKERS = 6

_local = threading.local()


def client() -> StockHistoricalDataClient:
    """One raw-JSON client per thread: tens of millions of quotes are too slow through the SDK's models."""
    if not hasattr(_local, "client"):
        s = load_secrets()
        c = StockHistoricalDataClient(s.alpaca_api_key, s.alpaca_secret_key, raw_data=True)
        _local.client = with_retries(with_timeouts(c))
    return _local.client


def at(day: pd.Timestamp, t: time) -> datetime:
    return datetime.combine(day.date(), t, ET)


def all_picks(inp: StatArbInputs) -> tuple[dict[pd.Timestamp, tuple[list[str], list[str]]], pd.DataFrame]:
    """Each session's long and short fifths, ranked as research_statarb_volgated.py ranks them (gate
    aside), and the hedged five-session outcome it scores them on."""
    sig_prev = signal(inp.resid).shift(1)
    bm, bs = inp.b_m.shift(1), inp.b_s.shift(1)
    oo = inp.open.shift(-HOLD) / inp.open - 1
    m_oo = inp.etf_open["SPY"].shift(-HOLD) / inp.etf_open["SPY"] - 1
    sec_oo = inp.etf_open[SECTOR_ETFS_11].shift(-HOLD) / inp.etf_open[SECTOR_ETFS_11] - 1
    hedged = oo - bm.mul(m_oo, axis=0) - bs * sector_series(inp.sectors.shift(1), sec_oo).sub(m_oo, axis=0)
    ok = inp.member & sig_prev.notna() & hedged.notna()
    pct = sig_prev.where(ok).rank(axis=1, pct=True)
    enough = ok.sum(axis=1) >= 25
    out = {}
    for day in pct.index[(pct.index >= START) & enough]:
        row = pct.loc[day]
        out[day] = (row.index[row <= FRACTION].tolist(), row.index[row > 1 - FRACTION].tolist())
    return out, hedged


def check_against_backtest(picks: dict, hedged: pd.DataFrame, cohorts: pd.DataFrame) -> None:
    """The picks must reproduce the backtest's saved long and short returns, or nothing below means anything."""
    for day in cohorts.index:
        longs, shorts = picks[day]
        got = (hedged.loc[day, longs].mean(), hedged.loc[day, shorts].mean())
        want = (cohorts.at[day, "long"], cohorts.at[day, "short"])
        if not np.allclose(got, want, atol=1e-12):
            raise SystemExit(f"picks do not match the backtest on {day.date()}: {got} against {want}")
    logger.info("picks reproduce the backtest's {} cohorts exactly", len(cohorts))


# ---------------------------------------------------------------- part 1: the wait
def session_moves(day: pd.Timestamp, symbols: set[str]) -> pd.Series:
    """Each symbol's move from its opening trade to 09:35 on one session."""
    start = at(day, time(9, 30))
    syms = sorted(symbols)
    raw: dict[str, list[dict]] = {}
    for i in range(0, len(syms), 200):
        req = StockBarsRequest(
            symbol_or_symbols=syms[i : i + 200],
            timeframe=TimeFrame.Minute,
            start=start,
            end=start + timedelta(minutes=6) - timedelta(seconds=1),
            feed=DataFeed.SIP,
            limit=None,
        )
        raw.update(client().get_stock_bars(req))
    out = {}
    for sym, rows in raw.items():
        ts = pd.to_datetime([r["t"] for r in rows], utc=True)
        bars = pd.DataFrame(
            {
                "minute": ((ts - pd.Timestamp(start)).total_seconds() // 60).astype(int),
                "open": [r["o"] for r in rows],
                "close": [r["c"] for r in rows],
                "vwap": [r.get("vw") or 0.0 for r in rows],
            }
        )
        out[sym] = open_to_later(bars[bars["minute"] >= 0])
    return pd.Series(out, dtype=float)


def measure_wait(inp: StatArbInputs, picks: dict, gated: list[pd.Timestamp]) -> pd.DataFrame:
    idx = inp.close.index
    pos = {d: i for i, d in enumerate(idx)}
    exit_day = {d: idx[pos[d] + HOLD] for d in gated if pos[d] + HOLD < len(idx)}
    need: dict[pd.Timestamp, set[str]] = {}
    for d in gated:
        names = set(picks[d][0]) | set(picks[d][1])
        for s in (d, exit_day.get(d)):
            if s is not None:
                need.setdefault(s, set(ETFS)).update(names)
    sessions = sorted(need)
    logger.info("the wait: minute bars for {} sessions", len(sessions))
    with ThreadPoolExecutor(WORKERS) as pool:
        moves = dict(zip(sessions, pool.map(lambda s: session_moves(s, need[s]), sessions), strict=True))
    bm, bs, sectors = inp.b_m.shift(1), inp.b_s.shift(1), inp.sectors.shift(1)
    rows = []
    for d in gated:
        longs, shorts = picks[d]
        args = (longs, shorts, bm.loc[d], bs.loc[d], sectors.loc[d])
        entry, n_in = long_short_gap(moves[d], *args)
        leave, n_out = long_short_gap(moves[exit_day[d]], *args) if d in exit_day else (None, 0)
        rows.append({"day": d, "entry": entry, "exit": leave, "names": len(longs) + len(shorts),
                     "priced_entry": n_in, "priced_exit": n_out})  # fmt: skip
    return pd.DataFrame(rows).set_index("day")


# ---------------------------------------------------------------- part 2: the spread
def window_spreads(day: pd.Timestamp, window: str, symbols: list[str]) -> dict[str, float | None]:
    """Each symbol's time-weighted half-spread over one window of one session."""
    start, end = (at(day, t) for t in WINDOWS[window])
    req = StockQuotesRequest(
        symbol_or_symbols=symbols,
        start=start,
        end=end - timedelta(microseconds=1),
        feed=DataFeed.SIP,
        limit=None,
    )
    raw = client().get_stock_quotes(req)
    end_ns = pd.Timestamp(end).value
    out: dict[str, float | None] = dict.fromkeys(symbols)
    for sym, rows in raw.items():
        ts = pd.to_datetime([r["t"] for r in rows], utc=True, format="ISO8601").asi8
        bid = np.array([r["bp"] for r in rows], dtype=float)
        ask = np.array([r["ap"] for r in rows], dtype=float)
        order = np.argsort(ts, kind="stable")
        out[sym] = half_spread_bp(ts[order], bid[order], ask[order], end_ns)
    return out


def measure_spreads(picks: dict, gated: list[pd.Timestamp]) -> pd.DataFrame:
    """One row per (session, window, symbol): its side and its half-spread."""
    rng = np.random.default_rng(SEED)
    calm = [d for d in picks if d not in set(gated)]
    sample = {"gated": sorted(rng.choice(np.array(gated), N_GATED, replace=False)),
              "calm": sorted(rng.choice(np.array(calm), N_CALM, replace=False))}  # fmt: skip
    jobs = [(regime, pd.Timestamp(d), w) for regime, days in sample.items() for d in days for w in WINDOWS]
    logger.info("the spread: quotes for {} session-windows", len(jobs))

    def run(job: tuple[str, pd.Timestamp, str]) -> list[dict]:
        regime, day, window = job
        longs, shorts = picks[day]
        side = {**dict.fromkeys(ETFS, "etf"), **dict.fromkeys(longs, "long"), **dict.fromkeys(shorts, "short")}
        got = window_spreads(day, window, sorted(side))
        return [{"day": day, "regime": regime, "window": window, "symbol": s, "side": side[s], "half_bp": got[s]}
                for s in side]  # fmt: skip

    with ThreadPoolExecutor(WORKERS) as pool:
        rows = [r for part in pool.map(run, jobs) for r in part]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- summary
def t_stat(x: pd.Series, lags: int = 0) -> float:
    """Mean over its standard error; with ``lags``, Newey-West for overlapping holds."""
    x = x.dropna()
    d = (x - x.mean()).to_numpy()
    n = len(d)
    s = d @ d / n
    for k in range(1, lags + 1):
        s += 2 * (1 - k / (lags + 1)) * (d[k:] @ d[:-k]) / n
    return float(x.mean() / math.sqrt(s / n)) if s > 0 else 0.0


def by_day(names: pd.DataFrame) -> pd.DataFrame:
    """Per session and window: what the picks cost, equal-weighted as the book holds them."""
    stocks = names[names["side"] != "etf"].assign(capped=lambda f: f["half_bp"].clip(upper=CAP_BP))
    g = stocks.groupby(["regime", "day", "window"])
    out = g.agg(mean_bp=("capped", "mean"), median_bp=("half_bp", "median"),
                unquoted=("half_bp", lambda s: float(s.isna().mean())), names=("half_bp", "size"))  # fmt: skip
    for side in ("long", "short", "etf"):
        sub = names[names["side"] == side].assign(capped=lambda f: f["half_bp"].clip(upper=CAP_BP))
        out[f"{side}_bp"] = sub.groupby(["regime", "day", "window"])["capped"].mean()
    return out.reset_index()


def summarise(wait: pd.DataFrame, names: pd.DataFrame, cohorts: pd.DataFrame) -> dict:
    days = by_day(names)
    res: dict = {"wait": {}, "spread": {}, "repriced": {}}
    wait = wait.assign(net=wait["exit"] - wait["entry"])
    spans = {"all": (START, "2026-12-31"), **HALVES}
    for label, (a, b) in spans.items():
        w = wait.loc[a:b]
        res["wait"][label] = {
            "days": int(w["net"].notna().sum()),
            "entry_bp": float(w["entry"].mean() * 1e4), "entry_t": t_stat(w["entry"]),
            "exit_bp": float(w["exit"].mean() * 1e4), "exit_t": t_stat(w["exit"]),
            "net_bp": float(w["net"].mean() * 1e4), "net_t": t_stat(w["net"]),
            "priced_share": float((w["priced_entry"] / w["names"]).mean()),
        }  # fmt: skip
    for (regime, window), g in days.groupby(["regime", "window"]):
        res["spread"][f"{regime} {window}"] = {
            "days": int(len(g)), "mean_bp": float(g["mean_bp"].mean()), "median_bp": float(g["median_bp"].mean()),
            "long_bp": float(g["long_bp"].mean()), "short_bp": float(g["short_bp"].mean()),
            "etf_bp": float(g["etf_bp"].mean()), "unquoted": float(g["unquoted"].mean()),
            "day_min_bp": float(g["mean_bp"].min()), "day_max_bp": float(g["mean_bp"].max()),
        }  # fmt: skip
    at_trade = days[(days["regime"] == "gated") & (days["window"] == "09:35")].set_index("day")["mean_bp"]
    for label, (a, b) in spans.items():
        c = cohorts.loc[a:b]
        w = wait.loc[a:b].reindex(c.index)
        half = float(at_trade.loc[a:b].mean())
        gross_open = c["gross"] * 1e4
        gross_935 = gross_open + w["net"].fillna(0.0) * 1e4
        cost = 4 * half + HEDGE_BP + BORROW_BP
        res["repriced"][label] = {
            "cohorts": int(len(c)), "spread_days": int(at_trade.loc[a:b].count()), "half_spread_bp": half,
            "cost_bp": cost, "assumed_cost_bp": 4 * ASSUMED_BP + HEDGE_BP + BORROW_BP,
            "gross_open_bp": float(gross_open.mean()), "gross_0935_bp": float(gross_935.mean()),
            "net_backtest_bp": float(c["net"].mean() * 1e4),
            "net_0935_bp": float(gross_935.mean() - cost), "net_0935_t": t_stat(gross_935 - cost, HOLD - 1),
            "net_open_measured_spread_bp": float(gross_open.mean() - cost),
            "breakeven_half_spread_0935_bp": float((gross_935.mean() - HEDGE_BP - BORROW_BP) / 4),
        }  # fmt: skip
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["all", "wait", "spread", "summary"], default="all")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cohorts = pd.read_parquet(OUT / "volgated_cohorts_A.parquet")
    gated = list(cohorts.index)
    wait_file, names_file = OUT / "costs_wait.parquet", OUT / "costs_spread_names.parquet"
    if args.part != "summary":
        inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
        vix = load_external("vix")["close"].reindex(inp.close.index).ffill()
        picks, hedged = all_picks(inp)
        check_against_backtest(picks, hedged, cohorts)
        if list(vix.index[(vix.shift(1) >= VIX_GATE) & vix.index.isin(gated)]) != gated:
            raise SystemExit("the saved cohorts are not all on gated sessions")
        if args.part in ("all", "wait"):
            measure_wait(inp, picks, gated).to_parquet(wait_file)
        if args.part in ("all", "spread"):
            measure_spreads(picks, gated).to_parquet(names_file)
    res = summarise(pd.read_parquet(wait_file), pd.read_parquet(names_file), cohorts)
    (OUT / "costs_results.json").write_text(json.dumps(res, indent=1))
    for part in ("wait", "spread", "repriced"):
        for label, r in res[part].items():
            logger.info("{} | {}: {}", part, label, {k: round(v, 2) for k, v in r.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
