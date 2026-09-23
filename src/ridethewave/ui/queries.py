"""Read-only SQL for the dashboard. Returns pandas DataFrames."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def connect(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def state(conn: sqlite3.Connection, key: str):
    r = conn.execute("SELECT value, updated_at FROM bot_state WHERE key=?", (key,)).fetchone()
    if not r:
        return None, None
    return json.loads(r["value"]), datetime.fromisoformat(r["updated_at"])


def heartbeat_age_seconds(conn: sqlite3.Connection) -> float | None:
    val, ts = state(conn, "heartbeat")
    if not ts:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds()


def positions(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM positions ORDER BY entry_time", conn)
    if df.empty:
        return df
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["unrealized"] = (df["last_price"] - df["entry_price"]) * df["qty"]
    df["unrealized_pct"] = (df["last_price"] / df["entry_price"] - 1) * 100
    df["from_peak_pct"] = (df["last_price"] / df["peak_price"] - 1) * 100
    df["held_min"] = (pd.Timestamp.now(tz="UTC") - df["entry_time"]).dt.total_seconds() / 60
    return df


def trades(
    conn: sqlite3.Connection, mode: str = "live", run_id: str | None = None, since: str | None = None, limit: int = 500
) -> pd.DataFrame:
    q = "SELECT * FROM trades WHERE mode IN (?, 'shadow')" if mode == "live" else "SELECT * FROM trades WHERE mode=?"
    args: list = [mode]
    if run_id:
        q += " AND run_id=?"
        args.append(run_id)
    if since:
        q += " AND exit_time>=?"
        args.append(since)
    q += " ORDER BY exit_time DESC LIMIT ?"
    args.append(limit)
    df = pd.read_sql_query(q, conn, params=args)
    if df.empty:
        return df
    for c in ("entry_time", "exit_time"):
        df[c] = pd.to_datetime(df[c], utc=True)
    df["held_min"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60
    return df


def ledger(conn: sqlite3.Connection, run_id: str = "live") -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM daily_ledger WHERE run_id=? ORDER BY date", conn, params=[run_id])


def backtest_runs(conn: sqlite3.Connection, limit: int = 30) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT ?", conn, params=[limit])
    if df.empty:
        return df
    df["summary"] = df["summary_json"].apply(lambda s: json.loads(s) if s else {})
    df["universe"] = df["universe_json"].apply(json.loads)
    return df


def equity_curve(conn: sqlite3.Connection, run_id: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT ts, equity, cash FROM equity_curve WHERE run_id=? ORDER BY ts", conn, params=[run_id]
    )
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def orders_today(conn: sqlite3.Connection, since: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT symbol, side, type, status, qty, limit_price, stop_price, filled_qty, filled_avg_price, "
        "submitted_at, filled_at, reason FROM orders WHERE mode='live' AND submitted_at>=? "
        "ORDER BY submitted_at DESC",
        conn,
        params=[since],
    )
