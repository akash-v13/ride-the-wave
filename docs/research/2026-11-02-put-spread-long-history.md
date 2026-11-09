# The bull put spread over 36 years, 1990 to 2026: does `bps_spy` survive the crashes?

**Pre-registered 2 November 2026, before any result was computed.** Question 1b of the strategy
re-think (owner's go-ahead 2026-11-02). Code: `src/ridethewave/options/history_sim.py`,
`scripts/backtest_put_spread_history.py`, tests in `tests/test_put_spread_history.py`.

## Why this test

The shadow slot `bps_spy` sells a put about 5% below the S&P 500 and buys one about 10% below, about
35 days out, only when implied volatility is at least 3 points above the last 20 days' realised
volatility, and holds to the day before expiry. Its only evidence is the 2024-26 backtest on real
option prices (docs/research/2026-09-24-options-backtest.md): +28.8%, Sharpe 1.13, max drawdown
−7.2%, **20 trades in one bull market**. Selling puts is the strategy that looks best right up to the
crash it was never tested on. Before it gets any real weight, it has to be run through 1998, the
2000-02 bear market, 2008, the August 2011 and 2015 drops, February 2018, the fourth quarter of 2018,
March 2020 and 2022.

## Method (fixed before looking)

**No option prices before 2024 are in our data**, so each leg is priced with the project's
Black-Scholes code (`options/greeks.py`) on the S&P 500 close (Cboe), at an implied volatility read
off that day's VIX through a skew curve:

    IV(strike) / VIX = c0 + c1·z + c2·z²,   z = ln(strike / spot) / (VIX · √T)

`z` measures how far out of the money a strike is in units of the expected move, so one curve
serves every expiry and every level of volatility. The coefficients are fitted on the real SPY put
prices from the 2024-26 options backtest (Alpaca daily option bars, 20 to 50 days to expiry,
strikes from 15% below to 2% above the price). The gate's "ATM implied volatility" is the slot's own
measure (the mean of the six contracts nearest the price) divided by VIX on the same days, fitted the
same way. Calibration error is reported in volatility points and as an error on the entry credit.

**Rules: the production slot's, from `config/settings.yaml` → `bps_spy`.**
- Entry when flat, decided once a day at the close: the monthly expiry (third Friday) nearest 35
  days, inside 20 to 50 days; short put at 95% of the price, long put at 90%.
- Gate `vrp`: modelled ATM IV − 20-day realised volatility ≥ 3 points.
- Exits: the day before expiry (`close_dte 1`); profit target 100% of max profit; stop at a loss of
  10× the credit. Marked every day from the S&P close and VIX, so drawdowns inside a trade count.
- Sizing: the max loss of each spread is 20% of current equity (the slot's `risk_fraction`), in
  fractional units so a $20,000 slot is sized the same way at any index level. Start $20,000.
- Costs: the 2024-26 backtest's assumption: a modelled bid-ask spread of 3% of each option's price
  (at least the equivalent of $0.01 on SPY), paid in full on every leg in both directions.
- Cash: all of the slot's cash, including the collateral, earns the 3-month T-bill rate (FRED). The
  Sharpe ratio is on returns **in excess of T-bills**, so the interest does not flatter it.
- Dividends: a constant 1.8% yield in the pricing (the S&P's long-run average); the same constant is
  used in the calibration, so the convention cancels to first order.

**Configurations: five, all reported.** Base; skew slope and curvature ×0.75; ×1.25 (the 1990s skew
was steeper than today's, and its level is the biggest modelling unknown); gate off; costs ×3 (option
spreads before about 2008 were much wider than today's). Also reported, not counted as trials: the
same base rule with all capital as collateral (return on risk capital), and the synthetic model run
over February 2024 to September 2026 with the old backtest's settings, as a check against the real
chains.

**Pass/fail, decided now.**
1. Positive excess return in both halves, 1990-2007 and 2008-2026 (base).
2. Excess Sharpe ≥ 0.3 over 1990-2026 in the base **and** in both skew variants.
3. Maximum drawdown on the slot's capital no worse than half of the S&P 500's over the same years.
4. Deflated Sharpe probability ≥ 0.90 with the five trials counted (Bailey and López de Prado). The
   1990-2023 period is out of sample for this rule: it was chosen in September 2026 from 144
   configurations run on 2024-26 only.

All four pass: recommend live paper trading at the tested size. 1 to 3 pass: keep in shadow, accept
it as a portfolio sleeve with the measured drawdown as its budget. 1 or 2 fails: reject.

**What this cannot show.** Prices are modelled, not traded: a skew curve fitted on 2024-26 is an
assumption for 1990, and the ±25% variants bound it rather than remove it. Closing prices only, so a
fill at the 15:40 decision is approximated by the close. No early assignment. SPX options are
European and cash-settled, SPY's are American; the difference is small for out-of-the-money puts held
to the day before expiry.

## Results (run 2 November 2026)

Full output: `data/research/put_spread_history/report.md`, per-configuration statistics `summary.csv`,
the base configuration's 266 trades `trades_base.csv`. Re-run with
`uv run python scripts/backtest_put_spread_history.py` (about 15 seconds).

### Calibration: how well VIX plus a skew curve prices real SPY puts

- 55,360 SPY put closes on 628 days (February 2024 to September 2026), 20 to 50 days out, strikes 85%
  to 102% of the price.
- Fitted curve: **IV / VIX = 0.834 − 0.254·z + 0.008·z²**. At 35 days with VIX at 18, the 95% put is
  priced at 1.07 × VIX and the 90% put at 1.34 × VIX: the further out, the dearer per unit of risk.
- The slot's "ATM implied vol" is 0.844 × VIX (median; middle half 0.820 to 0.869).
- Error: 0.86 volatility points root-mean-square over all strikes, 0.72 at 5% out, 0.77 at 10% out,
  no bias. On the thing that matters, the credit of the 95/90 spread at entry: median error +3.1%,
  mean absolute error 11%, correlation 0.96 with the real credit over 628 days.

**The model against the real chains**, same rules, same months, same sizing, no interest:

| | Return | Sharpe | Max DD | Trades | Win |
| --- | --- | --- | --- | --- | --- |
| Model (S&P 500 + VIX) | +35.2% | 1.21 | −9.9% | 20 | 95% |
| Real SPY chains (the September backtest) | +28.8% | 1.13 | −7.2% | 20 | 95% |

13 of the 20 entry days coincide; the gate sits near its threshold, so a volatility point either way
moves an entry by a few days. The model is slightly generous to the strategy, so the long history is
if anything flattered.

### 1990 to 2026, the five configurations

Sharpe and Sortino on returns in excess of T-bills. "In market": share of days with a spread open.

| Configuration | CAGR | Over T-bills | Vol | Sharpe | Sortino | Max DD | Deepest drawdown | Worst month | Months up | Trades | Win | PF | In market |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Base** | +5.3% | +2.4% | 12.8% | **0.25** | 0.33 | **−52.2%** | Sep 2000 → Oct 2002 | −20.5% (Aug 2011) | 86% | 266 | 90% | 1.36 | 64% |
| Skew ×0.75 | +5.7% | +2.8% | 13.1% | 0.27 | 0.36 | −51.1% | Sep 2000 → Oct 2002 | −20.4% (Aug 2011) | 86% | 266 | 90% | 1.42 | 64% |
| Skew ×1.25 | +4.5% | +1.6% | 12.4% | 0.19 | 0.25 | −52.0% | Sep 2000 → Oct 2002 | −20.5% (Aug 2011) | 86% | 267 | 90% | 1.24 | 65% |
| Gate off | +6.0% | +3.1% | 16.4% | 0.27 | 0.35 | −59.9% | Sep 2000 → Mar 2009 | −19.8% (Nov 2008) | 81% | 442 | 90% | 1.22 | 100% |
| Costs ×3 | +3.5% | +0.7% | 13.1% | 0.12 | 0.15 | −57.9% | Sep 2000 → Oct 2002 | −22.6% (Mar 2020) | 86% | 266 | 90% | 1.08 | 64% |
| _Base at 1× notional (5% risk), not a trial_ | +3.6% | +0.7% | 3.1% | 0.26 | 0.34 | −11.7% | Jun 2008 → Mar 2009 | −5.1% (Aug 2011) | 88% | 266 | 90% | 1.42 | 64% |
| US market, total return | +10.9% | +7.9% | 18.0% | 0.51 | 0.72 | −54.6% | Oct 2007 → Mar 2009 | −17.2% (Oct 2008) | 65% | | | | |

- Base: correlation with the US market 0.57 (daily), 0.53 (monthly), beta 0.41. The gate is open on
  34% of days. 263 of 266 exits are the day before expiry; the 10× stop fired 3 times.
- **Out of sample only, 1990-2023** (the rule was chosen on 2024-26): excess Sharpe **0.19**; the
  market's 0.48.
- Return on the capital at risk, per trade: mean +2.2%, median +6.4%, 5th percentile −36.8%, worst
  −110.6% (a full loss plus the cost of closing two deep-in-the-money legs).

**Halves (base).** 1990-2007: +7.1% a year, +2.7% over T-bills, Sharpe 0.28, max DD −52.2% (market
+10.5%, −49.2%). 2008-2026: +3.6%, +2.1%, Sharpe 0.22, max DD −42.6% (market +11.4%, −51.1%). At
1× notional: Sharpe 0.29 and 0.23, max DD −10.9% and −11.7%.

### Stress episodes (S&P 500 peak to trough)

| Episode | Window | Market | Base | Base drawdown inside | Gate off | Skew ×1.25 |
| --- | --- | --- | --- | --- | --- | --- |
| 1990 Gulf War | 17 Jul to 11 Oct 1990 | −20.8% | −17.4% | −19.4% | −18.6% | −17.2% |
| 1998 LTCM / Russia | 20 Jul to 8 Oct 1998 | −21.9% | −13.7% | −20.4% | −15.3% | −13.4% |
| 2000-02 bear market | Mar 2000 to Oct 2002 | −49.2% | **−49.0%** | −52.2% | −46.9% | −48.9% |
| 2007-09 financial crisis | Oct 2007 to Mar 2009 | −54.6% | −39.3% | −42.6% | −54.1% | −39.9% |
| Aug 2011 US downgrade | 25 Jul to 3 Oct 2011 | −19.3% | **−25.2%** | −25.2% | −25.3% | −24.9% |
| Aug 2015 yuan devaluation | 17 Aug to 29 Sep 2015 | −10.0% | +1.5% | −8.6% | −2.8% | +1.3% |
| Feb 2018 volatility spike | 29 Jan to 8 Feb 2018 | −9.8% | −9.5% | −9.5% | −9.5% | −9.1% |
| Q4 2018 sell-off | 21 Sep to 24 Dec 2018 | −20.4% | −4.1% | −7.9% | −23.6% | −4.1% |
| Mar 2020 Covid crash | 20 Feb to 23 Mar 2020 | −34.2% | −22.1% | −22.2% | −35.8% | −22.0% |
| 2022 bear market | 4 Jan to 12 Oct 2022 | −25.4% | −9.1% | −14.7% | −30.5% | −9.5% |
| Apr 2025 tariff drop | 20 Feb to 8 Apr 2025 | −19.6% | −3.5% | −9.7% | −21.7% | −3.3% |

The five deepest drawdowns of the base: Sep 2000 to Oct 2002, −52.2%, recovered Sep 2007; Jun 2008
to Mar 2009, −42.6%, recovered **Jul 2019**; Mar to Jun 2020, −23.8%; Jul to Aug 1998, −20.4%; Jul
to Aug 1990, −19.4%. The worst single spreads: Feb-Mar 2020 (−$16,974), Jan-Feb 2009, Jul-Aug 2011,
Feb-Mar 2001, Apr-May 2010 (the flash crash), Apr-May 2022, Aug-Sep 2001: each a full loss of 20% of
equity.

### Against Cboe's published option-strategy indexes

Total return, Sharpe on excess over T-bills, over the years each index has daily data.

| Index | Period | CAGR | Vol | Sharpe | Max DD | Base, same period: CAGR / Sharpe / Max DD |
| --- | --- | --- | --- | --- | --- | --- |
| PutWrite (one-month ATM put, fully collateralised) | 2007-2026 | +7.2% | 13.8% | 0.46 | −37.1% | +3.8% / 0.23 / −42.6% |
| Iron Condor | 1990-2026 | +5.0% | 7.3% | 0.33 | −19.7% | +5.3% / 0.25 / −52.2% |
| 5% Put Protection (long index, long put) | 1990-2026 | +7.5% | 13.4% | 0.40 | −42.0% | +5.3% / 0.25 / −52.2% |
| BuyWrite (covered call) | 2002-2026 | +6.2% | 13.7% | 0.38 | −40.1% | +4.4% / 0.27 / −42.6% |

### The pre-registered criteria

1. Positive excess return in both halves: **pass** (+2.7% and +2.1% a year).
2. Excess Sharpe ≥ 0.3 in the base and both skew variants: **fail** (0.25, 0.27, 0.19).
3. Max drawdown no worse than half the market's (−27.3%): **fail** (−52.2%).
4. Deflated Sharpe ≥ 0.90 with five trials: **fail** (0.847; the probability that the true Sharpe is
   above zero is 0.932; daily returns have skew −2.1 and kurtosis 63, the shape of a premium-selling
   strategy).

Configurations run: the five trials above, plus runs that are not strategy variants (the 2024-26
check, and sizing). One change from the pre-registration: the "all capital as collateral" run was
replaced, because with all capital at risk a single full loss empties the account (it did, in
2000-01), so the run says nothing about the rule. Return on risk is reported per trade instead, and
the 1× notional run was added.

## Reading

1. **The 2024-26 Sharpe of 1.1 was the bull market, not the rule.** Over 36 years the same rule
   earned 2.4% a year over T-bills at a Sharpe of 0.25, half the market's; 0.19 on the years it was
   not chosen on. Cboe's plain at-the-money PutWrite did better over 2007-2026 (0.46 against 0.23).
2. **It is not a diversifier.** It loses in the same crises as the market, and in a grinding bear
   market as much: −49% in 2000-02 (market −49%), −25% in August 2011 (market −19%). That is the
   failure the September page predicted: implied volatility stays above realised in a slow decline,
   so the gate keeps opening and each month's spread goes to its full loss. Correlation with the
   market is 0.57.
3. **The gate does what it was built for in fast crashes** (2008 −39% against −54% without it, Q4 2018
   −4% against −24%, 2020 −22% against −36%, 2022 −9% against −31%, 2025 −3.5% against −22%) **and
   nothing in slow ones** (1990, 1998, 2000-02, 2011, February 2018). Over the whole period it trades
   return for drawdown: Sharpe 0.25 with it, 0.27 without.
4. **The size sets the drawdown, not the quality.** Risking 20% of equity on a spread 5% wide is about
   four times the index notional, and the full loss arrives in any month the index falls about 10%.
   At one times notional (5% risk) the drawdown is −11.7% and the excess return 0.7% a year: the same
   Sharpe, a fifth of the pain.
5. **The long put is the expensive part.** A steeper skew (like the 1990s) lowers the Sharpe to 0.19,
   because the 10% put the spread buys is the most richly priced option on the curve; and wider
   option spreads (×3, closer to pre-2008 markets) take it to 0.12, so the 1990-2007 half is, if
   anything, flattered by the base costs.

## Verdict

**Reject as a strategy to promote.** Criterion 2 fails, and so do 3 and 4. `bps_spy` should not go
live and should not get more capital.

If it stays in shadow as an observation of a known premium: cut its risk from 20% to **5% of the slot
per spread** (one times notional) and **budget a −15% drawdown** for it (−11.7% measured at that size,
plus a margin for the skew and pre-2008 costs this model cannot pin down). At its current 20% the
honest budget is −55% to −60%, as deep as the market's own worst. `bps_qqq` runs the same rule; Cboe's
VXN (from 2001) would allow the same test, and nothing here suggests a different answer.

For combining sleeves: the base daily returns (gate on, 20% risk), 1990-01-03 to 2026-10-30, are in
`data/research/put_spread_history.parquet`, columns `ret` (on the slot's capital, T-bill interest
included) and `excess` (over T-bills). They scale close to linearly with the risk fraction.
