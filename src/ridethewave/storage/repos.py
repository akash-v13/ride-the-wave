"""Small typed repositories. All SQL for the project lives here."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone

from ridethewave.models import Bar, DailyLedger, Position, Trade


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _now() -> str:
    return _iso(datetime.now(timezone.utc))


class _Repo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn


class BarRepo(_Repo):
    def upsert_many(self, bars: Iterable[Bar], feed: str) -> int:
        rows = [
            (b.symbol, _iso(b.ts), feed, b.open, b.high, b.low, b.close, b.volume, b.trade_count, b.vwap) for b in bars
        ]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                """INSERT INTO bars (symbol, ts, feed, open, high, low, close, volume, trade_count, vwap)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol, ts, feed) DO UPDATE SET
                     open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                     volume=excluded.volume, trade_count=excluded.trade_count, vwap=excluded.vwap""",
                rows,
            )
        return len(rows)

    def range(self, symbol: str, start: datetime, end: datetime, feed: str) -> list[Bar]:
        cur = self.conn.execute(
            "SELECT * FROM bars WHERE symbol=? AND feed=? AND ts>=? AND ts<? ORDER BY ts",
            (symbol, feed, _iso(start), _iso(end)),
        )
        return [self._row_to_bar(r) for r in cur.fetchall()]

    def range_all(self, symbols: list[str], start: datetime, end: datetime, feed: str) -> list[Bar]:
        if not symbols:
            return []
        q = ",".join("?" * len(symbols))
        cur = self.conn.execute(
            f"SELECT * FROM bars WHERE feed=? AND ts>=? AND ts<? AND symbol IN ({q}) ORDER BY ts, symbol",
            (feed, _iso(start), _iso(end), *symbols),
        )
        return [self._row_to_bar(r) for r in cur.fetchall()]

    def count(self, symbol: str, feed: str, start: datetime, end: datetime) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM bars WHERE symbol=? AND feed=? AND ts>=? AND ts<?",
            (symbol, feed, _iso(start), _iso(end)),
        )
        return int(cur.fetchone()[0])

    @staticmethod
    def _row_to_bar(r: sqlite3.Row) -> Bar:
        return Bar(
            symbol=r["symbol"],
            ts=_dt(r["ts"]),
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
            trade_count=r["trade_count"],
            vwap=r["vwap"],
        )


class OrderRepo(_Repo):
    def upsert(
        self,
        *,
        id: str,
        run_id: str,
        mode: str,
        symbol: str,
        side: str,
        type: str,
        strategy: str = "wave_rider",
        status: str,
        qty: float | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
        filled_qty: float = 0.0,
        filled_avg_price: float | None = None,
        submitted_at: datetime | None = None,
        filled_at: datetime | None = None,
        canceled_at: datetime | None = None,
        reason: str | None = None,
        parent_id: str | None = None,
        client_order_id: str | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO orders (
                     id, client_order_id, run_id, mode, strategy,
                     symbol, side, type, qty, limit_price,
                     stop_price, status, filled_qty, filled_avg_price, submitted_at,
                     filled_at, canceled_at, reason, parent_id, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     status=excluded.status, filled_qty=excluded.filled_qty,
                     filled_avg_price=excluded.filled_avg_price, filled_at=excluded.filled_at,
                     canceled_at=excluded.canceled_at, updated_at=excluded.updated_at""",
                (
                    id,
                    client_order_id,
                    run_id,
                    mode,
                    strategy,
                    symbol,
                    side,
                    type,
                    qty,
                    limit_price,
                    stop_price,
                    status,
                    filled_qty,
                    filled_avg_price,
                    _iso(submitted_at) if submitted_at else None,
                    _iso(filled_at) if filled_at else None,
                    _iso(canceled_at) if canceled_at else None,
                    reason,
                    parent_id,
                    _now(),
                ),
            )

    def for_run(self, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM orders WHERE run_id=? ORDER BY submitted_at", (run_id,)).fetchall()


class TradeRepo(_Repo):
    def insert(self, t: Trade) -> int:
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO trades (
                     run_id, mode, strategy, symbol, qty,
                     entry_price, entry_time, exit_price, exit_time, exit_reason,
                     peak_price, pnl, pnl_pct, entry_order_id, exit_order_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    t.run_id,
                    t.mode,
                    t.strategy,
                    t.symbol,
                    t.qty,
                    t.entry_price,
                    _iso(t.entry_time),
                    t.exit_price,
                    _iso(t.exit_time),
                    t.exit_reason,
                    t.peak_price,
                    t.pnl,
                    t.pnl_pct,
                    t.entry_order_id,
                    t.exit_order_id,
                ),
            )
        return int(cur.lastrowid)

    def for_run(self, run_id: str) -> list[Trade]:
        cur = self.conn.execute("SELECT * FROM trades WHERE run_id=? ORDER BY exit_time", (run_id,))
        return [self._row_to_trade(r) for r in cur.fetchall()]

    def between(self, start: datetime, end: datetime, mode: str = "live", strategy: str | None = None) -> list[Trade]:
        q = "SELECT * FROM trades WHERE mode=? AND exit_time>=? AND exit_time<?"
        args: list = [mode, _iso(start), _iso(end)]
        if strategy:
            q += " AND strategy=?"
            args.append(strategy)
        cur = self.conn.execute(q + " ORDER BY exit_time", args)
        return [self._row_to_trade(r) for r in cur.fetchall()]

    def recent(self, limit: int = 50, mode: str = "live", strategy: str | None = None) -> list[Trade]:
        q = "SELECT * FROM trades WHERE mode=?"
        args: list = [mode]
        if strategy:
            q += " AND strategy=?"
            args.append(strategy)
        cur = self.conn.execute(q + " ORDER BY exit_time DESC LIMIT ?", [*args, limit])
        return [self._row_to_trade(r) for r in cur.fetchall()]

    @staticmethod
    def _row_to_trade(r: sqlite3.Row) -> Trade:
        return Trade(
            symbol=r["symbol"],
            qty=r["qty"],
            entry_price=r["entry_price"],
            entry_time=_dt(r["entry_time"]),
            exit_price=r["exit_price"],
            exit_time=_dt(r["exit_time"]),
            exit_reason=r["exit_reason"],
            peak_price=r["peak_price"],
            mode=r["mode"],
            run_id=r["run_id"],
            entry_order_id=r["entry_order_id"],
            exit_order_id=r["exit_order_id"],
        )


class PositionRepo(_Repo):
    def upsert(self, p: Position, run_id: str, exit_trigger: float | None = None) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO positions (
                     symbol, strategy, run_id, qty, entry_price,
                     entry_time, peak_price, last_price, exit_trigger, stop_order_id,
                     entry_order_id, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol, strategy) DO UPDATE SET
                     qty=excluded.qty, entry_price=excluded.entry_price, entry_time=excluded.entry_time,
                     peak_price=excluded.peak_price, last_price=excluded.last_price,
                     exit_trigger=excluded.exit_trigger, stop_order_id=excluded.stop_order_id,
                     entry_order_id=excluded.entry_order_id, updated_at=excluded.updated_at""",
                (
                    p.symbol,
                    p.strategy,
                    run_id,
                    p.qty,
                    p.entry_price,
                    _iso(p.entry_time),
                    p.peak_price,
                    p.last_price,
                    exit_trigger,
                    p.stop_order_id,
                    p.entry_order_id,
                    _now(),
                ),
            )

    def delete(self, symbol: str, strategy: str | None = None) -> None:
        with self.conn:
            if strategy:
                self.conn.execute("DELETE FROM positions WHERE symbol=? AND strategy=?", (symbol, strategy))
            else:
                self.conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,))

    def clear(self, strategy: str | None = None) -> None:
        with self.conn:
            if strategy:
                self.conn.execute("DELETE FROM positions WHERE strategy=?", (strategy,))
            else:
                self.conn.execute("DELETE FROM positions")

    def all(self, strategy: str | None = None) -> list[Position]:
        if strategy:
            cur = self.conn.execute("SELECT * FROM positions WHERE strategy=? ORDER BY entry_time", (strategy,))
        else:
            cur = self.conn.execute("SELECT * FROM positions ORDER BY entry_time")
        return [
            Position(
                symbol=r["symbol"],
                qty=r["qty"],
                entry_price=r["entry_price"],
                entry_time=_dt(r["entry_time"]),
                peak_price=r["peak_price"],
                last_price=r["last_price"],
                entry_order_id=r["entry_order_id"],
                stop_order_id=r["stop_order_id"],
            )
            for r in cur.fetchall()
        ]

    def all_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM positions ORDER BY entry_time").fetchall()


class LedgerRepo(_Repo):
    def upsert(self, l: DailyLedger) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO daily_ledger (
                     run_id, strategy, date, mode, base_allocation,
                     allocation, realized_pnl, unrealized_pnl, cumulative_realized, trades,
                     wins, losses, largest_win, largest_loss, next_allocation,
                     equity_close, extra_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(run_id, strategy, date) DO UPDATE SET
                     base_allocation=excluded.base_allocation, allocation=excluded.allocation,
                     realized_pnl=excluded.realized_pnl, unrealized_pnl=excluded.unrealized_pnl,
                     cumulative_realized=excluded.cumulative_realized, trades=excluded.trades,
                     wins=excluded.wins, losses=excluded.losses, largest_win=excluded.largest_win,
                     largest_loss=excluded.largest_loss, next_allocation=excluded.next_allocation,
                     equity_close=excluded.equity_close, extra_json=excluded.extra_json""",
                (
                    l.run_id,
                    l.strategy,
                    l.date,
                    l.mode,
                    l.base_allocation,
                    l.allocation,
                    l.realized_pnl,
                    l.unrealized_pnl,
                    l.cumulative_realized,
                    l.trades,
                    l.wins,
                    l.losses,
                    l.largest_win,
                    l.largest_loss,
                    l.next_allocation,
                    l.equity_close,
                    json.dumps(l.extra),
                ),
            )

    def latest(self, run_id: str = "live", strategy: str = "wave_rider") -> DailyLedger | None:
        r = self.conn.execute(
            "SELECT * FROM daily_ledger WHERE run_id=? AND strategy=? ORDER BY date DESC LIMIT 1", (run_id, strategy)
        ).fetchone()
        return self._row_to_ledger(r) if r else None

    def latest_before(self, date: str, run_id: str = "live", strategy: str = "wave_rider") -> DailyLedger | None:
        r = self.conn.execute(
            "SELECT * FROM daily_ledger WHERE run_id=? AND strategy=? AND date<? ORDER BY date DESC LIMIT 1",
            (run_id, strategy, date),
        ).fetchone()
        return self._row_to_ledger(r) if r else None

    def get(self, date: str, run_id: str = "live", strategy: str = "wave_rider") -> DailyLedger | None:
        r = self.conn.execute(
            "SELECT * FROM daily_ledger WHERE date=? AND run_id=? AND strategy=?", (date, run_id, strategy)
        ).fetchone()
        return self._row_to_ledger(r) if r else None

    def all(self, run_id: str = "live", strategy: str | None = None) -> list[DailyLedger]:
        if strategy:
            cur = self.conn.execute(
                "SELECT * FROM daily_ledger WHERE run_id=? AND strategy=? ORDER BY date", (run_id, strategy)
            )
        else:
            cur = self.conn.execute("SELECT * FROM daily_ledger WHERE run_id=? ORDER BY date, strategy", (run_id,))
        return [self._row_to_ledger(r) for r in cur.fetchall()]

    def for_day(self, date: str, run_id: str = "live") -> list[DailyLedger]:
        cur = self.conn.execute(
            "SELECT * FROM daily_ledger WHERE run_id=? AND date=? ORDER BY strategy", (run_id, date)
        )
        return [self._row_to_ledger(r) for r in cur.fetchall()]

    @staticmethod
    def _row_to_ledger(r: sqlite3.Row) -> DailyLedger:
        return DailyLedger(
            date=r["date"],
            mode=r["mode"],
            run_id=r["run_id"],
            base_allocation=r["base_allocation"],
            allocation=r["allocation"],
            realized_pnl=r["realized_pnl"],
            unrealized_pnl=r["unrealized_pnl"],
            cumulative_realized=r["cumulative_realized"],
            trades=r["trades"],
            wins=r["wins"],
            losses=r["losses"],
            largest_win=r["largest_win"],
            largest_loss=r["largest_loss"],
            next_allocation=r["next_allocation"],
            equity_close=r["equity_close"],
            extra=json.loads(r["extra_json"] or "{}"),
        )


class StateRepo(_Repo):
    def set(self, key: str, value) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO bot_state (key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value, default=str), _now()),
            )

    def get(self, key: str, default=None):
        r = self.conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r and r["value"] is not None else default

    def get_with_time(self, key: str) -> tuple[object, datetime] | None:
        r = self.conn.execute("SELECT value, updated_at FROM bot_state WHERE key=?", (key,)).fetchone()
        if not r:
            return None
        return json.loads(r["value"]), _dt(r["updated_at"])


class BacktestRepo(_Repo):
    def insert_run(
        self, *, id: str, start_date: str, end_date: str, feed: str, params: dict, universe: list[str]
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO backtest_runs (id, created_at, start_date, end_date, feed, params_json, "
                "universe_json, summary_json) VALUES (?,?,?,?,?,?,?,NULL)",
                (id, _now(), start_date, end_date, feed, json.dumps(params, default=str), json.dumps(universe)),
            )

    def set_summary(self, id: str, summary: dict) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE backtest_runs SET summary_json=? WHERE id=?", (json.dumps(summary, default=str), id)
            )

    def runs(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

    def add_equity_points(self, run_id: str, points: Iterable[tuple[datetime, float, float]]) -> None:
        rows = [(run_id, _iso(ts), eq, cash) for ts, eq, cash in points]
        if not rows:
            return
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO equity_curve (run_id, ts, equity, cash) VALUES (?,?,?,?)", rows
            )

    def equity_curve(self, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT ts, equity, cash FROM equity_curve WHERE run_id=? ORDER BY ts", (run_id,)
        ).fetchall()


class FeatureRepo(_Repo):
    """Per-minute feature rows recorded by the live bot, labelled after the close."""

    def insert(self, *, symbol: str, ts: datetime, feed: str, day: str, candidate: bool, features: dict) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO features_live (symbol, ts, feed, day, candidate, features_json, labels_json) "
                "VALUES (?,?,?,?,?,?,NULL)",
                (symbol, _iso(ts), feed, day, int(candidate), json.dumps(features, default=str)),
            )

    def insert_many(self, rows: Iterable[tuple]) -> int:
        rows = [(sym, _iso(ts), feed, day, int(c), json.dumps(f, default=str)) for sym, ts, feed, day, c, f in rows]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO features_live (symbol, ts, feed, day, candidate, features_json, labels_json) "
                "VALUES (?,?,?,?,?,?,NULL)",
                rows,
            )
        return len(rows)

    def unlabelled(self, day: str, feed: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT symbol, ts, features_json FROM features_live WHERE day=? AND feed=? AND labels_json IS NULL",
            (day, feed),
        ).fetchall()

    def set_labels(self, updates: Iterable[tuple[str, datetime, str, dict]]) -> int:
        rows = [(json.dumps(lab, default=str), sym, _iso(ts), feed) for sym, ts, feed, lab in updates]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany("UPDATE features_live SET labels_json=? WHERE symbol=? AND ts=? AND feed=?", rows)
        return len(rows)

    def days(self, feed: str = "iex") -> list[str]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT DISTINCT day FROM features_live WHERE feed=? ORDER BY day", (feed,)
            ).fetchall()
        ]

    def rows(self, feed: str = "iex", day: str | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM features_live WHERE feed=?"
        args: list = [feed]
        if day:
            q += " AND day=?"
            args.append(day)
        return self.conn.execute(q + " ORDER BY day, symbol, ts", args).fetchall()


class ControlRepo(_Repo):
    """Requests from outside the bot (the TypeScript API, a script). The bot polls and applies them."""

    def submit(self, command: str, strategy: str | None = None, source: str = "api") -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO control_requests (created_at, command, strategy, source) VALUES (?,?,?,?)",
                (_now(), command, strategy, source),
            )
        return int(cur.lastrowid)

    def pending(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM control_requests WHERE status='pending' ORDER BY id").fetchall()

    def finish(self, req_id: int, status: str, result: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE control_requests SET status=?, result=?, handled_at=? WHERE id=?",
                (status, result, _now(), req_id),
            )

    def recent(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM control_requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


class StructureRepo(_Repo):
    """Option structures (feature 22). Rows are plain dicts; ridethewave.options.lifecycle turns them into objects."""

    def insert(self, row: dict) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO structures (id, strategy, run_id, mode, template_id, underlying, qty, legs_json,
                     entry_net, max_profit, max_loss, status, opened_at, closed_at, exit_net, realized_pl,
                     close_reason, broker_order_id)
                   VALUES (:id, :strategy, :run_id, :mode, :template_id, :underlying, :qty, :legs_json,
                     :entry_net, :max_profit, :max_loss, :status, :opened_at, :closed_at, :exit_net, :realized_pl,
                     :close_reason, :broker_order_id)""",
                row,
            )

    def close(self, id: str, closed_at: str, exit_net: float | None, realized_pl: float | None, reason: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE structures SET status='closed', closed_at=?, exit_net=?, realized_pl=?, close_reason=? "
                "WHERE id=?",
                (closed_at, exit_net, realized_pl, reason, id),
            )

    def open_for(self, strategy: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM structures WHERE strategy=? AND status='open' ORDER BY opened_at", (strategy,)
        ).fetchall()

    def recent(self, limit: int = 50, strategy: str | None = None) -> list[sqlite3.Row]:
        if strategy:
            return self.conn.execute(
                "SELECT * FROM structures WHERE strategy=? ORDER BY opened_at DESC LIMIT ?", (strategy, limit)
            ).fetchall()
        return self.conn.execute("SELECT * FROM structures ORDER BY opened_at DESC LIMIT ?", (limit,)).fetchall()
