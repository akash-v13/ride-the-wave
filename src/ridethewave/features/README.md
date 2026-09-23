# features

Turning bars into numbers a filter or a model can use. Everything here is pure (lists in, dataclasses out).

- `compute.py`: `compute_features(bars, spy_bars, session_start)`: volume, trade-count, VWAP, range and market-context features for the latest bar of a symbol, using only that session's bars up to now.
- `labels.py`: what happened after a bar. `forward_outcome` gives max favourable / adverse excursion and "hit target before stop". `simulate_exit` replays the strategy's own exit rules from that bar and returns the P/L the bot would have made.
- `dataset.py`: walks cached history and writes one row per symbol per minute in the entry window (prospects), flagging which rows the current entry rule would have bought (candidates), with features and labels. Output is a Parquet file under `data/features/`.

The strategy imports `compute.py` so live entries and backtests use the identical feature code.
- `live.py`: `LiveFeatureRecorder`, records feature rows during a live session and labels them after the close from the day's IEX bars. Never raises into the trading loop.
