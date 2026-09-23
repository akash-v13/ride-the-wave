# 07 · Order execution

**What it does.** Turns the strategy's signals into real orders and keeps track of them.

**On a buy signal.**
- Size: `position_size_pct` of today's allocation, divided by the price, rounded down to whole shares. With $10,000 and 10%, roughly $1,000 per trade.
- Order: limit buy at the current ask plus `entry_limit_buffer_pct`, valid for the day, with a **protective stop** attached (an OTO order; the stop leg activates only after the buy fills). The stop sits `hard_stop_pct` below the limit price. If the bot dies, Alpaca still has the stop.
- If the buy has not filled after `entry_fill_timeout_seconds`, it is cancelled. A partial fill is kept.

**On a sell signal.** Cancel the protective stop, then send a market sell so it fills immediately. When the fill comes back, the trade is written to the database with its reason.

**Every tick** the bot polls its in-flight orders. It also checks whether the server-side stop fired on its own (reason `server_stop`).

**Startup.** The bot's position list is reconciled with Alpaca's. Positions Alpaca has that the bot forgot (after a crash) are adopted with the peak reset to the higher of entry and current price.

**Shutdown (Ctrl-C).** Pending buys are cancelled. Open positions are left alone with their protective stops in place; the ledger is written.

**Verified 2026-09-17** against the paper account: a limit buy with stop leg was submitted, showed as accepted with the leg held, and cancelled cleanly.

**Code:** `src/ridethewave/execution/`, `src/ridethewave/engine.py`, `src/ridethewave/runner.py`, `scripts/run_bot.py`.
