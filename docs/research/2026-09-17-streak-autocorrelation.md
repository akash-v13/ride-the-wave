# Is the streak a signal? Autocorrelation and conditional-return test

**Prompted by** the reading of Dixon, Halperin & Bilokon ch. 6 and 8: before fitting any model, test whether the series has the structure the model assumes. Their protocol: stationarity (ADF), autocorrelation against the 99% white-noise band 2.58/√T, Ljung-Box on the result. Script: `scripts/diagnose_returns.py`.

**Data:** SIP 1-minute bars, 2026-06-01 to 09-16, 82 symbols (point-in-time top 50 per day), regular session, returns computed within session only. 1,487,603 bars.

## Autocorrelation of 1-minute returns

| Lag | 1 | 2 | 3 | 4 | 5 | 10 |
|---|---|---|---|---|---|---|
| Pooled ACF | -0.0009 | 0.0017 | 0.0061 | -0.0049 | 0.0022 | 0.0143 |

99% white-noise band: ±0.0021. Lags 1 and 2 are inside it. Per symbol, median lag-1 autocorrelation is -0.004 and 63% of symbols are negative, the signature of bid-ask bounce, not momentum. ADF rejects a unit root everywhere (returns are stationary). Ljung-Box finds weak structure in some names (ORCL, JPM) and none in NVDA.

## What happens after an up-streak (09:31 to 11:30 ET window)

Mean forward log-return in basis points:

| Condition | n | +1 min | +5 | +10 | +30 | +60 |
|---|---|---|---|---|---|---|
| Unconditional | 455,156 | 0.0 | -0.1 | -0.2 | -1.1 | -2.0 |
| Up-streak = 3 | 26,325 | +0.2 | +0.1 | +0.1 | -1.7 | -2.4 |
| Up-streak >= 5 | 11,964 | -0.3 | -0.7 | +1.0 | +0.5 | -4.3 |
| **Streak >= 3 and 3-bar gain >= 1% (our rule)** | 4,525 | +0.5 | +2.2 | +5.9 | +0.6 | **-10.7 ± 9.2** |

Probability the next bar is up: 0.49 unconditional, 0.51 after our rule.

## Reading

1. **One-minute returns are white noise at the lags the streak rule uses.** A streak of three up closes carries no information about the next hour; forward returns after it match the unconditional average.
2. **Our candidate rule shows a small continuation for about ten minutes** (about 6 basis points, below the 10 basis points of round-trip slippage we assume), **then reverses.** By 60 minutes the average candidate is down 10.7 basis points, and the confidence interval excludes zero. A 1% three-bar surge is, on average, followed by mean reversion, not by a wave.
3. **The strategy's thin profit therefore does not come from the trigger.** It comes from the three entry filters (which select a subset of surges that do continue) and from the asymmetric exit rule (which cuts most losers at 1% and lets the minority of winners run). Sweeping trigger parameters was never going to find much, which matches the sweep result.

## Consequences for the plan

- **The classifier's job is to find the continuation subset**, and the diagnostics say that subset is small. Expect a modest lift and treat any large one with suspicion.
- **The "enter on the first pullback" idea gains weight.** If surges mean-revert on average, buying the top of the surge is the worst moment; buying the retrace, in a stock that then resumes, is the natural fix. The dataset can test this without new downloads.
- **Longer bars deserve a test.** Momentum in equities is documented at horizons of weeks to months and, intraday, at tens of minutes rather than single minutes. Rerunning this diagnostic on 5- and 15-minute bars is a one-line change and tells us whether a slower streak is a signal at all.
- **The market gate is doing real work.** The one condition in the table with a positive, growing return is the candidate rule, and the filter analysis showed it only pays when SPY is up on the day. That is consistent with intraday momentum existing at the index level more than at the single-stock level.

Reproduce: `uv run python scripts/diagnose_returns.py --start 2026-06-01 --end 2026-09-16`.
