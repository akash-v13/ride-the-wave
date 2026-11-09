# Statistical arbitrage, stage 2a: residual reversal only in volatile markets, as a tradable rule

**Run 2 November 2026, evening.** The owner expects a volatile week (US midterm elections on 3
November, war news, AI listings) and asked whether stat arb can use it. The only lead is stage 1's
finding (docs/research/2026-11-02-statarb-stage1.md): with VIX ≥ 20, the 5-day residual reversal
earned +51 bp per round trip (t 2.6), and on calm days nothing. That was a diagnostic. This page
turns it into a rule the bot can follow and tests it with costs, *before* anything trades, even
in simulation. Code: `src/ridethewave/daily/statarb.py`, `scripts/research_statarb_volgated.py`.
Results: `data/research/statarb/`.

**A point fixed before anything else.** The strategy does not bet on the owner's forecast. It
switches itself on only when VIX already shows stress, and stays in cash otherwise. If the week is as
volatile as expected it will trade; if not, it will not. VIX closed at 19.42 on Friday 30 October,
just under the line.

## 1. What was fixed before running

**Same universe and residuals as stage 1:**
- each month, the 300 most-traded company stocks, point-in-time and survivorship-free;
- residuals after SPY and each stock's sector ETF, with 60-session betas.

**Timing, chosen so the bot can follow it exactly.** On each session *d*:

1. **Gate.** VIX closed at 20 or above on the previous session. Cboe publishes the close after the
   market shuts, so today's close cannot be used.
2. **Signal.** Each stock's residuals summed over the 5 sessions up to *yesterday's* close.
3. **Cohort.** If the gate is open, a new cohort is formed:
   - buy the fifth of the universe with the most negative signal, short the fifth with the most
     positive, equal weights;
   - each side is 20% of capital, so five cohorts at once make 100% long and 100% short;
   - the market and sector betas are hedged with SPY and the sector ETFs.
4. **Entry and exit.** Enter at the open of *d* (live: the 09:35 decision). Exit at the open of
   *d*+5, when that cohort's slot comes round again.
5. **Costs:**
   - 5 bp on every stock trade: buy, sell, short and cover, so 20 bp per round trip on the cohort's
     capital;
   - 5 bp per round trip for the ETF hedges;
   - borrow at 0.5% a year on the short side, about 1 bp per cohort.
   - In all, 26 bp per cohort round trip.

**Return per cohort:** (the long fifth's hedged return minus the short fifth's) − 0.26%, earned on
20% of capital.

**Two configurations, both counted:**
- **A, base:** the rule above.
- **B, news-jump filter:** before ranking, drop any stock whose 5-day residual is more than 3 times
  its normal 5-day residual size (60-session residual volatility × √5). Big jumps are usually news
  such as earnings, and news-driven moves tend to continue rather than reverse (our own
  post-earnings study; Chan 2003). This week is the middle of earnings season.

**What passes:** profitable after costs in **both** halves (2017-2021 and 2022-2026), as stage 1's
page committed. Also reported, though not part of the test:
- the t-statistic;
- return, volatility and Sharpe on capital;
- the share of time invested;
- the worst cohort and the worst month;
- the years.

**If it passes:** a shadow slot from the next session, nothing sent to Alpaca. One week is an
anecdote, not evidence. The live record only becomes evidence over many volatile weeks.

## 2. Results

From 3 January 2017 to 22 September 2026, 779 sessions opened the gate (VIX ≥ 20 the day
before). With five-day holds, the book was invested on 42% of days, with about 59 names a side
per cohort.

| Configuration | Net per cohort (gross) | t | Hit rate | 2017-2021 / 2022-2026 | Return on capital a year | Volatility | Sharpe | Max drawdown |
|---|---|---|---|---|---|---|---|---|
| **A, base** | **+29.7 bp** (+55.7) | 1.5 | 51% | +37.4 / +22.3 bp | **+4.3%** | 9.0% | **0.48** | −11.2% |
| B, news-jump filter | +21.5 bp (+47.5) | 1.2 | 51% | +23.7 / +19.4 bp | +3.1% | 8.0% | 0.39 | −14.4% |

**Both pass** the test fixed in advance: profitable after costs in both halves.

**The base rule, year by year** (return on capital; 2017 had no cohorts, as VIX never closed at 20):

| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 to Sep |
|---|---|---|---|---|---|---|---|---|
| +4.0% (58 cohorts) | −1.1% (16) | **+33.8%** (217) | −7.9% (93) | +0.8% (227) | +1.3% (43) | −0.7% (25) | **+14.8%** (63) | +1.4% (37) |

Worst month: −5.0% (October 2022). Worst single cohort: −11.9% (formed 1 March 2021, the
growth-to-value rotation).

**The live rule matches the backtest.** On 9 April 2025, `cohort_targets` (the function the slot
calls) rebuilt from a window of completed sessions picked exactly the same 60 longs and 60 shorts
as the backtest. Net stock weight was zero, gross 40%, and the ETF hedges were small (SPY +8.6%,
XLK +10.6%).

## 3. Reading and verdict

1. **It passes, but the evidence is thin.**
   - t is 1.5 after costs.
   - It was chosen from 18 looks in stage 1.
   - Two episodes did most of the work: the 2020 crash and rebound, and the April 2025 tariff drop
     and rebound.
   - In the slow 2022 bear market, 227 cohorts made almost nothing, and 2021's rotation lost 7.9%.
2. **It pays in sharp shocks that reverse.** Volatility spikes, prices dislocate stock by stock,
   and dealers pull back, so whoever supplies liquidity is paid to wait a week. That is the opposite
   of trend following, which paid in the slow 2022 decline and lost in April 2025. The two could
   complement each other in a combined book. That has not been tested.
3. **The news-jump filter made it worse.** In stressed markets the biggest dislocations reverted
   too. The base rule is kept.
4. **What it cannot do.**
   - It does not predict volatility; it waits for VIX to show it.
   - It cannot trade new listings, which have no history.
   - Its hedges are set once a day from 60-session betas. In a crash, when stocks suddenly move more
     with the market than they did, some market exposure is left over until the next day's hedge.

**Verdict:**
- **Shadow slot `sa_volrev`** from 3 November 2026: decision at 09:35 ET, $500,000 simulated, the base
  rule, idle while VIX is below 20. Nothing reaches Alpaca.
- **The live universe differs from the backtest:** it is the 254 most-traded stocks fixed in
  September, not a monthly top 300. Close enough to observe.
- **The live record becomes evidence only after many volatile weeks.** One week is an anecdote.
