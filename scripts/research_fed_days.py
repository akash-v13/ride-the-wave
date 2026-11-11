"""Signal E (2026-11-10): scheduled Fed announcement days, on Ken French's daily US market returns.

The test was fixed before running: docs/research/2026-11-10-signals-e-b-f.md, section 2. The statistic
is the market's average return above cash on announcement days minus its average on all other days.
Lucca and Moench measured it from September 1994 to early 2011, so 2012 onward decides.

    uv run python scripts/build_fomc_dates.py      # refresh the dates first (once a year)
    uv run python scripts/research_fed_days.py
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
from ridethewave.daily.signals import mean_difference
from ridethewave.data import fomc
from ridethewave.data.external import load as load_external
from ridethewave.storage import Database

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "signals"
COST = 0.0002  # in at one close, out at the next: two trades at 1 bp
PERIODS = {
    "replication 1994-09 to 2011-03": ("1994-09-01", "2011-03-31"),
    "unseen 2012-2026": ("2012-01-01", "2026-12-31"),
    "unseen, first half 2012-2018": ("2012-01-01", "2018-12-31"),
    "unseen, second half 2019-2026": ("2019-01-01", "2026-12-31"),
    "after publication 2015-2026": ("2015-01-01", "2026-12-31"),
    "all 1994-2026": ("1994-01-01", "2026-12-31"),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    excess = load_external("ff_factors")["Mkt-RF"].dropna()
    days = pd.DatetimeIndex([pd.Timestamp(d) for d in fomc.load()])
    missing = [str(d.date()) for d in days if excess.index[0] <= d <= excess.index[-1] and d not in excess.index]
    fed = pd.Series(excess.index.isin(days), index=excess.index)
    before, after = fed.shift(-1, fill_value=False), fed.shift(1, fill_value=False)
    results: dict = {"data_to": str(excess.index[-1].date()), "announcement_days_not_trading_days": missing}
    for label, (a, b) in PERIODS.items():
        e, f = excess.loc[a:b], fed.loc[a:b]
        r = mean_difference(e, f)
        ev = e[f] - COST
        results[label] = {
            "fed_bp": r["flagged"] * 1e4, "other_bp": r["rest"] * 1e4, "difference_bp": r["difference"] * 1e4,
            "t": r["t"], "days": r["n_flagged"], "won": float((e[f] > 0).mean()),
            "day_before_bp": float(e[before.loc[a:b]].mean() * 1e4),
            "day_after_bp": float(e[after.loc[a:b]].mean() * 1e4),
            "traded_per_event_bp": float(ev.mean() * 1e4),
            "traded_t": float(ev.mean() / ev.std() * math.sqrt(len(ev))),
            "traded_a_year": float(ev.sum() / (len(e) / 252)),
            "share_of_market_excess_return": float(e[f].sum() / e.sum()),
        }  # fmt: skip
        x = results[label]
        logger.info(
            "{}: Fed days {:+.1f} bp, other days {:+.1f}, difference {:+.1f} (t {:+.1f}, {} days, {:.0%} up) | day "
            "before {:+.1f}, day after {:+.1f} | as traded {:+.1f} bp per event (t {:+.1f}), {:+.2%} a year, "
            "{:.0%} of the market's excess return",
            label, x["fed_bp"], x["other_bp"], x["difference_bp"], x["t"], x["days"], x["won"], x["day_before_bp"],
            x["day_after_bp"], x["traded_per_event_bp"], x["traded_t"], x["traded_a_year"],
            x["share_of_market_excess_return"],
        )  # fmt: skip
    spy = load_panel(Database(load_settings().storage.resolved_db_path()), ["SPY"], date(2016, 1, 1), date(2026, 9, 22))
    r = spy.close["SPY"].dropna().pct_change().dropna()
    on = r[r.index.isin(days)]
    results["spy_alpaca_2016_2026"] = {
        "days": int(len(on)), "fed_bp": float(on.mean() * 1e4), "other_bp": float(r[~r.index.isin(days)].mean() * 1e4),
        "t": float(on.mean() / on.std() * math.sqrt(len(on))),
    }  # fmt: skip
    logger.info("SPY (Alpaca) 2016-2026: {}", {k: round(v, 2) for k, v in results["spy_alpaca_2016_2026"].items()})
    p1, p2 = results["replication 1994-09 to 2011-03"], results["unseen 2012-2026"]
    h1, h2 = results["unseen, first half 2012-2018"], results["unseen, second half 2019-2026"]
    results["pass"] = {
        "replication": bool(p1["difference_bp"] > 0 and p1["t"] >= 2),
        "unseen": bool(p2["difference_bp"] > 0 and p2["t"] >= 2),
        "both_halves": bool(h1["difference_bp"] > 0 and h2["difference_bp"] > 0),
    }
    results["pass"]["all"] = all(results["pass"].values())
    (OUT / "fed_days_results.json").write_text(json.dumps(results, indent=1))
    logger.info("announcement days that were not trading days: {}; pass: {}", missing, results["pass"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
