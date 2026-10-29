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


def test_ledger_rows_read_back_with_their_strategy(db):
    # _row_to_ledger dropped the column, so every row read back claimed to be wave_rider (found 2026-10-29)
    db.ledger.upsert(
        DailyLedger("2026-10-29", "shadow", "live", 20_000, 20_000, realized_pnl=303.25, strategy="bps_qqq")
    )
    db.ledger.upsert(DailyLedger("2026-10-29", "live", "live", 10_000, 10_000, realized_pnl=-32.93))
    assert [(r.strategy, r.realized_pnl) for r in db.ledger.for_day("2026-10-29")] == [
        ("bps_qqq", 303.25),
        ("wave_rider", -32.93),
    ]
    assert db.ledger.get("2026-10-29", "live", "bps_qqq").strategy == "bps_qqq"


def test_pnl_pct_sign_for_credit_structures():
    t0 = datetime(2026, 10, 22, 19, 40, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=7)
    # a credit spread is booked with a negative entry value: sold for 3.365, bought back for 0.3325
    credit = Trade("QQQ:bull_put_spread", 100, -3.365, t0, -0.3325, t1, "dte_exit", -0.3325)
    assert round(credit.pnl, 2) == 303.25 and round(credit.pnl_pct, 2) == 90.12
    assert round(Trade("X", 100, -3.0, t0, -4.5, t1, "stop", -3.0).pnl_pct, 2) == -50.0  # a losing credit
    # stocks and debits are unchanged: long, short, debit spread
    assert round(Trade("AAPL", 10, 100.0, t0, 101.0, t1, "x", 101.0).pnl_pct, 2) == 1.0
    assert round(Trade("AAPL", -10, 100.0, t0, 101.0, t1, "x", 100.0).pnl_pct, 2) == -1.0
    assert round(Trade("SPY:call_spread", 100, 2.0, t0, 3.0, t1, "x", 3.0).pnl_pct, 2) == 50.0


def test_trades_read_back_with_their_strategy(db):
    # same omission as the ledger: read-back trades all said wave_rider, which the report's strategy column exposed
    t0 = datetime(2026, 10, 29, 19, 40, tzinfo=timezone.utc)
    db.trades.insert(Trade("CDE", 10, 13.88, t0, 13.95, t0, "xs_close", 13.95, mode="shadow", strategy="xs_combo"))
    db.trades.insert(Trade("CDE", 10, 13.88, t0, 13.95, t0, "xs_close", 13.95, mode="shadow", strategy="xs_overnight"))
    got = db.trades.between(t0, t0 + timedelta(seconds=1), mode="shadow")
    assert sorted(t.strategy for t in got) == ["xs_combo", "xs_overnight"]
