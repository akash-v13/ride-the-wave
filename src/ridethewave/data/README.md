# data

Getting prices into the bot.

- `universe.py`: builds today's symbol list from the screener or a static list, filtered by the assets endpoint and a price band.
- `assets.py`: reads Alpaca's asset list as raw JSON into `AssetInfo` rows. It does not use alpaca-py's strict models, so a new exchange code such as `TXSE` (2026-10-20) cannot break the whole list.
- `market_data.py`: `MarketData` interface with two implementations: `SnapshotPoller` (live, multi-symbol snapshots every N seconds) and `HistoricalReplay` (backtest, reads bars from cache/DB).
- `bars.py`: `Bar` model and `BarAggregator`, which turns snapshot ticks into completed one-minute bars and keeps a rolling window per symbol.
- `pit_universe.py`: point-in-time universe for backtests, ranked by trailing dollar volume from cached daily bars.
- `resample.py`: `Resampler`, rolls completed 1-minute bars into N-minute bars per symbol, anchored at 09:30 ET; used per strategy by the engine.
- `delistings.py`: which stocks stopped trading and when (2026-11-09): Massive's list of delisted tickers read once as a backfill, our own record from two days of saved asset lists (`left_the_list`), and a check that keeps a ticker change from being counted as a second company.
- `recordings.py`: the daily recordings of borrow flags and option quotes (feature 25): which monthly expiries, one row per contract as the feed sent it, and day files that are written whole and never replaced.
- `external.py`: free outside histories for research (Ken French factors from 1926, Cboe S&P 500 / VIX / option-strategy indexes, FRED Treasury yields and T-bills): dataset registry, download, parsers, and derived series (US market total return, a 10-year Treasury rebuilt from its yield, cash). The bot never trades on these. (feature 23)
