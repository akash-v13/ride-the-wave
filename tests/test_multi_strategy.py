from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ridethewave.config import Settings
from ridethewave.execution.shadow_broker import ShadowBroker
from ridethewave.models import Position, Tick
from ridethewave.strategy import REGISTRY, build
from ridethewave.strategy.base import StrategyContext
from ridethewave.strategy.spy_intraday import SpyIntradayMomentum
from tests.conftest import make_bars

ET = ZoneInfo("America/New_York")


def test_registry_builds_every_kind():
    s = Settings()
    for kind in REGISTRY:
        st = build(kind, s, {})
        assert st.name
    wr = build("wave_rider", s, {"entry": {"green_streak_minutes": 7}})
    assert wr.entry.green_streak_minutes == 7
    spy = build("spy_intraday", s, {"threshold_bp": 25})
    assert spy.p.threshold_bp == 25 and spy.symbols(["AAPL"]) == ["SPY", "SH"]
    assert spy.flatten_at_close is False and spy.uses_protective_stop is False


def test_settings_reject_duplicate_or_all_disabled_strategies():
    import pytest

    with pytest.raises(ValueError):
        Settings.model_validate({"strategies": [{"id": "a", "kind": "wave_rider"}, {"id": "a", "kind": "wave_rider"}]})
    with pytest.raises(ValueError):
        Settings.model_validate({"strategies": [{"id": "a", "kind": "wave_rider", "enabled": False}]})


def _ctx(bars_by_symbol, positions=None, now=None):
    return StrategyContext(
        now=now or datetime.now(timezone.utc),
        bars=lambda s: bars_by_symbol.get(s, []),
        positions=positions or {},
        pending_entries=set(),
        entries_today={},
        open_slots=5,
    )


def test_spy_intraday_decides_once_and_exits_on_time():
    strat = SpyIntradayMomentum({"threshold_bp": 10, "decision_time": "15:30", "exit_time": "15:58"})
    open_ = datetime(2026, 9, 22, 9, 30, tzinfo=ET).astimezone(timezone.utc)
    # first half-hour up 0.5%: 30 bars rising 100 -> 100.5, then flat until 15:30
    closes = [100 + 0.5 * i / 29 for i in range(30)] + [100.5] * 345
    spy = make_bars("SPY", closes, start=open_)
    sh = make_bars("SH", [20.0] * len(closes), start=open_)
    bars = {"SPY": spy, "SH": sh}
    decision_bar = next(b for b in spy if b.ts.astimezone(ET).hour == 15 and b.ts.astimezone(ET).minute == 30)
    sigs = strat.on_bar(decision_bar, _ctx(bars))
    assert len(sigs) == 1 and sigs[0].symbol == "SPY" and sigs[0].type.value == "buy"
    # no second decision the same day
    later = next(b for b in spy if b.ts > decision_bar.ts)
    assert strat.on_bar(later, _ctx(bars)) == []
    # timed exit
    pos = Position("SPY", 10, 100.5, decision_bar.ts, 100.5, 100.5, strategy="spy_intraday")
    exit_tick = Tick("SPY", datetime(2026, 9, 22, 15, 58, tzinfo=ET).astimezone(timezone.utc), 100.7)
    sigs = strat.on_tick(exit_tick, _ctx(bars, positions={"SPY": pos}))
    assert sigs and sigs[0].type.value == "sell" and sigs[0].qty == 10
    # down open -> buys the inverse ETF
    strat2 = SpyIntradayMomentum({"threshold_bp": 10})
    spy_dn = make_bars("SPY", [100 - 0.5 * i / 29 for i in range(30)] + [99.5] * 345, start=open_)
    dbar = next(b for b in spy_dn if b.ts.astimezone(ET).hour == 15 and b.ts.astimezone(ET).minute == 30)
    sigs = strat2.on_bar(dbar, _ctx({"SPY": spy_dn, "SH": sh}))
    assert sigs and sigs[0].symbol == "SH"


def test_shadow_broker_fills_on_next_tick():
    sb = ShadowBroker(cash=10_000, slippage_pct=0)
    t0 = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)
    o = sb.submit_limit_buy("AAPL", 10, 100.0, "c1")
    assert not sb.get_order(o.id).is_filled
    sb.on_tick(Tick("AAPL", t0, 100.3))  # above limit: no fill
    assert not sb.get_order(o.id).is_filled
    sb.on_tick(Tick("AAPL", t0 + timedelta(seconds=15), 99.9))
    assert sb.get_order(o.id).is_filled and o.filled_avg_price == 99.9
    s = sb.submit_market_sell("AAPL", 10, "c2")
    sb.on_tick(Tick("AAPL", t0 + timedelta(seconds=30), 101.0))
    assert sb.get_order(s.id).is_filled and sb.positions() == [] and abs(sb.sim.cash - (10_000 + 11.0)) < 1e-9


def test_migration_adds_strategy_columns(tmp_path):
    import sqlite3

    from ridethewave.storage import Database

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE trades (id INTEGER PRIMARY KEY, run_id TEXT, mode TEXT, symbol TEXT, qty REAL, entry_price REAL,
          entry_time TEXT, exit_price REAL, exit_time TEXT, exit_reason TEXT, peak_price REAL, pnl REAL, pnl_pct REAL,
          entry_order_id TEXT, exit_order_id TEXT);
        CREATE TABLE orders (id TEXT PRIMARY KEY, client_order_id TEXT, run_id TEXT, mode TEXT, symbol TEXT, side TEXT,
          type TEXT, qty REAL, limit_price REAL, stop_price REAL, status TEXT, filled_qty REAL, filled_avg_price REAL,
          submitted_at TEXT, filled_at TEXT, canceled_at TEXT, reason TEXT, parent_id TEXT, updated_at TEXT);
        CREATE TABLE positions (symbol TEXT PRIMARY KEY, run_id TEXT, qty REAL, entry_price REAL, entry_time TEXT,
          peak_price REAL, last_price REAL,
            exit_trigger REAL, stop_order_id TEXT, entry_order_id TEXT, updated_at TEXT);
        CREATE TABLE daily_ledger (run_id TEXT, date TEXT, mode TEXT, base_allocation REAL, allocation REAL,
          realized_pnl REAL, unrealized_pnl REAL, cumulative_realized REAL, trades INTEGER, wins INTEGER,
          losses INTEGER, largest_win REAL, largest_loss REAL, next_allocation REAL, equity_close REAL,
          extra_json TEXT, PRIMARY KEY (run_id, date));
        INSERT INTO daily_ledger VALUES ('live','2026-09-21','live',10000,10000,0,0,0,0,0,0,0,0,10000,100000,'{}');
        INSERT INTO positions VALUES ('AAPL','live',5,100,'2026-09-21T14:00:00+00:00',101,100.5,NULL,NULL,NULL,'x');
    """)
    con.commit()
    con.close()
    db = Database(path)
    led = db.ledger.get("2026-09-21", "live", "wave_rider")
    assert led is not None and led.strategy == "wave_rider"
    pos = db.positions.all("wave_rider")
    assert len(pos) == 1 and pos[0].symbol == "AAPL"
    db.close()
    Database(path).close()  # idempotent
