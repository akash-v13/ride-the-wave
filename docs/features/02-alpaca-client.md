# 02 · Alpaca connection

**What it does.** Creates the three SDK clients the bot uses: trading (orders, positions, account, clock), market data (snapshots, historical bars) and screener (most-active stocks). Wraps them in a `Broker` interface so the rest of the code never calls the SDK directly.

**Check it works.**
```bash
uv run python scripts/check_env.py
```
Prints account equity, whether the market is open, the latest SPY price, and confirms the database can be written.

**Why an interface.** The backtester swaps in a simulated broker with the same methods. The bot logic cannot tell the difference, which is what makes backtests trustworthy.

**Retries.** Every call retries up to three times with a short, growing delay. A failed call is logged and the current tick is skipped rather than crashing the bot.

**Code:** `src/ridethewave/clients.py`, `src/ridethewave/execution/broker.py`. Endpoint notes with sample responses: [docs/api/](../api/).
