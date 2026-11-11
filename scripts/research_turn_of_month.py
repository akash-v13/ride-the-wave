"""Signal D (2026-11-10): the turn of the month, on a century of daily US market returns.

The test was fixed before running: docs/research/2026-11-10-signals-a-c-d.md, section 4. Turn days are
the last trading day of a month and the first three of the next. The statistic is the market's average
daily return above cash on those days minus its average on all other days. McConnell and Xu (2008)
measured it on 1926-2005, so 2006 onward is the period that decides.

    uv run python scripts/download_external.py --only ff_factors   # refresh Ken French's file first
    uv run python scripts/research_turn_of_month.py
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger

from ridethewave.config import load_settings
from ridethewave.daily.data import load_panel
from ridethewave.daily.signals import mean_difference, month_position, turn_of_month
from ridethewave.data.external import load as load_external
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "signals"
COST = 0.0001  # one trade at the closing auction; two per turn
PERIODS = {
    "replication 1926-2005": ("1926-07-01", "2005-12-31"),
    "unseen 2006-2026": ("2006-01-01", "2026-12-31"),
    "unseen, first half 2006-2015": ("2006-01-01", "2015-12-31"),
    "unseen, second half 2016-2026": ("2016-01-01", "2026-12-31"),
    "since 2000": ("2000-01-01", "2026-12-31"),
    "whole century": ("1926-07-01", "2026-12-31"),
}


def as_traded(excess: pd.Series, turn: pd.Series) -> pd.Series:
    """Daily return above cash of holding the market on turn days only, 1 bp to get in and 1 bp out."""
    held = turn.astype(float)
    trades = held.diff().abs().fillna(held.iloc[0])  # 1 on the day a holding starts, 1 on the day after it ends
    return excess * held - COST * trades


def sharpe(x: pd.Series) -> float:
    return float(x.mean() / x.std() * math.sqrt(252)) if x.std() > 0 else 0.0


def spy_check(db: Database) -> dict:
    """SPY from Alpaca: bought at the close two sessions before month-end, sold at the close of the
    third session of the new month (the four turn days), less 2 bp."""
    close = load_panel(db, ["SPY"], date(2016, 1, 1), date(2026, 9, 22)).close["SPY"].dropna()
    r = close.pct_change()
    from_start, from_end = month_position(close.index)
    turn = (from_start <= 3) | (from_end <= 1)
    block = (turn != turn.shift()).cumsum()[turn]
    trips = (1 + r[turn]).groupby(block).prod() - 1 - 2 * COST
    days = turn.groupby(block).sum()
    trips = trips[days == 4].loc[lambda s: s.index > 1]  # whole turns only; the first block has no entry price
    return {
        "turns": int(len(trips)),
        "mean_per_turn_bp": float(trips.mean() * 1e4),
        "t": float(trips.mean() / trips.std() * math.sqrt(len(trips))),
        "won": float((trips > 0).mean()),
        "any_four_days_bp": float(r.mean() * 4 * 1e4),
        "from": str(close.index[0].date()),
        "to": str(close.index[-1].date()),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ff = load_external("ff_factors")
    excess = ff["Mkt-RF"].dropna()
    turn = turn_of_month(excess.index)
    traded = as_traded(excess, turn)
    results: dict = {"data": {"from": str(excess.index[0].date()), "to": str(excess.index[-1].date())}}
    for label, (a, b) in PERIODS.items():
        e, t, s = excess.loc[a:b], turn.loc[a:b], traded.loc[a:b]
        r = mean_difference(e, t)
        curve = (1 + s).cumprod()
        results[label] = {
            "turn_bp_a_day": r["flagged"] * 1e4,
            "other_bp_a_day": r["rest"] * 1e4,
            "difference_bp": r["difference"] * 1e4,
            "t": r["t"],
            "turn_days": r["n_flagged"],
            "share_of_days": r["n_flagged"] / r["n"],
            "share_of_market_excess_return": float(e[t].sum() / e.sum()),
            "traded_excess_a_year": float(s.mean() * 252),
            "traded_vol": float(s.std() * math.sqrt(252)),
            "traded_sharpe": sharpe(s),
            "traded_max_dd": float((curve / curve.cummax() - 1).min()),
            "market_sharpe": sharpe(e),
        }
        x = results[label]
        logger.info(
            "{}: turn {:+.1f} bp a day, other {:+.1f}, difference {:+.1f} (t {:+.1f}, {} turn days) | "
            "as traded {:+.1%} a year, Sharpe {:.2f} (market {:.2f}), {:.0%} of the market's excess return",
            label, x["turn_bp_a_day"], x["other_bp_a_day"], x["difference_bp"], x["t"], x["turn_days"],
            x["traded_excess_a_year"], x["traded_sharpe"], x["market_sharpe"], x["share_of_market_excess_return"],
        )  # fmt: skip
    from_start, from_end = month_position(excess.index)
    place = pd.Series(float("nan"), index=excess.index)
    place[from_start <= 5] = from_start[from_start <= 5]
    place[from_end <= 5] = -from_end[from_end <= 5]  # months have about 21 sessions, so the two never clash
    results["by_day"] = {
        label: {f"{int(k):+d}": float(v * 1e4) for k, v in excess.loc[a:b].groupby(place.loc[a:b]).mean().items()}
        for label, (a, b) in list(PERIODS.items())[:2]
    }
    decades = (excess.index.year // 10) * 10
    results["by_decade"] = {
        str(dec): {"difference_bp": mean_difference(g, turn.loc[g.index])["difference"] * 1e4,
                   "t": mean_difference(g, turn.loc[g.index])["t"]}
        for dec, g in excess.groupby(decades)
    }  # fmt: skip
    results["spy_alpaca"] = spy_check(Database(load_settings().storage.resolved_db_path()))
    p1, p2 = results["replication 1926-2005"], results["unseen 2006-2026"]
    h1, h2 = results["unseen, first half 2006-2015"], results["unseen, second half 2016-2026"]
    results["pass"] = {
        "replication": bool(p1["difference_bp"] > 0 and p1["t"] >= 2),
        "unseen": bool(p2["difference_bp"] > 0 and p2["t"] >= 2),
        "both_halves": bool(h1["difference_bp"] > 0 and h2["difference_bp"] > 0),
    }
    results["pass"]["all"] = all(results["pass"].values())
    (OUT / "turn_of_month_results.json").write_text(json.dumps(results, indent=1))
    logger.info("by day: {}", {k: {d: round(v, 1) for d, v in x.items()} for k, x in results["by_day"].items()})
    logger.info(
        "by decade: {}", {k: (round(v["difference_bp"], 1), round(v["t"], 1)) for k, v in results["by_decade"].items()}
    )  # noqa: E501
    logger.info(
        "SPY (Alpaca): {}", {k: round(v, 2) if isinstance(v, float) else v for k, v in results["spy_alpaca"].items()}
    )  # noqa: E501
    logger.info("pass: {}", results["pass"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
