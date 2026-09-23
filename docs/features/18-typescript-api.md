# 18 · TypeScript API and web UI

**What it does.** A small TypeScript service (Node 26, Fastify) that exposes the system's state over
HTTP and serves a web page built on it, at `http://127.0.0.1:8787`. The Python bot stays the owner of
trading, data and the database; the service reads the same SQLite file and can only *ask* the bot to
do things, by queuing control requests the bot applies on its next tick.

**Endpoints** (all JSON, all read-only except the last):

| Path | Returns |
|---|---|
| `GET /api/health` | bot status (running / waiting / stopped), last tick age, active halt, current alerts |
| `GET /api/status` | heartbeat, run info, account, allocation, risk state, per-strategy live figures, operator tick |
| `GET /api/positions` | open positions with strategy, entry, last, exit trigger |
| `GET /api/trades?day=YYYY-MM-DD&strategy=&mode=&limit=` | closed trades, newest first |
| `GET /api/ledger?strategy=&run_id=live` | daily ledger rows |
| `GET /api/strategies` | configured strategies with mode, weight, params and today's live figures |
| `GET /api/reports`, `/api/reports/latest`, `/api/reports/:day/:file` | check-in pages as Markdown |
| `GET /api/backtests`, `/api/backtests/:id/equity` | stored backtest runs and equity curves |
| `GET /api/features/today` | feature rows recorded and labelled today |
| `GET /api/controls` | recent control requests and what the bot did with them |
| `POST /api/controls {command, strategy}` | queue `pause`, `resume`, `flatten` or `halt` for one strategy or `all` |

**Controls.** A request is written to the `control_requests` table; the bot reads pending rows every
tick (about 15 seconds while running), applies them per strategy (pause stops new entries, resume
lifts that, flatten sells the strategy's positions, halt does both) and records the outcome. When
`RTW_API_TOKEN` is set the POST requires `Authorization: Bearer <token>`; the service binds to
localhost only unless `RTW_API_HOST` says otherwise.

**The page.** Status tiles, strategies with pause / resume / flatten buttons, open positions, today's
trades and the check-in reports, refreshing every five seconds. It replaces nothing yet; the
Streamlit dashboard still runs on port 8501. It is the base for the web UI to come.

**Running it.** `scripts/install_launchd.py install` adds a `com.ridethewave.api` agent that keeps the
service up. By hand: `cd web && npm install && npm run build && npm start`. Tests: `npm test`.

**Why this shape.** The trading core needs pandas, numpy and statsmodels and stays in Python; the
API layer is what a web UI, a phone page or another tool talks to, and TypeScript is a good fit for
that. Putting a TypeScript process on the trading path itself (for the Alpaca calls) would add
latency and a failure mode for no gain, so that was not done.

**Code:** `web/` (`src/server.ts`, `src/routes/api.ts`, `src/db.ts`, `src/config.ts`, `public/`),
`control_requests` in `src/ridethewave/storage/`, `_apply_controls` in `src/ridethewave/runner.py`.
