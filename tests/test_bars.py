from datetime import datetime, timedelta, timezone

from ridethewave.data.bars import BarAggregator
from ridethewave.models import Bar, Tick
from tests.conftest import make_bars


def test_seed_and_dedupe():
    agg = BarAggregator()
    bars = make_bars("AAPL", [1, 2, 3])
    assert agg.seed(bars) == 3
    assert agg.seed(bars) == 0
    assert [b.close for b in agg.history("AAPL")] == [1, 2, 3]


def test_snapshot_emits_only_completed_minutes():
    agg = BarAggregator()
    t0 = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)
    mb = Bar("AAPL", t0, 10, 11, 10, 11, 100)
    tick = Tick("AAPL", t0 + timedelta(seconds=20), 11.0)
    # still inside minute 14:00 -> in progress, nothing emitted
    assert agg.on_snapshot(tick, mb, now=t0 + timedelta(seconds=20)) is None
    assert agg.in_progress("AAPL") is mb
    assert agg.last_price("AAPL") == 11.0
    # clock rolls to 14:01, same bar object comes back -> now complete
    out = agg.on_snapshot(Tick("AAPL", t0 + timedelta(seconds=70), 11.2), mb, now=t0 + timedelta(seconds=70))
    assert out is mb
    assert agg.in_progress("AAPL") is None
    # same bar again -> not re-emitted
    assert agg.on_snapshot(tick, mb, now=t0 + timedelta(seconds=80)) is None
    assert agg.history("AAPL") == [mb]


def test_window_limit():
    agg = BarAggregator(window=2)
    agg.seed(make_bars("AAPL", [1, 2, 3, 4]))
    assert [b.close for b in agg.history("AAPL")] == [3, 4]
