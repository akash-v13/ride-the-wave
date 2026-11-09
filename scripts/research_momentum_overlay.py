"""Momentum with a volatility-scaled overlay on our own data (2026-11-02).

The design was fixed before running: docs/research/2026-11-02-momentum-overlay.md, section 1. The
plain book is `pm_actives`' rule on September's survivorship-free point-in-time top 100. The overlay
holds SPY plus L times the book's return beyond SPY, with L = 10% / the trailing 126-session
volatility of that active return, capped at 2, set the day before, 5 bp on each change.

    uv run python scripts/research_momentum_overlay.py
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
from ridethewave.daily import build_daily, run_daily
from ridethewave.daily.data import Panel, load_panel
from ridethewave.daily.panel_store import load_long, monthly_universes
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "momentum_overlay"
START, END = date(2017, 1, 3), date(2026, 9, 22)
PARAMS = {"formation_days": 231, "skip_days": 21, "fraction": 0.3}  # pm_actives, config/settings.yaml
TARGET, VOL_DAYS, MAX_LEV, COST = 0.10, 126, 2.0, 0.0005
HALVES = {"2017-2021": ("2017-01-01", "2021-12-31"), "2022-2026": ("2022-01-01", "2026-12-31")}
EPISODES = {
    "Covid crash": ("2020-02-19", "2020-03-23"),
    "Vaccine rotation, Nov 2020": ("2020-11-06", "2020-11-13"),
    "2022 bear market": ("2022-01-03", "2022-10-12"),
    "Tariffs 2025": ("2025-02-19", "2025-04-08"),
}


def curve(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    return {
        "cagr": float(eq.iloc[-1] ** (252 / len(r)) - 1),
        "vol": float(r.std() * math.sqrt(252)),
        "sharpe": float(r.mean() / r.std() * math.sqrt(252)),
        "max_dd": float(dd.min()),
    }


def active(a: pd.Series) -> dict:
    eq = (1 + a).cumprod()
    return {
        "ir": float(a.mean() / a.std() * math.sqrt(252)),
        "t": float(a.mean() / a.std() * math.sqrt(len(a))),
        "active_return": float(a.mean() * 252),
        "tracking_error": float(a.std() * math.sqrt(252)),
        "active_max_dd": float((eq / eq.cummax() - 1).min()),
        **{
            f"ir {k}": float(g.mean() / g.std() * math.sqrt(252))
            for k, (x, y) in HALVES.items()
            if len(g := a.loc[x:y])
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    long = load_long(5.0, 2e6)
    universes = monthly_universes(long, 100)
    chosen = sorted({s for lst in universes.values() for s in lst})
    sub = long[long["symbol"].isin(chosen)]
    wide = {
        c: sub.pivot(index="day", columns="symbol", values=c).sort_index()
        for c in ("open", "high", "low", "close", "volume")
    }
    db = Database(load_settings().storage.resolved_db_path())
    spy = load_panel(db, ["SPY"], date(2015, 6, 1), END)
    for c in wide:
        wide[c] = wide[c].join(getattr(spy, c)[["SPY"]], how="left")
    panel = Panel(**wide)
    res = run_daily(build_daily("price_momentum", PARAMS), panel, START, END,
                    universe_fn=lambda d: universes.get(d.strftime("%Y-%m"), []), capital=100_000)  # fmt: skip

    r_book = res.equity.pct_change().dropna()
    r_spy = panel.close["SPY"].ffill().pct_change().reindex(r_book.index)
    a = r_book - r_spy
    lev = (TARGET / (a.rolling(VOL_DAYS).std() * math.sqrt(252))).clip(upper=MAX_LEV).shift(1)
    lev = lev.loc[lev.first_valid_index() :]
    cost = 2 * lev.diff().abs().fillna(0.0) * COST
    r_overlay = r_spy.loc[lev.index] + lev * a.loc[lev.index] - cost
    # both judged from the first day the overlay exists, so they cover the same sessions
    idx = lev.index
    rows = {}
    for label, r in (("plain book", r_book.loc[idx]), ("overlay", r_overlay), ("SPY", r_spy.loc[idx])):
        rows[label] = {**curve(r), **({} if label == "SPY" else active(r - r_spy.loc[idx]))}
        rows[label]["episodes"] = {k: float((1 + r.loc[x:y]).prod() - 1) for k, (x, y) in EPISODES.items()}
        rows[label]["years"] = {str(y): float((1 + g).prod() - 1) for y, g in r.groupby(r.index.year)}
    rows["overlay"]["avg_leverage"] = float(lev.mean())
    rows["overlay"]["leverage_range"] = [float(lev.min()), float(lev.max())]
    rows["overlay"]["overlay_cost_a_year"] = float(cost.mean() * 252)
    rows["from"] = str(idx[0].date())
    p, o = rows["plain book"], rows["overlay"]
    rows["pass"] = bool(o["ir"] >= 0.3 and o["ir 2017-2021"] > 0 and o["ir 2022-2026"] > 0
                        and o["active_max_dd"] > p["active_max_dd"])  # fmt: skip
    (OUT / "results.json").write_text(json.dumps(rows, indent=1))
    pd.DataFrame({"book": r_book.loc[idx], "overlay": r_overlay, "spy": r_spy.loc[idx], "leverage": lev}).to_parquet(
        OUT / "daily.parquet"
    )
    for label in ("plain book", "overlay"):
        d = rows[label]
        logger.info(
            "{:10} CAGR {:+.1%} Sharpe {:.2f} DD {:.1%} | IR vs SPY {:+.2f} (t {:+.1f}; halves {:+.2f} / {:+.2f}) "
            "active DD {:.1%} TE {:.1%}",
            label, d["cagr"], d["sharpe"], d["max_dd"], d["ir"], d["t"], d["ir 2017-2021"], d["ir 2022-2026"],
            d["active_max_dd"], d["tracking_error"],
        )  # fmt: skip
    s = rows["SPY"]
    logger.info(
        "SPY        CAGR {:+.1%} Sharpe {:.2f} DD {:.1%}; from {}", s["cagr"], s["sharpe"], s["max_dd"], rows["from"]
    )
    logger.info("overlay leverage avg {:.2f} range {}; pass: {}", o["avg_leverage"], o["leverage_range"], rows["pass"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
