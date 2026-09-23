"""Market intraday momentum on SPY (Gao, Han, Li & Zhou, JFE 2018): does the first half-hour
return predict the last half-hour return? Downloads SPY minute bars (SIP) into the cache if
needed, then measures the effect, its stability by year, and a simple long-only strategy using
SPY (up days) and SH, the inverse ETF (down days).

    uv run python scripts/study_spy_intraday.py --start 2016-01-04 --end 2026-09-18
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import HistoricalBars
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")


def load_minutes(h: HistoricalBars, symbol: str, start: date, end: date) -> pd.DataFrame:
    """Fetch month by month (one API call each) so the cache fills in reusable chunks."""
    frames = []
    cur = start.replace(day=1)
    while cur <= end:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        s = datetime.combine(cur, datetime.min.time(), timezone.utc)
        e = datetime.combine(min(nxt, end + timedelta(days=1)), datetime.min.time(), timezone.utc)
        bars = h.fetch([symbol], s, e)
        frames.append(
            pd.DataFrame(
                [(b.ts, b.open, b.high, b.low, b.close, b.volume) for b in bars],
                columns=["ts", "open", "high", "low", "close", "volume"],
            )
        )
        cur = nxt
    df = pd.concat(frames, ignore_index=True)
    df["et"] = df["ts"].dt.tz_convert(ET)
    df["day"] = df["et"].dt.date
    df["hm"] = df["et"].dt.hour * 100 + df["et"].dt.minute
    return df[(df["hm"] >= 930) & (df["hm"] < 1600)].sort_values("ts").reset_index(drop=True)


def daily_halves(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for day, g in df.groupby("day"):
        g = g.set_index("hm")
        if 930 not in g.index or 1530 not in g.index or len(g) < 300:
            continue
        o930 = g.loc[930, "open"]
        c1000 = g[g.index < 1000]["close"].iloc[-1]
        c1530 = g[g.index < 1530]["close"].iloc[-1]  # close of the 15:29 bar = price at 15:30
        c1559 = g["close"].iloc[-1]
        rows.append(
            {
                "day": day,
                "r_first": c1000 / o930 - 1,
                "r_last": c1559 / c1530 - 1,
                "r_mid": c1530 / c1000 - 1,
                "year": day.year,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=date(2016, 1, 4))
    ap.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    ap.add_argument("--threshold-bp", type=float, default=0.0, help="only trade when |first half-hour| exceeds this")
    ap.add_argument("--cost-bp", type=float, default=1.0, help="round-trip cost assumption for SPY/SH")
    args = ap.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    settings = load_settings()
    clients = make_clients(load_secrets(), settings)
    db = Database(settings.storage.resolved_db_path())
    h = HistoricalBars(clients.data, db, feed="sip")
    spy = load_minutes(h, "SPY", args.start, args.end)
    d = daily_halves(spy)
    print(
        f"SPY minute bars {len(spy):,}; trading days with both halves: {len(d)} ({d.day.min()} to {d.day.max()}); "
        f"API calls {h.calls}"
    )

    # 1. the effect: regression and sign agreement
    x, y = d["r_first"].to_numpy(), d["r_last"].to_numpy()
    beta = np.polyfit(x, y, 1)[0]
    corr = np.corrcoef(x, y)[0, 1]
    agree = np.mean(np.sign(x) == np.sign(y))
    print(
        f"\n[1] r_last on r_first: beta {beta:+.3f}, corr {corr:+.3f}, sign agreement {agree:.1%} "
        f"(50% = nothing); t-stat of corr ≈ {corr * np.sqrt(len(d) - 2) / np.sqrt(1 - corr**2):+.2f}"
    )
    print(
        f"    mean r_last when r_first > 0: {y[x > 0].mean() * 1e4:+.2f} bp (n={int((x > 0).sum())}); "
        f"when r_first < 0: {y[x < 0].mean() * 1e4:+.2f} bp (n={int((x < 0).sum())})"
    )

    # 2. by year
    print("\n[2] by year: corr, sign agreement, mean |r_first| bp, strategy bp/day")
    thr = args.threshold_bp / 1e4
    d["signal"] = np.where(d["r_first"] > thr, 1, np.where(d["r_first"] < -thr, -1, 0))
    d["strat"] = d["signal"] * d["r_last"] - (d["signal"] != 0) * args.cost_bp / 1e4
    by = (
        d.groupby("year")
        .apply(
            lambda g: pd.Series(
                {
                    "days": len(g),
                    "corr": np.corrcoef(g.r_first, g.r_last)[0, 1] if len(g) > 10 else np.nan,
                    "agree": (np.sign(g.r_first) == np.sign(g.r_last)).mean(),
                    "abs_first_bp": g.r_first.abs().mean() * 1e4,
                    "strat_bp_day": g.strat.mean() * 1e4,
                    "strat_total_pct": g.strat.sum() * 100,
                }
            ),
            include_groups=False,
        )
        .round(3)
    )
    print(by.to_string())

    # 2b. the paper's second predictor: previous day's last half-hour; and high-volatility days
    d = d.sort_values("day").reset_index(drop=True)
    d["r_prev_last"] = d["r_last"].shift(1)
    dd_ = d.dropna(subset=["r_prev_last"])
    X = np.column_stack([np.ones(len(dd_)), dd_.r_first, dd_.r_prev_last])
    coef, *_ = np.linalg.lstsq(X, dd_.r_last.to_numpy(), rcond=None)
    resid = dd_.r_last.to_numpy() - X @ coef
    r2 = 1 - resid.var() / dd_.r_last.var()
    print(
        f"\n[2b] r_last = a + b1·r_first + b2·r_prev_last: b1 {coef[1]:+.3f}, b2 {coef[2]:+.3f}, R² {r2:.4f}; "
        f"corr(r_last, r_prev_last) {np.corrcoef(dd_.r_last, dd_.r_prev_last)[0, 1]:+.3f}"
    )
    hi = d[d.r_first.abs() > 0.003]
    hi_corr = np.corrcoef(hi.r_first, hi.r_last)[0, 1]
    hi_agree = (np.sign(hi.r_first) == np.sign(hi.r_last)).mean()
    print(
        f"     high-volatility days (|r_first| > 30 bp, n={len(hi)}): corr {hi_corr:+.3f}, "
        f"sign agreement {hi_agree:.1%}"
    )
    rev = -np.sign(d.r_first.to_numpy()) * d.r_last.to_numpy() - args.cost_bp / 1e4
    print(
        f"     contrarian (fade the first half-hour) after {args.cost_bp} bp: {rev.mean() * 1e4:+.2f} bp/day, "
        f"annualised Sharpe {rev.mean() / rev.std() * np.sqrt(252):.2f}"
    )

    # 3. strategy summary with thresholds
    print(f"\n[3] long SPY (up) / long SH (down) in the last half-hour, cost {args.cost_bp} bp round trip:")
    for t_bp in (0, 10, 20, 30, 50):
        t = t_bp / 1e4
        rf = d.r_first.to_numpy()
        rl = d.r_last.to_numpy()
        sig = np.where(rf > t, 1, np.where(rf < -t, -1, 0))
        ret = sig * rl - (sig != 0) * args.cost_bp / 1e4
        traded = ret[sig != 0]
        if len(traded) == 0:
            continue
        sharpe = traded.mean() / traded.std() * np.sqrt(252) if traded.std() > 0 else float("nan")
        eq = np.cumprod(1 + ret)
        max_dd = (eq / np.maximum.accumulate(eq) - 1).min()
        print(
            f"    |r_first| > {t_bp:>2} bp: trades {int((sig != 0).sum()):>4}/{len(d)} days, "
            f"mean {traded.mean() * 1e4:+.2f} bp, win {np.mean(traded > 0):.1%}, annualised Sharpe {sharpe:.2f}, "
            f"total {(eq[-1] - 1) * 100:+.1f}%, max drawdown {max_dd * 100:.1f}%"
        )

    # 4. halves for honesty
    mid = d.day.iloc[len(d) // 2]
    for label, g in (("first half", d[d.day <= mid]), ("second half", d[d.day > mid])):
        c = np.corrcoef(g.r_first, g.r_last)[0, 1]
        print(
            f"\n    {label} ({g.day.min()}..{g.day.max()}): corr {c:+.3f}, "
            f"agree {(np.sign(g.r_first) == np.sign(g.r_last)).mean():.1%}, "
            f"strategy {g.strat.mean() * 1e4:+.2f} bp/day"
        )
    out = settings.storage.resolved_db_path().parent / "research" / "spy_intraday_daily.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(out, index=False)
    print(f"\nsaved per-day table to {out}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
