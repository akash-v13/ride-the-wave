# Signals A, C and D: sector-stress reversal, overnight momentum, turn of the month

**Sections 1 to 4 were written on 10 November 2026 before any of the three was run.** The owner
chose these three from the shortlist (docs/strategies/2026-11-09-signal-shortlist.md) and confirmed
the target: a yearly Sharpe ratio of 1.4, ideally above 2. Results are in section 5 onward.

Each signal gets **one configuration and one pass test**, fixed here. Nothing is re-run with other
settings if it fails. These are looks 22, 23 and 24 of the project.

## 1. Rules common to the three

- **Prices.** The repaired daily panel (adjusted, 2016-01 to 2026-09-22) for stocks and ETFs; Ken
  French's daily market returns (1926-07 to 2026-09) for the long history.
- **Universe (A and C).** The 300 most-traded company stocks, re-chosen each month from the month
  before (the same universe as the stat-arb studies).
- **Halves.** 2017-2021 and 2022-2026 for A and C. D has its own periods (section 4).
- **t-statistics.** Newey-West, so overlapping or neighbouring results are not counted as
  independent.
- **Costs.** 1 bp per stock trade at an opening or closing auction (the allowance adopted on
  9 November); 5 bp per cohort for hedges and 1 bp for borrowing where there are shorts.

## 2. Signal A: sector-stress reversal

**Checked against the source.** No paper tests this exact rule. It extends our own finding that
residual reversal pays when the market is stressed (VIX 20 or above).

**Stress.** For each of the 11 sector ETFs, at each close:

$$x_s(t) = \Big|\sum_{j=0}^{4}\big(r_{s,\,t-j} - r_{\text{SPY},\,t-j}\big)\Big|$$

The sector is stressed at $t$ when $x_s(t)$ is at or above the 90th percentile of its own values
over the 252 sessions before $t$ (at least 200 needed).

**The trade.** On session $d$, using everything known at the close of $d-1$:
1. Only if VIX closed **below 20** on $d-1$. These are the days the rule we have does not trade.
2. Take the sectors stressed at $d-1$ that have at least 10 universe stocks with a signal.
3. Inside each one, rank its stocks on the 5-session residual $s_i$. Buy the lowest fifth, short the
   highest fifth.
4. The day's cohort is all those picks together, equal weight per name. It needs at least 4 names a
   side.
5. Enter at the open of $d$, exit at the open five sessions later, hedged with SPY and the sector
   ETFs exactly as the VIX rule is.

**Result per cohort.** The bought names' average hedged return minus the sold names', less
$4\times1 + 5 + 1 = 10$ bp.

**Pass:** average net result above zero with t of at least 2 (4 lags), and above zero in both halves.

**Reported for context, not for choosing:** the same picks in sectors that are not stressed (VIX
below 20), and in stressed sectors when VIX is 20 or above.

## 3. Signal C: momentum held overnight only

**Checked against the source.** Lou, Polk and Skouras (2019, *Journal of Financial Economics* 134)
find that momentum's abnormal return is earned overnight: about 0.95% a month for a portfolio that
buys the top tenth and **shorts the bottom tenth**, roughly 4.5 bp a night. Our version only buys
(the top 30%) and is measured against its universe, so the paper itself suggests well under half of
that. The 4 bp bar below is set by the cost, not by the paper, and the paper says it will be hard
to clear. It stays as written in the shortlist.

**Signal.** For the night from the close of $t$ to the open of $t+1$, each stock's return from 252
to 21 sessions before $t-1$ (an order for the closing auction is sent before the close, so the last
price used is yesterday's):

$$m_i = \frac{C_{t-22}}{C_{t-253}} - 1$$

**The trade.** Buy the 30% of universe stocks with the highest $m_i$ at the close of $t$, sell at
the open of $t+1$.

**Result per night.**

$$x_t = \overline{r^{\text{night}}}_{\text{winners}} - \overline{r^{\text{night}}}_{\text{universe}}$$

An overnight move beyond ±50% is treated as a data error and left out; the count is reported, and
the result with them left in.

**Pass:** $x_t$ averages **at least 4 bp** a night; $x_t - 2$ bp (two trades) has t of at least 2
(5 lags); and $x_t - 2$ bp is above zero in both halves.

**Reported for context:** the winners' own overnight and daytime returns, the losers' (bottom 30%),
and the universe's.

## 4. Signal D: turn of the month

**Checked against the source.** McConnell and Xu (2008, *Financial Analysts Journal* 64(2)): over
1926-2005 the US market returned 0.15% a day on the last trading day of a month and the first three
of the next, and −0.001% a day on all other days. Their data end in 2005, so **2006 onward is a
period the authors never saw**. That is the test.

**Turn days.** The last trading day of each month and the first three of the next, from the data's
own calendar.

**Statistic.** The market's average daily return above cash on turn days minus its average on all
other days, in bp a day ($b$ in $r^e_t = a + b\,\text{Turn}_t + \varepsilon_t$, 5 lags).

**Pass, all three:**
1. **Replication, 1926-07 to 2005-12:** $b$ above zero with t of at least 2. This only shows the
   code finds what the paper found.
2. **Unseen period, 2006-01 to 2026-09:** $b$ above zero with t of at least 2.
3. $b$ above zero in each half of the unseen period: 2006-2015 and 2016-2026.

**Reported for context:** the rule as it would trade (the market on turn days, cash otherwise, 2 bp
per turn) with its Sharpe ratio; SPY from Alpaca over 2017-2026, bought at the close two days before
month-end and sold at the close of the third day; each day from −5 to +5 (to describe, not to pick
a better window).

---

## 5. Results at a glance (run 10 November 2026, after sections 1 to 4)

| Signal | The statistic | Result | Pre-set test | Verdict |
|---|---|---|---|---|
| A. Sector-stress reversal | Net per cohort, calm markets | **−28.6 bp** (t −2.1) | Above zero, t ≥ 2, both halves | **Fails.** It loses |
| C. Momentum overnight | Winners beyond universe, per night | **+3.76 bp** (t 4.3); +1.76 after costs (t 2.0) | At least 4 bp; t ≥ 2 after costs; both halves | **Fails the 4 bp bar by 0.24 bp.** Passes the other two |
| D. Turn of the month | Turn days minus other days, 2006-2026 | **+0.8 bp a day** (t 0.2) | Above zero with t ≥ 2 | **Fails.** The effect is gone |

None of the three passes as written. C is the only one with something in it. Nothing was re-run
with other settings. The project has now taken 24 looks.

## 6. Signal D: the turn of the month has faded away

`scripts/research_turn_of_month.py`; Ken French daily market returns above cash, 1926-07 to 2026-09.

| Period | Turn days | Other days | Difference | t | Turn days |
|---|---|---|---|---|---|
| 1926-2005 (the paper's years) | +14.8 bp a day | +0.2 | **+14.6** | 8.0 | 3,816 |
| **2006-2026 (unseen)** | +5.0 | +4.2 | **+0.8** | **0.2** | 995 |
| 2006-2015 | +3.8 | +3.2 | +0.6 | 0.1 | 480 |
| 2016-2026 | +6.1 | +5.1 | +1.0 | 0.2 | 515 |

- **The code finds what the paper found:** 14.8 bp a day against 0.2 (the paper: 15 against 0).
- **Since the paper's data end, turn days are ordinary days.** The difference fell decade by decade:

| 1920s | 1930s | 1940s | 1950s | 1960s | 1970s | 1980s | 1990s | 2000s | 2010s | 2020s |
|---|---|---|---|---|---|---|---|---|---|---|
| +20.9 | +19.8 | +16.5 | +17.5 | +11.6 | +11.2 | +15.0 | +9.5 | +5.6 | +1.2 | +3.5 |

- **As it would trade** (the market on turn days, cash otherwise, 2 bp per turn):

| | Return above cash a year | Sharpe | The market's Sharpe | Share of the market's excess return, earned in 19% of days |
|---|---|---|---|---|
| 1926-2005 | +6.5% | 0.96 | 0.43 | 95% |
| 2006-2026 | +2.2% | 0.26 | 0.56 | 22% |

- **SPY from Alpaca, 2016-2026:** 128 turns, +28.1 bp per turn after costs (t 1.7, 60% won), against
  +24.9 bp for any four days. No different from holding SPY on ordinary days.
- **An observation, not a result.** In 2006-2026 the three days *before* the window (−4, −3, −2)
  averaged +20.6, +9.0 and +12.4 bp, and day −1 −3.0. That would fit buyers moving earlier once the
  effect was known. It was seen after the test, in a table with ten cells, so it counts for nothing
  until it is written down as its own candidate and tested on data not used here.

**Verdict: rejected.** A century of evidence, and none of it from the last twenty years.

## 7. Signal C: the overnight effect is real, and just short of its bar

`scripts/research_overnight_momentum.py`; 2,441 nights, 4 January 2017 to 21 September 2026; 294
stocks a night on average, 89 winners.

| | All | 2017-2021 | 2022-2026 |
|---|---|---|---|
| Winners beyond universe, a night | **+3.76 bp** (t 4.3) | +2.34 (t 2.3) | +5.26 (t 3.7) |
| After 2 bp of costs | **+1.76 bp** (t 2.0) | +0.34 | +3.26 |
| Nights the winners were ahead | 57% | 58% | 57% |

| Test | Needed | Got | |
|---|---|---|---|
| Average beyond universe | at least 4 bp | 3.76 bp | **Fails by 0.24 bp** |
| t after costs | at least 2 | 2.02 | Passes |
| Above zero after costs in both halves | yes | +0.34 / +3.26 | Passes |

- **Every year was positive before costs** (2017 to 2026: +2.7, +1.4, +0.7, +2.0, +4.8, +5.5, +1.5,
  +5.7, +5.1, +9.7 bp). After costs 2018, 2019 and 2023 were slightly negative.
- **The paper's pattern is there in full.** Average return in bp:

| | Winners | Universe | Losers | Winners minus losers |
|---|---|---|---|---|
| Overnight (close to open) | **+9.20** | +5.45 | +3.21 | **+5.99** (t 3.8) |
| Daytime (open to close) | +0.09 | +0.80 | +1.58 | −1.49 |

  Winners earned everything overnight and nothing by day. Losers did the opposite.
- **A wider fact:** nearly all of these 300 stocks' return in 2017-2026 came overnight: +5.45 bp a
  night against +0.80 bp a day.
- **The rule as it would trade** (winners overnight, cash by day, 2 bp a night): +15.6% a year above
  cash, volatility 16.8%, Sharpe 0.93 (1.15 and 0.71 by half). Most of that is the market's own
  overnight return; the universe held overnight has a Sharpe of 0.46. The part that is the signal,
  the winners beyond the universe after costs, has a Sharpe of about 0.65.
- **Data errors:** 19 overnight moves beyond ±50% were left out. With them in: +3.90 bp, still
  under 4.

**Verdict: fails as written, narrowly. Not promoted.** The bar was fixed at twice the cost before
the data was opened and is not moved afterwards. What the test cannot settle:
- **The cost.** 1 bp a trade is an allowance, not a measurement. Whether the daily bar's close is
  the closing auction price has not been checked the way the open was.
- **The risk.** The rule holds the whole market's overnight gap risk every night.
- **Overlap.** It is momentum again, so it will win and lose with the momentum book.

## 8. Signal A: sector stress does not bring the reversal; in calm markets it loses

`scripts/research_sector_stress.py`. A sector was stressed on 11.6% of its days, as designed; some
sector was stressed on 57% of sessions.

| | Cohorts | Names a side | Gross | Net | t | Halves (net) |
|---|---|---|---|---|---|---|
| **Stressed sectors, VIX below 20 (the test)** | 706 | 13 | −18.6 bp | **−28.6 bp** | −2.1 | −38.5 / −18.2 |
| Context: other sectors, VIX below 20 | 1,659 | 52 | 0.0 | −10.0 | −1.6 | −10.9 / −9.1 |
| Context: stressed sectors, VIX 20 or above | 427 | 16 | +85.7 | +75.7 | 2.5 | +147.6 / +6.1 |

- **Net by year (the test):** negative in every year from 2017 to 2025 (−46, −17, −31, −139, −57,
  −262, −56, −5, −26 bp), +18 in 2026. 45% of cohorts made money.
- **What happened is what the shortlist warned of.** When a sector is hit while the market is calm,
  the stocks that fell most kept falling, and the ones that rose most kept rising. That is news
  being absorbed, not forced selling that snaps back.
- **The reversal belongs to market-wide stress.** With VIX at 20 or above it is strongest inside
  stressed sectors, but nearly all of that came in 2017-2021 (+147.6 against +6.1 bp), and those are
  days `sa_volrev` already trades. It is the same fish, not a new one.
- **Not a signal in reverse either:** the opposite trade would gross 18.6 bp against 10 bp of costs,
  and it was not the question asked.

**Verdict: rejected.**

## 9. Reading

1. **Two clean rejections and one near miss** from three candidates given about a 30% chance each.
   That is roughly what the odds said.
2. **D shows why "unseen years" matter.** A t of 8 over eighty years and nothing since publication.
   Calendar effects that are public and cheap to trade should be assumed gone until shown otherwise.
   The same will apply to signal E (Fed days), whose paper was published in 2015.
3. **A narrows the stat-arb story.** Reversal is paid for by market-wide stress, not by any stress.
   Sector conditions are not a second trigger.
4. **C is a lead, alongside momentum.** It is the strongest ranking result in the project so far
   (t 4.3 before costs, positive in all ten years), and it lives where costs are lowest, at the two
   auctions. It did not clear a bar set at twice its cost.

**Next:** signals E, B and F. E needs the list of Fed announcement dates. B needs earnings dates
that were known in advance. F uses the news already scored. Whether C is observed in a shadow slot
anyway is the owner's decision; it needs a slot that trades at the close and again at the next open,
which does not exist yet.
