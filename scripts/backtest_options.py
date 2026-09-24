"""Grid backtest of option structures on rebuilt historical chains (ridethewave.options.backtest).

uv run python scripts/download_option_history.py        # once
uv run python scripts/backtest_options.py               # full grid -> data/research/options/grid.csv + report.md
"""

from __future__ import annotations

import argparse
import itertools
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger

from ridethewave.config import OptionsSpec
from ridethewave.options.backtest import HistoricalChains, run_options_backtest

OUT = Path("data/research/options")
TEMPLATES = [
    "long_iron_condor",
    "bull_put_spread",
    "long_iron_butterfly",
    "short_strangle",
    "covered_call",
    "long_straddle",
]
EXITS = {
    "managed": {"profit_target_pct": 0.5, "stop_mult": 2.0, "close_dte": 7},
    "hold": {"profit_target_pct": 1.0, "stop_mult": 10.0, "close_dte": 1},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlyings", default="SPY,QQQ,IWM")
    ap.add_argument("--templates", default=",".join(TEMPLATES))
    ap.add_argument("--steps", default="0.01,0.025")
    ap.add_argument("--start", type=date.fromisoformat, default=date(2024, 2, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 18))
    ap.add_argument(
        "--spread-pct", type=float, default=0.03, help="modelled full bid-ask spread as a fraction of price"
    )
    ap.add_argument("--spread-fraction", type=float, default=1.0, help="share of the half-spread paid per leg")
    ap.add_argument("--risk-fraction", type=float, default=0.2)
    args = ap.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for und in args.underlyings.split(","):
        chains = HistoricalChains.load(und, spread_pct=args.spread_pct)
        for tpl, step, gate, (ex_name, ex) in itertools.product(
            args.templates.split(","), [float(x) for x in args.steps.split(",")], ["none", "vrp"], EXITS.items()
        ):
            spec = OptionsSpec(
                id="bt",
                template=tpl,
                underlying=und,
                strike_step_pct=step,
                entry_gate=gate,
                spread_fraction=args.spread_fraction,
                risk_fraction=args.risk_fraction,
                **ex,
            )
            res = run_options_backtest(spec, chains, args.start, args.end)
            m = res.metrics
            rows.append(
                {
                    "underlying": und,
                    "template": tpl,
                    "step": step,
                    "gate": gate,
                    "exits": ex_name,
                    **{k: v for k, v in m.items() if k != "exits"},
                    "exit_mix": m["exits"],
                }
            )
            print(
                f"{und} {tpl:22s} step {step:.3f} gate {gate:4s} {ex_name:7s} | ret {m['total_return']:+7.1%} CAGR {m['cagr']:+6.1%} "
                f"Sharpe {m['sharpe']:+.2f} DD {m['max_dd']:+6.1%} | {m['trades']:3d} tr win {m['win_rate']:.0%} PF {m['profit_factor']:.2f} "
                f"| halves {m['h1_return']:+.1%}/{m['h2_return']:+.1%} | {und} {m['underlying_return']:+.1%} Sh {m['underlying_sharpe']:.2f}",
                flush=True,
            )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "grid.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
