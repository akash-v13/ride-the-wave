-- Ride The Wave SQLite schema. Applied idempotently on every start.
-- All timestamps are ISO-8601 UTC strings. Money is REAL (floats are fine at this scale).

CREATE TABLE IF NOT EXISTS bars (
    symbol      TEXT NOT NULL,
    ts          TEXT NOT NULL,          -- bar start, UTC
    feed        TEXT NOT NULL,          -- iex | sip | live
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      INTEGER NOT NULL,
    trade_count INTEGER NOT NULL DEFAULT 0,
    vwap        REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, ts, feed)
);
CREATE INDEX IF NOT EXISTS idx_bars_ts ON bars (ts);

CREATE TABLE IF NOT EXISTS orders (
    id               TEXT PRIMARY KEY,   -- Alpaca order id (or sim id)
    client_order_id  TEXT,
    run_id           TEXT NOT NULL,
    mode             TEXT NOT NULL,      -- live | backtest | shadow
    strategy         TEXT NOT NULL DEFAULT 'wave_rider',
    symbol           TEXT NOT NULL,
    side             TEXT NOT NULL,
    type             TEXT NOT NULL,
    qty              REAL,
    limit_price      REAL,
    stop_price       REAL,
    status           TEXT NOT NULL,
    filled_qty       REAL DEFAULT 0,
    filled_avg_price REAL,
    submitted_at     TEXT,
    filled_at        TEXT,
    canceled_at      TEXT,
    reason           TEXT,               -- why the bot placed it
    parent_id        TEXT,               -- for stop-loss legs
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_run ON orders (run_id);

CREATE TABLE IF NOT EXISTS trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL,
    mode           TEXT NOT NULL,        -- live | backtest | shadow
    strategy       TEXT NOT NULL DEFAULT 'wave_rider',
    symbol         TEXT NOT NULL,
    qty            REAL NOT NULL,
    entry_price    REAL NOT NULL,
    entry_time     TEXT NOT NULL,
    exit_price     REAL NOT NULL,
    exit_time      TEXT NOT NULL,
    exit_reason    TEXT NOT NULL,
    peak_price     REAL NOT NULL,
    pnl            REAL NOT NULL,
    pnl_pct        REAL NOT NULL,
    entry_order_id TEXT,
    exit_order_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_run ON trades (run_id);
CREATE INDEX IF NOT EXISTS idx_trades_exit_time ON trades (exit_time);

CREATE TABLE IF NOT EXISTS positions (
    symbol         TEXT NOT NULL,
    strategy       TEXT NOT NULL DEFAULT 'wave_rider',
    run_id         TEXT NOT NULL,
    qty            REAL NOT NULL,
    entry_price    REAL NOT NULL,
    entry_time     TEXT NOT NULL,
    peak_price     REAL NOT NULL,
    last_price     REAL NOT NULL,
    exit_trigger   REAL,                 -- current wave-exit trigger price, for the UI
    stop_order_id  TEXT,
    entry_order_id TEXT,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (symbol, strategy)
);

CREATE TABLE IF NOT EXISTS daily_ledger (
    run_id              TEXT NOT NULL,   -- 'live' for the real bot, backtest run id otherwise
    strategy            TEXT NOT NULL DEFAULT 'wave_rider',
    date                TEXT NOT NULL,   -- YYYY-MM-DD, US/Eastern
    mode                TEXT NOT NULL,
    base_allocation     REAL NOT NULL,
    allocation          REAL NOT NULL,
    realized_pnl        REAL NOT NULL DEFAULT 0,
    unrealized_pnl      REAL NOT NULL DEFAULT 0,
    cumulative_realized REAL NOT NULL DEFAULT 0,
    trades              INTEGER NOT NULL DEFAULT 0,
    wins                INTEGER NOT NULL DEFAULT 0,
    losses              INTEGER NOT NULL DEFAULT 0,
    largest_win         REAL NOT NULL DEFAULT 0,
    largest_loss        REAL NOT NULL DEFAULT 0,
    next_allocation     REAL NOT NULL DEFAULT 0,
    equity_close        REAL,
    extra_json          TEXT,
    PRIMARY KEY (run_id, strategy, date)
);

CREATE TABLE IF NOT EXISTS bot_state (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    feed          TEXT NOT NULL,
    params_json   TEXT NOT NULL,
    universe_json TEXT NOT NULL,
    summary_json  TEXT
);

CREATE TABLE IF NOT EXISTS equity_curve (
    run_id  TEXT NOT NULL,
    ts      TEXT NOT NULL,
    equity  REAL NOT NULL,
    cash    REAL NOT NULL,
    PRIMARY KEY (run_id, ts)
);

CREATE TABLE IF NOT EXISTS features_live (
    symbol        TEXT NOT NULL,
    ts            TEXT NOT NULL,          -- bar start, UTC
    feed          TEXT NOT NULL,          -- iex (what the live bot saw)
    day           TEXT NOT NULL,          -- YYYY-MM-DD ET
    candidate     INTEGER NOT NULL,       -- streak rule would have bought this bar
    features_json TEXT NOT NULL,
    labels_json   TEXT,                   -- filled at end of day from the day's bars
    PRIMARY KEY (symbol, ts, feed)
);
CREATE INDEX IF NOT EXISTS idx_features_live_day ON features_live (day);

CREATE TABLE IF NOT EXISTS control_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    command     TEXT NOT NULL,          -- pause | resume | flatten | halt
    strategy    TEXT,                   -- strategy id, or NULL / 'all'
    source      TEXT NOT NULL DEFAULT 'api',
    status      TEXT NOT NULL DEFAULT 'pending',   -- pending | done | rejected
    result      TEXT,
    handled_at  TEXT
);
