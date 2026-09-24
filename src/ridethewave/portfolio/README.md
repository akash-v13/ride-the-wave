# portfolio

Money management.

- `allocator.py`: computes today's allocation from the ledger and splits it into slots.
- `ledger.py`: end-of-day summary row (realized, unrealized, trades, wins, losses) and the reinvestment rule for tomorrow's allocation.
- `daily_slot.py`: a daily-bar portfolio slot (feature 21): target weights to whole-share fills, signed positions held overnight, persisted across restarts, ledger per slot. Shadow only.
