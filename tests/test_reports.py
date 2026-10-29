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


def test_alerts_empty_universe_and_skipped_decisions(db):
    seed(db)
    s = Settings()
    hb = db.state.get("heartbeat")
    hb["universe"] = 0
    hb["portfolios"] = {"pm_actives": {"skipped": {"day": "2026-09-22", "reason": "universe empty"}}}
    hb["options"] = {"bps_spy": {"skipped": {"day": "2026-09-21", "reason": "old"}}, "bps_qqq": {"skipped": None}}
    db.state.set("heartbeat", hb)
    alerts = check_alerts(db, s, NOW)
    assert "universe empty: the intraday strategies have no symbols to trade" in alerts
    assert "decision skipped [pm_actives]: universe empty" in alerts
    assert not any("bps_spy" in a or "bps_qqq" in a for a in alerts)  # yesterday's skip and no skip stay quiet
    # after the close the same heartbeat still raises them, so the close report shows the day's problems
    evening = datetime(2026, 9, 22, 21, 0, tzinfo=timezone.utc)
    assert any(a.startswith("decision skipped [pm_actives]") for a in check_alerts(db, s, evening))
    # the next morning, before the bot runs, yesterday's heartbeat does not alert
    next_day = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    assert not any(a.startswith(("universe empty", "decision skipped")) for a in check_alerts(db, s, next_day))


def test_positions_table_names_the_strategy(db):
    seed(db)
    text = build_report("morning", db, Settings(), NOW)
    row = next(line for line in text.splitlines() if "| AAPL |" in line)
    header = next(line for line in text.splitlines() if line.startswith("| Strategy |"))
    assert row.startswith("| wave_rider | AAPL |") and row.count("|") == header.count("|")


def test_close_report_by_strategy_with_dates_and_split_holds(db):
    """Fixes from the 2026-10-29 close report: no strategy column (CDE showed twice), multi-day holds showed only
    clock times, a +$303 credit spread showed -90%, one average hold mixed minutes with weeks, and the strategies
    line came from the bot's last tick instead of the ledgers."""
    seed(db)
    hb = db.state.get("heartbeat")
    hb["slots"] = {"wave_rider": {"mode": "live", "positions": 1, "trades": 2, "realized": -17.83}}
    db.state.set("heartbeat", hb)
    utc = timezone.utc
    db.trades.insert(
        Trade(
            "WULF",
            76,
            11.74,
            datetime(2026, 9, 14, 19, 50, tzinfo=utc),
            12.72,
            datetime(2026, 9, 22, 19, 50, tzinfo=utc),
            "rebalance",
            12.72,
            mode="shadow",
            run_id="live",
            strategy="pm_actives",
        )
    )
    db.trades.insert(
        Trade(
            "QQQ:bull_put_spread",
            100,
            -3.365,
            datetime(2026, 9, 15, 19, 40, tzinfo=utc),
            -0.3325,
            datetime(2026, 9, 22, 19, 40, tzinfo=utc),
            "dte_exit",
            -0.3325,
            mode="shadow",
            run_id="live",
            strategy="bps_qqq",
        )
    )
    s = Settings()
    after_close = datetime(2026, 9, 22, 20, 30, tzinfo=utc)  # 16:30 ET
    # before the ledgers exist the heartbeat line is all there is
    assert "- Strategies: wave_rider (live: 1 open" in build_report("close", db, s, after_close)
    db.ledger.upsert(
        DailyLedger(
            "2026-09-22", "live", "live", 10_000, 10_000, realized_pnl=7.5, trades=1, wins=1, equity_close=100_050.0
        )
    )
    db.ledger.upsert(
        DailyLedger(
            "2026-09-22",
            "shadow",
            "live",
            20_000,
            20_000,
            realized_pnl=303.25,
            trades=1,
            wins=1,
            equity_close=20_303.25,
            strategy="bps_qqq",
        )
    )
    text = build_report("close", db, s, after_close)
    assert "| wave_rider | MSFT | 10:10 | 10:30 |" in text
    assert "| pm_actives | WULF | 14 Sep 15:50 | 15:50 |" in text
    assert (
        "| bps_qqq | QQQ:bull_put_spread | 15 Sep 15:40 | 15:40 | -3.37 | -0.33 | +303.25 | +90.12% | dte_exit |"
        in text
    )
    assert "## Strategies at the close" in text and "- Strategies:" not in text
    assert "| bps_qqq | shadow | 1 | 1 | +303.25 | +0.00 | $20,303.25 |" in text
    assert "| wave_rider | live | 1 | 1 | +7.50 | +0.00 | $100,050.00 |" in text
    assert "- Average hold: day trades 20 min (1); held overnight or longer 7.5 days (2)" in text
