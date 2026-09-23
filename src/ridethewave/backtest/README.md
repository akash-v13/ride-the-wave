# backtest

Replay past days through the live code path.

- `engine.py`: `ReplayEngine` loads bars for a universe and date range and drives `BarAggregator` → `Strategy` → `OrderManager` minute by minute.
- `sim_broker.py`: `SimBroker`, fills at next bar open plus slippage, tracks cash and positions, honours safety stops.
- `report.py`: per-trade table, per-day summary, equity curve, and a plain-English verdict. Stores results in `backtest_runs` / `backtest_trades`.
- `data_loader.py`: downloads and caches historical bars (SIP and IEX) under `data/cache/`.
