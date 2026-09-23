from datetime import datetime, timezone

from ridethewave.config import CapitalSettings, EntrySettings
from ridethewave.models import DailyLedger, Position, Trade
from ridethewave.portfolio import CapitalAllocator, build_ledger, next_allocation


def test_allocator_sizing():
    a = CapitalAllocator(CapitalSettings(base_allocation=10000), EntrySettings(position_size_pct=10))
    assert a.slot_dollars() == 1000
    assert a.qty_for(99.5) == 10
    assert a.qty_for(1500) == 0
    a2 = CapitalAllocator(CapitalSettings(base_allocation=10000), EntrySettings(position_size_pct=10), allocation=20000)
    assert a2.qty_for(100) == 20


def test_next_allocation_reinvests_half_and_floors():
    cfg = CapitalSettings(base_allocation=10000, reinvest_gains_pct=50, min_allocation_ratio=0.5)
    assert next_allocation(200, cfg) == 10100
    assert next_allocation(-2000, cfg) == 9000
    assert next_allocation(-50000, cfg) == 5000


def test_build_ledger():
    t0 = datetime(2026, 9, 16, 14, tzinfo=timezone.utc)
    trades = [Trade("A", 10, 100, t0, 101, t0, "wave_exit", 101.5), Trade("B", 10, 100, t0, 99.5, t0, "hard_stop", 100)]
    positions = [Position("C", 5, 50, t0, 51, 51)]
    prev = DailyLedger("2026-09-15", "live", "live", 10000, 10000, cumulative_realized=40)
    cfg = CapitalSettings(base_allocation=10000, reinvest_gains_pct=50)
    l = build_ledger("2026-09-16", "live", "live", trades, positions, prev, 10020, cfg, equity_close=100050)
    assert l.realized_pnl == 5.0 and l.unrealized_pnl == 5.0
    assert l.trades == 2 and l.wins == 1 and l.losses == 1
    assert l.largest_win == 10.0 and l.largest_loss == -5.0
    assert l.cumulative_realized == 45.0
    assert l.next_allocation == 10022.5
    assert l.extra["win_rate"] == 0.5
