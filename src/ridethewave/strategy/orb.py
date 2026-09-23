"""Opening-range breakout on stocks in play, long-only version (Zarattini, Aziz & Barbon, 2024, adapted).

At the open, each symbol's first ``range_minutes`` bars define the opening range. A symbol is "in
play" when its opening-range volume is at least ``rvol_min`` times its normal volume for that many
minutes (from the last 14 sessions' average daily volume). After the range closes, the first
1-minute close above the range high buys; the stop sits ``stop_atr`` average true ranges below the
entry (ATR from daily bars, 14 sessions); the position is sized to risk ``risk_pct`` of the
allocation between entry and stop, capped by the slot; exit at the stop or at ``exit_time``.
Short side (break below the low) needs short selling and is not implemented.

Research: docs/research/2026-09-22-orb-backtest.md.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from ridethewave.models import Bar, Position, Signal, SignalType, Tick
from ridethewave.strategy.base import Strategy, StrategyContext

ET = ZoneInfo("America/New_York")


class OrbParams(BaseModel):
    range_minutes: int = Field(5, ge=1, le=60)
    rvol_min: float = Field(2.0, ge=0)
    stop_atr: float = Field(0.1, gt=0)
    risk_pct: float = Field(1.0, gt=0)  # of allocation, per trade
    entry_until: str = "11:30"
    exit_time: str = "15:55"
    max_positions: int = Field(5, ge=1)
    min_price: float = 5.0

    model_config = {"extra": "forbid"}


def _t(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


class OpeningRangeBreakout(Strategy):
    name = "orb"
    flatten_at_close = True
    uses_protective_stop = True

    def __init__(self, params: dict | None = None):
        self.p = OrbParams.model_validate(params or {})
        self._entry_until = _t(self.p.entry_until)
        self._exit = _t(self.p.exit_time)
        self.avg_vol: dict[str, float] = {}  # average daily volume, last 14 sessions
        self.atr: dict[str, float] = {}  # average true range (dollars), 14 sessions
        self.range_high: dict[str, float] = {}
        self.range_vol: dict[str, float] = {}
        self.in_play: set[str] = set()
        self.done_today: set[str] = set()
        self.stops: dict[str, float] = {}
        self._day: str | None = None

    # ---------- daily context ----------
    def on_session_start(self, day: str, daily: dict[str, list[Bar]]) -> None:
        self._day = day
        self.avg_vol.clear()
        self.atr.clear()
        self.range_high.clear()
        self.range_vol.clear()
        self.in_play.clear()
        self.done_today.clear()
        self.stops.clear()
        for sym, bars in daily.items():
            last = bars[-14:]
            if len(last) < 5:
                continue
            self.avg_vol[sym] = sum(b.volume for b in last) / len(last)
            trs = []
            for i in range(1, len(last)):
                prev_close = last[i - 1].close
                trs.append(
                    max(last[i].high - last[i].low, abs(last[i].high - prev_close), abs(last[i].low - prev_close))
                )
            if trs:
                self.atr[sym] = sum(trs) / len(trs)

    # ---------- bars ----------
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Signal]:
        et = bar.ts.astimezone(ET)
        mins = et.hour * 60 + et.minute - (9 * 60 + 30)
        sym = bar.symbol
        pos = ctx.position(sym)
        if pos is not None:
            return self._check_exit(pos, bar.close, bar.ts)
        if mins < 0:
            return []
        if mins < self.p.range_minutes:
            self.range_high[sym] = max(self.range_high.get(sym, 0.0), bar.high)
            self.range_vol[sym] = self.range_vol.get(sym, 0.0) + bar.volume
            if mins == self.p.range_minutes - 1:
                av = self.avg_vol.get(sym)
                if av and av > 0:
                    normal = av * self.p.range_minutes / 390
                    if self.range_vol[sym] >= self.p.rvol_min * normal and bar.close >= self.p.min_price:
                        self.in_play.add(sym)
            return []
        if sym not in self.in_play or sym in self.done_today or sym in ctx.pending_entries:
            return []
        if et.time() >= self._entry_until or ctx.open_slots <= 0:
            return []
        hi = self.range_high.get(sym)
        atr = self.atr.get(sym)
        if hi is None or atr is None or atr <= 0 or bar.close <= hi:
            return []
        stop = bar.close - self.p.stop_atr * atr
        if stop <= 0 or (bar.close - stop) / bar.close > 0.1:
            return []
        self.done_today.add(sym)
        self.stops[sym] = stop
        rvol = self.range_vol[sym] / (self.avg_vol[sym] * self.p.range_minutes / 390)
        return [
            Signal(
                SignalType.BUY,
                sym,
                bar.ts,
                f"orb_break high={hi:.2f} rvol={rvol:.1f} atr={atr:.2f}",
                bar.close,
                noise_pct=None,
            )
        ]

    def on_tick(self, tick: Tick, ctx: StrategyContext) -> list[Signal]:
        pos = ctx.position(tick.symbol)
        if pos is None:
            return []
        return self._check_exit(pos, tick.price, tick.ts)

    def _check_exit(self, pos: Position, price: float, ts: datetime) -> list[Signal]:
        if pos.exit_pending:
            return []
        pos.update_price(price)
        stop = self.stops.get(pos.symbol)
        if stop is not None and price <= stop:
            return [Signal(SignalType.SELL, pos.symbol, ts, f"orb_stop | stop={stop:.2f}", price, pos.qty)]
        if ts.astimezone(ET).time() >= self._exit:
            return [Signal(SignalType.SELL, pos.symbol, ts, "orb_close | timed exit", price, pos.qty)]
        return []

    def exit_trigger(self, pos: Position) -> float | None:
        return self.stops.get(pos.symbol)

    # sizing hook used by the order manager when present
    def qty_for(self, symbol: str, price: float, allocation: float, slot_dollars: float) -> int | None:
        stop = self.stops.get(symbol)
        if stop is None or price <= stop:
            return None
        risk_dollars = allocation * self.p.risk_pct / 100
        qty = int(risk_dollars / (price - stop))
        return max(0, min(qty, int(slot_dollars / price)))
