from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ridethewave.backtest import ReplayEngine, SimBroker
from ridethewave.config import Settings
from ridethewave.models import Bar
from tests.conftest import make_bars

ET = ZoneInfo("America/New_York")


def test_sim_broker_limit_fill_then_stop():
    sim = SimBroker(cash=10000, slippage_pct=0)
    t0 = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)
    o = sim.submit_limit_buy("A", 10, 100.0, "c1", stop_loss_price=99.0)
    # next bar opens at 99.5 (below limit) -> fills at 99.5
    sim.process_bar(Bar("A", t0, 99.5, 100.5, 99.2, 100.2, 1000))
    assert sim.get_order(o.id).is_filled and o.filled_avg_price == 99.5
    assert sim.cash == 10000 - 995 and o.legs[0].status == "accepted"
    assert sim.equity() == 10000 - 995 + 10 * 100.2
    # gap down through the stop: fills at the open, not the stop
    sim.process_bar(Bar("A", t0 + timedelta(minutes=1), 98.0, 98.5, 97.5, 98.2, 1000))
    assert o.legs[0].is_filled and o.legs[0].filled_avg_price == 98.0
    assert sim.positions() == [] and sim.cash == 10000 - 995 + 980


def test_sim_broker_limit_not_reached():
    sim = SimBroker(cash=10000, slippage_pct=0)
    o = sim.submit_limit_buy("A", 10, 100.0, "c1")
    sim.process_bar(Bar("A", datetime(2026, 9, 16, 14, tzinfo=timezone.utc), 100.5, 101, 100.2, 100.8, 10))
    assert not sim.get_order(o.id).is_filled


class _FakeHistory:
    feed = "sip"
    calls = 0

    def __init__(self, bars):
        self._bars = bars

    def fetch(self, symbols, start, end, use_cache=True):
        return [b for b in self._bars if start <= b.ts < end and b.symbol in symbols]


def test_replay_end_to_end_takes_a_trade_and_flattens(db):
    s = Settings.model_validate(
        {
            "entry": {
                "green_streak_minutes": 3,
                "min_streak_gain_pct": 0.5,
                "min_streak_volume": 100,
                "entry_start": "09:30",
                "filters": {
                    "min_spy_ret_session_pct": None,
                    "max_session_ret_pct": None,
                    "max_trade_count_ratio": None,
                },
            },
            "exit": {
                "trail_pct": 1.0,
                "min_gain_pct": 0.5,
                "hard_stop_pct": 2.0,
                "max_hold_minutes": 0,
                "flatten_at_close": True,
            },
        }
    )
    start = datetime(2026, 9, 16, 10, 0, tzinfo=ET).astimezone(timezone.utc)
    # 3 rising closes (+1.2%) -> buy; then run to 106 and pull back below the trail -> wave exit
    closes = [100, 100.4, 100.8, 101.2, 102.5, 104, 106, 105.5, 104.5, 104.4, 104.3]
    bars = make_bars("AAPL", closes, start=start, volume=500)
    eng = ReplayEngine(s, db, _FakeHistory(bars), ["AAPL"], date(2026, 9, 16), date(2026, 9, 16), run_id="bt-test")
    res = eng.run()
    assert res.days == 1 and res.bars_replayed == len(bars)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.symbol == "AAPL" and t.exit_reason == "wave_exit"
    assert t.entry_price > 101 and t.exit_price > t.entry_price
    assert res.ledgers[0].trades == 1 and res.ledgers[0].wins == 1
    assert db.ledger.get("2026-09-16", "bt-test").run_id == "bt-test"
    assert len(db.backtests.equity_curve("bt-test")) == len(bars)
    assert db.trades.for_run("bt-test")[0].exit_reason == "wave_exit"
