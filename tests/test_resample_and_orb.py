from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ridethewave.backtest import ReplayEngine
from ridethewave.config import Settings
from ridethewave.data.resample import Resampler, bucket_start
from ridethewave.models import Bar
from ridethewave.strategy import build
from ridethewave.strategy.orb import OpeningRangeBreakout
from tests.conftest import make_bars

ET = ZoneInfo("America/New_York")
OPEN = datetime(2026, 9, 22, 9, 30, tzinfo=ET).astimezone(timezone.utc)


def test_bucket_start_anchors_at_open():
    t = datetime(2026, 9, 22, 9, 47, tzinfo=ET).astimezone(timezone.utc)
    assert bucket_start(t, 15).astimezone(ET).strftime("%H:%M") == "09:45"
    assert bucket_start(OPEN + timedelta(minutes=14), 15) == OPEN
    assert bucket_start(OPEN + timedelta(minutes=15), 15) == OPEN + timedelta(minutes=15)


def test_resampler_builds_15_minute_bars():
    r = Resampler(15)
    bars = make_bars("AAPL", [100 + i * 0.1 for i in range(31)], start=OPEN, volume=100)
    out = [b for b in (r.on_bar(x) for x in bars) if b is not None]
    assert [b.ts for b in out] == [OPEN, OPEN + timedelta(minutes=15)]
    assert out[0].open == 100.0 and abs(out[0].close - 101.4) < 1e-9 and out[0].volume == 1500
    assert r.in_progress("AAPL").ts == OPEN + timedelta(minutes=30)
    assert len(r.flush()) == 1 and len(r.history("AAPL")) == 3
    assert Resampler(1).on_bar(bars[0]) is bars[0]


class _Hist:
    feed = "sip"
    calls = 0

    def __init__(self, bars):
        self._bars = bars

    def fetch(self, symbols, start, end, use_cache=True):
        return [b for b in self._bars if start <= b.ts < end and b.symbol in symbols]


def test_wave_rider_on_15_minute_bars_in_replay(db):
    s = Settings.model_validate(
        {
            "entry": {
                "green_streak_minutes": 3,
                "min_streak_gain_pct": 0.5,
                "min_streak_volume": 100,
                "entry_start": "09:30",
                "entry_end": "12:00",
                "filters": {
                    "min_spy_ret_session_pct": None,
                    "max_session_ret_pct": None,
                    "max_trade_count_ratio": None,
                },
            },
            "exit": {"trail_pct": 1.0, "min_gain_pct": 0.3, "hard_stop_pct": 3.0, "max_hold_minutes": 0},
        }
    )
    # 1-minute bars: three rising 15-minute buckets (+0.5% each), then a run-up and a pullback
    closes = (
        [100 + 0.5 * (i // 15) + 0.01 * (i % 15) for i in range(60)]
        + [102.5 + 0.1 * j for j in range(20)]
        + [104.0 - 0.15 * j for j in range(15)]
    )
    bars = make_bars("AAPL", closes, start=OPEN, volume=50)
    strat = build("wave_rider", s, {"bar_minutes": 15, "entry": {"green_streak_minutes": 3}})
    assert strat.bar_minutes == 15 and strat.name == "wave_rider_15m"
    eng = ReplayEngine(s, None, _Hist(bars), ["AAPL"], date(2026, 9, 22), date(2026, 9, 22), strategy=strat, run_id="t")
    res = eng.run()
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.entry_time >= OPEN + timedelta(minutes=45) and t.exit_reason in ("wave_exit", "close_flatten")


def test_orb_marks_in_play_and_breaks_out():
    p = OpeningRangeBreakout({"range_minutes": 5, "rvol_min": 2.0, "stop_atr": 0.1, "risk_pct": 1.0})
    daily = [Bar("XYZ", OPEN - timedelta(days=15 - i), 50, 52, 48, 50, 1_000_000) for i in range(15)]
    p.on_session_start("2026-09-22", {"XYZ": daily})
    assert abs(p.atr["XYZ"] - 4.0) < 1e-9 and p.avg_vol["XYZ"] == 1_000_000
    from ridethewave.strategy.base import StrategyContext

    ctx = StrategyContext(
        now=OPEN, bars=lambda s: [], positions={}, pending_entries=set(), entries_today={}, open_slots=5
    )
    # normal 5-minute volume = 1e6 * 5/390 ≈ 12,820; give 3x that in the range
    rng = [Bar("XYZ", OPEN + timedelta(minutes=i), 50, 50.5, 49.8, 50.2, 8000) for i in range(5)]
    for b in rng:
        assert p.on_bar(b, ctx) == []
    assert "XYZ" in p.in_play and p.range_high["XYZ"] == 50.5
    below = Bar("XYZ", OPEN + timedelta(minutes=5), 50.2, 50.4, 50.1, 50.3, 3000)
    assert p.on_bar(below, ctx) == []
    brk = Bar("XYZ", OPEN + timedelta(minutes=6), 50.4, 50.9, 50.4, 50.8, 5000)
    sigs = p.on_bar(brk, ctx)
    assert len(sigs) == 1 and sigs[0].reason.startswith("orb_break") and abs(p.stops["XYZ"] - (50.8 - 0.4)) < 1e-9
    assert p.qty_for("XYZ", 50.8, 10_000, 1_000) == min(int(100 / 0.4), int(1000 / 50.8))
    assert p.on_bar(brk, ctx) == []  # once per day
    # a low-volume name is never in play
    q = OpeningRangeBreakout({"range_minutes": 5, "rvol_min": 2.0})
    q.on_session_start("2026-09-22", {"XYZ": daily})
    for b in [Bar("XYZ", OPEN + timedelta(minutes=i), 50, 50.5, 49.8, 50.2, 1000) for i in range(5)]:
        q.on_bar(b, ctx)
    assert "XYZ" not in q.in_play
