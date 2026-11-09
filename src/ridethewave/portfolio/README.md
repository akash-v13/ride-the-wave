# portfolio

Money management.

- `allocator.py`: computes today's allocation from the ledger and splits it into slots.
- `ledger.py`: end-of-day summary row (realized, unrealized, trades, wins, losses) and the reinvestment rule for tomorrow's allocation.
- `daily_slot.py`: a daily-bar portfolio slot (feature 21): target weights to whole-share fills, signed positions held overnight, persisted across restarts, ledger per slot; trades only every `rebalance_days` sessions and marks in between (since 2026-11-02). Each fill is stored with the bid and ask at that moment (`portfolio_fills`, since 2026-11-09). Shadow only.
