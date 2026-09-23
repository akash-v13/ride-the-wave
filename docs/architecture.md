# Architecture

This document explains how Ride The Wave is put together and why. It is written for someone who can read code but has not built a trading system before. Each section says what the piece does, then why it is built that way.

## 1. The one-paragraph version

The bot is a loop that runs every few seconds during market hours. Each tick it (1) fetches the latest prices for a list of candidate stocks in a single API call, (2) turns those prices into one-minute bars kept in memory and on disk, (3) hands the bars to the strategy, which answers "buy this", "sell that" or "do nothing", (4) sends any orders to Alpaca and records what happened, and (5) refreshes the numbers the dashboard reads. At the close it writes a ledger line for the day and decides how much capital tomorrow gets. The backtester runs the exact same loop, but the prices come from Alpaca's history instead of live, and orders go to a fake broker instead of Alpaca.

## 2. Constraints that shaped the design

These are facts about the environment, verified on 2026-09-17. They drove most decisions below.

| Constraint | Consequence |
|---|---|
| Free Alpaca data plan: IEX feed only, 200 REST requests/min, 30 websocket symbols, latest 15 minutes of SIP history withheld | Use `feed=iex` everywhere. Use the multi-symbol snapshot endpoint so one call covers the whole universe. Websockets cannot cover a 100+ stock universe, so v1 polls instead |
| Paper trading fills are optimistic (no slippage, no market impact, random 10% partial fills) | Backtest and paper results will both overstate real performance. The backtester models a small slippage so it is not more optimistic than paper |
| Pattern Day Trader rule was retired 2026-06-04 and replaced by an intraday margin framework | No day-trade counting is needed. The bot still tracks trade counts for reporting |
| Owner's machine: Apple Silicon Mac, brand new, only system Python 3.9 | Pick a pure-Python stack, no Node or Docker. The SDK needs Python 3.10+, so we install 3.12 via uv |
| Owner wants to plug in more complex strategies later | Strategy is an interface; the current one is one implementation. Data, execution and UI never depend on which strategy is loaded |

## 3. Component diagram

```
                      ┌───────────────────────────────────────────┐
                      │               Alpaca (paper)              │
                      │  Market Data API          Trading API     │
                      └───────▲───────────────────────▲───────────┘
                              │ snapshots, bars       │ orders, positions, account
                              │                       │
┌───────────────┐    ┌────────┴────────┐     ┌────────┴─────────┐
│  Universe     │───▶│  MarketData     │     │  Broker          │
│  builder      │    │  (poller + bar  │     │  (AlpacaBroker   │
│  (most-active │    │   aggregator)   │     │   or SimBroker)  │
│   / static)   │    └────────┬────────┘     └────────▲─────────┘
└───────────────┘             │ Bar events            │ OrderRequest
                              ▼                       │
                     ┌─────────────────┐     ┌────────┴─────────┐
                     │  Strategy       │────▶│  Execution       │
                     │  (WaveRider)    │Signal│  (OrderManager,  │
                     │  pure logic     │     │   PositionBook)  │
                     └─────────────────┘     └────────┬─────────┘
                                                      │ fills, positions
                                                      ▼
                     ┌───────────────────────────────────────────┐
                     │  Storage (SQLite): bars, orders, trades,  │
                     │  positions, daily_ledger, bot_state       │
                     └───────────────┬───────────────────────────┘
                                     │ read-only
                                     ▼
                     ┌───────────────────────────────────────────┐
                     │  Dashboard (Streamlit, separate process)  │
                     └───────────────────────────────────────────┘
```

The **Portfolio** component (not drawn) sits beside Execution: it decides position size from today's allocated capital and writes the end-of-day ledger.

## 4. Components in detail

### 4.1 Universe builder (`data/universe.py`)

**What.** Produces the list of symbols the bot watches today. Sources, in priority order: a static list from config, or Alpaca's most-actives screener (top N by volume), filtered by the assets endpoint (tradable, not fractional-only, price within a band, listed on NYSE/NASDAQ/ARCA).

**Why.** Scanning every US stock (about 11,000) is pointless on a 200-call/minute budget and would fill the universe with illiquid names where IEX prints almost no trades. Most-actives are liquid, so IEX quotes are meaningful and paper fills are closer to reality. The universe is rebuilt once at start and optionally every 30 minutes.

### 4.2 Market data (`data/market_data.py`, `data/bars.py`)

**What.** Every `poll_interval_seconds` (default 15) it calls the multi-symbol snapshot endpoint with up to 200 symbols per request. From each snapshot it takes `latestTrade.p` and `minuteBar`. A `BarAggregator` keeps a rolling window of one-minute bars per symbol in memory and appends completed bars to SQLite.

**Why polling, not websockets.** The free plan caps websocket subscriptions at 30 symbols, which is smaller than a useful universe. One snapshot call for 200 symbols every 15 seconds is 4 calls a minute against a 200-call budget, so polling is cheap and simple. A websocket feed for the handful of held positions is a planned v2 upgrade for faster exits.

**Why minute bars.** The strategy's "green streak" is defined over consecutive minute closes. Minute bars are also what the historical API returns, so live and backtest see identical shapes.

### 4.3 Strategy (`strategy/`)

**What.** A `Strategy` interface with one method: `on_bar(bar, context) -> list[Signal]`. `context` exposes the bar history, open positions and available capital. The v1 implementation, `WaveRider`, is specified in [strategy.md](strategy.md).

**Why pure.** The strategy makes no network calls and touches no database. Everything it needs is passed in. That is what makes the backtester trustworthy: the code that decided to buy in a simulation is byte-for-byte the code that decides live. It also makes unit tests trivial: feed in a list of bars, assert the signals.

### 4.4 Execution (`execution/`)

**What.** `OrderManager` turns a `Signal` into an Alpaca order request, submits it through the `Broker` interface, and listens for fills. `PositionBook` is the bot's own record of what it holds: entry price, quantity, peak price since entry, entry time. It reconciles against Alpaca's positions endpoint on startup and every few minutes.

**Entry orders** are limit orders at the ask plus a small buffer (default 0.1%), time-in-force `day`. **Safety net:** each entry is a bracket-style order with a server-side stop-loss at `entry × (1 − hard_stop_pct)`. If the bot process dies, Alpaca still protects the position.

**Exit orders** are decided client-side by the strategy (trailing from peak with a gain floor) and sent as market orders so they fill immediately. When the client-side exit fires, the safety stop is cancelled first.

**Why client-side exits.** Alpaca's native trailing stop follows the high-water mark but cannot express "never sell below entry plus X%". Doing it ourselves gives exactly the rule in the brief and keeps the logic reusable in backtests.

### 4.5 Portfolio (`portfolio/`)

**What.** `CapitalAllocator` knows how much money the strategy may use today and divides it into position slots. `Ledger` writes one row per trading day: realized profit, unrealized profit, number of trades, win rate, and the allocation for tomorrow (= today's base + `reinvest_gains_pct` of today's realized gains).

**Why separate from execution.** Sizing rules will change (Kelly-style sizing, volatility scaling) without the order plumbing changing.

### 4.6 Storage (`storage/`)

**What.** SQLite database at `data/ridethewave.db`. Tables: `bars`, `orders`, `trades`, `positions`, `daily_ledger`, `bot_state`, `backtest_runs`, `backtest_trades`. Thin repository classes wrap the SQL.

**Why SQLite.** Already installed on the machine, zero setup, a single file to back up, and fast enough for tens of thousands of bars per day. The bot is the only writer, the UI only reads, so there is no concurrency problem. If bar volume ever becomes an issue, bars move to Parquet files and everything else stays.

### 4.7 Backtest (`backtest/`)

**What.** `ReplayEngine` loads historical minute bars for a date range and a universe, then drives the same `Strategy` bar by bar. `SimBroker` implements the `Broker` interface: fills at the next bar's open plus configurable slippage, tracks cash and positions. A `Report` prints and stores per-trade and per-day results and an equity curve.

**Why the same loop.** The engine reuses `BarAggregator`, `Strategy`, `OrderManager` and `PositionBook`. Only `MarketData` (history instead of snapshots) and `Broker` (sim instead of Alpaca) are swapped. This is the core reason the code is split the way it is.

**Data for backtests.** Historical minute bars come from the bars endpoint. For dates older than 15 minutes the SIP feed is available even on the free plan, so backtests use better data than live trading does. The doc for the backtester will call this out on every report.

### 4.8 Dashboard (`ui/`)

**What.** A Streamlit app that reads SQLite and shows: account equity and cash, today's allocation, open positions (symbol, quantity, entry price, current price, peak, unrealized profit and percent, time held, current exit trigger), closed trades today, the daily ledger, and the bot's heartbeat. Auto-refreshes every few seconds.

**Why Streamlit.** Pure Python, no JavaScript build, and tables plus line charts are exactly what a trading dashboard needs. It runs as its own process so a UI crash cannot stop the bot, and a bot crash is visible in the UI as a stale heartbeat.

### 4.9 Runner (`scripts/run_bot.py`)

**What.** Starts everything, waits for market open using the clock endpoint, runs the tick loop, handles the 3:55pm flatten step if enabled, writes the ledger, exits. Logs to `data/logs/`. Handles Ctrl-C by cancelling open orders (positions are left alone unless configured otherwise).

## 5. Data flow for one tick

1. Poller requests snapshots for the universe (1 call per 200 symbols).
2. Aggregator updates the current minute bar for each symbol; when a minute rolls over, the completed bar is stored and emitted.
3. For each new bar, the strategy is called with the bar and context. It returns signals.
4. Execution checks each signal against the position book and capital allocator (slot free? cash available? already holding?), then submits orders.
5. Fills arrive (v1: polled from the orders endpoint each tick; v2: trade-updates websocket). Position book and trades table are updated.
6. Heartbeat and per-position metrics are written to `bot_state` for the UI.

Typical tick cost on the free plan: 1 to 2 data calls, 1 orders poll, occasional order submissions. Well under the 200-call budget.

## 6. Failure handling

- **API errors / rate limits:** exponential backoff with jitter; the tick is skipped, not retried in a tight loop.
- **Bot crash while holding:** the server-side stop-loss remains. On restart the position book reconciles from Alpaca and resumes managing the position with peak reset to max(entry, current).
- **Clock drift / market closed:** every tick checks the cached clock; outside regular hours the loop sleeps.
- **Bad data:** bars with zero volume or a price more than 20% from the previous close are dropped and logged rather than fed to the strategy.

## 7. What changes for v2 and beyond

- Trade-updates websocket for instant fill notifications.
- IEX websocket for held positions (up to 30) for faster exits.
- Additional strategies behind the same interface (mean reversion, breakout with volume confirmation).
- Parameter sweeps in the backtester to tune streak length, trail percent and gain floor.
- Optional upgrade to the paid data plan if IEX-only quotes prove too thin.
