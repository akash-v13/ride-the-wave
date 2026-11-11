# Signals B and G: reversal around earnings, and news carrying related stocks

**Sections 1 to 3 were written on the evening of 10 November 2026 before either was run.** B is the
last of the six shortlist signals. G is the owner's idea of 10 November, written up as a candidate at
the end of docs/strategies/2026-11-09-signal-shortlist.md. One configuration and one pass test each.
These are looks 28 and 29 of the project.

## 1. Rules common to both

- **Prices.** The repaired daily panel; the 300 most-traded company stocks, re-chosen each month.
- **t-statistics.** Each day's trades are averaged first, then Newey-West with 4 lags, so trades
  made on the same day are not counted as independent.
- **Costs.** 1 bp per trade at an auction; 5 bp for a hedge; 1 bp to borrow for a short.
- **No second version.** If a test fails, the signal is recorded as failed.

## 2. Signal B: reversal around earnings

**Checked against the source, and the shortlist had it wrong.** So and Wang (2014, *Journal of
Financial Economics* 114, "News-driven return reversals: liquidity provision ahead of earnings
announcements") report that short-term reversal pays about six times as much around earnings
announcements as at other times. As summarised by secondary sources (I could not open the paper's
full text), stocks are sorted on their returns over the three days from four to two days before the
announcement, and the reversal is earned over the three days **around** it, the announcement day
included. The explanation is that firms which take the other side of trades are paid for carrying
positions *through* the report.

The shortlist said "be out before the report". That is not what the paper found, and it has no
published support. **The test below follows the paper.** The shortlist's version is reported beside
it for context only.

**Report days.** From the SEC's filings: each company's 8-K with item 2.02 ("Results of Operations"),
with the minute it was accepted (`src/ridethewave/data/edgar.py`).
- **The report day $R$** is the first session that could trade on it: the same day when accepted
  before 16:00 New York time, otherwise the next session.
- **One per quarter:** where a company filed more than once within 45 days, the last is used. An
  earlier one is usually a preliminary announcement that nobody could have traded ahead of.
- **Assumed:** the date was known two sessions ahead. Companies announce their report dates weeks
  ahead, so this is nearly always true, but the test uses the dates as they happened.

**Signal.** The stock's own moves (residuals after SPY and its sector ETF) added over the three
sessions $R-4$, $R-3$, $R-2$.

**Picks.** At the close of $R-2$, a reporting stock is **bought** if its signal is in the lowest
fifth of the whole universe's that day, and **shorted** if it is in the highest fifth. Others are
left alone.

**The trade.** Enter at the close of $R-2$, exit at the close of $R+1$: three sessions, through the
report. Hedged with SPY and the sector ETF.

**Result per trade.** The hedged return for a purchase, its negative for a short, less 5 bp (half
of the 10 bp charged to a long-short pair elsewhere).

**Pass, all four:**
1. At least 1,000 trades.
2. The average net result is above zero.
3. Its t is at least 2.
4. Above zero in both halves: 2017-2021 and 2022-2026.

The paper's data end in 2011, so every year tested here is one the authors did not see.

**Reported for context:**
- the same picks and holding period for stocks with **no** report within ten sessions (ordinary
  reversal; the paper's claim is that B is several times larger);
- the shortlist's version: signal over the five sessions to the close of $R-4$, in at the open of
  $R-3$, out at the close of $R-1$, before the report.

## 3. Signal G: news about one stock carrying its related stocks

**Checked against the source.** Cohen and Frazzini (2008, *Journal of Finance* 63, "Economic links
and predictable returns"): prices are slow to reflect news about economically related firms; buying
the suppliers of firms with good news and shorting those of firms with bad news earned over 1.5% a
month. Their links come from company filings and their horizon is a month. This test uses
statistical links and a three-day horizon, so it is our own rule, not theirs.

**Events.** A stock-day $(A, d)$ counts when:
- $A$ had at least one headline that day that our scoring called relevant, not stale, and material
  (expected materiality of at least 1 on the 0-to-2 scale); a headline after 16:00 belongs to the
  next session;
- $A$'s own move that day (its residual) was at least twice its usual size (the standard deviation
  of its residuals over the 60 sessions before);
- the scored news covers the 100 most-traded stocks, 2019 to 2026, so $A$ comes from those.
A second event in the same stock within three sessions is ignored.

**Related stocks.** The ten universe stocks (the top 300 that month, $A$ left out) whose daily
returns beyond the market moved most closely with $A$'s over the 252 sessions before $d$. Chosen
from past prices only, so nothing about which stocks "belong together" comes from hindsight.

**The trade.** In the direction of $A$'s move: buy the ten if $A$ jumped, short them if it fell. In at
the open of $d+1$, out at the open of $d+4$. Equal weights, hedged with SPY only (a sector hedge
would remove the thing being tested).

**Result per event.** The ten stocks' average market-hedged return, signed by $A$'s direction, less
7 bp (two auction trades and the hedge).

**Pass, all four:**
1. At least 500 events.
2. The average net result is above zero.
3. Its t is at least 2.
4. Above zero in both halves: 2019-2022 and 2023-2026.

**Reported for context:** how much the ten had already moved on day $d$ itself; the first day alone;
jumps and falls separately; $A$'s own continuation.

**What this version cannot say.** It trades the next morning. The owner's picture is of entering
during the same day, which needs intraday prices and the news read as it arrives. If the daily
version shows nothing, the move may simply be over by the next open; the "already moved on day $d$"
number is there to show that.

---

## 4. Results at a glance (run 10 November 2026, after sections 1 to 3)

| Signal | The statistic | Result | Pre-set test | Verdict |
|---|---|---|---|---|
| B. Reversal around earnings | Net per trade, held through the report | **+1.3 bp** (t 1.0); halves −32.6 / +35.6 | Above zero, t ≥ 2, both halves | **Fails** |
| G. News carrying related stocks | Net per event, next open to three sessions later | **−0.1 bp** (t 0.5) | Above zero, t ≥ 2, both halves | **Fails as tested.** The move is over by the next open |

29 looks so far.

## 5. Signal B: no extra reversal around earnings in these stocks

`scripts/research_earnings_reversal.py`. Report days: 36,161 filings from the SEC for 1,031 of the
1,151 stocks ever in the monthly top 300 (`scripts/download_earnings_dates.py`). The 120 without
any are mostly foreign companies, which report on a different form. After keeping one report a
quarter and only universe members: 10,671 reports, about 1,040 a year.

| | Trades | Average net | Median | t | Won | Bought | Shorted | Halves |
|---|---|---|---|---|---|---|---|---|
| **Through the report (the test)** | 3,513 | **+1.3 bp** | +13.8 | 1.0 | 51% | +12.4 | −9.2 | −32.6 / +35.6 |
| Context: same picks, no report near | 202,959 | −1.1 | −1.3 | −0.1 | 50% | −3.9 | +1.7 | −2.3 / +0.2 |
| Context: out before the report (the shortlist's version) | 3,434 | +2.4 | +3.0 | −0.1 | 50% | +4.5 | +0.4 | −0.6 / +5.3 |

- **Before costs** the test earned 6.3 bp a trade, against 3.9 bp for the same picks on ordinary
  days. The paper's sixfold difference is not there in the 300 most-traded stocks since 2017.
- **By year** it swings without pattern: −27, −29, +14, −16, −117, +95, +98, +23, −98, +62 bp
  (2017 to 2026).
- **Holding through a report is noisy.** A typical trade moves several percent either way, so 3,500
  trades cannot separate 6 bp from zero.
- **Getting out before the report earns nothing either** (+2.4 bp, t −0.1).

**Verdict: fails.** Possible reasons, none tested: the effect was measured to 2011 and on all
stocks, where the firms taking the other side were scarcer; in today's most-traded names that
service is cheap.

**A by-product worth keeping:** a clean, time-stamped earnings calendar for the universe from 2016,
from the official source. Any later rule that must avoid or target report days can use it.

## 6. Signal G: the related stocks do move, on the same day

`scripts/research_related_news.py`. 27,376 stock-days with material news; 3,528 of them with a move
of twice the usual size; 3,208 events after spacing and data checks, on 1,411 days.

| | Events | Average net | t | Won | Halves |
|---|---|---|---|---|---|
| **All events (the test)** | 3,208 | **−0.1 bp** | 0.5 | 48% | −2.3 / +2.0 |
| Context: after a jump | 1,689 | +1.8 | 0.9 | 48% | −4.3 / +7.5 |
| Context: after a fall | 1,519 | −2.2 | 0.2 | 48% | −0.2 / −4.2 |

**When the related stocks moved** (average, in the direction of the news stock, market taken out):

| On the day of the news | The next session, open to close | Next open to three sessions later |
|---|---|---|
| **+76.4 bp** | +5.7 bp | +6.9 bp before costs |

- **The link is real.** On the day a stock jumps or falls on news, its ten related stocks move 76 bp
  the same way, and they do so on two days out of three.
- **By the next morning it is finished.** What is left over three sessions is 7 bp, the cost of
  trading it.
- **The related stocks are found from prices alone.** For Nvidia in summer 2026 the ten were CoreWeave,
  TSMC, Oracle, Vertiv, Broadcom, Credo, Nebius, Celestica, AMD and Fabrinet: the AI infrastructure
  group, without anyone naming it.
- **The news stock itself** drifted +5.0 bp further in its own direction over the three sessions.

**Verdict: fails as tested.** The daily version arrives after the move.

## 7. Reading

1. **All six shortlist signals have now had their test, and G one.** None passes. C (momentum held
   overnight) is the one lead.
2. **G's failure is informative.** It says where the profit would have to be: inside the news day,
   between the first stock's move and the related stocks catching up. That is the owner's picture
   ("enter before it starts normalising"). Whether there is a gap to trade there depends on how fast
   the related stocks follow: minutes or hours. The daily data cannot tell.
3. **The next test is G inside the day** (run the same night: 2026-11-10-signal-g-intraday.md; it fails,
   the related stocks follow within minutes). As first sketched here:
   - headlines published while the market is open, with their time;
   - the news stock's move in the first minutes after;
   - the related stocks' move from then to the close, from minute bars;
   - costs at real intraday spreads, which are several bp a trade, not 1 bp.
   The same-day total is 76 bp, so there is room; how much of it comes after a tradable moment is
   the question.
