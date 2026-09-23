from datetime import datetime, timedelta, timezone

from ridethewave.models import DailyLedger, Position, Trade
from tests.conftest import make_bars


def test_bars_roundtrip(db):
    bars = make_bars("AAPL", [100, 101, 102])
    assert db.bars.upsert_many(bars, feed="iex") == 3
    db.bars.upsert_many(bars, feed="iex")  # idempotent
    start = bars[0].ts
    got = db.bars.range("AAPL", start, start + timedelta(minutes=10), feed="iex")
    assert [b.close for b in got] == [100, 101, 102]
    assert got[0].ts == start
    assert db.bars.range("AAPL", start, start + timedelta(minutes=10), feed="sip") == []


def test_positions_roundtrip(db):
    p = Position("AAPL", 5, 100.0, datetime(2026, 9, 16, 14, tzinfo=timezone.utc), 101.0, 100.5, "e1", "s1")
    db.positions.upsert(p, run_id="r1", exit_trigger=100.4)
    rows = db.positions.all_rows()
    assert rows[0]["exit_trigger"] == 100.4
    got = db.positions.all()[0]
    assert got.symbol == "AAPL" and got.peak_price == 101.0 and got.stop_order_id == "s1"
    db.positions.delete("AAPL")
    assert db.positions.all() == []


def test_trades_and_ledger(db):
    t0 = datetime(2026, 9, 16, 14, tzinfo=timezone.utc)
    t = Trade("AAPL", 5, 100.0, t0, 101.0, t0 + timedelta(minutes=30), "wave_exit", 101.6, run_id="r1")
    db.trades.insert(t)
    got = db.trades.for_run("r1")
    assert len(got) == 1 and abs(got[0].pnl - 5.0) < 1e-9 and got[0].exit_reason == "wave_exit"
    assert db.trades.between(t0, t0 + timedelta(hours=1))[0].symbol == "AAPL"

    l = DailyLedger(
        "2026-09-16", "live", "live", 10000, 10000, realized_pnl=5, trades=1, wins=1, next_allocation=10002.5
    )
    db.ledger.upsert(l)
    assert db.ledger.latest().next_allocation == 10002.5
    assert db.ledger.get("2026-09-16").trades == 1


def test_state(db):
    db.state.set("heartbeat", {"tick": 3})
    assert db.state.get("heartbeat") == {"tick": 3}
    assert db.state.get("missing", 7) == 7
    val, ts = db.state.get_with_time("heartbeat")
    assert val["tick"] == 3 and ts.tzinfo is not None


def test_backtest_run(db):
    db.backtests.insert_run(
        id="bt1", start_date="2026-09-08", end_date="2026-09-12", feed="sip", params={"a": 1}, universe=["AAPL"]
    )
    ts = datetime(2026, 9, 8, 14, tzinfo=timezone.utc)
    db.backtests.add_equity_points("bt1", [(ts, 10000.0, 10000.0), (ts + timedelta(minutes=1), 10010.0, 9000.0)])
    db.backtests.set_summary("bt1", {"pnl": 10})
    assert len(db.backtests.equity_curve("bt1")) == 2
    assert db.backtests.runs()[0]["id"] == "bt1"
