# Statistical arbitrage: would filling at the opening auction restore the edge?

**Run 9 November 2026, night.** The owner's go-ahead after the cost study and the panel repair. Code:
`scripts/research_statarb_auction.py`, `src/ridethewave/daily/costs.py`. Results:
`data/research/statarb/auction_*`.

## 1. Why

On the repaired price panel the VIX-gated reversal rule earns +50.9 bp per cohort before costs. As
the shadow slot trades it, with market orders at 09:35, the spread on four trades takes 43 bp of
that and the rule nets +7.5 bp (t 0.4): no edge (docs/research/2026-11-09-statarb-costs.md,
section 6).

The opening auction is the one way to trade these stocks without paying a spread. Every stock is
crossed at a single price, and an order sent before the open (`opg`, which Alpaca supports) is
filled at it. The backtest "enters at the open", but its open is the daily bar's open, which a spot
check showed is close to the auction price and not the same. So the question is narrow:

**If every trade were filled at the official opening auction price, what would the rule earn?**

## 2. What was fixed before running

**The picks.** The repaired backtest's own, configuration A, on all 779 volatile sessions. The
script first checks that its picks reproduce the backtest's saved returns exactly.

**The auction price.** Alpaca's history of auction prints gives, for each stock and day, every
opening print with its size. A stock's auction price is the price of its **largest** opening print:
the cross on its listing exchange. Smaller prints are other venues' own openings. A stock with no
opening print that day is left out and counted.

**The gap.** For each stock on each day: auction price ÷ the daily bar's open (unadjusted) − 1.
Hedged as in the backtest, with SPY's and the sector ETFs' own gaps.
- **Entry gap** = the longs' average hedged gap minus the shorts', on the entry day.
- **Exit gap** = the same for the same picks on the exit day, five sessions later.
- **Auction-priced spread** = the backtest's spread − entry gap + exit gap.

**Amended before the full run: the hedges are not re-priced.** (The reason given here was wrong;
see section 6.) A one-day trial showed that Alpaca's
auction history has no opening prints for SPY and the sector ETFs in many later years (present in
2018 and 2020, absent in 2022 and 2025). So the hedge legs stay at the backtest's price, the daily
open, and only the stocks are re-priced at their auctions. The ETFs' gaps are set to zero. The hedge
charge of 5 bp is unchanged.

**Costs at the auction.** No spread is paid. Per cohort: 1 bp for each of the four stock trades as
an allowance for fees and for moving the auction price, plus the backtest's 5 bp for hedges and
1 bp for borrow. 10 bp in all, against 49 bp for market orders at 09:35.

**How the result will be read:**
1. **Does the daily open stand in for the auction?** Yes if the entry and exit gaps are each within
   3 bp per cohort.
2. **Does the rule pass?** The same test as before: net profit after costs in both halves
   (2017-2021 and 2022-2026). The t-statistic is reported beside it.
3. **What follows.**
   - If it passes with at least +20 bp per cohort: propose that the shadow slot decide before the
     open and book its fills at the auction price. The owner decides.
   - If it fails: stat arb in this form is closed until there is older data to test it on.

**This is one more look at the same decade.** It changes how the rule is executed, not what it
picks, but it is counted: 18 looks in stage 1, 2 configurations in stage 2a, and this.

**Limits, known in advance:**
- History shows the auction price, not whether our order would have been part of the auction. For
  orders of about $2,000 in liquid stocks that is a safe assumption, and it cannot be proved on a
  paper account.
- The allowance of 1 bp a trade is an assumption.
- The price panel's remaining holes apply (docs/research/2026-11-09-panel-survivorship-gap.md).

## 3. Results

The picks reproduced the repaired backtest exactly on all 779 volatile sessions (92,081 picks).

**Is the daily open the auction price?**
- **Stock by stock, often not:** 60% of picks opened at exactly the daily bar's open. For the rest
  the two differ, by 9 bp on average and by more than 28 bp for a tenth of them. Stocks listed on
  the New York Stock Exchange often open a minute or two late on volatile days, and the daily bar's
  open is then an earlier print elsewhere.
- **Long against short, yes:** the differences cancel.

| Basis points per cohort (t) | Entry gap | Exit gap |
|---|---|---|
| All | +0.0 (0.2) | −0.2 (−1.3) |
| 2017-2021 | −0.0 (−0.1) | −0.4 (−1.5) |
| 2022-2026 | +0.1 (0.5) | −0.1 (−0.3) |

Both are well inside the 3 bp set in advance. The backtest's daily open stands in for the auction.

**The rule priced at the auction** (basis points per cohort):

| | Market orders at 09:35 | At the opening auction |
|---|---|---|
| Spread before costs | 56.6 | 50.6 |
| Cost per cohort | 49.1 | 10.0 |
| **Net** | **+7.5** (t 0.4) | **+40.6** (t 2.0) |
| Net, 2017-2021 | +14.0 | +47.7 |
| Net, 2022-2026 | +1.4 | +33.7 |

- **Return on capital:** about +6% a year. Added up by month from 2017, the auction-priced cohorts earn
  +6.5% a year with 9.2% volatility: a Sharpe of 0.71 and a worst drawdown of −7.1%, idle in four
  months out of ten. (Scaling the backtest's +3.6% at +24.9 bp gives +5.9%; it counts 2016, when
  nothing traded.)
- **The edge is gone** at 11 bp per stock trade. The allowance used is 1 bp.
- **Net by year:** 2018 +49, 2019 −18, 2020 +83, 2021 −25, 2022 +14, 2023 +16, 2024 +1,
  2025 +131, 2026 +34.

**Coverage** (wrong, corrected in section 6: the prints exist). Alpaca's auction history had an opening print for 92% of picks: nearly all until 2020,
then about three quarters of New York Stock Exchange stocks from 2022 (Nasdaq stocks stay near
100%). Those stocks did have an opening auction; the history simply lacks the print. Their gap is
unmeasured and assumed to be like the others'.

## 4. Reading

1. **The rule passes the test set in advance:** positive in both halves, +40.6 bp per cohort, above
   the +20 bp needed to propose a change.
2. **How it is executed decides everything.** The same picks earn +7.5 bp with market orders at 09:35
   and +40.6 bp at the auction. The stocks this rule picks are expensive to cross the spread in, and
   the auction is the one place where nobody pays it.
3. **It is still thin evidence.**
   - t is 2.0, after 21 looks at one decade.
   - Two years still carry it: 2020 and 2025. 2019 and 2021 lost.
   - The second half's coverage has the gap described above.
   - The 1 bp allowance and "our order is in the auction" are assumptions. A paper account cannot
     prove either, because it does not send orders to a real auction.

## 5. Verdict and next step

- **Done 9 November, approved by the owner; in effect from the 10 November start**
  (docs/features/24-statarb-volatility-gated.md). As proposed: change the shadow slot `sa_volrev` to decide before the
  open and book each fill at that stock's opening auction price, in place of 09:35 and a flat 5 bp.
  The picks do not change. Its record from that day would be the record of the rule as this page
  prices it.
- **If that is done, what it needs:** the decision moved to before 09:28 ET (the signal uses
  yesterday's close, so nothing is lost), fills booked from the auction prints once they exist, and
  a rule for a stock with no print.
- **Not proposed:** live orders. That still needs the borrow checks and fill reconciliation listed
  on the feature page.

## 6. Correction, 10 November 2026: the missing prints were a reading error

**Found on the slot's first auction-priced session.** At 09:35 on 10 November only 114 of 266
symbols were priced at the auction, and every New York Stock Exchange stock was missing. The prints
were in Alpaca's history. The code was losing them.

**The cause.** A request for one day's auctions can return two rows for a symbol. NYSE- and
ARCA-listed symbols carry a late closing print stamped 20:00 New York time. In winter that is 01:00
UTC on the next date, so the day before comes back first, with no opening prints, and the code read
the first row. It failed from Tuesday to Friday between November and March, for NYSE stocks and
for the ETFs. Rows are now matched on their own date (`daily/costs.auction_day`), in the bot and in
the study, with tests.

**What was wrong on this page.**
- "An opening print for 92% of picks" and "about three quarters of NYSE stocks from 2022": with the
  corrected reader **99.9%** of picks have a print.
- "No opening prints for SPY and the sector ETFs in many later years": they have them. The
  amendment in section 1 rested on this error.

**Re-run, corrected, nothing else changed:**

| | As published | Corrected reader | Corrected, hedges at their auctions too (the design as first written) |
|---|---|---|---|
| Picks with a print | 92% | 99.9% | 99.9% |
| Entry gap, per cohort | +0.0 bp | −0.0 bp | −0.1 bp |
| Exit gap, per cohort | −0.2 bp | −0.3 bp | −0.3 bp |
| **Net at the auction** | **+40.6 bp (t 2.0)** | **+40.6 bp (t 2.0)** | **+40.7 bp (t 2.0)** |
| Halves | +47.7 / +33.7 | +47.5 / +34.0 | +47.6 / +34.0 |

**The verdict does not change.** The published result was right for a wrong reason: the 8% of picks
it could not price turned out to be like the rest. Old outputs are kept in
`data/research/statarb/before-dayfix-2026-11-10/`.

**The 10 November session.** 59 fills were booked at the auction price and 52 at the day's first
trade (the fallback). Against the true auction prices, read afterwards, the fallback fills differed
by 0 bp at the median and cost the slot about 1 bp of their value in total (about $45). The record
is left as booked. From 11 November the reader is correct.
