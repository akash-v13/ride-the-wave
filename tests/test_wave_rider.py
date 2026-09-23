from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from ridethewave.config import EntryFilterSettings, EntrySettings, ExitSettings
from ridethewave.models import Position, SignalType, Tick
from ridethewave.strategy import StrategyContext, WaveRider
from tests.conftest import make_bars

ET = ZoneInfo("America/New_York")
# Defaults now include market/context gates that need SPY bars; most tests exercise the streak rule alone.
NO_FILTERS = EntryFilterSettings(min_spy_ret_session_pct=None, max_session_ret_pct=None, max_trade_count_ratio=None)
T0 = datetime(2026, 9, 16, 10, 0, tzinfo=ET).astimezone(timezone.utc)  # inside entry window


def ctx_for(bars, positions=None, slots=5, now=None, pending=None, entries=None):
    hist = {}
    for b in bars:
        hist.setdefault(b.symbol, []).append(b)
    return StrategyContext(
        now=now or (bars[-1].ts if bars else T0),
        bars=lambda s: hist.get(s, []),
        positions=positions or {},
        pending_entries=pending or set(),
        entries_today=entries or {},
        open_slots=slots,
    )


@pytest.fixture
def strat():
    return WaveRider(
        EntrySettings(green_streak_minutes=3, min_streak_gain_pct=0.5, min_streak_volume=1000, filters=NO_FILTERS),
        ExitSettings(trail_pct=1.0, min_gain_pct=0.5, hard_stop_pct=1.0, max_hold_minutes=60),
    )


def test_buy_on_qualifying_streak(strat):
    bars = make_bars("AAPL", [100, 100.3, 100.6, 101.0], start=T0)
    sigs = strat.on_bar(bars[-1], ctx_for(bars))
    assert len(sigs) == 1 and sigs[0].type == SignalType.BUY and sigs[0].symbol == "AAPL"
    assert "streak=3" in sigs[0].reason


def test_no_buy_when_streak_too_short(strat):
    bars = make_bars("AAPL", [100, 99, 100.6, 101.0], start=T0)
    assert strat.on_bar(bars[-1], ctx_for(bars)) == []


def test_no_buy_when_gain_too_small(strat):
    bars = make_bars("AAPL", [100, 100.01, 100.02, 100.03], start=T0)
    assert strat.on_bar(bars[-1], ctx_for(bars)) == []


def test_no_buy_when_volume_too_low(strat):
    bars = make_bars("AAPL", [100, 100.3, 100.6, 101.0], start=T0, volume=100)
    assert strat.on_bar(bars[-1], ctx_for(bars)) == []


def test_no_buy_outside_window_or_without_slot_or_pending(strat):
    bars = make_bars("AAPL", [100, 100.3, 100.6, 101.0], start=T0)
    early = datetime(2026, 9, 16, 9, 20, tzinfo=ET)  # before entry_start
    assert strat.on_bar(bars[-1], ctx_for(bars, now=early)) == []
    assert strat.on_bar(bars[-1], ctx_for(bars, slots=0)) == []
    assert strat.on_bar(bars[-1], ctx_for(bars, pending={"AAPL"})) == []
    assert strat.on_bar(bars[-1], ctx_for(bars, entries={"AAPL": 1})) == []


def pos(entry=100.0, peak=None, t=None):
    return Position("AAPL", 10, entry, t or T0, peak or entry, entry)


def tick(price, t=None):
    return Tick("AAPL", t or (T0 + timedelta(minutes=5)), price)


def test_wave_exit_fires_only_above_floor(strat):
    # peak 102 -> trigger 100.98, floor 100.5: trigger above floor, so a print at 100.9 sells
    p = pos(100.0, peak=102.0)
    sigs = strat.on_tick(tick(100.9), ctx_for([], positions={"AAPL": p}))
    assert len(sigs) == 1 and sigs[0].reason.startswith("wave_exit") and sigs[0].qty == 10

    # peak 100.8 -> trigger 99.79, below floor 100.5: pullback to 99.8 must NOT wave-exit
    p = pos(100.0, peak=100.8)
    assert strat.on_tick(tick(99.8), ctx_for([], positions={"AAPL": p})) == []


def test_peak_updates_from_ticks(strat):
    p = pos(100.0)
    c = ctx_for([], positions={"AAPL": p})
    assert strat.on_tick(tick(103.0), c) == []
    assert p.peak_price == 103.0
    assert strat.exit_trigger(p) == pytest.approx(101.97)
    sigs = strat.on_tick(tick(101.9), c)
    assert sigs and "wave_exit" in sigs[0].reason


def test_hard_stop(strat):
    p = pos(100.0)
    sigs = strat.on_tick(tick(98.9), ctx_for([], positions={"AAPL": p}))
    assert sigs and sigs[0].reason.startswith("hard_stop")


def test_timeout_only_if_profitable(strat):
    p = pos(100.0)
    late = T0 + timedelta(minutes=61)
    assert strat.on_tick(tick(99.9, late), ctx_for([], positions={"AAPL": p})) == []
    sigs = strat.on_tick(tick(100.2, late), ctx_for([], positions={"AAPL": p}))
    assert sigs and sigs[0].reason.startswith("timeout")


def test_close_flatten(strat):
    late = datetime(2026, 9, 16, 15, 56, tzinfo=ET)
    p = pos(100.0, t=late - timedelta(minutes=5))
    sigs = strat.on_tick(tick(100.1, late), ctx_for([], positions={"AAPL": p}))
    assert sigs and sigs[0].reason.startswith("close_flatten")


def test_exit_checked_on_bar_close_too(strat):
    p = pos(100.0, peak=102.0)
    bars = make_bars("AAPL", [101.5, 100.9], start=T0 + timedelta(minutes=5))
    sigs = strat.on_bar(bars[-1], ctx_for(bars, positions={"AAPL": p}))
    assert sigs and "wave_exit" in sigs[0].reason


def test_no_double_exit_when_pending(strat):
    p = pos(100.0, peak=102.0)
    p.exit_pending = True
    assert strat.on_tick(tick(100.9), ctx_for([], positions={"AAPL": p})) == []


def test_entry_filters_gate_entries():
    from ridethewave.config import EntryFilterSettings

    entry = EntrySettings(
        green_streak_minutes=3,
        min_streak_gain_pct=0.5,
        min_streak_volume=1000,
        filters=EntryFilterSettings(
            min_rvol_20=2.0, min_spy_ret_session_pct=None, max_session_ret_pct=None, max_trade_count_ratio=None
        ),
    )
    strat = WaveRider(entry, ExitSettings())
    # 25 quiet bars then a 3-bar streak at the same volume: rvol ~1 -> rejected
    session = datetime(2026, 9, 16, 9, 30, tzinfo=ET).astimezone(timezone.utc)
    closes = [100.0] * 25 + [100.3, 100.6, 101.0]
    bars = make_bars("AAPL", closes, start=session, volume=1000)
    assert strat.on_bar(bars[-1], ctx_for(bars)) == []
    # same streak on 5x volume -> passes
    from ridethewave.models import Bar

    loud = bars[:25] + [Bar("AAPL", b.ts, b.open, b.high, b.low, b.close, 5000, 50, b.vwap) for b in bars[25:]]
    sigs = strat.on_bar(loud[-1], ctx_for(loud))
    assert len(sigs) == 1 and sigs[0].type == SignalType.BUY
    # filters all None -> no feature computation, streak alone decides
    plain = WaveRider(
        EntrySettings(green_streak_minutes=3, min_streak_gain_pct=0.5, min_streak_volume=1000, filters=NO_FILTERS),
        ExitSettings(),
    )
    assert len(plain.on_bar(bars[-1], ctx_for(bars))) == 1


def test_vol_scaled_exits_use_entry_noise():
    ex = ExitSettings(
        vol_scaled=True,
        trail_range_mult=2.0,
        gain_floor_range_mult=1.0,
        stop_range_mult=2.0,
        noise_floor_pct=0.2,
        noise_cap_pct=2.0,
    )
    assert ex.effective(0.5) == (1.0, 0.5, 1.0)
    assert ex.effective(5.0) == (4.0, 2.0, 4.0)  # capped at 2.0 noise
    assert ex.effective(None) == (ex.trail_pct, ex.min_gain_pct, ex.hard_stop_pct)  # adopted positions: fixed
    strat = WaveRider(
        EntrySettings(green_streak_minutes=3, min_streak_gain_pct=0.5, min_streak_volume=1000, filters=NO_FILTERS), ex
    )
    # noisy stock (noise 1.0%): stop at -2%, trail 2%, floor 1%
    p = Position("AAPL", 10, 100.0, T0, 100.0, 100.0, noise_pct=1.0)
    assert strat.on_tick(tick(98.5), ctx_for([], positions={"AAPL": p})) == []  # -1.5% is inside noise
    sigs = strat.on_tick(tick(97.9), ctx_for([], positions={"AAPL": p}))
    assert sigs and sigs[0].reason.startswith("hard_stop")
    # entry signal carries the measured noise
    session = datetime(2026, 9, 16, 9, 30, tzinfo=ET).astimezone(timezone.utc)
    bars = make_bars("AAPL", [100.0] * 25 + [100.3, 100.6, 101.0], start=session, volume=5000)
    sig = strat.on_bar(bars[-1], ctx_for(bars))[0]
    assert sig.noise_pct is not None and sig.noise_pct >= 0
