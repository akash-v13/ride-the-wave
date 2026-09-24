# What Alpaca gives us, what we use, and what is still on the table

Probed against the paper account and the Algo Trader Plus data plan on 23 September 2026 with
alpaca-py 0.44. "Used" means the running bot depends on it today.

## Account and permissions (paper)

| Capability | State | Used? |
| --- | --- | --- |
| US stocks and ETFs, long | enabled, 14,373 active symbols | yes (Wave Rider live, shadow slots) |
| Short selling | enabled; 5,267 symbols shortable / easy to borrow | shadow only (daily portfolio slots) |
| Margin | multiplier 4 | no, and not planned |
| Fractional shares | enabled; 7,795 symbols fractionable; orders by dollar amount (`notional`) | no |
| Options | level 3 (multi-leg spreads, no naked shorts), $100k options buying power | shadow (options slots); live multi-leg placement implemented, unused |
| Crypto | active; 73 pairs (BTC/USD, ETH/USD, ...), 24/7 | no |
| Extended hours | limit orders 04:00 to 20:00 ET with `extended_hours=true` | no |
| Pattern-day-trader rule | not a constraint above $25k equity | n/a |
| Delisted stocks | 19,174 inactive symbols listed, full price history served | yes since tonight (survivorship-free pool) |

## Market data (Algo Trader Plus)

| Data | Coverage | Used? |
| --- | --- | --- |
| Stock bars, minute and daily, full tape (SIP) | since January 2016, adjusted or raw | yes (polling, cache, daily engine) |
| Stock snapshots (latest trade, quote, minute bar, daily bar) | real time, 200 symbols per call | yes (every 15 s) |
| Stock trades and quotes, tick by tick | full history | no |
| Screener: most actives, movers | real time | yes (universe) |
| News (Benzinga) | history and real time | yes (research); Jev scores it |
| Corporate actions: dividends, splits, mergers | history | no (earnings dates are not in it) |
| Trading calendar and clock | yes | yes |
| Option chains with greeks and implied volatility (OPRA) | real time | shadow (options slots) |
| Option bars, trades, quotes | since February 2024 | no (options backtester pending) |
| Crypto bars, trades, quotes | since 2021, 24/7 | no |
| Websocket streams: stocks, options, crypto, news | unlimited symbols on this plan | no (REST polling instead) |

## Orders

| Order feature | Used? | What it would unlock |
| --- | --- | --- |
| Limit buy with a stop leg (OTO) | yes | |
| Market sell | yes | |
| Bracket orders (take-profit and stop on the server) | no | exits that survive a bot crash without the bot |
| Trailing stop orders (server-side trailing) | no | the Wave Rider's exit as one order; fewer polls |
| Extended-hours limit orders | no | pre-market and post-market strategies, the overnight effect |
| Notional (dollar) orders and fractional shares | no | equal-dollar portfolios without rounding; small capital per slot |
| Short sale and buy-to-cover | no (shadow books only) | the long-short half of every book strategy |
| Multi-leg option orders (up to 4 legs) | implemented, unused | live options structures on the paper account |
| Crypto orders (GTC, 24/7) | no | a crypto book: no close, no PDT, trend and volatility strategies |

## What each unused piece would let us do

1. **Short selling on the paper account.** The shadow daily slot already books shorts; promoting it
   needs a buy-to-cover path in the broker and a borrow check (`easy_to_borrow`). Unlocks pairs,
   stat-arb and every dollar-neutral construction, plus short-side momentum.
2. **Extended hours.** Buy at 15:59, sell at 04:05 or at the open: the overnight-return effect
   (returns accrue overnight, intraday drift is negative in our own sample). Testable now with
   daily bars (close-to-open), tradable with extended-hours limit orders.
3. **Websocket streams.** Replace 15-second polling with real-time ticks: intraday exits that fire
   on the tick, VWAP-aware execution, and microstructure features (order-flow imbalance, trade-size
   ratios) from the trade and quote streams. The plan allows unlimited symbols.
4. **Tick history.** Backtests of microstructure signals and honest fill models (was the bid there?).
5. **Fractional and notional orders.** Daily portfolios sized in dollars, not whole shares; slots
   with $1,000 of capital that still hold ten names.
6. **Crypto.** A 24/7 market with its own data stream; chapter 18 of the book; trend, volatility
   targeting and momentum on BTC/ETH; also the only market open when the owner checks in at night.
7. **Corporate actions.** Dividend-capture and split-driven effects; the dividend calendar for
   options (assignment risk before ex-dates).
8. **Bracket and trailing-stop orders.** Server-side exits for every live position.
9. **Option history.** A chain-reconstruction backtester from February 2024: iron condors, put
   spreads and the volatility risk premium tested over two and a half years.

Still not available from Alpaca: earnings dates and fundamentals (an outside source is needed),
futures, FX, bonds.
