"""Cross-sectional open-to-close strategy (Kakushadze 3.9 / Appendix A, long leg)."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ridethewave.backtest import ReplayEngine
from ridethewave.config import Settings
from ridethewave.models import Bar, Position, Tick
from ridethewave.strategy import build
from ridethewave.strategy.base import StrategyContext
from ridethewave.strategy.xs_daytrade import CrossSectionalDaytrade

ET = ZoneInfo("America/New_York")
OPEN = datetime(2026, 9, 22, 9, 30, tzinfo=ET).astimezone(timezone.utc)
SYMS = ["AAA", "BBB", "CCC", "DDD"]
OPENS = {"AAA": 97.0, "BBB": 99.0, "CCC": 101.0, "DDD": 103.0}  # yesterday closed at 100


def daily_for(sym: str, n: int = 25, last_open: float = 99.0, wobble: float = 1.0) -> list[Bar]:
    out = []
    for i in range(n):
        c = 100.0 + wobble * ((i % 3) - 1)
        out.append(Bar(sym, OPEN - timedelta(days=n - i), c - 0.5, c + 1, c - 1.5, c, 1_000_000))
    last = out[-1]
    out[-1] = Bar(sym, last.ts, last_open, 101, 98, 100.0, 1_000_000)
    return out


def ctx_with(positions=None, open_slots=5) -> StrategyContext:
    return StrategyContext(
        now=OPEN,
        bars=lambda s: [],
        positions=positions or {},
        pending_entries=set(),
        entries_today={},
        open_slots=open_slots,
    )


def flat_bar(sym: str, minute: int, px: float) -> Bar:
    return Bar(sym, OPEN + timedelta(minutes=minute), px, px, px, px, 1000)


def test_overnight_reversal_buys_the_biggest_relative_losers():
    p = CrossSectionalDaytrade(
        {
            "signal": "overnight_reversal",
            "top_n": 2,
            "entry_time": "09:32",
            "min_universe": 4,
            "min_score_pct": 0,
            "stop_pct": 3,
        }
    )
    assert p.name == "xs_overnight_reversal" and p.uses_protective_stop
    p.on_session_start("2026-09-22", {s: daily_for(s) for s in SYMS})
    ctx = ctx_with()
    for m in range(2):
        for s, o in OPENS.items():
            assert p.on_bar(flat_bar(s, m, o), ctx) == []
    sigs = p.on_bar(flat_bar("AAA", 2, 97.0), ctx)
    assert [s.symbol for s in sigs] == ["AAA", "BBB"]
    assert sigs[0].reason.startswith("xs_overnight_reversal | score=+3.0")
    assert abs(p.stops["AAA"] - 97 * 0.97) < 1e-6 and "CCC" not in p.stops
    assert p.on_bar(flat_bar("BBB", 2, 99.0), ctx) == []  # one decision per session
    # exits: stop, then timed close
    pos = Position("AAA", 10, 97.0, OPEN, 97.0, 97.0, strategy="xs")
    c2 = ctx_with({"AAA": pos})
    assert p.on_tick(Tick("AAA", OPEN + timedelta(minutes=10), 94.0), c2)[0].reason.startswith("xs_stop")
    assert p.on_tick(Tick("AAA", OPEN + timedelta(minutes=11), 96.0), c2) == []
    late = datetime(2026, 9, 22, 15, 55, tzinfo=ET).astimezone(timezone.utc)
    assert p.on_tick(Tick("AAA", late, 98.0), c2)[0].reason.startswith("xs_close")
    assert p.exit_trigger(pos) == p.stops["AAA"]


def test_threshold_gap_filter_and_slot_cap():
    p = CrossSectionalDaytrade(
        {
            "signal": "overnight_reversal",
            "top_n": 3,
            "entry_time": "09:31",
            "min_universe": 2,
            "min_score_pct": 2.0,
            "max_gap_pct": 2.5,
        }
    )
    p.on_session_start("2026-09-22", {s: daily_for(s) for s in SYMS})
    ctx = ctx_with(open_slots=1)
    for s, o in OPENS.items():
        p.on_bar(flat_bar(s, 0, o), ctx)
    # DDD (+3%) and AAA (-3%) exceed the gap filter; of BBB/CCC only BBB scores positive but below 2% -> nothing
    assert p.on_bar(flat_bar("AAA", 1, 97.0), ctx) == []
    assert set(p.last_scores) == {"BBB", "CCC"}
    q = CrossSectionalDaytrade(
        {"signal": "overnight_reversal", "top_n": 3, "entry_time": "09:31", "min_universe": 4, "min_score_pct": 0}
    )
    q.on_session_start("2026-09-22", {s: daily_for(s) for s in SYMS})
    for s, o in OPENS.items():
        q.on_bar(flat_bar(s, 0, o), ctx)
    assert [s.symbol for s in q.on_bar(flat_bar("AAA", 1, 97.0), ctx)] == ["AAA"]  # open_slots caps top_n


def test_other_signals_rank_as_documented():
    # previous-day momentum: AAA closed +4% over its open yesterday, DDD -2%
    daily = {s: daily_for(s, last_open=lo) for s, lo in {"AAA": 96.0, "BBB": 99.0, "CCC": 100.0, "DDD": 102.0}.items()}
    p = CrossSectionalDaytrade(
        {"signal": "prev_day_momentum", "top_n": 1, "entry_time": "09:31", "min_universe": 4, "min_score_pct": 0}
    )
    p.on_session_start("2026-09-22", daily)
    ctx = ctx_with()
    for s in SYMS:
        p.on_bar(flat_bar(s, 0, 100.0), ctx)
    assert [s.symbol for s in p.on_bar(flat_bar("AAA", 1, 100.0), ctx)] == ["AAA"]
    # intraday reversal: everyone opened at 100, by 09:40 CCC is the laggard
    q = CrossSectionalDaytrade(
        {"signal": "intraday_reversal", "top_n": 1, "entry_time": "09:40", "min_universe": 4, "min_score_pct": 0}
    )
    q.on_session_start("2026-09-22", {s: daily_for(s) for s in SYMS})
    for s in SYMS:
        q.on_bar(flat_bar(s, 0, 100.0), ctx)
    for s, px in {"AAA": 101.0, "BBB": 100.5, "CCC": 98.0, "DDD": 100.0}.items():
        q.on_bar(flat_bar(s, 9, px), ctx)
    assert [s.symbol for s in q.on_bar(flat_bar("AAA", 10, 101.0), ctx)] == ["CCC"]
    # combo adds the two book alphas; inverse-volatility sizing scales the slot
    r = CrossSectionalDaytrade({"signal": "combo", "weight_by": "inv_vol", "min_universe": 4})
    r.on_session_start("2026-09-22", {**{s: daily_for(s) for s in SYMS[:3]}, "DDD": daily_for("DDD", wobble=3.0)})
    assert r.qty_for("DDD", 100.0, 10_000, 1_000) < r.qty_for("AAA", 100.0, 10_000, 1_000) <= 20
    assert build("xs_daytrade", Settings(), {"signal": "combo"}).name == "xs_combo"


class _Hist:
    feed = "sip"
    calls = 0

    def __init__(self, bars):
        self._bars = bars

    def fetch(self, symbols, start, end, use_cache=True):
        return [b for b in self._bars if start <= b.ts < end and b.symbol in symbols]


def test_replay_uses_the_strategy_stop_not_the_global_one(db):
    """The strategy's 5% stop must reach the broker (strategy_obj wiring); with the global 1% stop the
    2% dip after entry would have stopped the trade out."""
    s = Settings.model_validate({"exit": {"hard_stop_pct": 1.0}, "backtest": {"slippage_pct": 0.0}})
    bars = []
    for sym, o in OPENS.items():
        for m in range(390):
            if sym == "AAA":
                px = 97.0 if m < 8 else (97.0 - 2.0 * min(m - 8, 60) / 60 if m < 200 else 95.0 + 3.0 * (m - 200) / 190)
            else:
                px = o
            bars.append(Bar(sym, OPEN + timedelta(minutes=m), px, px + 0.01, px - 0.01, px, 5000))
    strat = build(
        "xs_daytrade",
        s,
        {"signal": "overnight_reversal", "top_n": 1, "min_universe": 4, "stop_pct": 5.0, "min_score_pct": 0},
    )
    eng = ReplayEngine(
        s,
        db,
        _Hist(bars),
        SYMS,
        date(2026, 9, 22),
        date(2026, 9, 22),
        strategy=strat,
        run_id="t",
        daily_provider=lambda symbols, day: {x: daily_for(x) for x in symbols if x in OPENS},
    )
    res = eng.run()
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.symbol == "AAA" and abs(t.entry_price - 97.0) < 0.2
    assert t.exit_reason in ("xs_close", "close_flatten") and t.pnl > 0
    stops = [r for r in db.orders.for_run("t") if r["type"] == "stop"]
    assert stops and all(abs(r["stop_price"] - 97.0 * 0.95) < 0.2 for r in stops)
