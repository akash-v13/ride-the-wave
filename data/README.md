# data

Runtime files. Everything here except this README is gitignored.

- `ridethewave.db`: SQLite database (bars, orders, trades, positions, ledger, backtests).
- `logs/`: daily log files from the bot and backtester.
- `cache/`: downloaded historical bars for backtests, so re-runs do not re-download.
- `external/`: free outside histories for research, one folder per source (`french/`, `cboe/`, `fred/`), written by `scripts/download_external.py` (feature 23).
- `research/trend/`, `research/sleeves/`, `research/put_spread_history*`: outputs of the 2026-11-02 sleeve studies (daily return series and result tables).
- `recordings/`: one parquet file a day of market state that cannot be looked up later (feature 25), written by `scripts/record_market_state.py` at 15:45 ET: `assets/<day>.parquet` (every active stock's shortable and easy-to-borrow flags) and `options/<day>.parquet` (quotes, implied volatility and greeks near the money for the stat-arb universe). Never replaced once written.
- `research/statarb/costs_*`: the 2026-11-09 cost study (the picks' move from the open to 09:35, and their quoted spreads on 90 sampled sessions).
