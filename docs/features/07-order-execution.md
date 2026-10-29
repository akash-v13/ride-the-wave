# 07 · Order execution

**What it does.** Turns the strategy's signals into real orders and keeps track of them.

**On a buy signal.**
- Size: `position_size_pct` of today's allocation, divided by the price, rounded down to whole shares. With $10,000 and 10%, roughly $1,000 per trade.
- Order: limit buy at the current ask plus `entry_limit_buffer_pct`, valid for the day, with a **protective stop** attached (an OTO order; the stop leg activates only after the buy fills). The stop sits `hard_stop_pct` below the limit price. If the bot dies, Alpaca still has the stop.
- If the buy has not filled after `entry_fill_timeout_seconds`, it is cancelled. A partial fill is kept.

**On a sell signal.** Cancel the protective stop, then send a market sell so it fills immediately. When the fill comes back, the trade is written to the database with its reason.

**When the stop gets there first (fixed 2026-10-29).** The stop sits about 1% below entry, and so does the bot's own hard stop. So in a fast fall both can fire within seconds. On 29 October Alpaca's stop sold 151 NUWE at 11:27:12 ET. The bot's exit came six seconds later. The bot ignored the "already filled" reply to its cancel and sent a market sell for shares it no longer held. Alpaca refused only because NUWE could not be shorted. On a stock that can be shorted, that sell would have opened a short of the same size. The bot also kept NUWE as held, so its loss was missing from the day's records. Now:

1. After cancelling the stop, the bot reads the stop's final state, waiting up to 2 seconds while Alpaca reports `pending_cancel`. If the stop filled, the bot books that fill as the exit (reason `server_stop`) and sends nothing. If the stop filled in part, the bot sells only the rest.
2. Live slots also ask Alpaca how many shares it holds before every market sell, and never sell more. If Alpaca holds none, the position is dropped from the book with an error in the log, because it was closed outside the bot. Shadow slots skip this check, since their broker is simulated.

Tests: `tests/test_order_manager.py`, the five tests after "the 2026-10-29 NUWE race".

**Every tick** the bot polls its in-flight orders. It also checks whether the server-side stop fired on its own (reason `server_stop`).

**Startup.** The bot's position list is reconciled with Alpaca's. Positions Alpaca has that the bot forgot (after a crash) are adopted with the peak reset to the higher of entry and current price.

**Shutdown (Ctrl-C).** Pending buys are cancelled. Open positions are left alone with their protective stops in place; the ledger is written.

**Verified 2026-09-17** against the paper account: a limit buy with stop leg was submitted, showed as accepted with the leg held, and cancelled cleanly.

**Code:** `src/ridethewave/execution/`, `src/ridethewave/engine.py`, `src/ridethewave/runner.py`, `scripts/run_bot.py`.
