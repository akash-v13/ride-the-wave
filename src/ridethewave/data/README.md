# data

Getting prices into the bot.

- `universe.py`: builds today's symbol list from the screener or a static list, filtered by the assets endpoint and a price band.
- `market_data.py`: `MarketData` interface with two implementations: `SnapshotPoller` (live, multi-symbol snapshots every N seconds) and `HistoricalReplay` (backtest, reads bars from cache/DB).
- `bars.py`: `Bar` model and `BarAggregator`, which turns snapshot ticks into completed one-minute bars and keeps a rolling window per symbol.
- `pit_universe.py`: point-in-time universe for backtests, ranked by trailing dollar volume from cached daily bars.
- `resample.py`: `Resampler`, rolls completed 1-minute bars into N-minute bars per symbol, anchored at 09:30 ET; used per strategy by the engine.
