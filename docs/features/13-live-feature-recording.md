# 13 · Live feature recording

**What it does.** While the bot runs, every completed minute bar inside the entry window for every
stock in the universe is turned into the same feature row the research dataset uses (relative
volume, trade-count ratio, VWAP distance, session return, noise, SPY context, streak) and written to
the `features_live` table, flagged with whether the streak rule would have bought it. After the
close, the bot fetches the full session's IEX bars and labels each row with what happened next,
including the P/L our own exit rules would have produced.

**Why.** The research dataset is built from SIP data, which shows the whole market. The bot trades on
IEX, which shows a slice of it. Every paper day now produces labelled rows on the feed the bot really
sees, at zero cost, so the classifier can eventually be trained and checked on live-feed data.

**Where it shows up.** The heartbeat in the dashboard's Live tab carries `feature_rows` and
`feature_candidates` for the day. The log at shutdown prints how many rows were recorded and
labelled.

**Getting the data out.**
```bash
uv run python scripts/export_live_features.py            # -> data/features/live-iex.parquet
uv run python scripts/analyze_features.py data/features/live-iex.parquet
```
The parquet has the same columns as the research dataset, so every analysis script works on it.

**Safety.** Recording is wrapped so a failure is logged and skipped; it can never block a trade or a
tick. Rows are buffered and written 200 at a time. If the bot dies before the close, that day's rows
stay unlabelled and are exported with empty label columns.

**Settings.** None of its own; it reads the entry window and streak rule from `entry.*` and the
slippage from `backtest.slippage_pct`.

**Code:** `src/ridethewave/features/live.py`, `FeatureRepo` in `src/ridethewave/storage/repos.py`,
hooks in `src/ridethewave/runner.py`, `scripts/export_live_features.py`.
