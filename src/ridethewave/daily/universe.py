"""Universes for the daily engine: named lists (as TraderPro used) and point-in-time top-N by dollar volume."""

from __future__ import annotations

from datetime import date

import pandas as pd

from ridethewave.daily.data import Panel

# TraderPro's test universe (its database rows): 20 mega caps with LLY, not BRK.B as in its code.
MEGA_CAPS_20 = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "LLY", "JPM",
    "V", "UNH", "XOM", "MA", "HD", "PG", "COST", "JNJ", "ABBV", "WMT",
]  # fmt: skip
SECTOR_ETFS_11 = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLRE", "XLU", "XLC"]
MULTI_ASSET_8 = ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
NAMED: dict[str, list[str]] = {
    "mega_caps_20": MEGA_CAPS_20,
    "sector_etfs_11": SECTOR_ETFS_11,
    "multi_asset_8": MULTI_ASSET_8,
    "spy": ["SPY"],
    "qqq": ["QQQ"],
}


def resolve(name_or_symbols: str) -> list[str]:
    if name_or_symbols in NAMED:
        return list(NAMED[name_or_symbols])
    return [s.strip().upper() for s in name_or_symbols.split(",") if s.strip()]


def pit_top_fn(panel: Panel, top: int, lookback: int = 20, min_price: float = 5.0, exclude: set[str] | None = None):
    """A ``universe_fn(day)`` ranking the panel's symbols by trailing average dollar volume using only bars
    strictly before ``day``. The panel should be raw (unadjusted) or adjusted; ranks barely change."""
    dv = panel.dollar_volume(lookback)
    exclude = exclude or set()

    def fn(day: date) -> list[str]:
        ts = pd.Timestamp(day)
        prior = dv.index[dv.index < ts]
        if len(prior) == 0:
            return []
        row = dv.loc[prior[-1]].dropna()
        px = panel.close.loc[prior[-1]]
        row = row[(px[row.index] >= min_price) & ~row.index.isin(list(exclude))]
        return row.sort_values(ascending=False).head(top).index.tolist()

    return fn
