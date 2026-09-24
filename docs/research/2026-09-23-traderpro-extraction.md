# What TraderPro had, what it found, and what was carried into Ride The Wave

**Written 23 September 2026.** TraderPro (`../TraderPro`, July 2026, 22 commits, ~10k lines of
Python plus a React dashboard) is the owner's earlier platform: many bots on Alpaca's free tier,
85 of the 151 book strategies registered, its own daily-bar backtester, an options engine, a
regime-and-sentiment selector. This page records what it contains, what its results actually
say once re-run on adjusted data with a benchmark, and what was ported. Companion: the daily
research engine in `src/ridethewave/daily/` (feature 20).

## 1. Inventory

| Area | What is there | Verdict for Ride The Wave |
| --- | --- | --- |
| Strategies (28 daily-bar classes) | §3.1 momentum, §3.4 low vol, §3.6 multifactor, §3.7 residual momentum, §3.8 pairs, §3.9/3.9.1/3.10 mean reversion, §3.11 to 3.15 MA / channel / support-resistance, §3.17 KNN, §3.20 alpha combo, §4.1 sector rotation (+MA filter, dual momentum), §4.2/4.3 alpha and R² rotation, §4.4 ETF IBS reversion, §4.5 leveraged-ETF decay, §4.6 multi-asset trend, §6.5 vol targeting, §7.3 VXX/SVXY carry, §18.3 news momentum; §3.2/3.3 need yfinance fundamentals | **Ported the 13 price-only ones** as `daily/strategies.py`; fundamentals-based, options-based and yfinance-dependent ones not |
| Backtester | Signals on the close, fills next open + 5 bp, whole shares, target-percent of equity, daily evaluation, CAGR/Sharpe/Sortino/DD | Re-implemented on wide frames with what it lacked: benchmark and equal-weight-universe curves, information ratio with t-stat, split halves, profit factor, turnover, shorts, point-in-time universes |
| Data | Alpaca daily bars **unadjusted** for the live path, yfinance (adjusted) as fallback; parquet cache with atomic writes; 16-minute SIP clamp | We have Algo Trader Plus: adjusted daily bars straight from Alpaca (`sip-day-adj` tag, `scripts/download_daily.py`). The unadjusted data explains its lower momentum numbers (a 10-for-1 split reads as a −90% day) |
| Options engine | 57 declarative leg templates, own Black-Scholes and IV, chain resolver, lifecycle (DTE-first, profit target, stop), Alpaca multi-leg orders; 40 placeable, 17 sim-only (naked short legs) | Not ported yet. The template + resolver + lifecycle design is sound and self-contained; needs our own chain data path. Roadmap |
| Selector | Regime features (SPY vs 50/200-day, 3-month return and drawdown, 20-day realised vol, VIX and VIX term ratio, sector breadth), a rule-tree classifier (crisis / bear / chop / bull / range), a scorer (0.2 regime fit + 0.35 backtest + 0.35 live P&L + 0.1 sentiment), an allocator (top 3, 45% floor, 50% cap), pending-approval runs | Port the features and classifier (pure functions); the scorer's weights were an owner directive ("P&L is king", 23 July) and need re-deciding; the allocator's constants were hard-coded |
| Sentiment | Claude Haiku with a forced tool schema, VADER fallback, event tagger, impact-weighted 24 h aggregate | We already run Jev for headline scoring; the aggregate and event-tag ideas transfer |
| Catalog | `strategies.yaml`: all 176 book entries with status, direction, typical universe, honest caveats and a 5-regime fitness prior | Port as data (it is the knowledge base a selector needs) |
| Bots and risk | APScheduler cron schedules (15-min, hourly, `daily_close` at 15:50 ET), target-percent to order translation with a 1%-of-capital dead band, order guard (spread, notional, duplicates), sticky kill switch, 5% daily-loss halt, FIFO P&L with an options multiplier | Ideas match what Ride The Wave already has; the dead band and the 15:50 daily decision are the pieces the daily slot needs |
| UI | React + lightweight-charts: leaderboard, "why did it trade" disclosure on fills, health strip with a two-step kill switch, regime heat strip | Patterns for the TypeScript UI |

Known defects noted for the record: the strategy sizing hooks and per-leg multi-leg fills never
reached its fills table; the allocator keyed capital by strategy key so the three sector-rotation
entries collided; "resize" proposals were never applied; SimBroker had no margin check on shorts.

## 2. What TraderPro recorded (its own engine, 2019-01-01 to 2026-07-24, its 20 mega caps)

| Strategy | Return | CAGR | Sharpe | Max DD | Trades |
| --- | --- | --- | --- | --- | --- |
| residual_momentum | +473.6% | 26.1% | 1.01 | −32.9% | 746 |
| mean_reversion_multi | +349.0% | 22.0% | 0.90 | −37.6% | 1,562 |
| price_momentum (231/21/0.25) | +274.5% | 19.1% | 0.74 | −40.9% | 422 |
| mean_reversion_weighted | +242.9% | 17.8% | 0.83 | −33.1% | 1,710 |
| alpha_combo | +189.7% | 15.2% | 0.71 | −33.1% | 2,586 |
| vol_targeting (SPY) | +149.9% | 12.9% | 0.97 | −18.5% | 0 |
| low_volatility | +107.4% | 10.2% | 0.67 | −20.0% | 384 |
| etf_mean_reversion (11 sectors) | +59.0% | 6.3% | 0.39 | −46.1% | 1,433 |
| multi_asset_trend | +37.5% | 4.3% | 0.50 | −22.4% | 158 |
| r_squared_rotation | −22.5% | −3.3% | −0.05 | −45.1% | 358 |
| letf_decay (short TQQQ and SQQQ) | −100% | | | −100% | 46 |

No benchmark was recorded next to any of these. Its universe was the 20 largest US companies
*of July 2026* (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AVGO, LLY, JPM, V, UNH, XOM, MA, HD, PG,
COST, JNJ, ABBV, WMT): the winners of the very period being tested.

## 3. Replication on the new engine (adjusted data, same universe and period)

| Strategy | Ours: CAGR / Sharpe / DD | TraderPro | vs SPY (17.2%): IR, t | vs equal-weight universe (28.7%, Sharpe 1.37): IR, t | Excess CAGR vs EW by half |
| --- | --- | --- | --- | --- | --- |
| residual_momentum | 37.9% / 1.43 / −31.9% | 26.1% / 1.01 | +1.21, 3.3 | **+0.65, 1.8** | +12.5% / +5.9% |
| price_momentum | 37.0% / 1.26 / −37.6% | 19.1% / 0.74 | +1.03, 2.8 | +0.52, 1.4 | +7.3% / +9.5% |
| mean_reversion_multi | 28.4% / 1.13 / −37.9% | 22.0% / 0.90 | +0.72, 2.0 | +0.07, 0.2 | −1.1% / +0.4% |
| mean_reversion_weighted | 21.7% / 0.98 / −33.4% | 17.8% / 0.83 | +0.36, 1.0 | −0.44, −1.2 | −5.3% / −8.8% |
| alpha_combo | 22.2% / 1.02 / −32.4% | 15.2% / 0.71 | +0.38, 1.0 | −0.40, −1.1 | −1.9% / −11.1% |
| low_volatility | 16.2% / 1.03 / −19.8% | 10.2% / 0.67 | −0.10, −0.3 | −0.83, −2.3 | −9.9% / −15.2% |

Three things to read off this table.

1. **The ranking replicates; the levels do not, and ours are the right ones.** Every strategy
   scores higher here because TraderPro fed its momentum rules unadjusted Alpaca prices: NVDA, AVGO,
   WMT, GOOGL, AMZN and TSLA all split inside the window and each split looked like a crash.
2. **Most of the return is the universe, not the rule.** Holding the 20 names equal-weight earned
   28.7% a year with a Sharpe of 1.37. Against that benchmark, mean reversion in all its forms adds
   nothing or subtracts, low volatility subtracts a lot, and only the two momentum rankings add
   (6 to 12 points of CAGR a year, positive in both halves, t-statistics 1.4 to 1.8: suggestive,
   not conclusive).
3. **Profit factor on round trips is not the right lens for a rebalanced portfolio.** Momentum's
   PF of 1.5 on 790 trades understates a curve that compounds at 38%; the multi-asset trend rule
   shows PF 0.04 while earning 6% a year, because its many small trims book as losses while the
   gains sit in positions that never fully close. Read the curve statistics and the IR.

## 4. ETF and index rules, 2017-01-01 to 2026-09-22 (SPY: 15.3% CAGR, Sharpe 0.89, max DD −33.8%)

| Strategy | CAGR | Sharpe | Max DD | IR vs SPY (t) |
| --- | --- | --- | --- | --- |
| sector_rotation §4.1 (top 3 of 11, 6-month) | 10.5% | 0.66 | −32.3% | −0.44 (−1.4) |
| + 150-day MA filter §4.1.1 | 5.2% | 0.39 | −33.0% | −0.69 (−2.2) |
| + dual momentum §4.1.2 (SPY > 200-day else IEF) | 6.0% | 0.50 | −23.8% | −0.56 (−1.8) |
| multi_asset_trend §4.6 (defaults) | 6.4% | 0.73 | −14.1% | −0.55 (−1.7) |
| multi_asset_trend, 12-month, momentum/σ weights | 9.1% | 0.91 | −18.1% | −0.40 (−1.2) |
| ibs_mean_reversion §4.4 on sectors | −0.9% | 0.05 | −43.7% | −1.51 (−4.7) |
| vol_targeting §6.5 on SPY (15% target) | 12.6% | **0.99** | **−19.4%** | −0.40 (−1.2) |
| ma_rule SPY 20/50 §3.12 | 9.5% | 0.84 | −28.1% | −0.45 (−1.4) |
| ma_rule SPY price vs 200-day §3.11 | 10.7% | 0.90 | **−19.5%** | −0.37 (−1.2) |
| ma_rule QQQ 3/10/21 §3.13 | 4.7% | 0.57 | −15.1% | −0.69 (−2.2) |

Nothing beats holding SPY on return in a decade that rewarded holding SPY; volatility targeting and
the 200-day rule buy a much smaller drawdown for about 3 to 5 points of CAGR, which is what the
literature says they do. The daily IBS reversion on sector ETFs is a transaction-cost machine
(turnover 1.4 per day) and loses.

## 5. Point-in-time stock universes (the honest test)

_Universe = top 50 or top 100 of a 254-stock pool by trailing 20-day dollar volume, ranked each day
from prior data only; pool = today's top 320 names by dollar volume minus funds (survivorship
remains at the pool level, ranking is point-in-time). 2017-01-01 to 2026-09-22. Filled in below._

| Strategy (universe) | CAGR | Sharpe | Max DD | vs SPY: IR (t) | vs equal-weight universe (27.4%, Sharpe 1.24): IR (t) | Excess vs EW by half |
| --- | --- | --- | --- | --- | --- | --- |
| residual_momentum (top 50) | 24.8% | 0.87 | −38.9% | +0.51 (1.6) | +0.02 (0.1) | −2.3% / −3.0% |
| residual_momentum (top 100) | 26.5% | 1.00 | −34.2% | +0.65 (2.0) | +0.04 (0.1) | +0.3% / −2.4% |
| residual_momentum long-short (top 100) | 1.7% | 0.21 | −22.9% | −0.63 | −0.98 | |
| price_momentum (top 50) | 27.0% | 0.89 | −38.9% | +0.58 (1.8) | +0.13 (0.4) | −2.9% / +2.1% |
| price_momentum (top 100) | 28.8% | 1.01 | −35.0% | +0.71 (2.2) | +0.18 (0.6) | +0.0% / +2.6% |
| price_momentum long-short (top 100) | 4.8% | 0.43 | −18.3% | −0.49 | −0.88 | |
| mean_reversion (top 50) | 15.0% | 0.63 | −45.1% | +0.13 (0.4) | −0.54 (−1.7) | −9.2% / −15.4% |
| mean_reversion long-short (top 100) | −3.1% | −0.24 | −36.8% | −0.98 | −1.35 | |
| mean_reversion_weighted (top 100) | 16.1% | 0.77 | −41.9% | +0.14 (0.4) | −0.80 (−2.5) | −13.2% / −9.1% |
| alpha_combo (top 100) | 23.0% | 1.05 | −33.8% | +0.64 (2.0) | −0.30 (−0.9) | −5.5% / −3.3% |
| low_volatility (top 100) | 12.0% | 0.86 | −28.9% | −0.40 (−1.2) | −1.06 (−3.3) | −13.3% / −17.1% |
| multifactor (top 100) | 14.5% | 0.91 | −30.7% | −0.12 (−0.4) | −1.00 (−3.1) | −13.2% / −12.4% |

**Reading.** Against SPY, long-only momentum looks excellent (t up to 2.2). Against the universe it
is drawn from, it is nothing: information ratios of 0.0 to 0.2, excess return that flips sign across
halves. Every mean-reversion, low-volatility and multifactor ranking is worse than holding the
universe. Every long-short construction, which is what the book actually describes, is flat or
negative after 5 bp a side: the spread between the top and bottom of these rankings does not pay
for its own trading. The 27.4% a year of the equal-weight universe is the survivorship of a pool
picked by today's dollar volume plus the fact that heavily traded names were the decade's winners;
it is not a strategy anyone could have chosen in 2017.

So the result that matters from the whole TraderPro exercise is negative and clear: **on the data
we have, none of the book's daily stock rankings adds return over its own universe, and the
dollar-neutral versions lose.** The two things that did something useful were risk controls
(volatility targeting, the 200-day rule: same Sharpe as SPY with half the drawdown).

## 5b. The same test on a survivorship-free universe ("started in January 2017")

Pool: every NYSE, Nasdaq and Arca stock Alpaca has ever listed, active or delisted (7,786 after
removing funds; 12.2 million daily bars since 2016 in `data/daily_panel/`, script
`scripts/download_universe_history.py`), filtered to names with a median price above $5 and median
dollar volume above $2 million (3,129 symbols). Universe: each month, the top 100 by trailing
20-day dollar volume using only prior data; 446 names were ever selected, 39 of them since
delisted. Replay 2017-01-01 to 2026-09-22, $100,000, next-open fills, 5 bp a side. Script:
`scripts/study_survivorship_free.py`; log `data/research/daily/survivorship-free.log`.

| Strategy | CAGR | Sharpe | Max DD | vs SPY (15.3%): IR (t) | vs equal-weight universe (22.4%, Sharpe 1.05): IR (t) | Excess vs EW by half |
| --- | --- | --- | --- | --- | --- | --- |
| price_momentum | 23.9% | 0.83 | −36.6% | +0.47 (1.5) | +0.18 (0.6) | −8.3% / +9.9% |
| price_momentum long-short | 4.7% | 0.39 | −18.9% | −0.45 | −0.65 | |
| residual_momentum | 20.7% | 0.78 | −43.9% | +0.36 (1.1) | +0.03 (0.1) | −7.7% / +3.1% |
| residual_momentum long-short | 2.1% | 0.23 | −23.3% | −0.58 | −0.76 | |
| alpha_combo | 18.0% | 0.81 | −33.8% | +0.25 (0.8) | −0.23 (−0.7) | −13.8% / +3.6% |
| mean_reversion | 12.1% | 0.53 | −51.1% | 0.00 (0.0) | −0.42 (−1.3) | −16.0% / −5.2% |
| mean_reversion long-short | −2.4% | −0.14 | −32.6% | −0.91 | −1.13 | |
| mean_reversion_weighted | 13.0% | 0.63 | −41.1% | −0.06 (−0.2) | −0.59 (−1.8) | −19.4% / −0.3% |
| low_volatility | 11.7% | 0.84 | −29.3% | −0.42 (−1.3) | −0.75 (−2.3) | −18.9% / −3.2% |
| multifactor | 14.7% | 0.90 | −29.3% | −0.09 (−0.3) | −0.57 (−1.8) | −18.9% / +2.7% |

Same picture as section 5, with the universe premium smaller once the dead names are back (22.4%
a year instead of 27.4%). No ranking beats holding its own universe with any statistical weight;
momentum's excess flips sign between halves; every long-short version is flat or negative. This is
the "if we had started in 2017" answer the owner asked for: the book's daily stock rankings, as
implemented in TraderPro, would not have paid for their own trading.

## 5c. Does a shorter window or a regime gate change the answer? (asked by the owner)

**2023-01-01 to 2026-09-22 only** (SPY 22.6% a year, equal-weight universe 25.5%, Sharpe 1.05):

| Strategy | CAGR | Sharpe | Max DD | vs SPY IR (t) | vs universe IR (t) |
| --- | --- | --- | --- | --- | --- |
| price_momentum | 40.6% | 1.12 | −34.9% | +0.69 (1.3) | +0.59 (1.1) |
| residual_momentum | 36.8% | 1.10 | −32.8% | +0.62 (1.2) | +0.52 (1.0) |
| alpha_combo | 28.0% | 1.20 | −22.0% | +0.39 (0.7) | +0.19 (0.4) |
| mean_reversion | 28.5% | 1.04 | −26.3% | +0.38 (0.7) | +0.25 (0.5) |
| multifactor | 18.6% | 1.33 | −16.7% | −0.44 | −0.52 |
| price_momentum long-short | 7.8% | 0.54 | −19.0% | −0.68 | −0.72 |
| residual_momentum long-short | 5.5% | 0.46 | −16.0% | −0.87 | −0.88 |
| mean_reversion long-short | −0.7% | 0.01 | −26.8% | −1.12 (−2.1) | −1.15 (−2.2) |

In the recent window long-only momentum beat its universe by about 15 points a year, but with
3.7 years of data the t-statistic is 1.0 to 1.1: the same size of effect as the second half of the
full run, and no more proof. A shorter window does not make an effect more real; it makes it
harder to distinguish from luck. The long-short versions lose in this window too.

**By market regime, 2017 to 2026**, using the ported classifier on prior data only (days: bull
trend 1,836, bear trend 251, high-volatility chop 231, low-volatility range 126, crisis 51).
Excess return over the equal-weight universe, annualised, with t:

| Strategy | bull trend | bear trend | chop, high vol | range, low vol | crisis |
| --- | --- | --- | --- | --- | --- |
| price_momentum | +2.9% (0.3) | +3.9% (0.2) | **+22.2% (1.0)** | −11.5% (−0.4) | −1.1% |
| residual_momentum | −2.8% (−0.4) | −2.5% (−0.2) | **+35.4% (1.6)** | −9.3% (−0.3) | +4.2% |
| alpha_combo | −4.1% (−0.8) | −2.5% | +2.5% | −7.4% | +8.3% |
| multifactor | −6.2% (−1.6) | −7.9% | −13.7% | −7.6% | −16.6% |
| price_momentum long-short | **−17.4% (−2.6)** | −11.8% | −22.6% | −20.5% | +12.4% |
| residual_momentum long-short | **−21.3% (−3.2)** | −17.3% | −18.2% | −17.0% | +17.2% |

Two readings. Momentum's whole edge over the universe sits in high-volatility chop, about 10% of
the days, at t 1.0 to 1.6: suggestive, and consistent with the literature that momentum pays in
dislocated markets, but not established. A gated version (momentum only when the classifier says
chop) is a legitimate experiment; expect a small effect. The only statistically strong result in
the table is negative: the short leg loses about 17 to 21 points a year in bull trends (t −2.6 and
−3.2). Whatever else is built, shorting the bottom of a momentum ranking in an uptrend is the thing
not to do.

## 5d. Correction (2026-09-24): the equal-weight benchmark was not point-in-time

The daily engine's "equal-weight universe" curve averaged the returns of **every name ever selected**
during the run, not the names in the universe on each day. A stock that entered the top 100 in 2024
because it had risen was counted from 2017. That is a hindsight benchmark and it made the universe look
better than any investor could have held. Fixed in `ridethewave/daily/engine.py` (each day's benchmark
return is the mean over the names in the universe at the previous close) with a regression test
(`test_equal_weight_benchmark_is_point_in_time`). Sections 3 and 4 used fixed lists and are unaffected;
sections 5, 5b and 5c are superseded by the tables below. Section 5 (the 320-name pool) also carries
pool-level survivorship and is not re-run.

**Survivorship-free, monthly point-in-time top 100, 2017-01-01 to 2026-09-22** (true universe: 16.8% a
year, Sharpe 0.80, max DD −38.8%; SPY 15.3%):

| Strategy | CAGR | vs universe IR (t) | Excess by half | Bull trend | High-vol chop |
| --- | --- | --- | --- | --- | --- |
| price_momentum | 23.9% | **+0.51 (1.6)** | **+5.0% / +8.9%** | +6.9% (1.1) | +27.8% (1.6) |
| residual_momentum | 20.7% | +0.35 (1.1) | +5.6% / +2.1% | +1.3% (0.2) | **+41.0% (2.4)** |
| alpha_combo | 18.0% | +0.12 (0.4) | −0.6% / +2.7% | 0.0% | +8.1% (0.6) |
| mean_reversion | 12.1% | −0.16 (−0.5) | −2.8% / −6.2% | −4.1% | 0.0% |
| mean_reversion_weighted | 13.0% | −0.25 (−0.8) | −6.2% / −1.2% | −4.1% | −0.8% |
| low_volatility | 11.7% | −0.39 (−1.2) | −5.6% / −4.2% | | |
| price_momentum long-short | 4.7% | −0.51 (−1.6) | −18.6% / −5.5% | −13.3% (−2.3) | −17.1% |
| residual_momentum long-short | 2.1% | −0.61 (−1.9) | −20.0% / −9.3% | −17.3% (−2.8) | −12.6% |
| mean_reversion long-short | −2.4% | −0.87 (−2.7) | −23.0% / −15.1% | −21.1% (−2.9) | −44.3% |

**2023-01-01 to 2026-09-22 only** (true universe 29.7%): price momentum 40.6%, IR +0.62 (t 1.2);
residual momentum 36.8%, IR +0.51 (t 1.0); every long-short version IR −1.0 to −1.2.

**What changes.** Long-only price momentum now clears two of the three gates in
`docs/strategy-intake.md` (IR above the universe ≥ 0.5, positive in both halves) and falls short on
the third (t 1.6 against 2). Residual momentum in high-volatility chop is the first result in the
project with t above 2, on 231 days. Nothing changes for the short side: shorting the bottom of these
rankings loses heavily in bull trends. Momentum long-only, optionally leaning harder into chop, is now
the leading daily candidate; the `pm_megacaps` shadow slot should move to the point-in-time universe.

## 6. What was ported, and what comes next

Ported today: the 13 price-only daily strategies, the backtester with honest benchmarks, the
adjusted daily data path, point-in-time universes, the long-range downloader. Not yet: live
execution of daily portfolios (needs short selling and overnight holds in the execution layer, the
"daily slot"), the regime classifier and catalog, the options engine, the UI patterns.

Also ported: the regime features and rule-tree classifier (`daily/regime.py`, pure functions with
reasons; VIX optional since Alpaca has no index symbols).

Order of work proposed, given the results: (1) a daily "portfolio slot" with short selling and
overnight holds, in shadow first, because it is the enabling piece for every dollar-neutral
strategy in the book and for the risk-control rules that did help; (2) a survivorship-free pool
(historical index membership or point-in-time listings) before trusting any long-only ranking; (3)
the regime classifier as a research gate over the intraday strategies; (4) the catalog as data;
(5) options once a chain data path exists.
