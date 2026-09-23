# data

Runtime files. Everything here except this README is gitignored.

- `ridethewave.db`: SQLite database (bars, orders, trades, positions, ledger, backtests).
- `logs/`: daily log files from the bot and backtester.
- `cache/`: downloaded historical bars for backtests, so re-runs do not re-download.
