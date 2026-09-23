"""End-of-day bookkeeping and the reinvestment rule. Pure functions."""

from __future__ import annotations

from ridethewave.config import CapitalSettings
from ridethewave.models import DailyLedger, Position, Trade


def next_allocation(cumulative_realized: float, cfg: CapitalSettings) -> float:
    """Tomorrow's allocation = base + reinvest% of cumulative realized gains, floored."""
    alloc = cfg.base_allocation + cfg.reinvest_gains_pct / 100.0 * cumulative_realized
    floor = cfg.base_allocation * cfg.min_allocation_ratio
    return max(alloc, floor)


def build_ledger(
    date: str,
    mode: str,
    run_id: str,
    trades: list[Trade],
    positions: list[Position],
    prev: DailyLedger | None,
    allocation: float,
    cfg: CapitalSettings,
    equity_close: float | None = None,
) -> DailyLedger:
    realized = sum(t.pnl for t in trades)
    unrealized = sum(p.unrealized_pnl for p in positions)
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    cumulative = (prev.cumulative_realized if prev else 0.0) + realized
    return DailyLedger(
        date=date,
        mode=mode,
        run_id=run_id,
        base_allocation=cfg.base_allocation,
        allocation=allocation,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        cumulative_realized=cumulative,
        trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        largest_win=max(wins) if wins else 0.0,
        largest_loss=min(losses) if losses else 0.0,
        next_allocation=next_allocation(cumulative, cfg),
        equity_close=equity_close,
        extra={
            "win_rate": (len(wins) / len(trades)) if trades else None,
            "avg_pnl_pct": (sum(t.pnl_pct for t in trades) / len(trades)) if trades else None,
        },
    )
