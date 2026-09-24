"""Replay a daily-bar portfolio strategy over the adjusted daily cache.

    uv run python scripts/run_daily_backtest.py --strategy residual_momentum --universe mega_caps_20 \\
        --start 2019-01-01 --end 2026-07-24
    uv run python scripts/run_daily_backtest.py --strategy sector_rotation --universe sector_etfs_11 \\
        --param-json '{"dual_momentum_days": 200}' --start 2017-01-01 --end 2026-09-22 --save

Fill the cache first: scripts/download_daily.py --adjust all. --save stores the run in backtest_runs
(feed sip-day-adj) with its equity curve so the dashboards can show it.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta

from loguru import logger

from ridethewave.config import load_settings
from ridethewave.daily import build_daily, load_panel, run_daily
from ridethewave.daily.engine import format_report
from ridethewave.daily.universe import pit_top_fn, resolve
from ridethewave.storage import Database


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--param-json", default=None)
    ap.add_argument("--universe", default=None, help="named universe or comma-separated symbols")
    ap.add_argument("--pit-top", type=int, default=None, help="point-in-time top N by dollar volume from --pool")
    ap.add_argument("--pool", default=None, help="named universe or symbols to rank when --pit-top is used")
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--capital", type=float, default=100_000)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument("--rebalance-days", type=int, default=1)
    ap.add_argument("--benchmark", default="SPY")
    ap.add_argument("--max-gross", type=float, default=1.0)
    ap.add_argument("--warmup-days", type=int, default=600, help="calendar days of history loaded before --start")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if args.quiet:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    settings = load_settings()
    db = Database(settings.storage.resolved_db_path())
    strategy = build_daily(args.strategy, json.loads(args.param_json) if args.param_json else {})
    symbols = resolve(args.universe) if args.universe else []
    pool = resolve(args.pool) if args.pool else symbols
    extra = {args.benchmark}
    for attr in ("symbol", "defensive"):
        v = getattr(strategy.p, attr, None)
        if v:
            extra.add(v)
    load_syms = sorted(set(pool) | set(symbols) | extra)
    panel = load_panel(db, load_syms, args.start - timedelta(days=args.warmup_days), args.end)
    universe_fn = pit_top_fn(panel, args.pit_top) if args.pit_top else None
    res = run_daily(
        strategy,
        panel,
        args.start,
        args.end,
        universe=symbols or None,
        universe_fn=universe_fn,
        capital=args.capital,
        slippage_bps=args.slippage_bps,
        rebalance_days=args.rebalance_days,
        benchmark=args.benchmark,
        max_gross=args.max_gross,
    )
    print(format_report(res))
    if args.save:
        run_id = f"daily-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        db.backtests.insert_run(
            id=run_id,
            start_date=str(args.start),
            end_date=str(args.end),
            feed="sip-day-adj",
            params={
                "strategy": args.strategy,
                "params": res.params,
                "rebalance_days": args.rebalance_days,
                "slippage_bps": args.slippage_bps,
            },
            universe=res.universe,
        )
        db.backtests.add_equity_points(run_id, [(ts.to_pydatetime(), float(v), 0.0) for ts, v in res.equity.items()])
        db.backtests.set_summary(
            run_id, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.metrics.items()}
        )
        print(f"saved as {run_id}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
