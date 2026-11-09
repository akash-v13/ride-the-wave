# 24. Stat arb in volatile markets (shadow slot `sa_volrev`)

**Built 2 November 2026.** Shadow only. Evidence:
docs/research/2026-11-02-statarb-stage1.md (the diagnostic) and
docs/research/2026-11-02-statarb-volatility-gated.md (the tradable rule).

## What it does

Every morning at 09:35 ET the slot checks one thing first: **did VIX close at 20 or above
yesterday?**

- **No:** it opens nothing new, and the cohorts it already holds run out on schedule.
- **Yes:** it forms a new cohort.
  1. For each of 254 liquid stocks, it removes the part of the last five days' moves explained by the
     market (SPY) and the stock's sector ETF. What is left is the stock's own move, its "residual".
  2. It buys the fifth whose own moves fell most and shorts the fifth that rose most, in equal
     dollars: 20% of capital a side.
  3. It buys or sells SPY and the sector ETFs to cancel the cohort's market and sector exposure.
  4. It holds the cohort five sessions.

Up to five cohorts are alive at once, so a fully active book is 100% long, 100% short, plus hedges.

**Why.** Over 2017-2026 this earned about +30 bp per cohort after 26 bp of costs: +4.3% a year on
capital, Sharpe 0.48, positive in both halves. When stocks are knocked around in a stressed market,
dealers step back, and whoever buys the oversold and sells the overbought is paid when prices settle
(Nagel 2012). On calm days the same rule earns nothing, so it does not trade then.

**The cohorts are rebuilt from history each morning.** The slot keeps no list of its own cohorts. It
recomputes which ones are alive (formed on the last five sessions, each only if VIX was high the day
before), so a restart can never lose or double a cohort. On 9 April 2025 the rebuild picked exactly
the same stocks as the backtest.

## Settings

```yaml
portfolios:
  - id: sa_volrev
    kind: statarb_vol_reversal
    universe: file:config/universes/liquid_stocks_254.txt
    decision_time: "09:35"
    max_gross: 3.0
    weight: 50.0              # $500,000 simulated: about 60 names a side need room for whole shares
    dead_band_pct: 0.1        # skip adjustments under $500 (the 1% default would skip every add)
    fill_at: open_auction     # since 10 November: fills at each stock's opening auction price
    slippage_bps: 1.0         # the allowance on top of the auction price
    params: {}                # defaults: vix_gate 20, k 5, hold 5, fraction 0.2, side 0.2,
                              # decide_at_open true, market SPY, the 11 sector ETFs
```

## Where VIX comes from

Alpaca does not carry the VIX index. At each decision the bot downloads Cboe's VIX history, a public
file updated after each close (`ridethewave.data.external`). If the download fails, it uses the last
saved copy. The strategy needs yesterday's close:
- If that close is missing, it opens no new cohort that day and logs why.
- If the file is missing entirely, it holds nothing.

## What changed in the engine for this

- **Two optional hooks on daily strategies.**
  - `extra_symbols`: symbols the strategy reads but does not count as its universe (here SPY and the
    sector ETFs). The bot fetches them with the rest.
  - `external_series`: outside data the bot loads into `Window.external` (here `vix`).
- **`universe: file:<path>`** reads a symbol list from a file (`config/universes/`).
- **The close report** shows a strategy with more than 25 open positions or trades as one summary
  line (count, long/short, P/L).

## Files

- `src/ridethewave/daily/residuals.py`: sector assignment, rolling betas, residuals.
- `src/ridethewave/daily/statarb.py`: the cohort rules and `cohort_targets`. Pure.
- `src/ridethewave/daily/statarb_data.py`: loads the survivorship-free panel for the studies.
- `src/ridethewave/daily/strategies.py`: `VolGatedReversal` (`statarb_vol_reversal`).
- `scripts/research_statarb_stage1.py`, `scripts/research_statarb_volgated.py`.
- Tests: `tests/test_residuals.py`, `tests/test_statarb.py`, one case in `tests/test_reports.py`.

## Fixed on 4 November 2026: the dead band

**The bug.** Daily slots skip same-side adjustments smaller than a band, 1% of capital by default. For this slot that is $5,000, while one name in one cohort is 0.4% ($2,000). On 4 November, 79 names were in both live cohorts:
- **What should have happened:** each name goes from 0.4% to 0.8%.
- **What happened:** none of the 79 was added, but the ETF hedges were sized for both cohorts.
- **Result:** stocks were held at about 24% long and 22% short against 40% targets, which left roughly 20% of capital short SPY and long XLK.

**The fix.** The band is now a per-slot setting (`dead_band_pct`), and this slot uses 0.1%. The 4 November mark is not a clean observation; 3 November is.

## Fills at the opening auction, from 10 November 2026

**Why.** The stocks this rule picks cost about 11 bp each way to trade with a market order at 09:35.
The opening auction crosses each stock at one price with no spread. Priced there, the same picks
earn +40.6 bp per cohort, against +7.5 bp at 09:35
(docs/research/2026-11-09-statarb-auction-fills.md). The owner approved the change on 9 November.

**What the slot does now.** The picks are unchanged. Each fill is booked:
- **at that stock's opening auction price,** from Alpaca's auction prints, plus 1 bp;
- **in a number of shares set from yesterday's close,** which is all an order sent before the open
  could know;
- **at the day's first trade** when Alpaca has no auction print for the stock, and at the last
  trade when it has neither. The log counts each kind every day, and the fill record says which was
  used (`basis` in `portfolio_fills`).

**The decision still runs at 09:35.** It uses only yesterday's prices and yesterday's VIX, so the
picks are the same as a decision made before the open. Running it at 09:35 lets the slot read the
auction prices that have just printed. A live version would send its orders before 09:28 ET.

**The record changes basis on 10 November.** Fills up to 9 November were booked at 09:35 plus 5 bp.

## Measured on 9 November 2026: costs and the universe

- **Costs.** The slot charges itself 5 bp a trade. Measured from quotes, its picks cost 10.9 bp at 09:35. Re-priced on the repaired price panel, the backtest's +29.7 bp per cohort becomes +7.5 bp (t 0.4). docs/research/2026-11-09-statarb-costs.md, section 6.
- **At the opening auction** the same picks would earn +40.6 bp per cohort (t 2.0), because no spread is paid there. Changing the slot to book its fills at the auction price is proposed, not done. docs/research/2026-11-09-statarb-auction-fills.md.
- **Fill quotes.** From 10 November each fill is stored with its bid and ask (feature 25), so the slot's record can be re-priced exactly.
- **The universe file is ageing.** Of its 254 names, KVUE and WBD have been delisted since September. They cannot be picked, because their prices have stopped. ONDS cannot be shorted, and the slot does not check that.

## Limits

- **Shadow.** Fills are simulated, at the opening auction price plus 1 bp since 10 November (at the 09:35 price plus 5 bp before). Whether a real order would have been part of each auction cannot be shown on a paper account. No borrow is charged in the slot (the
  backtest charged 0.5% a year), and short availability is not checked.
- **Hedges are set once a day.** In a crash, when stocks suddenly move more with the market, some
  market exposure is left until the next morning.
- **The universe is a September snapshot** of the 254 most-traded stocks. Refresh it every few
  months.
- **The evidence is thin:** t 1.5, and two episodes (2020, April 2025) did most of the work. The live
  record becomes evidence only after many volatile weeks.
- **The 09:35 decision takes about 7 seconds,** fetching ~270 symbols' history. Wave Rider's ticks
  wait meanwhile; its protective stops sit with Alpaca.
