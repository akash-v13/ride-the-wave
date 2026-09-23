# SPY market intraday momentum: does the first half-hour predict the last?

**Claim tested.** Gao, Han, Li and Zhou (*Journal of Financial Economics*, 2018) reported that the
first half-hour return of the S&P 500 ETF predicts the last half-hour return, using data from 1993
to 2013. It was candidate 1 on the roadmap because it needs no stock selection and trades the most
liquid instrument there is.

**Data.** SPY 1-minute SIP bars, 2016-01-04 to 2026-09-16 (1,048,378 bars, 2,681 trading days).
`r_first` = close of the 09:59 bar over the 09:30 open, minus one. `r_last` = last close of the day
over the price at 15:30, minus one. Script: `scripts/study_spy_intraday.py`; per-day table saved to
`data/research/spy_intraday_daily.parquet`.

## Result: the effect is not present in this period

| Measure | Value |
|---|---|
| Correlation of `r_last` with `r_first` | -0.054 (t ≈ -2.8) |
| Sign agreement | 48.7% (50% is nothing) |
| Mean `r_last` after an up first half-hour | -1.1 bp (n = 1,392) |
| Mean `r_last` after a down first half-hour | +0.2 bp (n = 1,277) |
| Regression with the paper's second predictor (previous day's last half-hour) | b1 -0.048, b2 -0.100, R² 0.013 |
| High-volatility days only (\|r_first\| > 30 bp, n = 584) | correlation -0.068, agreement 47.9% |

By year the correlation is negative in eight of eleven years, and the sign agreement never exceeds
53%. Both halves of the period agree (first half correlation -0.061, second -0.046).

Trading it long-only with SPY on up days and SH (the inverse ETF) on down days, at 1 bp round-trip
cost:

| Threshold on \|r_first\| | Trades | Mean per trade | Win rate | Annualised Sharpe | Total | Max drawdown |
|---|---|---|---|---|---|---|
| any | 2,669 | -1.7 bp | 46.8% | -0.85 | -36.6% | -37.7% |
| 10 bp | 1,735 | -2.3 bp | 46.6% | -1.04 | -33.1% | -34.1% |
| 30 bp | 584 | -2.7 bp | 47.1% | -0.85 | -15.0% | -19.1% |
| 50 bp | 214 | -5.0 bp | 45.8% | -1.12 | -10.6% | -15.9% |

Fading the signal instead (contrarian) makes -0.3 bp a day after costs: the reversal is real but
too small to trade.

## Reading

1. A published anomaly from 1993 to 2013 is absent, and slightly reversed, in 2016 to 2026. This is
   the textbook case the modelling skill warns about: an effect documented in one period does not
   carry a warranty. Verifying before building was the right order and cost one script.
2. The direction of the reversal (a strong open tends to fade into the close) is consistent with
   the end-of-day rebalancing flows that grew after the paper's sample; it is not exploitable at
   our cost assumptions.
3. **Decision:** the `spy_intraday` strategy stays in the code as the first market-timing template
   and is disabled in settings. It does not enter incubation.

## Follow-ups worth a look, not yet done

- The same test on QQQ and IWM (one line each).
- Conditioning on the previous day's move plus overnight gap, which later papers report as the
  stronger predictor.
- The last-half-hour behaviour on the weeks of index rebalances and options expiry, where the flows
  are largest.
