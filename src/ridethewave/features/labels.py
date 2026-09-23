"""What happened after a bar. Pure; no I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ridethewave.config import ExitSettings
from ridethewave.models import Bar


@dataclass(frozen=True, slots=True)
class Outcome:
    entry_price: float
    mfe_pct: float  # best high relative to entry within the horizon
    mae_pct: float  # worst low relative to entry within the horizon (negative or zero)
    ret_h_pct: float  # close at the end of the horizon relative to entry
    hit_target_first: bool | None  # True target first, False stop first, None neither within horizon
    bars_to_resolve: int | None
    strat_pnl_pct: float  # P/L the strategy's exit rules would have produced
    strat_exit_reason: str
    strat_bars_held: int

    def as_dict(self) -> dict:
        return asdict(self)


def forward_outcome(future: list[Bar], entry_price: float, horizon: int, target_pct: float, stop_pct: float):
    """Scan the next ``horizon`` bars. If a bar touches both target and stop, the stop wins (pessimistic)."""
    fut = future[:horizon]
    if not fut or entry_price <= 0:
        return None
    target = entry_price * (1 + target_pct / 100)
    stop = entry_price * (1 - stop_pct / 100)
    mfe = max(b.high for b in fut)
    mae = min(b.low for b in fut)
    hit, n = None, None
    for i, b in enumerate(fut, 1):
        if b.low <= stop:
            hit, n = False, i
            break
        if b.high >= target:
            hit, n = True, i
            break
    return (
        (mfe / entry_price - 1) * 100,
        (mae / entry_price - 1) * 100,
        (fut[-1].close / entry_price - 1) * 100,
        hit,
        n,
    )


def simulate_exit(future: list[Bar], entry_price: float, ex: ExitSettings, slippage_pct: float = 0.05):
    """Replay the strategy's exit rules from a fill at ``entry_price`` over ``future`` bars (oldest first).

    Mirrors backtest/sim_broker + strategy/wave_rider: peak from bar highs, wave trigger checked on
    the close, stop checked on the low (gap fills at the open), timeout on bar count, flatten at end.
    Returns (pnl_pct, reason, bars_held).
    """
    if not future or entry_price <= 0:
        return None
    slip = slippage_pct / 100
    peak = entry_price
    floor = entry_price * (1 + ex.min_gain_pct / 100)
    stop = entry_price * (1 - ex.hard_stop_pct / 100) if ex.hard_stop_pct > 0 else None
    for i, b in enumerate(future, 1):
        if stop is not None and b.low <= stop:
            px = min(stop, b.open) * (1 - slip)
            return (px / entry_price - 1) * 100, "hard_stop", i
        peak = max(peak, b.high)
        trig = peak * (1 - ex.trail_pct / 100)
        if b.close <= trig and trig >= floor:
            # sells at the next bar's open in the simulator; approximate with this close
            px = b.close * (1 - slip)
            return (px / entry_price - 1) * 100, "wave_exit", i
        if ex.max_hold_minutes > 0 and i >= ex.max_hold_minutes:
            if not ex.timeout_exit_only_if_profitable or b.close > entry_price:
                px = b.close * (1 - slip)
                return (px / entry_price - 1) * 100, "timeout", i
    last = future[-1]
    px = last.close * (1 - slip)
    return (px / entry_price - 1) * 100, "end_of_data", len(future)


def label(
    future: list[Bar],
    entry_price: float,
    ex: ExitSettings,
    horizon: int = 60,
    target_pct: float = 1.0,
    stop_pct: float = 1.0,
) -> Outcome | None:
    fo = forward_outcome(future, entry_price, horizon, target_pct, stop_pct)
    se = simulate_exit(future, entry_price, ex)
    if fo is None or se is None:
        return None
    mfe, mae, ret_h, hit, n = fo
    pnl, reason, held = se
    return Outcome(entry_price, mfe, mae, ret_h, hit, n, pnl, reason, held)
