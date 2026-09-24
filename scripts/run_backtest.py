"""Replay the strategy over past days.

uv run python scripts/run_backtest.py --start 2026-09-08 --end 2026-09-12
uv run python scripts/run_backtest.py --start 2026-09-15 --end 2026-09-16 --feed iex --symbols AAPL,TSLA,NVDA
uv run python scripts/run_backtest.py --start 2026-09-15 --end 2026-09-16 --top 50   # today's most actives (lookahead!)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from loguru import logger

from ridethewave.backtest import ReplayEngine
from ridethewave.backtest.report import print_report
from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.market_data import DailyBars, HistoricalBars
from ridethewave.data.pit_universe import PointInTimeUniverse
from ridethewave.data.universe import UniverseBuilder
from ridethewave.storage import Database


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--feed", choices=["sip", "iex"], default=None, help="default: settings.backtest.feed")
    ap.add_argument("--symbols", default=None, help="comma-separated static universe")
    ap.add_argument("--top", type=int, default=None, help="use today's most-actives (lookahead bias, for smoke tests)")
    ap.add_argument(
        "--pit-top",
        type=int,
        default=None,
        help="point-in-time universe: top N by trailing 20-session dollar volume, recomputed daily",
    )
    ap.add_argument("--settings", default=None)
    ap.add_argument("--slippage", type=float, default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--strategy", default="wave_rider", help="registry name; params via --param-json")
    ap.add_argument("--param-json", default=None, help="strategy params, e.g. '{\"threshold_bp\": 20}'")
    args = ap.parse_args()

    settings = load_settings(args.settings)
    if args.feed:
        settings.backtest.feed = args.feed
    if args.slippage is not None:
        settings.backtest.slippage_pct = args.slippage
    if args.quiet:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    clients = make_clients(load_secrets(), settings)
    db = Database(settings.storage.resolved_db_path())

    import json as _json

    from ridethewave.strategy import build

    strategy = build(args.strategy, settings, _json.loads(args.param_json) if args.param_json else {})

    universe_fn = None
    if args.pit_top:
        pit = PointInTimeUniverse(clients, db, settings.universe)
        pit.preload(args.start, args.end)
        universe_fn = lambda d: pit.universe_for(d, args.pit_top, exclude_funds=strategy.stocks_only)  # noqa: E731
        universe = []
    elif args.symbols:
        universe = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.top:
        settings.universe.top = args.top
        settings.universe.source = "most_actives"
        universe = UniverseBuilder(clients, settings.universe, settings.alpaca.data_feed).build()
        logger.warning("universe is TODAY's most-actives; results carry lookahead bias")
    elif settings.universe.source == "static":
        universe = settings.universe.static_symbols
    else:
        universe = UniverseBuilder(clients, settings.universe, settings.alpaca.data_feed).build()
        logger.warning("universe is TODAY's screener output; results carry lookahead bias")

    history = HistoricalBars(clients.data, db, feed=settings.backtest.feed)

    # Daily context (previous sessions only) for strategies that use on_session_start; cached in SQLite.
    daily = DailyBars(clients.data, db)
    daily_memo: dict[str, dict[str, list]] = {}

    def daily_provider(symbols, day):
        key = str(day)
        if key not in daily_memo:
            bars = daily.fetch(symbols, day - timedelta(days=40), day - timedelta(days=1))
            by: dict[str, list] = {}
            for b in bars:
                by.setdefault(b.symbol, []).append(b)
            for lst in by.values():
                lst.sort(key=lambda b: b.ts)
            daily_memo[key] = by
        return daily_memo[key]

    engine = ReplayEngine(
        settings,
        db,
        history,
        universe,
        args.start,
        args.end,
        universe_fn=universe_fn,
        strategy=strategy,
        daily_provider=daily_provider,
    )
    res = engine.run()
    summary = print_report(res)
    db.backtests.set_summary(res.run_id, summary)
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
