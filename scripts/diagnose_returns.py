"""Is there anything to predict? Autocorrelation and conditional-return diagnostics on cached minute bars.

    uv run python scripts/diagnose_returns.py --start 2026-06-01 --end 2026-09-16
    uv run python scripts/diagnose_returns.py --start 2026-06-01 --end 2026-09-16 --feed iex --window 09:31-11:30

Follows the protocol in Dixon, Halperin & Bilokon ch. 6 and 8 (ADF stationarity, ACF/PACF against the
99% white-noise band 2.58/sqrt(T), Ljung-Box on residuals), then asks the strategy's own question directly:
what happens after k consecutive up closes, and after our candidate rule fires?
Reads the SQLite bar cache only; run scripts/download_history.py first.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import warnings
from datetime import date

import numpy as np
import pandas as pd

from ridethewave.config import load_settings

warnings.filterwarnings("ignore")


def aggregate_bars(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Roll 1-minute rows up to N-minute bars per symbol-day, bucketed from 09:30 ET. Keeps the first ts."""
    mins = df["et"].dt.hour * 60 + df["et"].dt.minute - (9 * 60 + 30)
    df = df.assign(bucket=mins // minutes)
    out = (
        df.sort_values("ts")
        .groupby(["symbol", "day", "bucket"], as_index=False)
        .agg(ts=("ts", "first"), et=("et", "first"), close=("close", "last"))
    )
    return out.sort_values(["symbol", "ts"]).reset_index(drop=True)


def pooled_acf(x: np.ndarray, lags: list[int]) -> list[float]:
    x = x - x.mean()
    v = float((x * x).sum())
    return [float((x[k:] * x[:-k]).sum() / v) for k in lags]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--feed", default="sip")
    ap.add_argument("--window", default="09:31-11:30", help="entry window ET for the conditional tables")
    ap.add_argument("--streak-gain", type=float, default=1.0, help="candidate rule: 3-bar gain %%")
    ap.add_argument("--bar-minutes", type=int, default=1, help="aggregate cached 1-min bars to this size first")
    args = ap.parse_args()
    from statsmodels.stats.diagnostic import acorr_ljungbox
    from statsmodels.tsa.stattools import adfuller

    settings = load_settings()
    con = sqlite3.connect(settings.storage.resolved_db_path())
    df = pd.read_sql_query(
        "SELECT symbol, ts, close FROM bars WHERE feed=? AND ts>=? AND ts<? ORDER BY symbol, ts",
        con,
        params=[args.feed, str(args.start), str(args.end + pd.Timedelta(days=1))],
    )
    if df.empty:
        sys.exit("no cached bars for that range/feed")
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["et"] = df["ts"].dt.tz_convert("America/New_York")
    df["day"] = df["et"].dt.date
    t = df["et"].dt.time
    df = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
    if args.bar_minutes > 1:
        df = aggregate_bars(df, args.bar_minutes)
    g = df.groupby(["symbol", "day"])
    df["r"] = g["close"].transform(lambda s: np.log(s).diff())
    df = df.dropna(subset=["r"])
    print(
        f"feed={args.feed} bar={args.bar_minutes}min bars={len(df):,} symbols={df.symbol.nunique()} "
        f"days={df.day.nunique()}"
    )

    r = df["r"].to_numpy()
    lags = list(range(1, 11))
    print("\n[1] pooled ACF of 1-min log returns, lags 1..10:", [round(a, 4) for a in pooled_acf(r, lags)])
    print("    99% white-noise band: ±", round(2.58 / np.sqrt(len(r)), 4))

    per = (
        df.groupby("symbol")["r"]
        .apply(lambda s: pd.Series({"lag1": s.autocorr(1), "lag2": s.autocorr(2), "lag3": s.autocorr(3), "n": len(s)}))
        .unstack()
    )
    per = per[per["n"] > 5000]
    print("\n[2] per-symbol autocorrelation (symbols with >5000 bars):")
    print(per[["lag1", "lag2", "lag3"]].describe(percentiles=[0.1, 0.5, 0.9]).round(4).to_string())
    print("    share with lag1 < 0:", round(float((per["lag1"] < 0).mean()), 2))

    print("\n[3] stationarity and whiteness, three most-traded symbols:")
    for sym in per.sort_values("n", ascending=False).index[:3]:
        s = df.loc[df.symbol == sym, "r"].to_numpy()
        adf_p = adfuller(s[:50000], autolag="AIC")[1]
        lb = acorr_ljungbox(s, lags=[3, 10], return_df=True)
        print(
            f"    {sym}: n={len(s):,} ADF p={adf_p:.1e} Ljung-Box p(3)={lb.loc[3, 'lb_pvalue']:.2e} "
            f"p(10)={lb.loc[10, 'lb_pvalue']:.2e} lag1={per.loc[sym, 'lag1']:+.4f}"
        )

    df["up"] = (df["r"] > 0).astype(int)
    g = df.groupby(["symbol", "day"])
    df["streak"] = g["up"].transform(lambda s: s.groupby((s != s.shift()).cumsum()).cumsum() * s)
    horizons = (1, 5, 10, 30, 60) if args.bar_minutes == 1 else (1, 2, 3, 6, 12)
    hmin = {h: h * args.bar_minutes for h in horizons}
    for h in horizons:
        df[f"fwd{h}"] = g["close"].transform(lambda s, h=h: np.log(s.shift(-h) / s))
    df["gain3"] = g["close"].transform(lambda s: (s / s.shift(3) - 1) * 100)
    w0, w1 = args.window.split("-")
    t = df["et"].dt.time
    win = df[(t >= pd.Timestamp(w0).time()) & (t < pd.Timestamp(w1).time())]

    def row(label, sub):
        d = {"condition": label, "n": len(sub)}
        d.update({f"fwd{hmin[h]}m_bp": round(float(sub[f"fwd{h}"].mean() * 1e4), 2) for h in horizons})
        d["p_next_up"] = round(float((sub["fwd1"] > 0).mean()), 3)
        return d

    rows = [row("unconditional", win)]
    for k in range(0, 5):
        rows.append(row(f"up-streak = {k}", win[win["streak"] == k]))
    rows.append(row("up-streak >= 5", win[win["streak"] >= 5]))
    cand = win[(win["streak"] >= 3) & (win["gain3"] >= args.streak_gain)]
    rows.append(row(f"streak>=3 & gain>={args.streak_gain}% (candidate rule)", cand))
    print(
        f"\n[4] mean forward log-return (basis points) in {args.window} ET, by condition "
        f"(streak counted in {args.bar_minutes}-min bars; horizons in minutes):"
    )
    print(pd.DataFrame(rows).to_string(index=False))
    last = horizons[-1]
    if len(cand) > 30:
        se = cand[f"fwd{last}"].std() / np.sqrt(len(cand)) * 1e4
        print(
            f"\n    candidate rule fwd{hmin[last]}m: {cand[f'fwd{last}'].mean() * 1e4:+.1f} ± {2 * se:.1f} bp "
            "(mean ± 2 s.e.)"
        )
    print(
        "\nReading: a momentum entry needs positive, growing conditional forward returns after the trigger and "
        "positive low-lag autocorrelation. Values inside the noise band or negative mean the trigger is not "
        "predictive on its own; any edge must come from filters, exits, or a different trigger."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
