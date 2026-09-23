# 10 · Daily ledger and reinvestment

**What it does.** When the bot shuts down for the day it writes one ledger row: realized P/L from closed trades, unrealized P/L on anything still held, number of trades, wins, losses, largest win and loss, account equity, and **tomorrow's allocation**.

**The reinvestment rule.**

    tomorrow = base_allocation + reinvest_gains_pct% × cumulative realized gains
    tomorrow = max(tomorrow, base_allocation × min_allocation_ratio)

With the defaults ($10,000 base, 50%, floor 0.5): after a cumulative +$200 the bot trades with $10,100; after a cumulative -$2,000 it trades with $9,000; it never goes below $5,000, so a bad streak shrinks it but cannot switch it off.

**Where to see it.** Ledger tab in the dashboard, or:
```bash
sqlite3 data/ridethewave.db "select date, trades, wins, realized_pnl, next_allocation from daily_ledger where run_id='live'"
```

**Backtests** use the same rule day by day, so multi-day backtests show the compounding effect.

**Code:** `src/ridethewave/portfolio/`.
