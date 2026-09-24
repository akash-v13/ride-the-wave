# 20 · Daily portfolio engine (research)

**What it is.** A second family of strategies beside the intraday ones: portfolios that are decided
once a day on the close, hold overnight for days to months, and may go short. The book's stock and
ETF chapters live here (momentum, residual momentum, mean reversion in three forms, alpha combo, low
volatility, multifactor, sector rotation with its MA-filter and dual-momentum variants, multi-asset
trend, ETF internal-bar-strength reversion, volatility targeting, the one/two/three moving-average
rules). They were first built in the owner's TraderPro project and re-implemented here on wide
pandas frames so a ten-year test takes seconds.

**How a strategy sees the world.** A `Window`: every symbol's adjusted open/high/low/close/volume up
to today's close, today's universe, the benchmark name and current holdings. It returns target
weights, a fraction of equity per symbol, negative for short. No I/O.

**How the replay works.** Weights decided on day t's close are filled at day t+1's open plus
slippage (5 bp), in whole shares. Equity is marked at every close. Positions that close or flip are
booked as round trips (for profit factor and hit rate); the curve statistics (CAGR, volatility,
Sharpe, max drawdown) are the ones to trust for a rebalanced portfolio. Every run also carries two
comparison curves: the benchmark (SPY) bought and held, and the universe held equal-weight, with an
information ratio and t-statistic against each and the excess return in each half of the period.

**Universes.** Named lists (TraderPro's 20 mega caps, the 11 sector ETFs, 8 asset-class ETFs) or a
point-in-time top-N by trailing dollar volume drawn from a pool, ranked each day from prior data.
Funds can be removed from a pool with the same name-based detector the intraday strategies use.

**Data.** Alpaca daily bars adjusted for splits and dividends, cached under the `sip-day-adj` tag;
`scripts/download_daily.py --adjust all` fills ten years for a symbol list or a named universe in a
handful of API calls. (Unadjusted bars make every split look like a crash, which is why TraderPro's
momentum numbers were too low.)

**Worked example.** Residual momentum, 20 mega caps, 2019 to July 2026: each day, regress each
stock's daily returns on SPY's over 126 days, sum the residuals excluding the last 10 days, buy the
top 30% equal-weight, sell the rest at the next open. CAGR 37.9%, Sharpe 1.43, max drawdown −32%,
790 round trips at 53% wins. Holding the same 20 names equal-weight: 28.7% and 1.37. The rule's
information ratio over that is +0.65 (t 1.8), positive in both halves. The universe is doing most
of the work. On point-in-time universes (research page, section 5) the rule adds nothing over holding
the universe, and the long-short versions lose: the engine's job today is to say so honestly.

**Commands.**

```bash
uv run python scripts/download_daily.py --start 2015-06-01 --end 2026-09-22 --universe traderpro --adjust all
uv run python scripts/run_daily_backtest.py --strategy residual_momentum --universe mega_caps_20 --start 2019-01-01 --end 2026-07-24
uv run python scripts/run_daily_backtest.py --strategy price_momentum --pit-top 100 --pool "$(cat data/research/daily/pool-top320-stocks.txt)" --start 2017-01-01 --end 2026-09-22 --save
```

`--save` stores the run in `backtest_runs` (feed `sip-day-adj`) with its equity curve.

**Not yet.** Live execution: these strategies need short selling and overnight holds in the
execution layer (the "daily slot"), which the intraday bot does not have. Until then this is a
research engine. Research page: `docs/research/2026-09-23-traderpro-extraction.md`.

**Code:** `src/ridethewave/daily/` (data, engine, strategies, universe); tests in
`tests/test_daily_engine.py`.
