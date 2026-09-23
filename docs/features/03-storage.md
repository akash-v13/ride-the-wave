# 03 · Storage

**What it does.** One SQLite file, `data/ridethewave.db`, holds everything: minute bars, orders, completed trades, open positions, the daily ledger, backtest runs and their equity curves, and a small key/value table the dashboard reads for live status.

**Why SQLite.** Nothing to install, one file to back up, fast enough. The bot is the only writer; the dashboard opens it read-only.

**Tables.**

| Table | One row per |
|---|---|
| `bars` | symbol + minute + feed. Cache for backtests and warm-up |
| `orders` | order sent to the broker (live or simulated), updated as its status changes |
| `trades` | completed round trip, with entry, exit, peak, reason, P/L. `mode` is live or backtest |
| `positions` | open position right now, with the current exit trigger for the dashboard |
| `daily_ledger` | trading day per run (`live` or a backtest id) |
| `bot_state` | key such as `heartbeat`, `account`, `allocation`, `universe` |
| `backtest_runs` | backtest, with the parameters and universe used and a summary |
| `equity_curve` | minute of a backtest: equity and cash |

**Looking inside.**
```bash
sqlite3 data/ridethewave.db "select symbol, pnl, exit_reason from trades order by exit_time desc limit 10"
```

**Resetting.** Delete `data/ridethewave.db`. The schema is recreated on next start. Cached bars will be re-downloaded on demand.

**Code:** `src/ridethewave/storage/`.
