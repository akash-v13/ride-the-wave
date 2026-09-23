# 05 · Market data poller and minute bars

**What it does.** Every `poll_interval_seconds` (default 15) the bot asks Alpaca for a snapshot of every symbol in the universe plus anything it holds. One request covers 200 symbols, so a 65-symbol universe is one call per poll: about four calls a minute against a 200-per-minute limit.

Each snapshot carries the latest trade, latest quote and the latest minute bar. The bot:
- records the latest trade price as a **tick** (used to track peaks and decide exits between bar closes),
- treats the minute bar as **complete** once its start time is older than the current minute, and hands completed bars to the strategy.

**Warm-up.** At start, the last `warmup_minutes` (default 60) of IEX minute bars are downloaded so streaks can be detected immediately rather than an hour after the open.

**Gaps.** If no IEX trade prints in a minute, there is no bar for that minute. Streaks are counted over consecutive *bars*, so a gap does not reset a streak. This is a known simplification.

**Historical bars.** The same module downloads past minute bars for backtests, caching them in SQLite so a repeat run is instant and free.

**Code:** `src/ridethewave/data/market_data.py`, `src/ridethewave/data/bars.py`.
