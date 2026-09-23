"""Check-in pages and alert checks, built from the database only."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ridethewave.config import Settings
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")


def _money(v) -> str:
    return "—" if v is None else f"${v:,.2f}"


def _state(db: Database, key: str):
    r = db.state.get_with_time(key)
    return (None, None) if r is None else r


def _heartbeat(db: Database):
    """(value, tick time). Uses the tick timestamp inside the heartbeat, not the row's write time."""
    hb, written = _state(db, "heartbeat")
    if hb and hb.get("ts"):
        try:
            return hb, datetime.fromisoformat(hb["ts"])
        except ValueError:
            pass
    return hb, written


def _today_et() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


def _day_bounds_utc(day: str) -> tuple[datetime, datetime]:
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=ET)
    return d.astimezone(timezone.utc), (d + timedelta(days=1)).astimezone(timezone.utc)


# ---------------------------------------------------------------- alerts
def check_alerts(
    db: Database, settings: Settings, now: datetime | None = None, market_open: bool | None = None
) -> list[str]:
    """Return a list of alert strings. Empty means healthy."""
    now = now or datetime.now(timezone.utc)
    alerts: list[str] = []
    hb, hb_ts = _heartbeat(db)
    et = now.astimezone(ET)
    in_hours = (
        market_open
        if market_open is not None
        else (et.weekday() < 5 and 9 * 60 + 30 <= et.hour * 60 + et.minute < 16 * 60)
    )
    if in_hours:
        if hb_ts is None:
            alerts.append("no heartbeat ever recorded during market hours")
        else:
            age = (now - hb_ts).total_seconds()
            if age > settings.operator.heartbeat_stale_seconds and not (hb and hb.get("waiting_for")):
                alerts.append(f"heartbeat stale: {age / 60:.1f} min since last tick")
    risk, _ = _state(db, "risk")
    if risk and risk.get("halted"):
        alerts.append(f"risk halt active: {risk['halted']}")
    if hb and hb.get("api_errors"):
        alerts.append(f"api errors this session: {hb['api_errors']}")
    return alerts


# ---------------------------------------------------------------- pages
def _positions_table(db: Database) -> str:
    rows = db.positions.all_rows()
    if not rows:
        return "No open positions.\n"
    out = [
        "| Strategy | Symbol | Qty | Entry | Last | Peak | Sell if ≤ | P/L | P/L % |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        pnl = (r["last_price"] - r["entry_price"]) * r["qty"]
        pct = (r["last_price"] / r["entry_price"] - 1) * 100 if r["entry_price"] else 0
        trig = f"{r['exit_trigger']:.2f}" if r["exit_trigger"] else "not armed"
        out.append(
            f"| {r['symbol']} | {r['qty']:.0f} | {r['entry_price']:.2f} | {r['last_price']:.2f} | "
            f"{r['peak_price']:.2f} | {trig} | {pnl:+.2f} | {pct:+.2f}% |"
        )
    return "\n".join(out) + "\n"


def _trades_table(trades) -> str:
    if not trades:
        return "No closed trades.\n"
    out = ["| Symbol | In | Out | Entry | Exit | P/L | P/L % | Why |", "|---|---|---|---|---|---|---|---|"]
    for t in trades:
        out.append(
            f"| {t.symbol} | {t.entry_time.astimezone(ET):%H:%M} | {t.exit_time.astimezone(ET):%H:%M} | "
            f"{t.entry_price:.2f} | {t.exit_price:.2f} | {t.pnl:+.2f} | {t.pnl_pct:+.2f}% | {t.exit_reason} |"
        )
    return "\n".join(out) + "\n"


def build_report(kind: str, db: Database, settings: Settings, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    et = now.astimezone(ET)
    day = et.strftime("%Y-%m-%d")
    d0, d1 = _day_bounds_utc(day)
    hb, hb_ts = _heartbeat(db)
    acct, _ = _state(db, "account")
    alloc, _ = _state(db, "allocation")
    run, _ = _state(db, "run")
    risk, _ = _state(db, "risk")
    universe, _ = _state(db, "universe")
    trades = db.trades.between(d0, d1, mode="live") + db.trades.between(d0, d1, mode="shadow")
    trades.sort(key=lambda t: t.exit_time)
    alerts = check_alerts(db, settings, now)

    title = {
        "premarket": "Pre-market brief",
        "morning": "Morning check-in",
        "midday": "Midday check-in",
        "close": "Close report",
        "research": "Research digest",
    }.get(kind, kind.title())
    lines = [f"# {title}: {et:%A %d %B %Y, %H:%M} ET", ""]

    # status block, every page
    if hb_ts is None:
        status = "never run"
    elif hb and hb.get("waiting_for"):
        status = f"waiting for open at {datetime.fromisoformat(hb['waiting_for']).astimezone(ET):%H:%M} ET"
    else:
        age = (now - hb_ts).total_seconds()
        status = (
            "running"
            if age < settings.operator.heartbeat_stale_seconds
            else f"stopped (last tick {hb_ts.astimezone(ET):%H:%M})"
        )
    lines += ["## Status", "", f"- Bot: **{status}**"]
    if acct:
        lines.append(f"- Equity {_money(acct.get('equity'))}, cash {_money(acct.get('cash'))}")
    lines.append(f"- Allocation today: {_money(alloc) if alloc else _money(settings.capital.base_allocation)}")
    if hb:
        lines.append(
            f"- Universe {hb.get('universe', '—')} symbols, {hb.get('tick', 0)} ticks, "
            f"{hb.get('feature_rows', 0)} feature rows recorded"
        )
    if risk and risk.get("halted"):
        lines.append(f"- **RISK HALT:** {risk['halted']}")
    slots = (hb or {}).get("slots") or {}
    if slots:
        lines.append(
            "- Strategies: "
            + "; ".join(
                f"{sid} ({v.get('mode')}: {v.get('positions', 0)} open, {v.get('trades', 0)} trades, "
                f"{v.get('realized', 0):+.2f})"
                for sid, v in slots.items()
            )
        )
    if alerts:
        lines += ["", "## Alerts", ""] + [f"- {a}" for a in alerts]
    lines.append("")

    if kind == "premarket":
        prev = db.ledger.latest("live")
        lines += ["## Yesterday", ""]
        if prev:
            lines.append(
                f"- {prev.date}: {prev.trades} trades, {prev.wins} wins, realised {prev.realized_pnl:+.2f}, "
                f"next allocation {_money(prev.next_allocation)}"
            )
        else:
            lines.append("- No ledger yet.")
        lines += [
            "",
            "## Today's setup",
            "",
            f"- Strategy: {run.get('strategy') if run else settings.universe.source} "
            f"on {settings.alpaca.data_feed.upper()} feed",
            f"- Entry window {settings.entry.entry_start:%H:%M} to {settings.entry.entry_end:%H:%M} ET; "
            f"filters: SPY ≥ {settings.entry.filters.min_spy_ret_session_pct}%, stock ≤ "
            f"{settings.entry.filters.max_session_ret_pct}%, "
            f"trade-count ratio ≤ {settings.entry.filters.max_trade_count_ratio}",
            f"- Risk: daily loss limit {settings.risk.max_daily_loss_pct}%, "
            f"open loss {settings.risk.max_open_loss_pct}%, "
            f"win-rate floor {'on' if settings.risk.winrate_floor_enabled else 'off'}",
            f"- Universe cached: {len(universe) if universe else 0} symbols from the last build",
            "",
            "Nothing to decide unless an alert is listed above.",
        ]
    elif kind in ("morning", "midday"):
        realized = sum(t.pnl for t in trades)
        lines += [
            "## Positions",
            "",
            _positions_table(db),
            "## Closed trades today",
            "",
            f"Realised so far: {realized:+.2f} on {len(trades)} trades.",
            "",
            _trades_table(trades),
        ]
    elif kind == "close":
        led = db.ledger.get(day, "live")
        lines += ["## Ledger", ""]
        if led:
            lines += [
                f"- Trades {led.trades}, wins {led.wins}, losses {led.losses}",
                f"- Realised {led.realized_pnl:+.2f}, unrealised {led.unrealized_pnl:+.2f}, "
                f"cumulative {led.cumulative_realized:+.2f}",
                f"- Largest win {led.largest_win:+.2f}, largest loss {led.largest_loss:+.2f}",
                f"- Equity at close {_money(led.equity_close)}, allocation tomorrow {_money(led.next_allocation)}",
            ]
        else:
            lines.append("- Ledger not written yet (bot still running or did not shut down cleanly).")
        lines += ["", "## Trades", "", _trades_table(trades), "## Still open", "", _positions_table(db)]
        # fills vs assumed slippage
        if trades:
            avg_hold = sum((t.exit_time - t.entry_time).total_seconds() for t in trades) / 60 / len(trades)
            lines += [
                "## Execution",
                "",
                f"- Average hold {avg_hold:.0f} min",
                "- Exit reasons: "
                + ", ".join(
                    f"{k} {v}"
                    for k, v in sorted(
                        {
                            r: sum(1 for t in trades if t.exit_reason == r) for r in {t.exit_reason for t in trades}
                        }.items()
                    )
                ),
            ]
    elif kind == "research":
        days = db.features.days(settings.alpaca.data_feed)
        n_rows = len(db.features.rows(settings.alpaca.data_feed, day)) if day in days else 0
        lines += [
            "## Data",
            "",
            f"- Live feature rows today: {n_rows}; days recorded: {len(days)}",
            f"- Ledger days: {len(db.ledger.all('live'))}",
            "",
            "## Research queue",
            "",
            "- Nightly research automation is not built yet (roadmap phase D). "
            "Candidates and results appear here once it is.",
            "",
            "## Decisions for you",
            "",
            "- None pending.",
        ]
    lines.append("")
    lines.append(f"_Generated {now.astimezone(ET):%Y-%m-%d %H:%M:%S} ET from {db.path.name}._")
    return "\n".join(lines)


def write_report(kind: str, db: Database, settings: Settings, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    text = build_report(kind, db, settings, now)
    root = Path(settings.operator.report_dir)
    root = root if root.is_absolute() else settings.storage.resolved_db_path().parent.parent / root
    day_dir = root / now.astimezone(ET).strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{now.astimezone(ET):%H%M}-{kind}.md"
    path.write_text(text)
    (root / "latest.md").write_text(text)
    (root / "latest.json").write_text(json.dumps({"kind": kind, "path": str(path), "at": now.isoformat()}))
    return path
