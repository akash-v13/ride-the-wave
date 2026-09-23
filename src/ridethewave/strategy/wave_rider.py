"""Wave Rider v1. The rules are specified in docs/strategy.md; this file is their code form.

Entry (on a completed bar):  green streak long enough, big enough, on enough volume, inside the
entry window, with a free slot, no position/pending order in the symbol, re-entry limit not hit.

Exit (on every tick, in this order):
  1. wave_exit    price <= peak*(1-trail) and that trigger is >= entry*(1+min_gain)
  2. hard_stop    price <= entry*(1-hard_stop)                       (0 disables)
  3. timeout      held > max_hold_minutes (and in profit, if configured)  (0 disables)
  4. close_flatten  time >= flatten_time ET and flatten_at_close
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ridethewave.config import EntrySettings, ExitSettings
from ridethewave.models import Bar, Position, Signal, SignalType, Tick
from ridethewave.strategy.base import Strategy, StrategyContext
from ridethewave.strategy.indicators import green_streak, streak_gain_pct, streak_volume

MARKET_SYMBOL = "SPY"

ET = ZoneInfo("America/New_York")


class WaveRider(Strategy):
    name = "wave_rider_v1"

    def __init__(self, entry: EntrySettings, exit: ExitSettings, bar_minutes: int = 1):
        self.entry = entry
        self.exit = exit
        self.bar_minutes = bar_minutes
        if bar_minutes > 1:
            self.name = f"wave_rider_{bar_minutes}m"

    # ---------- entries ----------
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Signal]:
        signals: list[Signal] = []
        # Exits also get a look at bar closes, so a symbol with no ticks between bars is still managed.
        pos = ctx.position(bar.symbol)
        if pos is not None:
            sig = self._check_exit(pos, bar.close, bar.ts, ctx)
            if sig:
                return [sig]
            return []

        if ctx.open_slots <= 0:
            return signals
        if bar.symbol in ctx.pending_entries:
            return signals
        if ctx.entries_today.get(bar.symbol, 0) >= self.entry.max_entries_per_symbol_per_day:
            return signals
        if not self._in_entry_window(ctx.now):
            return signals

        bars = ctx.bars(bar.symbol)
        if not bars or bars[-1].ts != bar.ts:
            bars = bars + [bar]
        streak = green_streak(bars)
        if streak < self.entry.green_streak_minutes:
            return signals
        gain = streak_gain_pct(bars, streak)
        if gain < self.entry.min_streak_gain_pct:
            return signals
        vol = streak_volume(bars, streak)
        if vol < self.entry.min_streak_volume:
            return signals
        rejected = self._filter_reject(bar, bars, ctx)
        if rejected:
            return signals
        noise = self._noise_pct(bar, bars) if self.exit.vol_scaled else None

        signals.append(
            Signal(
                type=SignalType.BUY,
                symbol=bar.symbol,
                ts=bar.ts,
                reason=f"streak={streak} gain={gain:.2f}% vol={vol}" + (f" noise={noise:.2f}%" if noise else ""),
                reference_price=bar.close,
                noise_pct=noise,
            )
        )
        return signals

    @staticmethod
    def _noise_pct(bar: Bar, bars: list[Bar]) -> float | None:
        """Mean (high-low)/close over the prior 20 bars of this session, in percent."""
        session_start = bar.ts.astimezone(ET).replace(hour=9, minute=30, second=0, microsecond=0)
        look = [b for b in bars[:-1] if b.ts >= session_start][-20:]
        if len(look) < 5:
            return None
        return sum((b.high - b.low) / b.close * 100.0 for b in look if b.close > 0) / len(look)

    def _filter_reject(self, bar: Bar, bars: list[Bar], ctx: StrategyContext) -> str | None:
        """Return the name of the first failing filter, or None if the entry passes."""
        f = self.entry.filters
        if all(getattr(f, name) is None for name in f.model_fields if name != "require_spy") and not f.require_spy:
            return None
        from ridethewave.features.compute import compute_features  # local import keeps strategy import light

        session_start = bar.ts.astimezone(ET).replace(hour=9, minute=30, second=0, microsecond=0)
        spy = ctx.bars(MARKET_SYMBOL) if ctx.bars else []
        feat = compute_features(bars, spy, session_start)
        if feat is None:
            return "no_features"
        if f.require_spy and feat.spy_ret_5m_pct is None:
            return "no_spy"

        def gate(name: str, value: float | None, lo: float | None, hi: float | None) -> str | None:
            if lo is None and hi is None:
                return None
            if value is None:
                return f"{name}_missing"
            if lo is not None and value < lo:
                return f"{name}<{lo}"
            if hi is not None and value > hi:
                return f"{name}>{hi}"
            return None

        checks = [
            gate("rvol_20", feat.rvol_20, f.min_rvol_20, None),
            gate("streak_vol_ratio", feat.streak_vol_ratio, f.min_streak_vol_ratio, None),
            gate("trade_count_ratio", feat.trade_count_ratio, f.min_trade_count_ratio, f.max_trade_count_ratio),
            gate("gain_vs_range", feat.gain_vs_range, f.min_gain_vs_range, f.max_gain_vs_range),
            gate("vwap_dist_pct", feat.vwap_dist_pct, f.min_vwap_dist_pct, f.max_vwap_dist_pct),
            gate("session_ret_pct", feat.session_ret_pct, f.min_session_ret_pct, f.max_session_ret_pct),
            gate("spy_ret_5m_pct", feat.spy_ret_5m_pct, f.min_spy_ret_5m_pct, None),
            gate("spy_ret_session_pct", feat.spy_ret_session_pct, f.min_spy_ret_session_pct, None),
            gate("range_pct_20", feat.range_pct_20, None, f.max_range_pct_20),
        ]
        return next((c for c in checks if c), None)

    def _in_entry_window(self, now: datetime) -> bool:
        t = now.astimezone(ET).time()
        return self.entry.entry_start <= t < self.entry.entry_end

    # ---------- exits ----------
    def on_tick(self, tick: Tick, ctx: StrategyContext) -> list[Signal]:
        pos = ctx.position(tick.symbol)
        if pos is None:
            return []
        sig = self._check_exit(pos, tick.price, tick.ts, ctx)
        return [sig] if sig else []

    def wave_trigger(self, pos: Position) -> float:
        trail, _, _ = self.exit.effective(pos.noise_pct)
        return pos.peak_price * (1.0 - trail / 100.0)

    def gain_floor(self, pos: Position) -> float:
        _, gain, _ = self.exit.effective(pos.noise_pct)
        return pos.entry_price * (1.0 + gain / 100.0)

    def exit_trigger(self, pos: Position) -> float | None:
        """Price at which a wave exit would fire right now, or None if the floor is not yet armed."""
        trig = self.wave_trigger(pos)
        return trig if trig >= self.gain_floor(pos) else None

    def _check_exit(self, pos: Position, price: float, ts: datetime, ctx: StrategyContext) -> Signal | None:
        if pos.exit_pending:
            return None
        pos.update_price(price)

        trig = self.wave_trigger(pos)
        if price <= trig and trig >= self.gain_floor(pos):
            return self._sell(pos, ts, price, f"wave_exit peak={pos.peak_price:.2f} trig={trig:.2f}", "wave_exit")

        _, _, stop_pct = self.exit.effective(pos.noise_pct)
        if stop_pct > 0 and price <= pos.entry_price * (1.0 - stop_pct / 100.0):
            return self._sell(pos, ts, price, f"hard_stop entry={pos.entry_price:.2f}", "hard_stop")

        if self.exit.max_hold_minutes > 0:
            held = ts - pos.entry_time
            if held >= timedelta(minutes=self.exit.max_hold_minutes):
                if not self.exit.timeout_exit_only_if_profitable or price > pos.entry_price:
                    return self._sell(pos, ts, price, f"timeout held={held}", "timeout")

        if self.exit.flatten_at_close and ts.astimezone(ET).time() >= self.exit.flatten_time:
            return self._sell(pos, ts, price, "close_flatten", "close_flatten")

        return None

    @staticmethod
    def _sell(pos: Position, ts: datetime, price: float, detail: str, code: str) -> Signal:
        return Signal(
            type=SignalType.SELL,
            symbol=pos.symbol,
            ts=ts,
            reason=code + " | " + detail,
            reference_price=price,
            qty=pos.qty,
        )
