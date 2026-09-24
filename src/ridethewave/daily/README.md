# src/ridethewave/daily

The daily-bar research engine: portfolio strategies that rebalance on daily closes, hold overnight and
may go short, replayed over ten years of adjusted daily bars in seconds. Ported from the owner's earlier
TraderPro project (docs/research/2026-09-23-traderpro-extraction.md) and made honest: every run reports
the benchmark, the equal-weight universe, split halves and an information ratio.

- `data.py`: load adjusted daily bars (`sip-day-adj`) from the SQLite cache into wide frames.
- `engine.py`: the replay (signals on the close, fills at the next open plus slippage), metrics.
- `strategies.py`: the strategy family (momentum, residual momentum, mean reversion, alpha combo, low
  volatility, sector rotation, multi-asset trend, ETF mean reversion, volatility targeting, MA rules).
- `universe.py`: named universes and point-in-time top-N by dollar volume.

Strategies here are pure (no I/O): they see a `Window` of history and return target weights.
