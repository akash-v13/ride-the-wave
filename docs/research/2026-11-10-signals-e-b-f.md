# Signals E, B and F: Fed announcement days, reversal before earnings, bounce after an offering

**Sections 1 to 4 were written on 10 November 2026 before any of these was run.** They are the
second half of the shortlist (docs/strategies/2026-11-09-signal-shortlist.md); the first half is in
2026-11-10-signals-a-c-d.md. Each signal gets one configuration and one pass test. These are looks
25, 26 and 27 of the project.

## 1. Rules common to the three

- **Prices.** The repaired daily panel for stocks and ETFs; Ken French's daily market returns for
  the long history.
- **t-statistics.** Newey-West, so neighbouring results are not counted as independent.
- **Costs.** 1 bp per trade at an opening or closing auction; 5 bp for a hedge.
- **No second version.** If a test fails, the signal is recorded as failed.

## 2. Signal E: Fed announcement days

**Checked against the source.** Lucca and Moench ("The pre-FOMC announcement drift", New York Fed
staff report 512, first draft September 2011; *Journal of Finance* 2015): on days of scheduled Fed
announcements the S&P 500 returned about 33 bp above cash from close to close, and about 49 bp over
the 24 hours ending 15 minutes before the announcement, in a sample that starts in September 1994
(as I recall it ends in March 2011; the summaries I could open confirm the start, not the end).

**Dates.** Every scheduled announcement from the Fed's own pages
(`config/calendars/fomc_scheduled.csv`, built by `scripts/build_fomc_dates.py`): 271 dates from 1994
to 2027, eight a year. Conference calls, unscheduled meetings and the cancelled March 2020 meeting
are left out, as in the paper.

**The trade.** Buy the market at the close the day before, sell at the close on the day.

**Statistic.** The market's average return above cash on announcement days minus its average on all
other days (Ken French daily data, 5 lags).

**Pass, all three:**
1. **Replication, 1994-09 to 2011-03:** the difference is above zero with t of at least 2. It should
   be near +33 bp.
2. **Unseen period, 2012-01 to 2026-09** (after the first draft was public): above zero with t of
   at least 2.
3. Above zero in each half of the unseen period: 2012-2018 and 2019-2026.

**Reported for context:** the day before and the day after; the rule as it would trade (2 bp per
announcement); SPY from Alpaca over 2016-2026.

**Not tested here:** the 24-hour window the paper found strongest (2 pm to 2 pm). That needs intraday
prices and is a different rule from the one on the shortlist.

## 3. Signal F: bounce after a share offering

**Checked against the source.** Corwin (2003, *Journal of Finance* 58) documents that seasoned
offerings are priced below the market. The trade is our own extension, not a published rule.

**Already seen once.** The September news study looked at all 1,571 "offering or dilution" events
that the scoring called negative: relative to peers they were +24 bp after one day and +42 bp after
five, not significant. This test is a narrower cut of the same events, so it is not a fully fresh
look.

**Events.** A stock-day counts when:
- at least one headline that day was scored as an offering (`offering_or_dilution`), relevant to the
  company and not stale (the September study's rule: relevance above 0.5, staleness below 0.5);
- a headline after 16:00 New York time belongs to the next trading day;
- the stock closed at least 5% below the previous close that day;
- the stock was in that month's scored universe (the 100 most traded, 2019 to 2026).
A second event in the same stock within five sessions of the first is ignored.

**The trade.** Buy at the open of the next session, sell at the open five sessions later, hedged
with SPY and the stock's sector ETF at the betas known on the event day.

**Result per event.** The hedged return less 7 bp (two auction trades at 1 bp, 5 bp for the hedge).

**Pass, all four:**
1. At least 100 events. Fewer cannot be judged, and the verdict is then "too few".
2. The average net result is above zero.
3. Its t is at least 2, with events grouped by entry day (4 lags).
4. Above zero in both halves: 2019-2022 and 2023-2026.

**Reported for context:** all offering events whatever the day's move; and falls of 5% or more with
no offering headline, which shows whether the offering matters or only the fall.

## 4. Signal B: reversal before earnings (design not yet fixed; waiting on dates)

The rule needs each company's report date, and whether it reported before the open or after the
close. Three sources were considered on 10 November:
- **Our scored news** (in-house). It holds dates for about 300 names from 2019, but they are noisy:
  several dates per quarter, and warnings mistaken for reports. A wrong date means holding through
  earnings, the one thing this rule must not do.
- **A public earnings calendar on the web.** It serves past dates, but only to requests dressed up
  as a browser, and it does not say before-open or after-close. Not used.
- **The SEC's EDGAR filings** (form 8-K, item 2.02, "Results of Operations"). The official record,
  free, with the time each was filed, and open to automated readers that identify themselves. This
  is the proposed source. The SEC asks for a contact address in each request, which is the owner's
  to give.

The design is written and the test run once the source is settled.

**Done the same evening:** the owner gave a contact line, the dates were read from EDGAR, and B was
tested. Design and result: 2026-11-10-signals-b-g.md. It fails (+1.3 bp a trade, t 1.0).

---

## 5. Results at a glance (run 10 November 2026, after sections 1 to 4)

| Signal | The statistic | Result | Pre-set test | Verdict |
|---|---|---|---|---|
| E. Fed announcement days | Fed days minus other days, 2012-2026 | **+5.8 bp** (t 0.6) | Above zero with t ≥ 2 | **Fails.** Faded after it was published |
| F. Bounce after an offering | Net hedged return per event | **+90.7 bp** on average, but the median is −74.5 bp (t 0.9) | Above zero with t ≥ 2 | **Fails.** One event makes the average |
| B. Reversal before earnings | | Not run | | Waiting on report dates |

27 looks so far (B will be the 28th).

## 6. Signal E: the Fed-day effect was real and is no longer there

`scripts/research_fed_days.py`; Ken French daily market returns above cash; 271 scheduled dates.

| Period | Fed days | Other days | Difference | t | Fed days | Share that rose |
|---|---|---|---|---|---|---|
| 1994-09 to 2011-03 (the paper's years) | +36.0 bp | +1.7 | **+34.3** | 3.4 | 133 | 62% |
| **2012-2026 (unseen)** | +11.1 | +5.3 | **+5.8** | **0.6** | 117 | 47% |
| 2012-2018 | +10.6 | +4.8 | +5.8 | 0.5 | 56 | 46% |
| 2019-2026 | +11.6 | +5.7 | +5.8 | 0.3 | 61 | 48% |
| 2015-2026 (after publication) | +6.7 | +4.8 | +1.9 | 0.2 | 93 | 45% |

- **The code finds what the paper found:** +34.3 bp against the paper's 33.
- **Since then the market has risen on fewer than half of Fed days.** As traded (2 bp per event) the
  rule earned +34 bp per announcement in the paper's years and +9 bp since (t 0.9), under 1% a year.
- **SPY from Alpaca, 2016-2026:** +2.8 bp on 85 Fed days against +6.3 bp on other days.
- **An observation, not a result:** since 2012 the day *after* an announcement has averaged −10.5 bp
  and the day before +12.1 bp. Seen after the test; it counts for nothing until tested as its own
  candidate.

**Verdict: rejected.** Same story as the turn of the month: strong in the years the authors studied,
gone in the years they could not see.

## 7. Signal F: too few events, and the average is one stock

`scripts/research_offering_bounce.py`. The scored news holds 1,860 offering stock-days in the 100
most-traded names; on 205 of them the stock fell 5% or more; 170 are left after spacing and data
checks.

| | Events | Average net | Median net | t | Won | Halves (average) |
|---|---|---|---|---|---|---|
| **Offering and a fall of 5% or more (the test)** | 170 | **+90.7 bp** | **−74.5 bp** | 0.9 | 46% | +105.5 / +73.3 |
| Context: every offering day | 1,341 | +3.0 | −20.5 | 0.2 | 47% | +6.6 / −0.5 |
| Context: a fall of 5% or more, no offering | 4,307 | +20.5 | −5.5 | −1.0 | 50% | +27.1 / +13.1 |

| Test | Needed | Got | |
|---|---|---|---|
| Events | at least 100 | 170 | Passes |
| Average net | above zero | +90.7 bp | Passes |
| t | at least 2 | 0.9 | **Fails** |
| Both halves above zero | yes | +105.5 / +73.3 | Passes |

- **More than half of the trades lost.** The average is positive because of a few very large
  winners: the best single event returned +89% in five sessions. Without it the average is +39 bp.
  The worst lost 29%.
- **By year** the average swings from +564 bp (2024, 17 events) to −167 bp (2025, 22 events).
- **An offering by itself changes nothing** (+3 bp over 1,341 events). A large fall without an
  offering is no better (+20 bp, t −1.0 by day).
- **These are the stocks where our cost and hedge assumptions are weakest:** heavily traded,
  volatile names raising money, often with borrowing and gap risk a daily backtest does not see.

**Verdict: fails.** It is a lottery ticket with a slightly positive average, not a repeatable
signal. A wider universe would give more events, but the scored news covers only the 100 most-traded
names, and widening it means scoring more news first.

## 8. Reading, with signals A, C and D

| Signal | Verdict |
|---|---|
| A. Sector-stress reversal | Rejected (it loses) |
| B. Reversal before earnings | Not yet run |
| C. Momentum held overnight | Near miss; in shadow |
| D. Turn of the month | Rejected (gone since 2006) |
| E. Fed announcement days | Rejected (gone since 2012) |
| F. Bounce after an offering | Fails (t 0.9; one stock makes the average) |

1. **Both calendar signals were real and both are gone.** D and E reproduce their papers almost
   to the basis point, then vanish in the years after. Published, cheap, index-level effects get
   traded away. This rules out the easiest family on the list.
2. **What is left alive is in stocks, at the auctions:** the VIX-gated reversal (in shadow, thin)
   and overnight momentum (in shadow from 11 November, a near miss).
3. **Signal A's failure points somewhere.** In calm markets the stocks hit hardest in a stressed
   sector kept falling and the strongest kept rising. That is continuation after sector news, the
   opposite of what A bet on, and it is the pattern the owner described on 10 November (news about
   one part of the market carrying its related stocks for days). It has not been tested as a rule.
   See the proposal in docs/strategies/2026-11-09-signal-shortlist.md, candidate G.
