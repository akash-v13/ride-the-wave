# Roadmap: beyond the base strategy

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
