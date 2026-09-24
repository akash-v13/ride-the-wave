"""Parameter sweep and time-of-day analysis over cached history.

    # base run with hour-of-day breakdown
    uv run python scripts/sweep.py --start 2026-06-01 --end 2026-09-16 --pit-top 50 --breakdown

    # sweep a grid; dotted keys into settings, comma-separated values; all combinations run
    uv run python scripts/sweep.py --start 2026-06-01 --end 2026-09-16 --pit-top 50 \\
        --param entry.entry_start=09:35,09:45,10:00,10:30 --param entry.entry_end=12:00,14:00,15:00

    # named grids
    uv run python scripts/sweep.py ... --grid time | streak | exit | hold

Bars are read from the SQLite cache once and kept in memory, so each extra combination costs only
the replay itself. Run scripts/download_history.py first for the same dates and universe.
Results: a table on stdout and a CSV under data/sweeps/.
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from loguru import logger

from ridethewave.backtest import ReplayEngine
from ridethewave.backtest.report import summarize
from ridethewave.clients import make_clients
from ridethewave.config import Settings, load_secrets, load_settings
from ridethewave.data.market_data import DailyBars, HistoricalBars
from ridethewave.data.pit_universe import PointInTimeUniverse
from ridethewave.storage import Database
from ridethewave.strategy import build

ET = ZoneInfo("America/New_York")

GRIDS = {
    "time": {
        "entry.entry_start": ["09:31", "09:40", "10:00", "10:30", "11:00"],
        "entry.entry_end": ["11:30", "13:00", "15:00"],
    },
    "streak": {"entry.green_streak_minutes": [3, 4, 5, 7, 10], "entry.min_streak_gain_pct": [0.3, 0.5, 1.0]},
    "exit": {"exit.trail_pct": [0.3, 0.5, 1.0, 1.5], "exit.min_gain_pct": [0.2, 0.3, 0.5]},
    "hold": {"exit.max_hold_minutes": [30, 60, 120, 240], "exit.hard_stop_pct": [0.5, 1.0, 2.0]},
}


class MemoHistory:
    """Wraps HistoricalBars; remembers every (symbols, start, end) result so repeat runs never touch SQLite."""

    def __init__(self, inner: HistoricalBars):
        self.inner = inner
        self.feed = inner.feed
        self.calls = 0
        self._memo: dict[tuple, list] = {}

    def fetch(self, symbols, start, end, use_cache=True):
        key = (tuple(sorted(set(symbols))), start, end)
        if key not in self._memo:
            self._memo[key] = self.inner.fetch(symbols, start, end, use_cache=use_cache)
        return self._memo[key]


def apply_overrides(base: Settings, overrides: dict[str, str]) -> Settings:
    d = base.model_dump(mode="json")
    for k, v in overrides.items():
        node = d
        parts = k.split(".")
        for p in parts[:-1]:
            node = node[p]
        cur = node[parts[-1]]
        if str(v).lower() in ("null", "none"):
            node[parts[-1]] = None
        elif isinstance(cur, bool):
            node[parts[-1]] = str(v).lower() in ("true", "1", "yes")
        elif isinstance(cur, (int, float)):
            node[parts[-1]] = type(cur)(v)
        elif cur is None:
            try:
                node[parts[-1]] = float(v)
            except ValueError:
                node[parts[-1]] = v
        else:
            node[parts[-1]] = v
    return Settings.model_validate(d)


def hour_breakdown(trades) -> pd.DataFrame:
    rows = defaultdict(list)
    for t in trades:
        h = t.entry_time.astimezone(ET)
        bucket = f"{h.hour:02d}:{'00' if h.minute < 30 else '30'}"
        rows[bucket].append(t)
    out = []
    for b in sorted(rows):
        ts = rows[b]
        pn = [t.pnl for t in ts]
        w = [p for p in pn if p > 0]
        losses = -sum(p for p in pn if p <= 0)
        out.append(
            {
                "entry_half_hour": b,
                "trades": len(ts),
                "win_rate": round(len(w) / len(ts), 2),
                "avg_pnl_pct": round(sum(t.pnl_pct for t in ts) / len(ts), 3),
                "total_pnl": round(sum(pn), 2),
                "profit_factor": round(sum(w) / losses, 2) if losses > 0 else None,
                "avg_hold_min": round(sum((t.exit_time - t.entry_time).total_seconds() for t in ts) / 60 / len(ts)),
            }
        )
    return pd.DataFrame(out)


def reason_breakdown(trades) -> pd.DataFrame:
    rows = defaultdict(list)
    for t in trades:
        rows[t.exit_reason].append(t)
    return pd.DataFrame(
        [
            {
                "exit_reason": r,
                "trades": len(ts),
                "win_rate": round(sum(t.pnl > 0 for t in ts) / len(ts), 2),
                "avg_pnl_pct": round(sum(t.pnl_pct for t in ts) / len(ts), 3),
                "total_pnl": round(sum(t.pnl for t in ts), 2),
            }
            for r, ts in sorted(rows.items())
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--pit-top", type=int, default=None)
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    ap.add_argument("--param", action="append", default=[], help="dotted.key=v1,v2,...")
    ap.add_argument("--grid", choices=list(GRIDS), default=None)
    ap.add_argument("--breakdown", action="store_true", help="hour-of-day and exit-reason tables for base and best")
    ap.add_argument("--save-trades", action="store_true", help="also write every combination's trades to a parquet")
    ap.add_argument("--settings", default=None)
    ap.add_argument("--strategy", default="wave_rider", help="registry name")
    ap.add_argument(
        "--param-json", default=None, help="fixed strategy params (json); swept keys go in --param strategy.<k>"
    )
    args = ap.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    base = load_settings(args.settings)
    base.backtest.feed = args.feed
    clients = make_clients(load_secrets(), base)
    db = Database(base.storage.resolved_db_path())
    history = MemoHistory(HistoricalBars(clients.data, db, feed=args.feed))
    daily = DailyBars(clients.data, db)
    daily_memo: dict = {}

    def daily_provider(symbols, day):
        from datetime import timedelta

        key = (tuple(sorted(symbols)), day)
        if key not in daily_memo:
            bars = daily.fetch(symbols, day - timedelta(days=40), day - timedelta(days=1))
            by: dict[str, list] = {}
            for b in bars:
                by.setdefault(b.symbol, []).append(b)
            for lst in by.values():
                lst.sort(key=lambda b: b.ts)
            daily_memo[key] = by
        return daily_memo[key]

    import json as _json

    base_params = _json.loads(args.param_json) if args.param_json else {}

    universe_fn = None
    universe: list[str] = []
    if args.pit_top:
        pit = PointInTimeUniverse(clients, db, base.universe)
        pit.preload(args.start, args.end)
        cache: dict[date, list[str]] = {}

        from ridethewave.strategy import build as _build

        stocks_only = _build(args.strategy, base, base_params).stocks_only

        def universe_fn(d, _pit=pit, _n=args.pit_top, _c=cache, _so=stocks_only):
            if d not in _c:
                _c[d] = _pit.universe_for(d, _n, exclude_funds=_so)
            return _c[d]
    elif args.symbols:
        universe = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        sys.exit("give --pit-top or --symbols")

    grid: dict[str, list[str]] = dict(GRIDS[args.grid]) if args.grid else {}
    for p in args.param:
        k, v = p.split("=", 1)
        grid[k] = [x.strip() for x in v.split(",")]
    keys = list(grid)
    combos = (
        [dict(zip(keys, vals, strict=True)) for vals in itertools.product(*[grid[k] for k in keys])] if keys else [{}]
    )
    print(f"{len(combos)} combination(s) over {args.start}..{args.end} feed={args.feed}")

    results = []
    trades_by_combo = {}
    t0 = time.time()
    for i, combo in enumerate(combos, 1):
        settings_overrides = {k: v for k, v in combo.items() if not k.startswith("strategy.")}
        params = _json.loads(_json.dumps(base_params))
        for k, v in combo.items():
            if k.startswith("strategy."):
                node = params
                parts = k.split(".")[1:]
                for pth in parts[:-1]:
                    node = node.setdefault(pth, {})
                try:
                    node[parts[-1]] = float(v) if "." in str(v) else int(v)
                except ValueError:
                    node[parts[-1]] = v
        s = apply_overrides(base, settings_overrides)
        strategy = build(args.strategy, s, params)
        eng = ReplayEngine(
            s,
            None,
            history,
            list(universe),
            args.start,
            args.end,
            universe_fn=universe_fn,
            run_id=f"sweep-{i}",
            strategy=strategy,
            daily_provider=daily_provider,
        )
        t1 = time.time()
        res = eng.run()
        summ = summarize(res)
        row = {
            **combo,
            "trades": summ["trades"],
            "win_rate": summ["win_rate"],
            "profit_factor": summ["profit_factor"],
            "total_pnl": round(summ["total_pnl"], 2),
            "avg_pnl_pct": summ["avg_pnl_pct"],
            "max_dd": round(summ["max_drawdown"], 2),
            "avg_hold": summ["avg_hold_minutes"],
            "secs": round(time.time() - t1, 1),
        }
        results.append(row)
        trades_by_combo[i - 1] = res.trades
        print(
            f"[{i}/{len(combos)}] {combo} -> trades={row['trades']} wr={row['win_rate']} pf={row['profit_factor']} "
            f"pnl={row['total_pnl']} ({row['secs']}s)",
            flush=True,
        )

    df = pd.DataFrame(results)
    if "profit_factor" in df:
        df = df.sort_values(["profit_factor", "total_pnl"], ascending=False, na_position="last")
    pd.set_option("display.width", 200)
    print("\n=== Results (best first) ===")
    print(df.to_string(index=False))
    out_dir = Path(base.storage.resolved_db_path()).parent / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"sweep-{datetime.now():%Y%m%d-%H%M%S}.csv"
    df.to_csv(out, index=False)
    print(f"\nsaved {out}  ({time.time() - t0:.0f}s total)")
    if args.save_trades:
        rows = []
        for idx, ts in trades_by_combo.items():
            for t in ts:
                rows.append(
                    {
                        "combo": idx,
                        **{k: str(v) for k, v in combos[idx].items()},
                        "symbol": t.symbol,
                        "entry_time": t.entry_time,
                        "exit_time": t.exit_time,
                        "entry": t.entry_price,
                        "exit": t.exit_price,
                        "qty": t.qty,
                        "pnl": t.pnl,
                        "pnl_pct": t.pnl_pct,
                        "reason": t.exit_reason,
                    }
                )
        tp = out.with_name(out.stem + "-trades.parquet")
        pd.DataFrame(rows).to_parquet(tp, index=False)
        print(f"saved per-trade P/L for {len(trades_by_combo)} combination(s): {tp}")

    if args.breakdown:
        base_idx = 0
        best_idx = int(df.index[0]) if len(df) else 0
        for label, idx in (("BASE", base_idx), ("BEST", best_idx)):
            if label == "BEST" and best_idx == base_idx:
                break
            ts = trades_by_combo[idx]
            print(f"\n=== {label} {combos[idx]}: by entry half-hour (ET) ===")
            print(hour_breakdown(ts).to_string(index=False) if ts else "no trades")
            print(f"\n=== {label}: by exit reason ===")
            print(reason_breakdown(ts).to_string(index=False) if ts else "no trades")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
