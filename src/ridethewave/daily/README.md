# src/ridethewave/daily

The daily-bar research engine: portfolio strategies that rebalance on daily closes, hold overnight and
may go short, replayed over ten years of adjusted daily bars in seconds. Ported from the owner's earlier
TraderPro project (docs/research/2026-09-23-traderpro-extraction.md) and made honest: every run reports
the benchmark, the equal-weight universe, split halves and an information ratio.

- `data.py`: load adjusted daily bars (`sip-day-adj`) from the SQLite cache into wide frames.
- `engine.py`: the replay (signals on the close, fills at the next open plus slippage), metrics.
- `strategies.py`: the strategy family (momentum, residual momentum, mean reversion, alpha combo, low
  volatility, sector rotation, multi-asset trend, ETF mean reversion, volatility targeting, MA rules),
  and `trend_following` (2026-11-02): long-short time-series momentum across asset classes, sized by
  volatility to a 10% book target. Its rule, `trend_weights`, is a plain function so the century test
  on outside data runs the same code (feature 23).
- `residuals.py`: residual returns for stat arb: each stock's sector ETF chosen monthly from prior data, rolling 60-session betas on SPY and the sector, residuals with lagged betas (2026-11-02). Pure.
- `costs.py`: cost measurements for the daily books (2026-11-09): time-weighted quoted half-spread from quotes, a stock's move from its opening trade to 09:35 from minute bars, and the long-minus-short hedged gap. Pure.
- `statarb.py`: the stat-arb cohort rules (signal, picks, equal-dollar weights, beta hedges) and `cohort_targets`, which rebuilds the live cohorts from history for the `statarb_vol_reversal` strategy. Pure. `statarb_data.py` loads the survivorship-free panel the studies share.
- `signals.py`: conditions and rankings of the shortlist signals (2026-11-10), pure: `turn_of_month` (last session of a month and the first three of the next), `sector_stress` (a sector's five-session move beyond the market against its own last year, judged on earlier days only), `momentum_12_1` as known the day before, and `mean_difference` (flagged days against the rest, Newey-West t).
  The shadow strategies built on them are in `strategies.py`: `overnight_momentum`, `statarb_sector_stress` (`statarb.sector_cohort_targets`), `turn_of_month` (docs/features/26-shortlist-shadow-slots.md).
- `universe.py`: named universes (including `trend_etfs_21`) and point-in-time top-N by dollar volume.

Strategies here are pure (no I/O): they see a `Window` of history and return target weights.
