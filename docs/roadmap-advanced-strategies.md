# Roadmap: beyond the base strategy

## What stat arb needs next, and what to look for (2026-11-09)

**Asked by the owner:** what would improve the strategies, mostly stat arb, and which outside
resources to look for. This section is the assessment and the wish list.

**Updated the same evening.** The owner approved the first two pieces of work. Costs are measured,
the daily recordings run, and a gap was found in the price panel. The changes are marked below.

**Where stat arb stands.** One rule runs in shadow (`sa_volrev`): +30 bp per cohort after costs over
2017-2026, t 1.5, as first tested. Re-priced with measured spreads on 9 November: +12 bp, t 0.6.
Three things limit it, in this order.

1. **Too little independent evidence.**
   - The rule traded on 779 days, but those days cluster into a handful of stress episodes, and two
     of them (2020 and April 2025) earned most of the profit.
   - It was picked from 18 looks at the same decade, then 2 configurations. Every refinement tested
     on 2017-2026 adds another look, so refinements cannot be trusted until there is a second sample.
   - **Found 9 November:** the decade's price panel lacks stocks delisted since late 2022, about 50
     to 60 liquid names, so its last four years are measured on survivors
     (docs/research/2026-11-09-panel-survivorship-gap.md).
2. **Costs were assumed. Measured on 9 November, they are twice the assumption**
   (docs/research/2026-11-09-statarb-costs.md).
   - The backtest charged 5 bp per stock trade. The picks really cost 10.9 bp at 09:35, on calm days
     nearly as much as on volatile ones.
   - As the slot trades, the rule has no demonstrable edge. How it is executed now matters more than
     any refinement of what it picks: the opening auction has no spread.
3. **The residuals still carry shared themes.**
   - Residuals are a stock's move after SPY and one sector ETF. In the first live week the shorts
     were mostly chip and AI-hardware names, and the hedge was as large as the stock book (4 Nov:
     SPY −52%, XLK +44% against 40% a side).
   - So part of what the rule calls a stock's "own move" is a theme the sector ETF does not capture.

**Resources to look for, most valuable first.**

| # | Resource | What it unlocks | Where to look (terms and prices not checked) |
|---|---|---|---|
| 1 | Daily US stock prices before 2016, back to 1998 or earlier. Must include delisted stocks, open prices, volume, and split and dividend adjustments. **Worth more since 9 November:** if it also covers 2016 to today, it checks our own panel, which lacks delisted stocks | The frozen `sa_volrev` rule run once on 1999-2016: 1998, 2000-02, August 2007, 2008-09, 2011 and 2015 as stress episodes it has never seen. Also a second sample for momentum and for every refinement below | CRSP through a university or alumni login (the standard); paid: Norgate Data, Sharadar on Nasdaq Data Link; cheaper: Tiingo, EODHD (check that delisted stocks are included) |
| 2 | Earnings dates and company fundamentals, point-in-time | Keeping earnings moves out of the reversal book; the book's "no data" strategies (earnings momentum, value, multifactor) | SEC EDGAR is free (filing dates, reported figures) but needs building; Sharadar bundles fundamentals with prices |
| 3 | Industry classification for each stock, with history | Residuals within an industry, which the literature finds revert more strongly than raw or sector-level ones | SIC codes from SEC EDGAR (free); GICS is better and paid |
| 4 | Books and papers on stat arb practice (list below) | Distilled into project skills, as was done for Dixon | PDFs into `docs/books/` (kept out of git) |
| 5 | The owner's own record: which of the 151 strategies worked, on what data and universe | Sets the order of everything else | Still open since 23 September |

Licensed data goes under `data/` only. That folder is kept out of git, and the repository is public.

**Reading list.**
- **Books:**
  - Isichenko, *Quantitative Portfolio Management: The Art and Science of Statistical Arbitrage*
    (2021). The practitioner's account of forecasts, risk models, costs and portfolio construction.
  - Paleologo, *Advanced Portfolio Management* (2021) and *The Elements of Quantitative Investing*
    (2025). Factor risk models, hedging and sizing.
  - Chan, *Algorithmic Trading* (2013). Mean reversion, cointegration and pairs. Named in the
    owner's first roadmap, not yet in `docs/books/`.
  - López de Prado, *Advances in Financial Machine Learning* (2018). How to count trials and
    discount a backtest for them.
- **Papers on what we already trade:**
  - Khandani and Lo, "What Happened to the Quants in August 2007?" The same reversal rule, its
    decline year by year and its worst week.
  - Nagel, "Evaporating Liquidity" (2012), and Drechsler, Moreira and Savov, "Liquidity and
    Volatility" (2020). Why reversal pays when VIX is high.
- **Papers on better residuals:**
  - Da, Liu and Schaumburg, "A Closer Look at the Short-Term Return Reversal" (2014).
  - Blitz, Huij, Lansdorp and Verbeek, "Short-Term Residual Reversal" (2013).
  - Hameed and Mian, "Industries and Stock Return Reversals" (2015).
  - Kakushadze and Yu, "Statistical Risk Models" (2017), and Kakushadze, "Heterotic Risk Models"
    (2015). Free, by the author of the 151 book; clusters built from prices alone.
- **Papers on which moves revert:**
  - Campbell, Grossman and Wang (1993), and Llorente, Michaely, Saar and Wang (2002). Low-volume
    moves revert; high-volume moves continue.
  - Tetlock, "Does Public Financial News Resolve Asymmetric Information?" (2010). Moves without
    news revert more.
  - So and Wang, "News-Driven Return Reversals" (2014). Reversal around earnings dates.

**Work that needs no new resource.**

1. **Done 9 November: the real cost is measured.** The picks cost 10.9 bp at 09:35, and each
   simulated fill now stores its bid and ask (feature 25).
2. **Done 9 November: the daily recordings run.** Borrow flags for every stock, and option quotes
   with implied volatility for the stat-arb names, at 15:45 ET (feature 25).
3. **Next, waiting on the owner: repair the price panel.** Add the stocks delisted since 2020 from
   Alpaca's corporate-actions feed, then re-run the frozen studies unchanged and report old against
   new. This comes first because every other 2017-2026 number rests on the panel.
4. **Then: test opening-auction fills.** Price every cohort at the official opening auction prints on
   all 779 volatile sessions, with the design fixed in writing first. If they match the backtest's
   open, auction orders (`opg`, which Alpaca supports) remove most of the cost.
5. **Test the combined book.** Reversal earned most in 2020 and April 2025, when momentum and trend
   did worst. Their daily returns have not yet been put side by side. This is item 4 below.
6. **Write the refinements down before running them:**
   - residuals within an industry or a price-based cluster;
   - picks that are sector-neutral by construction, so the hedge shrinks;
   - a low-volume or no-news condition. The 357,000 scored headlines have been tried as a signal,
     never as a filter on reversal;
   - signal at 15:50 and entry at the close auction. From the next open, 1-day reversal was zero in
     stage 1, so the first night may hold it. Minute bars since 2016 can test this.
   - Each is run once, on the older data when it arrives, or on 2017-2026 with the look counted.

**Other avenues, with an honest prior.**
- **Fundamental factors (value, quality, earnings momentum):** decades of evidence and slow
  turnover, so costs matter less. Needs resource 2. Fits the sleeves approach.
- **Option-implied stock signals (skew, implied minus realised volatility):** documented, and the
  chains are already on the plan, but history is short. Start recording now, judge in 6 to 12 months.
- **Pairs within a sector:** the same machinery as residual reversal. Published returns have
  declined since the 2000s. Worth a test only if it worked for the owner before.
- **Intraday stat arb:** the project's own tests found noise there. No.

## Direction from 2026-11-02: a book of sleeves, judged on long histories

**What the owner chose (29 October and 2 November 2026).** Stop competing at intraday horizons,
where market makers and high-frequency firms win and our own tests found noise. Instead, build a
book of three to five independent sleeves, each a documented risk premium or structural effect,
combined at equal risk under one volatility target. The owner also chose to:
- retire the intraday slots that failed;
- test on long outside histories, not only Alpaca's decade;
- allow defined-risk option selling;
- start with trend following plus a long-history test of the put spread.

**What the first tests found (same day).**

| Sleeve | Test | Result | Status |
|---|---|---|---|
| Bull put spread (`bps_spy`, `bps_qqq`) | 1990-2026, priced from S&P 500 + VIX, skew fitted to real chains | Sharpe 0.25 over T-bills, −52% drawdown, fails 3 of 4 criteria. Mostly a leveraged bet that stocks stay calm (correlation 0.53) | **Not promoted**; owner to choose retire or observe at 5% risk |
| Trend following (`tf_etfs`) | 21 ETFs 2017-2026; US stocks + 10y Treasury 1927/1963-2026 | Earned cash in the ETF decade; Sharpe 0.37 over a century; positive in nearly every long bear market | **Shadow from 2026-11-03**, as insurance |
| Constant-volatility stocks (`vt_spy`) | 1990-2026 inside the sleeve study | Sharpe 0.63 against 0.51 for buy and hold | Shadow since September |
| Combined book | 1990-2026 at 10% volatility | No stock-holding mix stayed inside a 15% drawdown; that needs ~4-6.5% volatility | Risk budget to re-decide |

Research pages: docs/research/2026-11-02-put-spread-long-history.md,
docs/research/2026-11-02-trend-following.md.

**Next, in order.**

1. **Owner decisions.**
   - Risk budget: about 6% volatility with a 15% drawdown, or 10% volatility with about 25-30%.
   - The put-spread slots: retire them, or observe them at 5% risk per spread.
   - Which of the *151 Trading Strategies* worked for the owner before (still open).
2. **Momentum on a century of data: done the same day**
   (docs/research/2026-11-02-momentum-and-reversal-century.md).
   - Scaled by its own volatility, long-only momentum beat the market with an information ratio of
     0.83 (t 8.5) over 1927-2026 and 0.38 (t 2.0) since 2000, and its crashes halved. It passes.
   - Short-term reversal, the base of stat arb, is gone since 2000: Sharpe 0.12, large caps 0.02,
     break-even 1 to 3 bp a trade.
   - **The overlay on our own 2017-2026 data passed** (docs/research/2026-11-02-momentum-overlay.md):
     IR 0.43 (plain 0.48), the worst stretch against SPY halved. **Next:** a shadow slot beside
     `pm_actives`.
3. **Statistical arbitrage: staged, with a kill test at each stage** (owner's request, 2026-11-02).
   - **Stage 1, diagnostic.** No engine yet, a few days' work.
     - On a point-in-time universe of 300 to 500 liquid stocks, 2017-2026, remove each stock's
       market and sector moves (rolling betas on SPY and its sector ETF). What is left is the
       stock's own move, its "residual".
     - Measure whether 1-, 3- and 5-day residual moves reverse, from the next open (so there is no
       bid-ask bounce): rank correlation, quintile spreads, day-block bootstrap, both halves.
     - Also measure it separately in high-volatility markets, where supplying liquidity pays most.
     - Kill test: no spread with t ≥ 2 in both halves, or a break-even cost below 5 bp, ends daily stat
       arb.
   - **Stage 1 result (2026-11-02):** **fails** always-on: +17 bp per 5-day trip, break-even 4.3 bp.
     With VIX ≥ 20: +51 bp (t 2.6), both halves positive, break-even 13 bp. So stage 2 is narrowed
     to a volatility-gated version and must first pass its own pre-registered strategy test
     (docs/research/2026-11-02-statarb-stage1.md).
   - **Stage 2a result (same evening):** the VIX-gated rule passed its pre-registered strategy test
     (+29.7 bp per cohort after costs, both halves positive, Sharpe 0.48, t 1.5). Shadow slot
     `sa_volrev` from 2026-11-03 (docs/features/24-statarb-volatility-gated.md).
   - **Stage 2, only if stage 1 passes: the strategy.**
     - Each residual is modelled as a spring pulling back to zero (an Ornstein-Uhlenbeck process).
       Its "s-score" says how stretched it is (Avellaneda and Lee 2010).
     - Enter at |s| > 1.25, exit at |s| < 0.5. The book is dollar- and beta-neutral.
     - Costs: 5 bp, plus a borrow charge on shorts, easy-to-borrow names only.
     - Rules fixed before the run, walk-forward, every configuration counted. Pairs within a sector
       are a variant of the same machinery: a pair is a one-stock factor model.
   - **Stage 3: shadow, then paper with real shorts.** The daily slot already holds shorts. Live
     needs opening-auction orders, fill reconciliation and real borrow costs.
   - **Expectation, stated in advance.** The same edge was strong before the 1990s and has been
     competed down by firms that trade it intraday, at fractions of a basis point, across thousands
     of names. Our version is daily, on hundreds of names, at about 5 bp. Stage 1 exists so that we
     learn this cheaply if it is true.
4. **The combined book as a slot.** Constant-volatility stocks or momentum, plus the trend overlay,
   at the chosen budget, observed in shadow as one book.
5. **Evidence bar for everything.** Pre-registered rules, every configuration counted (deflated
   Sharpe), a long outside history where one exists, and both halves positive.

---

**Direction from the owner (2026-09-21):** Ride The Wave, the streak-momentum strategy, was the
base the app was built on. The goal now is strategies with a materially higher chance of profit.
This page is the working proposal; the owner picks the order.

## Where higher P&L comes from

Grinold and Kahn's fundamental law: information ratio ≈ skill per bet × √(number of independent
bets). The base strategy makes about 1.5 bets a day with a tiny edge per bet, so its ceiling is low
no matter how well it is tuned. Three levers move the ceiling:

1. **Breadth**: many independent positions at once (long and short) instead of one or two.
2. **Holding period matched to a documented effect**: minutes-scale single-stock momentum is weak
   (measured in this project); hours- and days-scale effects are better documented.
3. **Risk sizing**: volatility-targeted exposure and correct stop geometry raise the ratio of return
   to drawdown for any strategy.

Everything below is chosen to use at least one of these, to be testable with data we already have
(SIP minute bars from 2016, daily bars, a free IEX live feed, a paper account with 4x margin and
short selling), and to reuse the engine, data cache, feature dataset and validation protocol.

## Candidates, ranked by evidence per unit of effort

### 1. Market intraday momentum on SPY — TESTED 2026-09-21, REJECTED

See [research/2026-09-21-spy-intraday-momentum.md](research/2026-09-21-spy-intraday-momentum.md): no effect in 2016-2026, every threshold loses after costs. Kept below for the record.

Effect: the first half-hour return of the S&P 500 ETF predicts its last half-hour return
(Gao, Han, Li, Zhou, *Journal of Financial Economics* 2018), strongest on volatile days. One trade
per day, index only, no stock selection. Our own data agrees in spirit: the edge we found lives at
the market level (the SPY gate does the work).

Fit: SPY minute bars back to 2016 are one download. Test = a 40-line script and the walk-forward
protocol. App changes: none for the test; a small "market timing" strategy type to trade it.
Risk: capacity is unlimited for us; the effect may have weakened since publication. Verify before
trading.

### 2. Opening-range breakout on stocks in play (extends what exists)

Effect: buy (or short) a break of the first 5- to 15-minute range in stocks with unusually high
relative volume at the open, ATR-scaled stop, hold to the close (Zarattini, Aziz, Barbon 2024;
Zarattini and Aziz 2023 on QQQ). The 15-minute finding in
[research/2026-09-21-slower-bars.md](research/2026-09-21-slower-bars.md) is consistent with it.

Fit: uses our universe builder, relative-volume and noise features, aggregator with a bar-size
setting, and the replay engine. Changes: a range-breakout trigger, ATR stop, hold-to-close exit,
optional short side. Risk: published returns rely on leverage and many trades a day; slippage on
IEX fills is the thing to measure.

### 3. Statistical arbitrage pairs (biggest breadth, biggest build)

Effect: long one stock, short its cointegrated partner when the spread deviates, close on reversion
(Gatev, Goetzmann, Rouwenhorst 2006 and the large literature after it). Market-neutral, many
simultaneous positions, holding hours to days. Tsay's cointegration chapters are the method.

Fit: daily and minute SIP data are cached; the paper account allows shorting. Changes are
architectural: a portfolio-level strategy interface that sees all symbols and emits target
weights, short support in the simulated broker and order manager, a weights-based allocator, and
daily-bar replay. Risk: pair edges have compressed; needs rigorous out-of-sample selection.

### 4. Later

- Cross-sectional daily momentum and short-term reversal, long-short, multi-day holds (Jegadeesh
  1990; Jegadeesh and Titman 1993): highest breadth, lowest turnover, needs the same portfolio
  interface as pairs.
- Volatility-targeting overlay on any of the above (Moreira and Muir 2017): scale exposure by
  inverse realised volatility.
- Post-earnings drift and news-driven selection, once the Jev key arrives.
- Learned exits by optimal stopping on logged paths (see the Dixon skill), applicable to all.

## What the app needs, in order

1. `bar_minutes` in the aggregator and replay engine (needed by 1 and 2).
2. A `MarketTimingStrategy` type: decides on one instrument at fixed times of day.
3. Short selling in `SimBroker`, the order manager and the position book (2 optional, 3 required).
4. `PortfolioStrategy` interface: input = bars for all symbols, output = target weights; a
   weights-based allocator; daily-bar replay mode (3 and 4 above).
5. Evaluation stays as the Dixon skill prescribes: day-level walk-forward, engine results on test
   days only, Bayes factor or bootstrap before any claim.

## Proposed order

Candidate 1 was tested first and rejected. Build 2 next on the existing engine. Take on 3 and 4 once the portfolio interface exists, because that is where the
breadth is. Ride The Wave stays as the reference strategy and keeps running on paper to accumulate
live-feed data.
