# Two new strategies in the engine: 15-minute Wave Rider and opening-range breakout

**Built 22 September 2026** so both could run in shadow mode the next day. Same data as every
previous study: 1 June to 16 September 2026, 75 days, full tape, point-in-time top-50 universe,
next-bar fills with 0.05% slippage. Sweeps: `data/sweeps/wr15-*.log`, `data/sweeps/orb-grid.log`.

## 15-minute Wave Rider

The base strategy run on 15-minute bars (the engine now resamples 1-minute bars per strategy),
because the diagnostic of 21 September found the only streak-level signal at that scale. Streak 3,
gain ≥ 1%, entries 09:30 to 11:30, hold up to 180 minutes, floor 0.5%.

| Filters | Trail | Stop | Trades | Win rate | PF | Net |
| --- | --- | --- | --- | --- | --- | --- |
| none | 2.0% | 2.0% | 468 | 49% | 0.89 | −$327 |
| none | 1.0% | 1.0% | 616 | 36% | 0.83 | −$493 |
| SPY ≥ 0.1%, stock ≤ 0.6% | 1.0% | 2.0% | 122 | 49% | **1.00** | +$1 |
| SPY ≥ 0.1%, stock ≤ 0.6% | 3.0% | 2.0% | 122 | 48% | 0.98 | −$12 |

Exit breakdown without filters (best row): timeouts 225 trades, 93% wins, +1.2% each; wave exits 25
trades, 72% wins, +1.5%; stops 160 trades, −1.9% each; close flatten 58 trades, −0.8%. The
timeout is doing the work a trailing exit should, and the stops cost almost the full 2% because
they fill on gaps. The +22 bp signal found in the diagnostic survives entry but is eaten by the exit
geometry and slippage. The trade-count filter could not be applied on 15-minute bars (it needs 20
prior bars, which do not exist by 10:15 ET).

## Opening-range breakout, long-only

Zarattini, Aziz and Barbon (2024) adapted: stocks whose first 5 or 15 minutes trade at least
`rvol_min` times their normal volume for that span (from the 14-day average daily volume); buy the
first close above the range high; stop at `stop_atr` average true ranges below entry; risk 1% of
the allocation per trade; exit at 15:55.

| Range | RVOL ≥ | Stop (ATR) | Trades | Win rate | PF | Net |
| --- | --- | --- | --- | --- | --- | --- |
| 15 min | 3.0 | 0.1 | 253 | 22% | **0.93** | −$92 |
| 5 min | 3.0 | 0.1 | 681 | 20% | 0.79 | −$702 |
| 15 min | 3.0 | 0.5 | 243 | 27% | 0.79 | −$306 |
| 5 min | 1.5 | 0.1 | 1,043 | 20% | 0.76 | −$1,183 |

In the best row the 59 trades that reached the close averaged +2.2% and won 95% of the time; the
other 194 were stopped out. Two reasons it does not match the paper: our universe is the fifty
largest names by dollar volume, not "stocks in play" drawn from the whole market, so relative
volume rarely means a real catalyst; and the short side, half of the published strategy, is not
implemented. Entries at 10:30 show profit factor 2.2 on 29 trades, too few to act on.

## Decision

Neither passes the protocol. Both are configured in **shadow mode** as observation only: they
trade on live prices with simulated fills and their own ledgers, at no risk, so the live record
accumulates while the two obvious next experiments are run in the engine: a broader universe and a
catalyst flag for the breakout, and an exit for the 15-minute variant that keeps the timeout's
behaviour without the stop's gap cost.

Bugs found and fixed on the way: end-of-day liquidation in the simulator cancelled the strategy's
own pending sell instead of filling it, so trades still open at 16:00 were lost from the results
(affects earlier results only for positions still open at the close); per-strategy exit reasons
were labelled with prices. Tests: 69.
