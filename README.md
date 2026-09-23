# Ride The Wave

An autonomous paper-trading system built on the [Alpaca](https://alpaca.markets) API. A Python engine trades
unattended during market hours, a TypeScript API and web UI expose its state and controls, and a backtester
plus a dated research log decide which strategies are worth running at all.

> **Paper trading only.** Nothing here is investment advice, and no strategy in this repo has yet shown a
> durable edge. See [Results so far](#results-so-far).

## What it does

- **Trades on its own.** Scans a universe of liquid US stocks, turns snapshots into bars, runs one or more
  strategies, places orders through Alpaca, and writes a daily ledger. A launchd-managed dispatcher starts
  and stops everything on schedule.
- **Protects itself.** Kill switches halt new entries and flatten positions on daily or open loss limits, or
  when a Bayesian test says the live win rate has fallen below break-even. A server-side stop order backs up
  every position in case the process dies.
- **Reports and alerts.** Publishes five check-in reports a day (pre-market, morning, midday, close,
  research) and raises alerts on a stale heartbeat, a trading halt, or API errors.
- **Exposes an API.** A TypeScript service serves 14 JSON endpoints and a web dashboard. Operator commands
  (pause, resume, flatten, halt) are queued for the bot rather than executed by the API.
- **Tests ideas before trading them.** A replay backtester runs the same strategy code against historical
  bars. New strategies run in *shadow mode* (simulated fills on live prices) before they get capital.

## Architecture

```
              Alpaca (paper)  ── market data ──┐    ┌── orders, positions, account
                                               ▼    │
 ┌──────────────────────── Python engine (src/ridethewave) ───────────────────────┐
 │  data/  ──bars──▶  strategy/  ──signals──▶  execution/  ──fills──▶  portfolio/ │
 │  (universe,        (pure logic: no         (broker, order        (sizing,     │
 │   poller, bars)     network, no DB)         manager, positions)   ledger)      │
 │  operator/: kill switches · reports · alerts · 5-min dispatcher (launchd)      │
 │  backtest/: same strategy code, simulated broker, historical bars              │
 └───────────────────────────────────┬────────────────────────────────────────────┘
                                     │ writes                ▲ applies pending
                                     ▼                       │ control requests
                        ┌────────────────────────────────────┴──┐
                        │ SQLite (WAL): bars, orders, trades,   │
                        │ positions, ledger, backtests, state,  │
                        │ features, control_requests            │
                        └────────────────────┬──────────────────┘
                                             │ read-only        ▲ enqueue only
                                             ▼                  │
                        ┌───────────────────────────────────────┴──┐
                        │ TypeScript API (web/): Fastify + Zod     │
                        │ 14 endpoints · web UI · bearer-token POST │
                        └──────────────────────────────────────────┘
```

### Design choices

- **One strategy codebase for live and backtest.** Strategies see only bars and positions and emit signals,
  so backtests exercise the exact code that trades.
- **The API asks; the bot decides.** The TypeScript service holds a read-only database connection. Its only
  write is a row in `control_requests`, which the bot applies on its next tick (about 15 seconds) and
  records the outcome. The API never touches the broker.
- **TypeScript stays off the trading path.** The engine needs pandas, numpy and statsmodels and stays in
  Python. Putting another process between the bot and Alpaca would add latency and a failure mode.
- **Every external call is retried.** Alpaca trading and market-data calls use exponential backoff with
  jitter. LLM scoring uses bounded retries, timeouts and a deterministic mock for tests.
- **Schema changes are idempotent.** The schema and migrations are applied on every start, behind one
  repository class per table.

Full reasoning: [docs/architecture.md](docs/architecture.md) and the decision log in
[docs/decisions.md](docs/decisions.md).

## Results so far

Each experiment has a dated write-up in [docs/research/](docs/research/). The short version:

| Experiment | Finding |
|---|---|
| 62-configuration parameter sweep, 75 trading days | No configuration profitable (best profit factor 0.91) |
| Feature dataset + three entry filters | First profitable configuration, but thin (PF 1.25 on SIP, 1.17 on IEX) |
| Autocorrelation of 1-minute returns | White noise: the streak trigger is not the edge |
| 15-minute bars | Small signal (+22 ± 12 bp at 180 min) that holds in both halves of the sample |
| SPY intraday momentum (published effect) | Absent in 2016–2026 data; rejected |
| LLM news scoring, 21k headline/return pairs | No intraday edge for positive news; filter **not** shipped |
| Opening-range breakout, 15-minute Wave Rider | PF 0.93 and 1.00; running in shadow mode only |

Negative results are kept on purpose: they decide which filters are on by default and why new strategies
run in shadow before they get capital.

## Tech stack

| Layer | Tools |
|---|---|
| Trading engine | Python 3.12, uv, alpaca-py, pandas, numpy, statsmodels, tenacity |
| Storage | SQLite (WAL mode) |
| API and UI | TypeScript (strict), Node 24+, Fastify, Zod, plain HTML/JS |
| Scheduling | macOS launchd, 5-minute dispatcher |
| Testing | pytest (70 tests), Vitest (API against a temporary database), ruff |

## Repository layout

```
src/ridethewave/   Python package: data, strategy, execution, portfolio, backtest, storage, operator, signals, ui
web/               TypeScript API and web UI
scripts/           Entry points: run_bot, run_backtest, sweep, reports, launchd install, research studies
tests/             pytest suite
config/            settings.example.yaml and saved strategy profiles
docs/              Architecture, strategy spec, feature pages, research write-ups, Alpaca API notes
ops/               launchd notes
```

Every folder has its own README describing what belongs in it.

## Running it

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24+, and an Alpaca **paper** account.

```bash
uv sync
cp .env.example .env                                   # add paper API keys
cp config/settings.example.yaml config/settings.yaml

uv run python scripts/run_bot.py                       # trade (paper) during market hours
uv run python scripts/run_backtest.py --start 2026-09-08 --end 2026-09-12
uv run python scripts/install_launchd.py install       # run unattended on a schedule

cd web && npm install && npm run build && npm start    # API + UI at http://127.0.0.1:8787
```

Tests: `uv run pytest` and `cd web && npm test`.

## Further reading

- [docs/strategy.md](docs/strategy.md): the trading rules, with parameters and a worked example
- [docs/features/](docs/features/): one plain-English page per feature
- [docs/handbook.md](docs/handbook.md): everything in one reference
- [CLAUDE.md](CLAUDE.md): running build status and decisions
