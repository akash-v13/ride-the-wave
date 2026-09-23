"""Summarise a backtest in numbers a person can act on."""

from __future__ import annotations

from collections import Counter

import pandas as pd

from ridethewave.backtest.engine import BacktestResult


def summarize(res: BacktestResult) -> dict:
    trades = res.trades
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    eq = [e for _, e, _ in res.equity_curve]
    max_dd = 0.0
    peak = eq[0] if eq else 0.0
    for v in eq:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)
    start_eq = eq[0] if eq else 0.0
    end_eq = eq[-1] if eq else 0.0
    return {
        "run_id": res.run_id,
        "start": str(res.start),
        "end": str(res.end),
        "feed": res.feed,
        "days": res.days,
        "universe_size": len(res.universe),
        "bars_replayed": res.bars_replayed,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(trades)) if trades else None,
        "total_pnl": sum(pnls),
        "avg_pnl": (sum(pnls) / len(pnls)) if pnls else None,
        "avg_pnl_pct": (sum(t.pnl_pct for t in trades) / len(trades)) if trades else None,
        "avg_win": (gross_win / len(wins)) if wins else None,
        "avg_loss": (-gross_loss / len(losses)) if losses else None,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "best_trade": max(pnls) if pnls else None,
        "worst_trade": min(pnls) if pnls else None,
        "max_drawdown": max_dd,
        "start_equity": start_eq,
        "end_equity": end_eq,
        "return_on_allocation_pct": (sum(pnls) / res.ledgers[0].allocation * 100) if res.ledgers else None,
        "exit_reasons": dict(Counter(t.exit_reason for t in trades)),
        "avg_hold_minutes": (sum((t.exit_time - t.entry_time).total_seconds() for t in trades) / 60 / len(trades))
        if trades
        else None,
        "api_calls": res.api_calls,
    }


def trades_frame(res: BacktestResult) -> pd.DataFrame:
    rows = [
        {
            "symbol": t.symbol,
            "qty": t.qty,
            "entry_time": t.entry_time,
            "entry": t.entry_price,
            "exit_time": t.exit_time,
            "exit": t.exit_price,
            "peak": t.peak_price,
            "pnl": round(t.pnl, 2),
            "pnl_pct": round(t.pnl_pct, 3),
            "reason": t.exit_reason,
            "held_min": round((t.exit_time - t.entry_time).total_seconds() / 60, 1),
        }
        for t in res.trades
    ]
    return pd.DataFrame(rows)


def daily_frame(res: BacktestResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": l.date,
                "trades": l.trades,
                "wins": l.wins,
                "realized": round(l.realized_pnl, 2),
                "cumulative": round(l.cumulative_realized, 2),
                "allocation": round(l.allocation),
                "next_allocation": round(l.next_allocation),
                "equity": round(l.equity_close or 0, 2),
            }
            for l in res.ledgers
        ]
    )


def verdict(summary: dict) -> str:
    """Plain-English one-liner."""
    n = summary["trades"]
    if n == 0:
        return (
            "No trades were taken. The entry rules never triggered on this data; "
            "loosen the streak or gain thresholds, or widen the universe."
        )
    wr = summary["win_rate"] or 0
    pf = summary["profit_factor"]
    pnl = summary["total_pnl"]
    parts = [f"{n} trades over {summary['days']} days, win rate {wr:.0%}, net {pnl:+,.2f}."]
    if pf is None:
        parts.append("Every trade won, which usually means too few trades to judge.")
    elif pf < 1:
        parts.append(f"Profit factor {pf:.2f}: losses outweigh wins. Not tradable as configured.")
    elif pf < 1.3:
        parts.append(f"Profit factor {pf:.2f}: barely positive; slippage and thin IEX fills could erase it.")
    else:
        parts.append(f"Profit factor {pf:.2f}: promising, but check it holds on IEX-feed data and on more days.")
    if summary["feed"] == "iex":
        parts.append("Note: IEX-feed replay; the live bot trades on the full tape (SIP) since 2026-09-21.")
    return " ".join(parts)


def print_report(res: BacktestResult) -> dict:
    s = summarize(res)
    pf = None if s["profit_factor"] is None else round(s["profit_factor"], 2)
    print("\n=== Backtest", s["run_id"], "===")
    print(
        f"{s['start']} to {s['end']}  feed={s['feed']}  days={s['days']}  universe={s['universe_size']}  "
        f"bars={s['bars_replayed']:,}  api_calls={s['api_calls']}"
    )
    print(
        f"trades={s['trades']}  wins={s['wins']}  losses={s['losses']}  "
        f"win_rate={(s['win_rate'] or 0):.1%}  profit_factor={pf}"
    )
    print(
        f"total_pnl={s['total_pnl']:+,.2f}  avg_pnl={s['avg_pnl'] or 0:+.2f}  "
        f"avg_pnl_pct={s['avg_pnl_pct'] or 0:+.3f}%  "
        f"best={s['best_trade'] or 0:+.2f}  worst={s['worst_trade'] or 0:+.2f}  max_dd={s['max_drawdown']:,.2f}"
    )
    print(f"avg_hold={s['avg_hold_minutes'] or 0:.1f}min  exits={s['exit_reasons']}")
    df = daily_frame(res)
    if not df.empty:
        print("\nPer day:")
        print(df.to_string(index=False))
    tf = trades_frame(res)
    if not tf.empty:
        print("\nTrades (last 25):")
        print(tf.tail(25).to_string(index=False))
    print("\nVerdict:", verdict(s))
    return s
