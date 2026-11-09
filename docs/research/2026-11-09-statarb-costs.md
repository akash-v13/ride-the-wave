# Statistical arbitrage, costs: what the VIX-gated reversal really pays to trade

**Run 9 November 2026.** The owner's go-ahead for the first item of the 9 November assessment
(docs/roadmap-advanced-strategies.md, top section): measure the real cost. Code:
`src/ridethewave/daily/costs.py`, `scripts/research_statarb_costs.py`. Results:
`data/research/statarb/costs_*`.

## 1. Why

The shadow slot `sa_volrev` rests on a backtest that earned +55.7 bp per cohort before costs and
+29.7 bp after (docs/research/2026-11-02-statarb-volatility-gated.md). Two of its assumptions were
never checked:

1. **Each stock trade costs 5 bp.** The edge is gone at about 12 bp. The rule trades only in
   stressed markets and just after the open, when quoted spreads are at their widest.
2. **It trades at the open.** The backtest enters at the opening price and exits at the opening
   price five sessions later. The slot decides at 09:35 and fills at the price then. If the picks
   move in those five minutes, the live record will differ from the backtest by that much.

Alpaca's quote history and minute bars answer both. Neither had been used for this.

## 2. What was fixed before running

**The picks.** The backtest's own, configuration A: on each session, the fifth of the point-in-time
top 300 with the most negative 5-day residual (bought) and the fifth with the most positive (sold).
The script first checks that its picks reproduce the backtest's saved long and short returns on all
779 gated sessions, and stops if they do not.

**Measurement 1: the wait.** On every gated session, from minute bars:
- **A stock's move** = its price at 09:35 ÷ its opening trade − 1.
  - Opening trade: the open of its first minute bar from 09:30.
  - Price at 09:35: the volume-weighted price of the 09:35 bar, or the last trade before it if
    nothing traded in that minute.
  - A stock that has not traded by 09:35 is left out and counted.
- **Hedged**, as in the backtest: minus its market beta times SPY's move, and its sector beta times
  its sector ETF's move beyond SPY.
- **Entry wait** = the longs' average hedged move minus the shorts', on the entry day. Positive
  means the longs had already gained on the shorts by 09:35, so the slot gives that up.
- **Exit wait** = the same for the same picks on the exit day, five sessions later. Positive means
  the slot gains it by leaving at 09:35.
- **The 09:35-priced spread** = the backtest's spread − entry wait + exit wait.

**Measurement 2: the spread.** From quote history, on a random sample of sessions (seed 20261109):
60 of the 779 gated sessions and 30 calm ones (VIX below 20 the day before).
- **Names:** that session's picks, plus SPY and the 11 sector ETFs.
- **Windows:** 09:35:15 to 09:35:45, when the slot trades, and 09:30:30 to 09:31:00, just after the
  open.
- **A name's cost** = its quoted half-spread in basis points of the mid, averaged over the window
  with each quote weighted by how long it stood. A market order pays about this one way. Quotes
  with no bid, or with the ask at or below the bid, are ignored.
- **A session's cost** = the average across its picks, each name capped at 100 bp. The book holds
  equal dollars in each name, so the average is what it pays. Names with no valid quote are
  counted. The median is reported beside it.

**The re-priced result.** Per cohort, as the slot actually trades:

    net = 09:35-priced spread − (4 × measured half-spread + 5 bp hedges + 1 bp borrow)

A round trip buys and sells both legs, so the spread is paid four times. The hedge and borrow
charges stay as the backtest had them. The half-spread is the gated sample's 09:35 average, for the
whole period and for each half from its own sessions.

**How the result will be read:**
1. **Is 5 bp fair?** If the measured half-spread at 09:35 on gated sessions is 5 bp or less, the
   backtest's cost stands.
2. **Does the rule still pass?** It was accepted on being profitable after costs in both halves
   (2017-2021, 2022-2026). The re-priced result is held to the same test.
3. **Is the wait worth removing?** If waiting until 09:35 costs more than 10 bp per cohort (entry
   wait minus exit wait), the next step is to test orders in the opening auction.

Nothing is tuned here. The cap, the windows and the sample were set before the first quote was
fetched, and the rule itself is unchanged.

**Limits, known in advance:**
- A quoted half-spread is what a small market order pays. The shadow book trades about $2,000 a
  name, well inside the quoted size. A larger book would also move the price.
- The spread is measured on 90 sessions, not all 2,438.
- Quoted spreads say nothing about the opening auction itself, which has no spread.

## 3. Results

The script's picks reproduced the backtest's long and short returns exactly on all 779 gated
sessions. Minute bars priced 99.8% of the picks.

**The wait** (all 779 gated sessions; basis points per cohort, t-statistics in brackets):

| | Entry wait | Exit wait | Gained by waiting (exit − entry) |
|---|---|---|---|
| All | −6.3 (−4.3) | −0.6 (−0.5) | **+5.7 (2.8)** |
| 2017-2021 | −6.2 (−2.9) | −2.4 (−1.2) | +3.8 (1.3) |
| 2022-2026 | −6.4 (−3.2) | +1.2 (0.7) | +7.5 (2.7) |

The entry wait is negative: by 09:35 the stocks the rule buys have fallen a further 6 bp against
the ones it sells. Entry wait by year: 2018 +1.0, 2019 −2.5, 2020 −9.7, 2021 −3.1, 2022 −8.5,
2023 −8.4, 2024 +3.6, 2025 −3.7, 2026 −2.1.

**The spread** (quoted half-spread of the picks, basis points):

| Sessions | At 09:35: average | At 09:35: middle name | Just after the open: average | Just after the open: middle name | ETFs at 09:35 |
|---|---|---|---|---|---|
| 60 gated (VIX ≥ 20) | **10.9** | 8.5 | 16.1 | 12.6 | 0.9 |
| 30 calm | 9.7 | 7.4 | 15.8 | 12.3 | 0.8 |

On gated sessions at 09:35:
- **Longs and shorts cost the same:** 10.7 and 11.1 bp.
- **The halves agree:** 10.6 bp (27 sessions in 2017-2021) and 11.1 bp (33 in 2022-2026).
- **Sessions ranged** from 7.4 to 23.4 bp.
- **Across names:** a tenth are under 2.2 bp, half under 8.2 bp, a tenth over 22.9 bp. 13% are over
  20 bp. The cap of 100 bp almost never applied, and nearly every name had a quote.
- **Tightest:** AAPL 1.0, MSFT 1.1, KO 1.3. **Widest:** TDG 53, WIX 44, HUBS 39.

**Re-priced, per cohort** (basis points):

| | Backtest as assumed | As the slot trades |
|---|---|---|
| Priced at | the open | 09:35 |
| Spread before costs | 55.7 | 61.4 |
| Cost per stock trade | 5.0 | 10.9 |
| Cost per cohort | 26.0 | 49.5 |
| **Net** | **+29.7** (t 1.5) | **+11.9** (t 0.6) |
| Net, 2017-2021 | +37.4 | +18.8 |
| Net, 2022-2026 | +22.3 | +5.4 |
| Return on capital a year | +4.3% | about +1.7% |

The edge is gone at a half-spread of 13.9 bp; the measured one is 10.9.

## 4. Reading

1. **5 bp was not fair.** The picks cost 10.9 bp each way at 09:35, more than twice the assumption.
   - **It is the stocks, not the stress.** Calm sessions are nearly as wide (9.7 bp). The rule picks
     the stocks that moved most, and those are the volatile ones, with many low-priced or very
     high-priced names among them.
   - **It is also the time of day.** Thirty seconds after the open the same names cost 16 bp.
2. **The rule still passes its test by the letter, and no more than that.**
   - Re-priced, it is positive in both halves: +18.8 and +5.4 bp.
   - But t is 0.6, and the margin is 3 bp of half-spread.
   - The pass depends on the 5.7 bp gained by waiting. Without it the net is +6.2 bp, and the second
     half is −2.1 bp.
   - **As the slot trades today, with market orders at 09:35, the rule has no demonstrable edge.**
3. **Waiting does not cost; it gains about 6 bp.** The stocks that fell keep falling against the
   ones that rose for the first five minutes. So the reason given in advance for testing the opening
   auction (a wait costing over 10 bp) does not apply.
4. **The spread gives a different reason to test the auction.** This was not planned, so it is a
   lead and not a result.
   - The opening auction has no spread. If the picks could be filled there at about the backtest's
     open, a cohort would cost about 6 bp, not 49.5, and would net roughly +50 bp, not +12.
   - **That is not shown here.** The backtest's open is the daily bar's open, which is close to the
     auction price but not the same. On 9 April 2025, of 8 names checked, 3 matched the auction
     print exactly, 4 differed by 1 to 19 bp, and 1 had no auction print in the first minute.

**One limit found afterwards.** The wait was measured from the first minute bar's open, as fixed in
section 2. The backtest uses the daily bar's open. The two differ by a few basis points on some
names. Whether that differs between longs and shorts was not measured, so the 5.7 bp carries that
doubt. The spread result does not depend on it.

## 5. Verdict and next step

- **The backtest's +29.7 bp per cohort overstated what the slot can earn as it trades.** With
  measured spreads it is +11.9 bp, t 0.6.
- **The rule is not changed and the slot keeps running** as observation. From 10 November every
  simulated fill is stored with its bid and ask (feature 25), so the live record can be re-priced
  at real spreads fill by fill.
- **Proposed next test, to be fixed in writing first:** price every cohort at the official opening
  auction prints on all 779 gated sessions. If the auction price matches the backtest's open, the
  rule's problem is how it is executed, and auction orders (`opg`, which Alpaca supports) fix it.
  If it does not match, the backtest's gross spread is itself in doubt.
- **Separate finding the same day:** the price panel behind this backtest is missing stocks
  delisted since late 2022 (docs/research/2026-11-09-panel-survivorship-gap.md). The numbers on
  this page inherit that gap.
