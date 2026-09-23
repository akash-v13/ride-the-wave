# storage

SQLite persistence. One file, `data/ridethewave.db`.

- `schema.sql`: tables `bars`, `orders`, `trades`, `positions`, `daily_ledger`, `bot_state`, `backtest_runs`, `equity_curve`, `features_live`. Applied idempotently on every start.
- `db.py`: `Database` wrapper (WAL mode, read-only mode for the UI, in-memory mode for tests).
- `repos.py`: one small repository class per table; no raw SQL outside this package except the dashboard's read-only queries.

`trades` and `daily_ledger` serve both live and backtest, distinguished by `mode` and `run_id` (`live` for the real bot).
