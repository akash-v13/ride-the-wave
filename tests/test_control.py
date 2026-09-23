from datetime import datetime, timezone

from ridethewave.config import Settings
from ridethewave.engine import TradingEngine
from ridethewave.execution import OrderManager, PositionBook
from ridethewave.models import Position
from ridethewave.portfolio import CapitalAllocator
from ridethewave.runner import BotRunner, Slot
from tests.fakes import FakeBroker


def _slot(db, sid, s):
    from ridethewave.data.bars import BarAggregator
    from ridethewave.strategy import build

    strat = build("wave_rider", s, {})
    book = PositionBook()
    broker = FakeBroker()
    alloc = CapitalAllocator(s.capital, s.entry, 10_000)
    orders = OrderManager(broker, book, alloc, db, s.entry, s.exit, run_id="live", mode="live", strategy=sid)
    eng = TradingEngine(s, strat, book, orders, BarAggregator(), db, "live")
    return Slot(
        spec=type("Spec", (), {"id": sid, "mode": "live", "kind": "wave_rider", "weight": 1.0})(),
        strategy=strat,
        broker=broker,
        book=book,
        allocator=alloc,
        orders=orders,
        engine=eng,
        symbols=["AAPL"],
        allocation=10_000,
        base_share=10_000,
    )


def test_control_requests_pause_resume_flatten(db):
    s = Settings()
    r = BotRunner.__new__(BotRunner)
    r.db = db
    r.slots = [_slot(db, "wave_rider", s), _slot(db, "orb", s)]
    now = datetime(2026, 9, 23, 15, 0, tzinfo=timezone.utc)
    db.control.submit("pause", "orb")
    db.control.submit("pause", "nope")
    r._apply_controls(now)
    assert r.slots[1].engine.halted and not r.slots[0].engine.halted
    rows = {row["strategy"]: row for row in db.control.recent()}
    assert rows["orb"]["status"] == "done" and rows["nope"]["status"] == "rejected"
    db.control.submit("resume", "orb")
    r._apply_controls(now)
    assert not r.slots[1].engine.halted
    # flatten submits a market sell for an open position
    r.slots[0].book.positions["AAPL"] = Position("AAPL", 5, 100.0, now, 101.0, 100.5, strategy="wave_rider")
    db.control.submit("flatten", "all")
    r._apply_controls(now)
    assert r.slots[0].book.positions["AAPL"].exit_pending
    assert db.control.pending() == []
