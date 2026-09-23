"""Which features separate winning entries from losing ones?

    uv run python scripts/analyze_features.py data/features/features-2026-06-01-2026-09-16-sip.parquet

For the candidate rows (bars the current entry rule would buy) and, for comparison, all prospect rows,
prints: overall strategy P/L and hit rate; then for each feature, quintile buckets with count, win rate,
mean strategy P/L, and mean forward return. A feature is useful when the buckets differ a lot.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

FEATURES = [
    "rvol_20",
    "streak_vol_ratio",
    "trade_count_ratio",
    "vwap_dist_pct",
    "session_ret_pct",
    "range_pct_20",
    "gain_vs_range",
    "spy_ret_5m_pct",
    "spy_ret_session_pct",
    "minutes_since_open",
    "streak",
    "streak_gain_pct",
]


def overall(df: pd.DataFrame, name: str) -> None:
    n = len(df)
    if n == 0:
        print(f"{name}: no rows")
        return
    wins = (df["strat_pnl_pct"] > 0).mean()
    pf_num = df.loc[df["strat_pnl_pct"] > 0, "strat_pnl_pct"].sum()
    pf_den = -df.loc[df["strat_pnl_pct"] <= 0, "strat_pnl_pct"].sum()
    hit = df["hit_target_first"].dropna()
    print(
        f"{name}: rows={n:,}  win_rate={wins:.1%}  mean_pnl={df['strat_pnl_pct'].mean():+.3f}%  "
        f"pf={pf_num / pf_den if pf_den else float('nan'):.2f}  "
        f"hit_target_first={hit.mean() if len(hit) else float('nan'):.1%} (n={len(hit):,})  "
        f"mean_ret_h={df['ret_h_pct'].mean():+.3f}%  mean_mfe={df['mfe_pct'].mean():+.3f}%  "
        f"mean_mae={df['mae_pct'].mean():+.3f}%"
    )
    print("   exits:", df["strat_exit_reason"].value_counts().to_dict())


def buckets(df: pd.DataFrame, feature: str, q: int = 5) -> pd.DataFrame | None:
    col = df[feature].dropna()
    if col.nunique() < q:
        return None
    try:
        cats = pd.qcut(df[feature], q=q, duplicates="drop")
    except ValueError:
        return None
    g = df.groupby(cats, observed=True)
    out = pd.DataFrame(
        {
            "n": g.size(),
            "win_rate": g["strat_pnl_pct"].apply(lambda s: (s > 0).mean()).round(3),
            "mean_pnl_pct": g["strat_pnl_pct"].mean().round(3),
            "pf": g["strat_pnl_pct"]
            .apply(lambda s: s[s > 0].sum() / -s[s <= 0].sum() if (s <= 0).any() else float("inf"))
            .round(2),
            "mean_ret_h_pct": g["ret_h_pct"].mean().round(3),
            "stop_rate": g["strat_exit_reason"].apply(lambda s: (s == "hard_stop").mean()).round(3),
        }
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--all", action="store_true", help="also bucket all prospect rows, not only candidates")
    args = ap.parse_args()
    df = pd.read_parquet(args.path)
    pd.set_option("display.width", 200)
    print(f"loaded {len(df):,} rows, {df['day'].nunique()} days, {df['symbol'].nunique()} symbols")
    cand = df[df["candidate"]]
    print()
    overall(df, "ALL PROSPECTS (every bar in the window)")
    overall(cand, "CANDIDATES (current entry rule)")
    for name, sub in (("CANDIDATES", cand),) + ((("ALL PROSPECTS", df),) if args.all else ()):
        print(f"\n==================== {name}: feature buckets (quintiles) ====================")
        for f in FEATURES:
            b = buckets(sub, f)
            if b is None:
                continue
            spread = b["mean_pnl_pct"].max() - b["mean_pnl_pct"].min()
            print(f"\n--- {f}   (spread between best and worst bucket: {spread:.3f}% per trade) ---")
            print(b.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
