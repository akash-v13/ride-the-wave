# 151 Trading Strategies (Kakushadze & Serur, 2018) against what Alpaca gives us

**Written 23 September 2026.** The owner added the SSRN paper (`docs/books/ssrn-3247865.pdf`, 361
pages, 20 chapters) and asked which of its strategies we can run with our Alpaca provisions, and to
have the feasible ones ready for the next session. This page is the map. Results of the strategies
built from it are in the last sections; the plain-English page for the new strategy family is
`docs/features/19-cross-sectional-daytrade.md`.

## What we can and cannot do on Alpaca today

| Provision | State | Consequence |
| --- | --- | --- |
| US stocks and ETFs, long | Yes (paper) | Every long-only equity and ETF strategy is in reach |
| Short selling | Alpaca paper allows it for shortable names; **our execution layer does not** (positions, ledger, brokers are long-only) | Every dollar-neutral construction runs as its long leg only until short support is built |
| Minute and daily bars, full tape (SIP) since 2016 | Yes (Algo Trader Plus) | Any price/volume signal, any horizon |
| Quotes (bid/ask) | Snapshot per poll (15 s) | Fine for limit pricing; no use for quote-driven arbitrage |
| News headlines | Yes (Benzinga via Alpaca) + Jev scoring | Sentiment features; validated 21 Sept: no intraday edge |
| Fundamentals (earnings, book value) | No | Earnings and value factors need an outside data source |
| Fama-French / Carhart factors | Not wired (free download from Ken French's site) | Residual momentum, alpha and R² rotation wait on that |
| Options | Alpaca trades them (paper too); data plan coverage to verify; nothing in our stack | Chapter 2 and the volatility chapter are a separate project |
| Futures, FX, bonds, swaps, credit, real assets | Not on Alpaca | Chapters 5, 8 to 17, 19 and 20 are out, except through ETFs |
| Overnight holds | Bot flattens at 15:55; nothing carries positions across days yet | Monthly-rebalance portfolios need a "daily portfolio" executor |

## Chapter by chapter

| Ch. | Topic | Numbered strategies | Verdict |
| --- | --- | --- | --- |
| 2 | Options (covered calls to seagull spreads) | 56 + 2 variants | **Not now.** Needs option chains, pricing and multi-leg orders in our stack |
| 3 | Stocks | 20 | **The chapter that matters.** Detail below |
| 4 | ETFs (sector rotation, alpha/R² rotation, IBS mean reversion, leveraged ETF decay, multi-asset trend) | 8 | Feasible with daily bars; needs overnight holds (4.1, 4.1.x, 4.6, 4.4), factors (4.2, 4.3) or shorts (4.5) |
| 5 | Fixed income | 14 | No (bonds); bond ETFs only as a portfolio ingredient |
| 6 | Index / ETF (cash-and-carry, dispersion, ETF arbitrage, vol targeting) | 5 | 6.5 vol targeting feasible (SPY + cash); the rest need futures, options or sub-second execution |
| 7 | Volatility (VIX futures basis, VXX carry, VRP, skew, variance swaps) | 7 | 7.3 needs shorting VXX; others need futures/options |
| 8 | FX | 6 | No FX on Alpaca |
| 9 | Commodities | 6 | Futures; commodity ETFs only as diversifiers |
| 10 | Futures | 4 | No |
| 11 to 17 | Structured credit, convertibles, tax arbitrage, misc., distressed, real estate, cash | 27 | No; REIT ETFs are the only touch point |
| 18 | Machine learning (ANN, naive-Bayes sentiment) | 2 | Research track (Dixon plan); Jev already covers sentiment |
| 19 | Global macro | 4 | 19.5 (trading on announcements) possible on SPY later |
| 20 | Infrastructure | 0 | Buy-and-hold, not for a bot |

## The stock chapter in detail

| § | Strategy | Data it needs | Our verdict |
| --- | --- | --- | --- |
| 3.1 | Price momentum (12-1 month, monthly rebalance) | Daily bars | Feasible as a long-only decile portfolio once overnight holds exist. Research queued |
| 3.2 | Earnings momentum (SUE) | Quarterly EPS | No data |
| 3.3 | Value (B/P) | Book value | No data |
| 3.4 | Low-volatility anomaly | Daily bars | Feasible, same executor as 3.1 |
| 3.5 | Implied volatility changes | Option IVs | No |
| 3.6 | Multifactor (rank averaging) | The factors above | Momentum + low-vol combination feasible later |
| 3.7 | Residual momentum | Fama-French factors | After the factor download |
| 3.8 | Pairs trading | Minute/daily bars, **shorts** | Long leg only is weak; wait for short selling |
| 3.9 | Mean reversion, single cluster | Bars | **Built (long leg), intraday version** |
| 3.9.1 / 3.10 | Multi-cluster / weighted regression | Industry map or statistical clusters | Universe demeaning today; clusters are the next refinement |
| 3.11 to 3.13 | One, two, three moving averages | Daily bars | Overnight holds; the paper itself calls single-stock TA "unscientific". Low priority |
| 3.14 | Support and resistance (pivot points) | Yesterday's H/L/C | Intraday version possible; overlaps ORB (feature 17) |
| 3.15 | Channel (Donchian) | Bars | Same family as ORB; parametrise ORB later |
| 3.16 | Merger arbitrage | Deal terms | No |
| 3.17 | Single-stock KNN | Bars | Research track, phase 13 plan |
| 3.18 | Statistical arbitrage with optimisation | Covariance model, shorts | After short selling; the optimiser is a day's work |
| 3.19 | Market making | Quote stream, speed | No |
| 3.20 | Alpha combos | Many alphas | The two Appendix-A alphas are built; combination rule implemented as a sum |

## What was built today: the cross-sectional day-trade family

`src/ridethewave/strategy/xs_daytrade.py`, registry name `xs_daytrade`. Once per session, on the
first completed bar at or after `entry_time` (default 09:35 ET), every stock in the universe with a
09:30 bar and yesterday's daily bar is scored with log returns demeaned across the universe:

| `signal` | Score | Book source |
| --- | --- | --- |
| `overnight_reversal` | −(r_on − mean), r_on = ln(open_today / close_yesterday) | Appendix A, "DELAY-0 MEAN-REVERSION" |
| `prev_day_momentum` | +(r_pd − mean), r_pd = ln(close_yesterday / open_yesterday) | Appendix A, "DELAY-1 MOMENTUM" |
| `intraday_reversal` | −(r_id − mean), r_id = ln(price_now / open_today) | 3.9 with t1 = open, t2 = now |
| `combo` | overnight_reversal + prev_day_momentum | 3.20, uniform weights |

The top `top_n` scores above `min_score_pct` are bought with equal dollars (or dollars proportional
to 1/σ, `weight_by: inv_vol`, σ from 20 daily returns), skipping names whose overnight move exceeds
`max_gap_pct` (earnings and news gaps, which the news study showed keep drifting). Each position
carries a hard stop `stop_pct` below entry, client-side and as a server-side stop leg, an optional
target, and is sold at `exit_time` (15:55). The book demeans within industry clusters and also
shorts the bottom of the ranking; we have neither industry data nor short selling, so this is the
long leg with universe demeaning. Worked example: 48 names scored at 09:35, mean overnight move
−0.4%; a stock that opened −2.9% scores +2.5% and is rank 1; with `min_score_pct: 0.5` it is bought
at the ask plus 0.1%, stop 3% below, sold at 15:55.

Two plumbing gaps found on the way, both fixed: the strategy sizing and stop hooks (`qty_for`,
`stops`) were never handed to the order manager by the runner or the backtester, so the ORB's ATR
stops had silently been the global 1% stop; and `scripts/run_backtest.py` gave strategies no daily
context (only the sweep script did).

## Gate 1 first: is there anything to predict?

`scripts/study_xs_signals.py` on 1 June to 16 September 2026, point-in-time top-50 company stocks
(3,746 stock-days, 75 days, 79 symbols). Forward return = 09:35 open to 15:55 close, SPY-adjusted;
quintiles formed each day on the demeaned score (Q5 = strongest buy); intervals from a day-block
bootstrap. Full tables: `data/research/xs-signals-diagnostic.md`.

| Score | Q5 (buy) bp | Q1 bp | Q5 − Q1 | Daily rank IC | t | Halves agree? |
| --- | --- | --- | --- | --- | --- | --- |
| Overnight reversal | −24.2 [−70.6, +18.6] | −7.5 | −16.7 | −0.018 | −0.44 | Q5 negative in both |
| Previous-day momentum | −37.0 [−79.6, +2.6] | −5.4 | −31.6 | −0.030 | −0.92 | Q5 negative in both |
| Intraday reversal at 10:30 | −21.2 [−56.3, +11.1] | −19.2 | −2.0 | +0.009 | +0.27 | no pattern |

Nothing passes. The buy quintile is the worst-performing one for the two Appendix-A alphas, and no
rank correlation is distinguishable from zero. The sample itself drifted down between the open and
the close: −15.8 bp a day raw across all stock-days, SPY −5.8 bp a day. By raw overnight gap, no
bucket has a forward return whose interval excludes zero; gaps beyond −3% keep drifting lower
(−21 to −37 bp vs SPY), consistent with the news study.

The one pocket worth remembering: the Q5 − Q1 spread of previous-day momentum is −32 bp a day,
i.e. buying yesterday's intraday losers *and shorting yesterday's winners* would have earned about
that gross. The long leg alone is −5 bp; the money is on the short side. Not significant (t −0.9),
but it is the sort of thing the book's dollar-neutral construction is built to capture.

## Backtests

Same 75 days, point-in-time top 50, full tape, next-bar fills, 0.05% slippage, five slots of 10% of
a $10,000 allocation. Logs under `data/sweeps/xs-*.log`.

**Signal by entry time** (funds included, 3% stop, 8% gap cap, 0.5% threshold):

| Signal | 09:31 | 09:35 | 10:00 | 10:30 |
| --- | --- | --- | --- | --- |
| overnight_reversal | 0.87 (274) | 0.80 (301) | 0.78 (314) | 0.61 (322) |
| prev_day_momentum | 0.72 (291) | 0.66 (311) | 0.60 (316) | 0.71 (325) |
| intraday_reversal | 0.52 (282) | 0.63 (286) | 0.66 (298) | 0.89 (328) |
| combo | **0.90** (291) | 0.87 (298) | 0.72 (309) | 0.73 (331) |

Profit factor (trades). Stocks-only made the overnight reversal worse (0.63 on 311 trades at 09:35).
Exit breakdown of the 09:31 overnight row: 103 stops at −2.5% each (−$2,283) against 171 closes
winning 66% at +1.2% (+$1,924).

**Stop, gap cap and threshold** (overnight reversal, 09:31, stocks only):

| Stop | Gap cap 3% | Gap cap 5% | Gap cap 8% |
| --- | --- | --- | --- |
| none, threshold 0.5% | 0.83 (270) | 0.79 (272) | 0.78 (278) |
| none, threshold 1.5% | **0.91** (208) | 0.79 (251) | 0.81 (263) |
| 2%, threshold 0.5% | 0.80 (270) | 0.71 (272) | 0.68 (278) |
| 2%, threshold 1.5% | 0.87 (208) | 0.69 (251) | 0.71 (263) |
| 5%, threshold 0.5% | 0.82 (270) | 0.70 (272) | 0.75 (278) |
| 5%, threshold 1.5% | 0.88 (208) | 0.70 (251) | 0.77 (263) |

Removing the stop and skipping gaps beyond 3% helps, as the diagnostic predicted, but the best row
is still a loss (−$171). The combo with the same geometry: 0.84 on 287 trades (−$446). 37
configurations in all; none profitable.

## The ORB correction

Wiring the hooks changed the opening-range breakout's evidence. With its intended 0.1-ATR stop the
22 September configuration is PF 0.74 (258 trades, 19% win, 207 stopped), not 0.93. Stop sweep
(15-minute range, 1% risk): 0.25 ATR with volume 3x is the best row at PF 0.91 on 230 trades
(33% win; the 100 trades that reached the close averaged +1.7%); 0.5 and 1.0 ATR are worse. Entries
after 10:00 were the only profitable pocket (PF 1.07 and 1.37 on 63 and 18 trades). The shadow
slot now uses 0.25 ATR.

## What runs tomorrow (24 September), and what does not

- `xs_overnight` (overnight reversal, 09:31, no stop, 3% gap cap, 1.5% threshold; PF 0.91) and
  `xs_combo` (combo, same geometry; PF 0.84) in **shadow**, weight 0.5, observation only.
- ORB stays in shadow with the corrected 0.25-ATR stop. The 15-minute Wave Rider is unchanged.
- The live slot is still the Wave Rider alone. Nothing from the book qualifies for capital.

## What would change the answer

1. **Short selling.** Every stock strategy in the book that showed promise anywhere is dollar-neutral.
   The long legs we can run carry the sample's negative intraday drift; the diagnostic's only
   interesting spread sits on the short side. Positions, ledger, both brokers and the reconcile step
   need a signed quantity. This is the next engine step.
2. **Industry or statistical clusters** for the demeaning (§3.9.1, §3.10) instead of one universe mean.
3. **A daily-portfolio executor** with overnight holds, for §3.1 momentum, §3.4 low volatility, §4.1
   sector rotation, §4.4 IBS mean reversion and §4.6 multi-asset trend, all testable on the ten years
   of daily bars we already have.
4. **Which of the 151 did the owner run with a good profit factor, and on what data?** That answer
   should set the order of the above.
