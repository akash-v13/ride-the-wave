"""Market intraday momentum (Gao, Han, Li & Zhou, 2018), long-only version.

At ``decision_time`` ET, compare the first half-hour return of SPY (open of 09:30 to the close of
the 09:59 bar) with a threshold. Up: buy SPY. Down: buy SH, the inverse S&P 500 ETF, which is how a
long-only account expresses "short the index". Sell at ``exit_time``. One decision a day; the
strategy manages its own exit and opts out of the global 15:55 flatten.

Study behind it: docs/research/2026-09-22-spy-intraday-momentum.md. Parameters under
``strategies[].params``: threshold_bp (default 10), decision_time ("15:30"), exit_time ("15:58"),
instruments {"up": "SPY", "down": "SH"}.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from ridethewave.models import Bar, Position, Signal, SignalType, Tick
from ridethewave.strategy.base import Strategy, StrategyContext

ET = ZoneInfo("America/New_York")


class SpyIntradayParams(BaseModel):
    threshold_bp: float = Field(10.0, ge=0)
    decision_time: str = "15:30"
    exit_time: str = "15:58"
    index_symbol: str = "SPY"
    inverse_symbol: str = "SH"
    first_half_hour_end: str = "10:00"

    model_config = {"extra": "forbid"}


def _t(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


class SpyIntradayMomentum(Strategy):
    name = "spy_intraday"
    flatten_at_close = False  # sells itself at exit_time, after the global flatten
    uses_protective_stop = False  # a stop on an index ETF over 30 minutes adds nothing but noise

    def __init__(self, params: dict | None = None):
        self.p = SpyIntradayParams.model_validate(params or {})
        self._decision = _t(self.p.decision_time)
        self._exit = _t(self.p.exit_time)
        self._fh_end = _t(self.p.first_half_hour_end)
        self._decided_day: str | None = None

    def symbols(self, universe: list[str]) -> list[str]:
        return [self.p.index_symbol, self.p.inverse_symbol]

    # ---------- signal ----------
    def first_half_hour_return(self, bars: list[Bar], day_start: datetime) -> float | None:
        sess = [b for b in bars if b.ts >= day_start]
        if not sess:
            return None
        first = sess[0]
        if first.ts.astimezone(ET).time() > time(9, 31):
            return None  # missed the open (late start): no decision today
        before = [b for b in sess if b.ts.astimezone(ET).time() < self._fh_end]
        if len(before) < 20:
            return None
        return before[-1].close / first.open - 1.0

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Signal]:
        et = bar.ts.astimezone(ET)
        day = et.strftime("%Y-%m-%d")
        t = et.time()
        pos_idx = ctx.position(self.p.index_symbol)
        pos_inv = ctx.position(self.p.inverse_symbol)
        # exit
        if t >= self._exit:
            out = []
            for pos in (pos_idx, pos_inv):
                if pos is not None and not pos.exit_pending:
                    out.append(
                        Signal(
                            SignalType.SELL,
                            pos.symbol,
                            bar.ts,
                            "timed_exit | end of last half-hour",
                            bar.close,
                            pos.qty,
                        )
                    )
            return out
        # decision, once per day, on the index bar
        if bar.symbol != self.p.index_symbol or t < self._decision or self._decided_day == day:
            return []
        if pos_idx is not None or pos_inv is not None or ctx.open_slots <= 0:
            return []
        self._decided_day = day
        day_start = et.replace(hour=9, minute=30, second=0, microsecond=0).astimezone(bar.ts.tzinfo)
        r = self.first_half_hour_return(ctx.bars(self.p.index_symbol), day_start)
        if r is None:
            return []
        thr = self.p.threshold_bp / 1e4
        if r > thr:
            return [
                Signal(
                    SignalType.BUY,
                    self.p.index_symbol,
                    bar.ts,
                    f"first half-hour {r * 1e4:+.1f} bp > {self.p.threshold_bp} bp",
                    bar.close,
                )
            ]
        if r < -thr:
            inv = ctx.bars(self.p.inverse_symbol)
            ref = inv[-1].close if inv else bar.close
            return [
                Signal(
                    SignalType.BUY,
                    self.p.inverse_symbol,
                    bar.ts,
                    f"first half-hour {r * 1e4:+.1f} bp < -{self.p.threshold_bp} bp",
                    ref,
                )
            ]
        return []

    def on_tick(self, tick: Tick, ctx: StrategyContext) -> list[Signal]:
        pos = ctx.position(tick.symbol)
        if pos is None or pos.exit_pending:
            return []
        pos.update_price(tick.price)
        if tick.ts.astimezone(ET).time() >= self._exit:
            return [
                Signal(SignalType.SELL, tick.symbol, tick.ts, "timed_exit | end of last half-hour", tick.price, pos.qty)
            ]
        return []

    def exit_trigger(self, pos: Position) -> float | None:
        return None
