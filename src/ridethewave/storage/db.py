"""SQLite connection and schema management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ridethewave.storage import repos

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Database:
    """One connection, one file. The bot is the only writer; the UI opens read-only."""

    def __init__(self, path: str | Path, read_only: bool = False):
        self.path = Path(path)
        if read_only:
            uri = f"file:{self.path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self._migrate()
            self.conn.executescript(SCHEMA_PATH.read_text())
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")

        self.bars = repos.BarRepo(self.conn)
        self.orders = repos.OrderRepo(self.conn)
        self.trades = repos.TradeRepo(self.conn)
        self.positions = repos.PositionRepo(self.conn)
        self.ledger = repos.LedgerRepo(self.conn)
        self.state = repos.StateRepo(self.conn)
        self.backtests = repos.BacktestRepo(self.conn)
        self.features = repos.FeatureRepo(self.conn)
        self.control = repos.ControlRepo(self.conn)

    def _migrate(self) -> None:
        """Bring a pre-multi-strategy database up to date. Idempotent."""
        c = self.conn

        def cols(table: str) -> set[str]:
            return {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}

        if not cols("trades"):
            return  # fresh database; schema.sql creates everything
        with c:
            for table in ("orders", "trades"):
                if "strategy" not in cols(table):
                    c.execute(f"ALTER TABLE {table} ADD COLUMN strategy TEXT NOT NULL DEFAULT 'wave_rider'")
            if "strategy" not in cols("positions"):
                c.execute("ALTER TABLE positions RENAME TO positions_old")
                c.execute(
                    "CREATE TABLE positions (symbol TEXT NOT NULL, strategy TEXT NOT NULL DEFAULT 'wave_rider', "
                    "run_id TEXT NOT NULL, qty REAL NOT NULL, entry_price REAL NOT NULL, entry_time TEXT NOT NULL, "
                    "peak_price REAL NOT NULL, last_price REAL NOT NULL, exit_trigger REAL, stop_order_id TEXT, "
                    "entry_order_id TEXT, updated_at TEXT NOT NULL, PRIMARY KEY (symbol, strategy))"
                )
                c.execute(
                    "INSERT INTO positions (symbol, strategy, run_id, qty, entry_price, entry_time, peak_price, "
                    "last_price, exit_trigger, stop_order_id, entry_order_id, updated_at) SELECT symbol, "
                    "'wave_rider', run_id, qty, entry_price, entry_time, peak_price, last_price, exit_trigger, "
                    "stop_order_id, entry_order_id, updated_at FROM positions_old"
                )
                c.execute("DROP TABLE positions_old")
            if "strategy" not in cols("daily_ledger"):
                c.execute("ALTER TABLE daily_ledger RENAME TO daily_ledger_old")
                c.execute(
                    "CREATE TABLE daily_ledger (run_id TEXT NOT NULL, strategy TEXT NOT NULL DEFAULT 'wave_rider', "
                    "date TEXT NOT NULL, mode TEXT NOT NULL, base_allocation REAL NOT NULL, allocation REAL NOT NULL, "
                    "realized_pnl REAL NOT NULL DEFAULT 0, unrealized_pnl REAL NOT NULL DEFAULT 0, "
                    "cumulative_realized REAL NOT NULL DEFAULT 0, trades INTEGER NOT NULL DEFAULT 0, "
                    "wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, "
                    "largest_win REAL NOT NULL DEFAULT 0, largest_loss REAL NOT NULL DEFAULT 0, "
                    "next_allocation REAL NOT NULL DEFAULT 0, equity_close REAL, extra_json TEXT, "
                    "PRIMARY KEY (run_id, strategy, date))"
                )
                c.execute(
                    "INSERT INTO daily_ledger SELECT run_id, 'wave_rider', date, mode, base_allocation, allocation, "
                    "realized_pnl, unrealized_pnl, cumulative_realized, trades, wins, losses, largest_win, "
                    "largest_loss, next_allocation, equity_close, extra_json FROM daily_ledger_old"
                )
                c.execute("DROP TABLE daily_ledger_old")

    @classmethod
    def in_memory(cls) -> Database:
        db = cls.__new__(cls)
        db.path = Path(":memory:")
        db.conn = sqlite3.connect(":memory:", check_same_thread=False)
        db.conn.executescript(SCHEMA_PATH.read_text())
        db.conn.row_factory = sqlite3.Row
        db.bars = repos.BarRepo(db.conn)
        db.orders = repos.OrderRepo(db.conn)
        db.trades = repos.TradeRepo(db.conn)
        db.positions = repos.PositionRepo(db.conn)
        db.ledger = repos.LedgerRepo(db.conn)
        db.state = repos.StateRepo(db.conn)
        db.backtests = repos.BacktestRepo(db.conn)
        db.features = repos.FeatureRepo(db.conn)
        db.control = repos.ControlRepo(db.conn)
        return db

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
