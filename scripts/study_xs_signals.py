"""Is there anything to predict? Diagnostic for the Kakushadze cross-sectional day-trade signals.

For every session and every company stock in the point-in-time universe: the overnight return
r_on = ln(open / prev close), the previous day's open-to-close return r_pd, the open-to-``mid`` return
r_id, each demeaned across that day's universe; and the forward return from the ``entry`` minute's
open to the ``exit`` minute's close (log), raw and SPY-adjusted. Reports quintile means with day-block
bootstrap intervals, split halves, the daily rank correlation (information coefficient) and the forward
return by raw overnight-gap bucket. Follows the research protocol in .claude/skills/dixon-ml-finance.

    uv run python scripts/study_xs_signals.py --start 2026-06-01 --end 2026-09-16 --pit-top 50
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import DailyBars, HistoricalBars, regular_session_utc
from ridethewave.data.pit_universe import PointInTimeUniverse
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")
BP = 10_000.0


def et_minute(day: date, hhmm: str) -> datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, dtime(hh, mm), ET).astimezone(timezone.utc)


def collect(args) -> pd.DataFrame:
    settings = load_settings()
    clients = make_clients(load_secrets(), settings)
    db = Database(settings.storage.resolved_db_path())
    pit = PointInTimeUniverse(clients, db, settings.universe)
    pit.preload(args.start, args.end)
    hist = HistoricalBars(clients.data, db, feed=args.feed)
    daily = DailyBars(clients.data, db)
    rows = []
    day = args.start
    while day <= args.end:
        if day.weekday() >= 5:
            day += timedelta(days=1)
            continue
        syms = pit.universe_for(day, args.pit_top, exclude_funds=True)
        s_utc, e_utc = regular_session_utc(day)
        bars = hist.fetch(syms + ["SPY"], s_utc, e_utc) if syms else []
        if not bars:
            day += timedelta(days=1)
            continue
        df = pd.DataFrame([(b.symbol, b.ts, b.open, b.close) for b in bars], columns=["symbol", "ts", "open", "close"])
        groups = {s: x.set_index("ts") for s, x in df.groupby("symbol")}
        prev: dict[str, tuple[float, float]] = {}
        for b in sorted(daily.fetch(syms, day - timedelta(days=10), day - timedelta(days=1)), key=lambda b: b.ts):
            prev[b.symbol] = (b.open, b.close)

        def px(sym: str, ts: datetime, col: str, _g=groups) -> float | None:
            x = _g.get(sym)
            if x is None or ts not in x.index:
                return None
            return float(x.at[ts, col])

        t_entry, t_mid, t_exit = et_minute(day, args.entry), et_minute(day, args.mid), et_minute(day, args.exit)
        spy_e, spy_x = px("SPY", t_entry, "open"), px("SPY", t_exit, "close")
        spy_f = np.log(spy_x / spy_e) if spy_e and spy_x else np.nan
        for s in syms:
            if s not in prev:
                continue
            po, pc = prev[s]
            o, e_o, x_c = px(s, s_utc, "open"), px(s, t_entry, "open"), px(s, t_exit, "close")
            m_c, m_o = px(s, t_mid - timedelta(minutes=1), "close"), px(s, t_mid, "open")
            if None in (o, e_o, x_c) or min(o, e_o, x_c, po, pc) <= 0:
                continue
            rows.append(
                {
                    "day": day,
                    "symbol": s,
                    "r_on": np.log(o / pc),
                    "r_pd": np.log(pc / po),
                    "r_id": np.log(m_c / o) if m_c else np.nan,
                    "f_entry": np.log(x_c / e_o),
                    "f_mid": np.log(x_c / m_o) if m_o else np.nan,
                    "spy_f": spy_f,
                }
            )
        day += timedelta(days=1)
    data = pd.DataFrame(rows)
    for col in ("r_on", "r_pd", "r_id"):
        data[col + "_dm"] = data[col] - data.groupby("day")[col].transform("mean")
    data["fx_entry"] = data["f_entry"] - data["spy_f"].fillna(0.0)
    data["fx_mid"] = data["f_mid"] - data["spy_f"].fillna(0.0)
    return data


def boot_mean(d: pd.DataFrame, col: str, n: int = 2000, seed: int = 7) -> tuple[float, float, float]:
    """Mean of ``col`` with a day-block bootstrap 95% interval (days resampled with replacement)."""
    by_day = d.groupby("day")[col].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    sums, counts = by_day["sum"].to_numpy(), by_day["count"].to_numpy()
    idx = rng.integers(0, len(by_day), size=(n, len(by_day)))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return float(d[col].mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def quintiles(data: pd.DataFrame, score: str, fwd: str, sign: float) -> str:
    d = data.dropna(subset=[score, fwd]).copy()
    d["s"] = sign * d[score]
    d["q"] = d.groupby("day")["s"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 5, labels=False) + 1 if len(x) >= 10 else np.nan
    )
    d = d.dropna(subset=["q"])
    days = sorted(d["day"].unique())
    half = days[len(days) // 2]
    out = [
        "| Quintile (5 = strongest buy score) | n | mean fwd (bp) | 95% CI | 1st half | 2nd half | win % |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for q in (1, 2, 3, 4, 5):
        x = d[d["q"] == q]
        m, lo, hi = boot_mean(x, fwd)
        h1, h2 = x[x["day"] < half][fwd].mean(), x[x["day"] >= half][fwd].mean()
        win = (x[fwd] > 0).mean() * 100
        ci = f"[{lo * BP:+.1f}, {hi * BP:+.1f}]"
        out.append(f"| Q{q} | {len(x)} | {m * BP:+.1f} | {ci} | {h1 * BP:+.1f} | {h2 * BP:+.1f} | {win:.0f} |")
    ics = d.groupby("day").apply(lambda g: g["s"].corr(g[fwd], method="spearman"), include_groups=False).dropna()
    t = ics.mean() / ics.std() * np.sqrt(len(ics)) if len(ics) > 2 and ics.std() > 0 else float("nan")
    pos = (ics > 0).mean() * 100
    out.append(
        f"\nDaily rank IC: mean {ics.mean():+.3f}, t = {t:+.2f} over {len(ics)} days ({pos:.0f}% of days positive)."
    )
    return "\n".join(out)


def gap_buckets(data: pd.DataFrame) -> str:
    edges = [-np.inf, -5, -3, -1.5, -0.5, 0.5, 1.5, 3, 5, np.inf]
    d = data.dropna(subset=["f_entry"]).copy()
    d["b"] = pd.cut(d["r_on"] * 100, edges)
    out = [
        "| Overnight gap (%) | n | fwd raw (bp) | fwd vs SPY (bp) | 95% CI (vs SPY) | win % |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for b, x in d.groupby("b", observed=True):
        if len(x) < 20:
            continue
        m, lo, hi = boot_mean(x, "fx_entry")
        raw, win = x["f_entry"].mean() * BP, (x["f_entry"] > 0).mean() * 100
        out.append(f"| {b} | {len(x)} | {raw:+.1f} | {m * BP:+.1f} | [{lo * BP:+.1f}, {hi * BP:+.1f}] | {win:.0f} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--pit-top", type=int, default=50)
    ap.add_argument("--entry", default="09:35")
    ap.add_argument("--mid", default="10:30")
    ap.add_argument("--exit", default="15:55")
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    ap.add_argument("--out", default="data/research/xs_signals.parquet")
    args = ap.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    data = collect(args)
    data.to_parquet(args.out)
    n_days, n_syms = data["day"].nunique(), data["symbol"].nunique()
    print(f"{len(data)} stock-days, {n_days} days, {n_syms} symbols, {args.start}..{args.end}")
    raw_mean = data["f_entry"].mean() * BP
    spy_mean = data.groupby("day")["spy_f"].first().mean() * BP
    window = f"Forward window {args.entry} open -> {args.exit} close"
    print(f"{window}; mean raw {raw_mean:+.1f} bp, SPY {spy_mean:+.1f} bp/day\n")
    for title, score, fwd, sign in [
        ("Overnight reversal (buy the biggest relative overnight losers)", "r_on_dm", "fx_entry", -1.0),
        ("Previous-day momentum (buy yesterday's relative intraday winners)", "r_pd_dm", "fx_entry", +1.0),
        (f"Intraday reversal at {args.mid} (buy the relative laggards since the open)", "r_id_dm", "fx_mid", -1.0),
    ]:
        print(f"## {title}\n")
        print(quintiles(data, score, fwd, sign) + "\n")
    print("## Forward return by raw overnight gap\n")
    print(gap_buckets(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
