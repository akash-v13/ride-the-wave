"""Statistical arbitrage, auction fills (2026-11-09): what the VIX-gated reversal would earn if every trade
were filled at the official opening auction price.

The design was fixed before running: docs/research/2026-11-09-statarb-auction-fills.md. For the repaired
backtest's picks on every gated session, the opening auction price (the largest opening print in
Alpaca's auction history) is compared with the daily bar's open the backtest used, on the entry day
and on the exit day five sessions later, long minus short and hedged as the backtest hedges.

    uv run python scripts/research_statarb_auction.py
    uv run python scripts/research_statarb_auction.py --part summary
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timezone
from pathlib import Path

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger
from research_statarb_costs import ETFS, HALVES, HOLD, START, WORKERS, all_picks, check_against_backtest, client, t_stat

from ridethewave.config import load_settings
from ridethewave.daily.costs import auction_price, long_short_gap
from ridethewave.daily.statarb_data import StatArbInputs, load_inputs
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "statarb"
AUCTION_BP, HEDGE_BP, BORROW_BP = 1.0, 5.0, 1.0  # allowance per stock trade at the auction; per cohort


def session_gaps(day: pd.Timestamp, symbols: set[str]) -> pd.DataFrame:
    """Each symbol's opening auction price and unadjusted daily open on one session."""
    syms, d = sorted(symbols), day.strftime("%Y-%m-%d")
    auctions: dict[str, float | None] = {}
    opens: dict[str, float] = {}
    for i in range(0, len(syms), 100):
        part = syms[i : i + 100]
        params = {"symbols": ",".join(part), "start": d, "end": d, "feed": "sip", "limit": 10000}
        raw = client().get("/stocks/auctions", params).get("auctions") or {}
        for sym, days in raw.items():
            auctions[sym] = auction_price(days[0].get("o") if days else None)
        bars = client().get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=part,
                timeframe=TimeFrame.Day,
                start=datetime.combine(day.date(), time(0), timezone.utc),
                end=datetime.combine(day.date(), time(23, 59), timezone.utc),
                feed=DataFeed.SIP,
                adjustment=Adjustment.RAW,
                limit=None,
            )
        )
        for sym, rows in bars.items():
            if rows:
                opens[sym] = float(rows[0]["o"])
    frame = pd.DataFrame({"auction": pd.Series(auctions, dtype=float), "open": pd.Series(opens, dtype=float)})
    frame["gap"] = frame["auction"] / frame["open"] - 1
    # Alpaca's auction history has no opening prints for the ARCA-listed ETFs in many later years, so the
    # hedges are left at the backtest's price: their gap is zero and only the stocks are re-priced.
    frame.loc[frame.index.isin(ETFS), "gap"] = 0.0
    return frame


def measure(inp: StatArbInputs, picks: dict, gated: list[pd.Timestamp]) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    logger.info("auction prints and daily opens for {} sessions", len(sessions))
    with ThreadPoolExecutor(WORKERS) as pool:
        gaps = dict(zip(sessions, pool.map(lambda s: session_gaps(s, need[s]), sessions), strict=True))
    bm, bs, sectors = inp.b_m.shift(1), inp.b_s.shift(1), inp.sectors.shift(1)
    rows, names = [], []
    for d in gated:
        longs, shorts = picks[d]
        args = (longs, shorts, bm.loc[d], bs.loc[d], sectors.loc[d])
        entry, n_in = long_short_gap(gaps[d]["gap"], *args)
        leave, n_out = long_short_gap(gaps[exit_day[d]]["gap"], *args) if d in exit_day else (None, 0)
        rows.append({"day": d, "entry": entry, "exit": leave, "names": len(longs) + len(shorts),
                     "priced_entry": n_in, "priced_exit": n_out})  # fmt: skip
        g = gaps[d].reindex(longs + shorts)
        names.append(pd.DataFrame({"day": d, "symbol": g.index, "gap": g["gap"].to_numpy()}))
    return pd.DataFrame(rows).set_index("day"), pd.concat(names, ignore_index=True)


def summarise(gaps: pd.DataFrame, names: pd.DataFrame, cohorts: pd.DataFrame) -> dict:
    res: dict = {}
    cost = 4 * AUCTION_BP + HEDGE_BP + BORROW_BP
    gaps = gaps.assign(net=gaps["exit"] - gaps["entry"])
    for label, (a, b) in {"all": (START, "2026-12-31"), **HALVES}.items():
        c, g = cohorts.loc[a:b], gaps.loc[a:b]
        g = g.reindex(c.index)
        gross = c["gross"] * 1e4 + g["net"].fillna(0.0) * 1e4
        res[label] = {
            "cohorts": int(len(c)),
            "entry_gap_bp": float(g["entry"].mean() * 1e4), "entry_gap_t": t_stat(g["entry"]),
            "exit_gap_bp": float(g["exit"].mean() * 1e4), "exit_gap_t": t_stat(g["exit"]),
            "gross_daily_open_bp": float(c["gross"].mean() * 1e4), "gross_auction_bp": float(gross.mean()),
            "cost_bp": cost, "net_auction_bp": float(gross.mean() - cost),
            "net_auction_t": t_stat(gross - cost, HOLD - 1),
            "net_without_allowance_bp": float(gross.mean() - HEDGE_BP - BORROW_BP),
            "breakeven_cost_per_trade_bp": float((gross.mean() - HEDGE_BP - BORROW_BP) / 4),
            "priced_share": float((g["priced_entry"] / g["names"]).mean()),
        }  # fmt: skip
    gap_bp = names["gap"].dropna() * 1e4
    res["names"] = {
        "picks": int(len(names)), "with_auction_and_open": float(names["gap"].notna().mean()),
        "same_price": float((gap_bp.abs() < 0.05).mean()), "mean_abs_gap_bp": float(gap_bp.abs().mean()),
        "median_abs_gap_bp": float(gap_bp.abs().median()), "p90_abs_gap_bp": float(gap_bp.abs().quantile(0.9)),
        "mean_gap_bp": float(gap_bp.mean()),
    }  # fmt: skip
    years = (cohorts["gross"] * 1e4 + gaps["net"].reindex(cohorts.index).fillna(0.0) * 1e4 - cost).groupby(
        cohorts.index.year
    )
    res["years_net_bp"] = {str(y): float(v) for y, v in years.mean().items()}
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["all", "summary"], default="all")
    args = ap.parse_args()
    cohorts = pd.read_parquet(OUT / "volgated_cohorts_A.parquet")
    gaps_file, names_file = OUT / "auction_gaps.parquet", OUT / "auction_names.parquet"
    if args.part == "all":
        inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
        picks, hedged = all_picks(inp)
        check_against_backtest(picks, hedged, cohorts)
        gaps, names = measure(inp, picks, list(cohorts.index))
        gaps.to_parquet(gaps_file)
        names.to_parquet(names_file)
    res = summarise(pd.read_parquet(gaps_file), pd.read_parquet(names_file), cohorts)
    (OUT / "auction_results.json").write_text(json.dumps(res, indent=1))
    for label, r in res.items():
        logger.info("{}: {}", label, {k: round(v, 3) for k, v in r.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
