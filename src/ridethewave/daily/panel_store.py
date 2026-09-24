"""The survivorship-free daily panel on disk (data/daily_panel/, written by scripts/download_universe_history.py):
loading it and building point-in-time monthly universes from it."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PANEL = Path("data/daily_panel")


def load_long(min_price: float, min_dollar_volume: float) -> pd.DataFrame:
    frames = []
    for f in sorted(PANEL.glob("bars_*.parquet")):
        df = pd.read_parquet(f)
        stats = df.groupby("symbol").agg(px=("close", "median"), dv=("volume", "median"), n=("close", "size"))
        stats["dv"] = stats["dv"] * stats["px"]
        keep = stats[(stats["px"] >= min_price) & (stats["dv"] >= min_dollar_volume) & (stats["n"] >= 120)].index
        frames.append(df[df["symbol"].isin(keep)])
    long = pd.concat(frames, ignore_index=True)
    long["day"] = pd.to_datetime(long["day"])
    return long


def monthly_universes(long: pd.DataFrame, top: int, lookback: int = 20, min_price: float = 5.0) -> dict[str, list[str]]:
    """{'YYYY-MM': symbols} ranked by trailing dollar volume as of the last session before the month."""
    dv = long.pivot(index="day", columns="symbol", values="close") * long.pivot(
        index="day", columns="symbol", values="volume"
    )
    px = long.pivot(index="day", columns="symbol", values="close")
    adv = dv.rolling(lookback, min_periods=10).mean()
    out: dict[str, list[str]] = {}
    months = sorted({d.strftime("%Y-%m") for d in adv.index})
    for m in months:
        first = pd.Timestamp(m + "-01")
        prior = adv.index[adv.index < first]
        if len(prior) < lookback:
            continue
        d = prior[-1]
        row = adv.loc[d].dropna()
        row = row[px.loc[d, row.index] >= min_price]
        out[m] = row.sort_values(ascending=False).head(top).index.tolist()
    return out
