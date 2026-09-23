from datetime import datetime, timedelta, timezone

from ridethewave.config import Settings
from ridethewave.models import DailyLedger, Position, Trade
from ridethewave.operator.reports import build_report, check_alerts

NOW = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)  # 11:00 ET, market hours


def seed(db):
    db.state.set("heartbeat", {"ts": NOW.isoformat(), "tick": 10, "universe": 60, "feature_rows": 500})
    db.state.set("account", {"equity": 100_050.0, "cash": 99_000.0, "buying_power": 400_000.0})
    db.state.set("allocation", 10_000.0)
    db.state.set("run", {"strategy": "wave_rider_v1"})
    db.positions.upsert(
        Position("AAPL", 9, 100.0, NOW - timedelta(minutes=20), 101.0, 100.8), "live", exit_trigger=None
    )
    db.trades.insert(
        Trade(
            "MSFT",
            5,
            200.0,
            NOW - timedelta(minutes=50),
            201.5,
            NOW - timedelta(minutes=30),
            "wave_exit",
            202,
            run_id="live",
        )
    )
    db.ledger.upsert(
        DailyLedger("2026-09-21", "live", "live", 10_000, 10_000, realized_pnl=0, trades=0, next_allocation=10_000)
    )


def test_reports_render_all_kinds(db):
    seed(db)
    s = Settings()
    for kind in ("premarket", "morning", "midday", "close", "research"):
        text = build_report(kind, db, s, NOW)
        assert text.startswith("# ") and "Bot: **running**" in text
    morning = build_report("morning", db, s, NOW)
    assert "| AAPL |" in morning and "| MSFT |" in morning and "Realised so far: +7.50" in morning
    pre = build_report("premarket", db, s, NOW)
    assert "2026-09-21: 0 trades" in pre and "Entry window" in pre


def test_alerts_stale_and_halt(db):
    seed(db)
    s = Settings()
    assert check_alerts(db, s, NOW) == []
    later = NOW + timedelta(minutes=5)
    alerts = check_alerts(db, s, later)
    assert any(a.startswith("heartbeat stale") for a in alerts)
    db.state.set("risk", {"halted": "daily loss breached"})
    assert any("risk halt" in a for a in check_alerts(db, s, later))
    # outside market hours a stale heartbeat is not an alert
    night = datetime(2026, 9, 22, 2, 0, tzinfo=timezone.utc)
    assert all("stale" not in a for a in check_alerts(db, s, night))
