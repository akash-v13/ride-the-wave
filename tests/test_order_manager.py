from datetime import datetime, timedelta, timezone

import pytest

from ridethewave.config import CapitalSettings, EntrySettings, ExitSettings
from ridethewave.execution import OrderManager, PositionBook
from ridethewave.execution.broker import BrokerPosition
from ridethewave.models import Signal, SignalType
from ridethewave.portfolio import CapitalAllocator
from tests.fakes import FakeBroker

T0 = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def om(db):
    broker = FakeBroker()
    book = PositionBook()
    alloc = CapitalAllocator(CapitalSettings(base_allocation=10000), EntrySettings(position_size_pct=10))
    m = OrderManager(
        broker,
        book,
        alloc,
        db,
        EntrySettings(entry_fill_timeout_seconds=30, max_positions=2),
        ExitSettings(hard_stop_pct=1.0),
        run_id="t",
        mode="live",
        ask_lookup=lambda s: 100.0,
    )
    return m, broker, book


def buy(sym="AAPL", price=100.0):
    return Signal(SignalType.BUY, sym, T0, "streak", price)


def test_buy_places_limit_with_stop_and_fills(om, db):
    m, broker, book = om
    m.handle([buy()], T0)
    assert "AAPL" in book.pending_entries
    o = broker.orders[book.pending_entries["AAPL"].order_id]
    assert o.limit_price == 100.1 and o.qty == 9  # floor(1000/100.1)
    assert o.legs and o.legs[0].stop_price == pytest.approx(99.1, abs=0.01)
    assert book.open_slots(2) == 1

    broker.fill(o.id, 100.05, at=T0 + timedelta(seconds=3))
    m.poll(T0 + timedelta(seconds=5))
    pos = book.positions["AAPL"]
    assert pos.entry_price == 100.05 and pos.qty == 9 and pos.stop_order_id == o.legs[0].id
    assert book.entries_today["AAPL"] == 1
    assert db.orders.for_run("t")  # recorded


def test_unfilled_entry_is_cancelled_after_timeout(om):
    m, broker, book = om
    m.handle([buy()], T0)
    oid = book.pending_entries["AAPL"].order_id
    m.poll(T0 + timedelta(seconds=10))
    assert "AAPL" in book.pending_entries
    m.poll(T0 + timedelta(seconds=40))
    assert oid in broker.cancelled and "AAPL" not in book.pending_entries


def test_duplicate_and_slot_limits(om):
    m, broker, book = om
    m.handle([buy("AAPL"), buy("AAPL"), buy("MSFT"), buy("NVDA")], T0)
    assert set(book.pending_entries) == {"AAPL", "MSFT"}  # max_positions=2


def test_sell_cancels_stop_then_market_sells_and_records_trade(om, db):
    m, broker, book = om
    m.handle([buy()], T0)
    o = broker.orders[book.pending_entries["AAPL"].order_id]
    broker.fill(o.id, 100.0)
    m.poll(T0)
    stop_id = book.positions["AAPL"].stop_order_id

    m.handle([Signal(SignalType.SELL, "AAPL", T0, "wave_exit | peak=102", 101.0, 9)], T0 + timedelta(minutes=10))
    assert stop_id in broker.cancelled
    assert book.positions["AAPL"].exit_pending
    sell_id = book.pending_exits["AAPL"].order_id
    broker.fill(sell_id, 100.9, at=T0 + timedelta(minutes=10))
    done = m.poll(T0 + timedelta(minutes=10))
    assert len(done) == 1 and done[0].exit_reason == "wave_exit" and done[0].pnl == pytest.approx(8.1)
    assert "AAPL" not in book.positions
    assert db.trades.for_run("t")[0].symbol == "AAPL"


def test_server_stop_fill_is_detected(om, db):
    m, broker, book = om
    m.handle([buy()], T0)
    o = broker.orders[book.pending_entries["AAPL"].order_id]
    broker.fill(o.id, 100.0)
    m.poll(T0)
    broker.fill(o.legs[0].id, 99.0)
    done = m.poll(T0 + timedelta(minutes=1))
    assert done and done[0].exit_reason == "server_stop" and done[0].pnl == pytest.approx(-9.0)


def test_reconcile_adopts_broker_positions():
    book = PositionBook()
    book.reconcile([BrokerPosition("TSLA", 3, 200.0, 205.0)], T0)
    p = book.positions["TSLA"]
    assert p.peak_price == 205.0 and p.entry_price == 200.0
    book.reconcile([], T0)
    assert book.positions == {}
