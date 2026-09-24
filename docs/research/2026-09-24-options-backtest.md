# Options backtest, February 2024 to September 2026: rebuilt chains, 144 configurations

**Run 24 September 2026.** First backtest of the options engine (feature 22). Code:
`src/ridethewave/options/backtest.py` (chains rebuilt from daily option bars, replayed through the
production `OptionsSlot`), `scripts/download_option_history.py`, `scripts/backtest_options.py`.
Grid results: `data/research/options/grid.csv`, log `data/research/options-grid.log`.

## Data and method

- **History.** Alpaca's option bars start in mid-January 2024. For SPY, QQQ and IWM, every monthly
  expiry (third Friday; the Thursday when the Friday is a holiday, as on 17 April 2025 and
  18 June 2026) from March 2024, all strikes within 18% of the price range, daily bars from 80 days
  before expiry. Expired contracts are included, so there is no survivorship gap.
- **Chains.** On each day, every contract that traded, priced from its close with a modelled spread of
  3% of the price (at least $0.01 a side); implied volatility solved from the close.
- **Fills.** Each leg pays the full modelled half-spread in both directions (pessimistic; the live shadow
  slots pay a quarter). Open legs are marked at their last close; legs at expiry are worth intrinsic
  value. Sizing: the structure's max loss is 20% of current equity; $100,000 start.
- **Grid.** 6 templates × 3 underlyings × strike step 1% or 2.5% of spot × entry gate (none, or implied
  minus 20-day realised volatility ≥ 3 points) × exits ("managed": 50% of max profit, 2× stop, close 7
  days before expiry; "hold": to the day before expiry). 144 runs, 660 trading days each.
- **Benchmarks** over the same days: SPY +55.7% (Sharpe 1.16, max DD −19.0%); QQQ +71.0% (1.08,
  −22.9%); IWM +45.4% (0.79, −27.9%).

## Results

Median Sharpe across all settings, by template: covered call 0.99, bull put spread 0.54, short strangle
0.15 (see note), iron butterfly −0.15, iron condor −0.22, long straddle (the control) −0.32.

**The bull put spread, strikes 5% and 10% out of the money:**

| Underlying | Gate, exits | Return | Sharpe | Max DD | Trades | Win | Halves |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QQQ | vrp, hold | +52.6% | **1.56** | −9.8% | 21 | 95% | +15.4% / +32.4% |
| QQQ | vrp, managed | +38.3% | 1.15 | −6.8% | 40 | 88% | +9.2% / +26.8% |
| QQQ | none, hold | +43.5% | 0.97 | −22.3% | 31 | 94% | +3.7% / +38.6% |
| SPY | vrp, hold | +28.8% | **1.13** | −7.2% | 20 | 95% | +8.4% / +19.0% |
| SPY | vrp, managed | +15.8% | 0.76 | −7.2% | 41 | 85% | +1.7% / +13.8% |
| SPY | none, hold | +24.1% | 0.69 | −20.7% | 31 | 94% | +0.3% / +23.9% |
| IWM | vrp, hold | +26.0% | 0.58 | −22.1% | 24 | 83% | +4.8% / +20.9% |
| IWM | none, managed | +26.7% | 0.63 | −23.0% | 68 | 81% | −1.4% / +29.8% |

**The covered call** (100 shares plus a call 5% out, vrp gate, hold): QQQ +30.0%, Sharpe 1.64, max DD
−6.2%; SPY +23.1%, Sharpe 1.30, max DD −5.9%. Correlation with the underlying 0.8 to 0.99: this is mostly
the stock's own return with the upside capped and the premium added, held part-time because of the gate.

**The iron condor** loses in most settings. With the inherited 2% strikes it lost every dollar on SPY:
in a market that rose 56%, calls 2% above the spot were run over in six of the first ten months.
Wider strikes help but do not rescue it; the call side is the problem in a trending market.

**Note on the short strangle.** Its best rows (+1,031% with a 94% drawdown) are an artefact: for
structures with undefined risk the sizer uses the credit as the risk and over-sizes. Ignore those rows;
the template is sim-only and cannot go live in any case.

## How the put spread got through April 2025

The volatility gate was closed going into the tariff crash (implied volatility was not rich relative to
realised), so neither SPY nor QQQ held a position on 2 to 7 April; they entered once premiums were rich
and earned through the recovery. The only losing trades were opened in late February 2025. That is the
textbook mechanism for the gate, but it is also one event: with 20 to 24 trades per underlying, a couple
of differently timed entries would change the headline.

## Reading

1. **Short puts on an index are a long-market position with a floor and a ceiling.** In a period
   where the market rose 45 to 71%, that paid. What the gate and the 5% strikes added is a much smaller
   drawdown than holding the index for about the same Sharpe (SPY) or a better one (QQQ).
2. **This is the first strategy family in the project that beats its benchmark on risk in all three
   underlyings' halves.** It is also the one with the least data: one bull market, one crash, about 20
   trades each. It is a candidate for observation, not a proven edge.
3. **What would break it:** a slow grinding decline (no volatility spike to close the gate, puts
   breached month after month), or an overnight gap larger than 10% while a position is open.

## Decisions

- Shadow options slots changed to the tested configurations: `bps_spy`, `bps_qqq` (bull put spread,
  2.5% strike step, vrp gate, hold to the day before expiry) and `cc_qqq` (covered call, same settings).
  The iron condor and the untested AAPL covered call are retired. Nothing goes live.
- `OptionsSpec.strike_step_pct` added (default 1%, unchanged for existing configs); structures are now
  sized from current equity, not starting capital.
- Next for options: rerun as history grows; test weekly expiries and a 45-day entry; fix the sizer for
  undefined-risk structures; reconcile live fills before any live slot.
