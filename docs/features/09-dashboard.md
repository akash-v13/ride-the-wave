# 09 · Dashboard

**What it does.** A browser page showing what the bot is doing. It only reads the database, so it can be open, closed or crashed without affecting trading.

**Run it.**
```bash
uv run python scripts/run_ui.py
```
Then open the URL it prints (normally http://localhost:8501).

**Live tab** (refreshes every 5 seconds): equity, cash, today's allocation, bot status (running / waiting for open / stale), universe size. Open positions with entry, current, peak, the price at which the wave exit would sell ("Sell if ≤", blank until the gain floor is reached), P/L in dollars and percent, distance from peak, minutes held. Today's closed trades with reason. Today's orders in an expander.

**Ledger tab:** realized P/L per day (blue up, red down), cumulative realized P/L, and the table with allocation and next-day allocation.

**Backtests tab:** pick a run, see its summary, equity curve, per-day P/L and every trade.

**"Stale" means** no heartbeat for over a minute while the bot should be running. Check the terminal running `run_bot.py` and the log in `data/logs/`.

**Code:** `src/ridethewave/ui/`.
