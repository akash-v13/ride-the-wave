"""The 'if we had started then' test on a survivorship-free universe.

Reads the parquet panel written by scripts/download_universe_history.py (active AND delisted stocks),
builds a point-in-time universe each month (top N by trailing 20-day dollar volume, using only prior
data), and replays the daily strategies from --start with SPY as the benchmark. Nothing in the run
uses information that was not available on the day.

    uv run python scripts/study_survivorship_free.py --start 2017-01-01 --end 2026-09-22 --top 100
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger

from ridethewave.config import load_settings
from ridethewave.daily import build_daily, run_daily
from ridethewave.daily.data import Panel, load_panel
from ridethewave.daily.engine import format_report
from ridethewave.daily.panel_store import PANEL, load_long, monthly_universes
from ridethewave.storage import Database

RUNS = [
    ("price_momentum", {}),
    ("price_momentum", {"allow_short": True}),
    ("residual_momentum", {}),
    ("residual_momentum", {"allow_short": True}),
    ("alpha_combo", {}),
    ("mean_reversion", {}),
    ("mean_reversion", {"allow_short": True}),
    ("mean_reversion_weighted", {}),
    ("low_volatility", {}),
    ("multifactor", {}),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=date(2017, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 22))
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--min-price", type=float, default=5.0)
    ap.add_argument("--min-dollar-volume", type=float, default=2e6)
    ap.add_argument("--out", default="data/research/daily/survivorship-free")
    ap.add_argument("--strategies", default=None, help="comma-separated subset of the run list")
    ap.add_argument(
        "--regimes", action="store_true", help="break each run's excess return over the universe down by market regime"
    )
    args = ap.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    long = load_long(args.min_price, args.min_dollar_volume)
    logger.info("panel: {} rows, {} symbols after liquidity filters", len(long), long["symbol"].nunique())
    universes = monthly_universes(long, args.top)
    chosen = sorted({s for lst in universes.values() for s in lst})
    delisted = pd.read_parquet(PANEL / "assets.parquet").set_index("symbol")["status"]
    n_dead = sum(1 for s in chosen if delisted.get(s) == "inactive")
    logger.info(
        "{} months of universes; {} distinct names ever selected, {} of them since delisted",
        len(universes),
        len(chosen),
        n_dead,
    )

    sub = long[long["symbol"].isin(chosen)]
    wide = {
        c: sub.pivot(index="day", columns="symbol", values=c).sort_index()
        for c in ("open", "high", "low", "close", "volume")
    }
    settings = load_settings()
    db = Database(settings.storage.resolved_db_path())
    spy = load_panel(db, ["SPY"], date(2015, 6, 1), args.end)  # SPY is a fund: it lives in the SQLite cache
    for c in wide:
        wide[c] = wide[c].join(getattr(spy, c)[["SPY"]], how="left")
    panel = Panel(**wide)

    def universe_fn(day: date) -> list[str]:
        return universes.get(day.strftime("%Y-%m"), [])

    regimes = None
    if args.regimes:
        from ridethewave.daily.regime import SECTOR_ETFS_11, regime_history

        ctx = load_panel(db, ["SPY", *SECTOR_ETFS_11, "HYG", "IEF"], date(2016, 1, 1), args.end)
        regimes = regime_history(ctx.close, every=1)["regime"]
        counts = regimes.value_counts().to_dict()
        logger.info("regime days: {}", counts)

    def regime_table(res) -> str:
        ex = (res.equity.pct_change() - res.equal_weight.pct_change()).dropna()
        j = ex.to_frame("ex").join(regimes.rename("regime"), how="inner")
        lines = ["| regime | days | excess vs universe, annualised | t |", "| --- | --- | --- | --- |"]
        for reg, g in j.groupby("regime"):
            n = len(g)
            if n < 20:
                continue
            m, sd = g["ex"].mean(), g["ex"].std()
            t = m / sd * (n**0.5) if sd > 0 else 0.0
            lines.append(f"| {reg} | {n} | {m * 252 * 100:+.1f}% | {t:+.1f} |")
        return "\n".join(lines)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with open(args.out + ".log", "w") as log:
        log.write(
            f"survivorship-free point-in-time top {args.top}; {len(chosen)} names ever selected, {n_dead} delisted\n"
        )
        wanted = set(args.strategies.split(",")) if args.strategies else None
        for kind, params in RUNS:
            if wanted and kind not in wanted:
                continue
            strat = build_daily(kind, params)
            res = run_daily(strat, panel, args.start, args.end, universe_fn=universe_fn, capital=100_000)
            m = res.metrics
            rows.append(
                {
                    "strategy": kind,
                    "params": json.dumps(params),
                    **{k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()},
                }
            )
            log.write(f"##### {kind} {params}\n{format_report(res, last_trades=0)}\n")
            if regimes is not None:
                log.write(regime_table(res) + "\n")
            log.write("\n")
            log.flush()
            logger.info(
                "{} {}: CAGR {:+.1%} Sharpe {:.2f} DD {:+.1%} | SPY {:+.1%} IR {:+.2f} (t {:+.1f}) | "
                "EW {:+.1%} IR {:+.2f} (t {:+.1f})",
                kind,
                params,
                m["cagr"],
                m["sharpe"],
                m["max_dd"],
                m["benchmark_cagr"],
                m["ir_vs_benchmark"],
                m["ir_t_vs_benchmark"],
                m["equal_weight_cagr"],
                m["ir_vs_equal_weight"],
                m["ir_t_vs_equal_weight"],
            )
    pd.DataFrame(rows).to_csv(args.out + ".csv", index=False)
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
