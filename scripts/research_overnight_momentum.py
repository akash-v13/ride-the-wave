"""Signal C (2026-11-10): momentum held overnight only.

The test was fixed before running: docs/research/2026-11-10-signals-a-c-d.md, section 3. Each day the
30% of the point-in-time top 300 with the highest twelve-month return (skipping the latest month, known
the day before) are bought at the close and sold at the next open. The statistic is their overnight
return beyond the universe's. It must average at least 4 bp a night, because two auction trades a night
cost about 2 bp.

    uv run python scripts/research_overnight_momentum.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
from loguru import logger
from research_statarb_volgated import HALVES, START, nw_t

from ridethewave.config import load_settings
from ridethewave.daily.signals import momentum_12_1
from ridethewave.daily.statarb_data import load_inputs
from ridethewave.data.external import tbill_daily_return
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "signals"
TOP, COST, BAR, ERROR, LAGS = 0.30, 0.0002, 0.0004, 0.5, 5  # COST: two trades a night at 1 bp


def nightly(close: pd.DataFrame, open_: pd.DataFrame, member: pd.DataFrame, max_move: float | None) -> pd.DataFrame:
    """One row per night: average overnight and next-day returns of the winners, losers and universe.

    The row for day t is the night from t's close to the open of t+1, then the day session of t+1."""
    mom = momentum_12_1(close)
    night = open_.shift(-1) / close - 1
    day = (close / open_ - 1).shift(-1)
    ok = member & mom.notna() & night.notna() & day.notna()
    if max_move is not None:
        ok &= night.abs() <= max_move
    pct = mom.where(ok).rank(axis=1, pct=True)
    win, lose = pct > 1 - TOP, pct <= TOP
    out = pd.DataFrame(
        {
            "win_night": night.where(win).mean(axis=1), "all_night": night.where(ok).mean(axis=1),
            "lose_night": night.where(lose).mean(axis=1), "win_day": day.where(win).mean(axis=1),
            "all_day": day.where(ok).mean(axis=1), "lose_day": day.where(lose).mean(axis=1),
            "names": ok.sum(axis=1), "winners": win.sum(axis=1),
        }
    )  # fmt: skip
    out = out[out["names"] >= 100].copy()
    out["x"] = out["win_night"] - out["all_night"]
    return out


def block(g: pd.DataFrame, cash: pd.Series) -> dict:
    net = g["x"] - COST
    rf = cash.reindex(g.index).fillna(0.0)
    held = g["win_night"] - COST - rf  # the rule itself, above cash
    base = g["all_night"] - COST - rf  # the whole universe held overnight, for comparison
    bp = {
        k: float(g[k].mean() * 1e4) for k in ("win_night", "all_night", "lose_night", "win_day", "all_day", "lose_day")
    }
    return {
        "nights": int(len(g)),
        "x_bp": float(g["x"].mean() * 1e4),
        "x_t": nw_t(g["x"], LAGS),
        "net_bp": float(net.mean() * 1e4),
        "net_t": nw_t(net, LAGS),
        "share_of_nights_ahead": float((g["x"] > 0).mean()),
        "long_short_night_bp": bp["win_night"] - bp["lose_night"],
        "long_short_night_t": nw_t(g["win_night"] - g["lose_night"], LAGS),
        "long_short_day_bp": bp["win_day"] - bp["lose_day"],
        **{k + "_bp": v for k, v in bp.items()},
        "rule_excess_a_year": float(held.mean() * 252),
        "rule_vol": float(held.std() * math.sqrt(252)),
        "rule_sharpe": float(held.mean() / held.std() * math.sqrt(252)),
        "universe_overnight_sharpe": float(base.mean() / base.std() * math.sqrt(252)),
    }  # fmt: skip


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inp = load_inputs(Database(load_settings().storage.resolved_db_path()))
    cash = tbill_daily_return()
    n = nightly(inp.close, inp.open, inp.member, ERROR).loc[START:]
    raw = nightly(inp.close, inp.open, inp.member, None).loc[START:]
    night = inp.open.shift(-1) / inp.close - 1
    errors = int(((night.abs() > ERROR) & inp.member).loc[START:].sum().sum())
    n.to_parquet(OUT / "overnight_momentum_nights.parquet")
    results = {
        "all": block(n, cash),
        **{k: block(n.loc[a:b], cash) for k, (a, b) in HALVES.items()},
        "years": {
            str(y): {"x_bp": float(g["x"].mean() * 1e4), "net_bp": float((g["x"] - COST).mean() * 1e4)}
            for y, g in n.groupby(n.index.year)
        },  # fmt: skip
        "errors_left_out": errors,
        "with_errors_left_in": {"x_bp": float(raw["x"].mean() * 1e4), "net_t": nw_t(raw["x"] - COST, LAGS)},
        "average_names": float(n["names"].mean()),
        "average_winners": float(n["winners"].mean()),
        "from": str(n.index[0].date()),
        "to": str(n.index[-1].date()),
    }
    a, h1, h2 = results["all"], *(results[k] for k in HALVES)
    results["pass"] = {
        "at_least_4bp": bool(a["x_bp"] >= BAR * 1e4),
        "net_t_at_least_2": bool(a["net_t"] >= 2),
        "both_halves": bool(h1["net_bp"] > 0 and h2["net_bp"] > 0),
    }
    results["pass"]["all"] = all(results["pass"].values())
    (OUT / "overnight_momentum_results.json").write_text(json.dumps(results, indent=1))
    for label in ("all", *HALVES):
        r = results[label]
        logger.info(
            "{}: {} nights | winners beyond universe {:+.2f} bp a night (t {:+.1f}), after 2 bp {:+.2f} (t {:+.1f}) | "
            "overnight: winners {:+.2f}, universe {:+.2f}, losers {:+.2f} | day: winners {:+.2f}, universe {:+.2f}, "
            "losers {:+.2f} | winners minus losers: night {:+.2f} (t {:+.1f}), day {:+.2f} | rule {:+.1%} a year "
            "above cash, Sharpe {:.2f}",
            label, r["nights"], r["x_bp"], r["x_t"], r["net_bp"], r["net_t"], r["win_night_bp"], r["all_night_bp"],
            r["lose_night_bp"], r["win_day_bp"], r["all_day_bp"], r["lose_day_bp"], r["long_short_night_bp"],
            r["long_short_night_t"], r["long_short_day_bp"], r["rule_excess_a_year"], r["rule_sharpe"],
        )  # fmt: skip
    logger.info("years: {}", {y: round(v["x_bp"], 2) for y, v in results["years"].items()})
    logger.info("errors left out: {}; with them in: {}", errors, results["with_errors_left_in"])
    logger.info("names {:.0f}, winners {:.0f}; pass: {}", results["average_names"], results["average_winners"],
                results["pass"])  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
