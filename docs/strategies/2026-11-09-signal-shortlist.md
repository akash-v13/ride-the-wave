# Signal shortlist: six conditional signals to hunt

> **Results so far (10 November 2026)**, in docs/research/2026-11-10-signals-a-c-d.md. The text
> below is unchanged from before the tests.
>
> | Signal | Verdict |
> |---|---|
> | A. Sector-stress reversal | **Rejected.** −28.6 bp per cohort (t −2.1) |
> | C. Momentum overnight | **Fails its 4 bp bar by 0.24 bp.** +3.76 bp a night (t 4.3). A lead |
> | D. Turn of the month | **Rejected.** +0.8 bp a day since 2006 (t 0.2); it was +14.6 before |
> | E. Fed announcement days | **Rejected.** +5.8 bp since 2012 (t 0.6); it was +34.3 before |
> | F. Bounce after an offering | **Fails.** t 0.9; more than half the trades lost |
> | B. Reversal around earnings | **Fails.** +1.3 bp a trade (t 1.0); halves −32.6 / +35.6 |
> | G. News carrying related stocks (added 10 Nov) | **Fails as tested.** −0.1 bp (t 0.5); the related stocks move 76 bp on the news day and nothing after |
>
> E and F: docs/research/2026-11-10-signals-e-b-f.md. B and G: docs/research/2026-11-10-signals-b-g.md. A, C and D run in shadow for observation
> from 11 November (docs/features/26-shortlist-shadow-slots.md). Candidate G, proposed by the owner,
> is at the end of this page.
>
> The owner confirmed on 10 November that the 1.4 target is a yearly Sharpe ratio, ideally above 2.

**Written 9 November 2026, before any of the six was tested.** The owner's direction: hunt for
signals that repeat under stated conditions, each used only when its conditions hold, toward a
long-term Sharpe ratio of 1.4. This report has four parts:

1. The goal in numbers: what 1.4 asks for.
2. The toolkit: every formula the tests use.
3. A worked example, as questions and answers.
4. The six candidates, one page each, and what was left out.

Nothing here is a result. Each candidate is a written-down bet that still has to be tested. The
published effects are quoted from memory and are checked against the papers before each test.

---

## Part 1. The goal in numbers

**Sharpe ratio.** Average return above cash, divided by how much the return bounces around:

$$\text{SR} = \frac{\bar r - r_f}{\sigma}\times\sqrt{\text{periods a year}}$$

- $\bar r$: the average return per period (day, month or trade).
- $r_f$: what cash earns over the same period.
- $\sigma$: the standard deviation of the returns.
- The square root turns it into a yearly number: $\sqrt{252}$ for daily returns, $\sqrt{12}$ for monthly.

**"1.4 a month" can mean two things**, and they are far apart:

$$\text{SR}_{\text{year}} = \text{SR}_{\text{month}}\times\sqrt{12}$$

| If 1.4 is | Then per month | Then per year | Who earns it |
|---|---|---|---|
| a yearly Sharpe, tracked monthly | 0.40 | 1.4 | A good multi-strategy book |
| a Sharpe on monthly returns | 1.4 | 4.85 | Market makers and high-frequency firms |

This report plans for 1.4 a year.

**1.4 comes from combining signals, not from one.** For $N$ signals of equal Sharpe $s$, with an
average correlation $\rho$ between them:

$$\text{SR}_{\text{book}} = s\times\sqrt{\frac{N}{1+(N-1)\rho}}$$

| Signals | Correlation between them | Book Sharpe as a multiple of one signal's |
|---|---|---|
| 4 | 0 | 2.00 |
| 8 | 0 | 2.83 |
| 4 | 0.2 | 1.58 |
| 8 | 0.2 | 1.83 |
| 8 | 0.5 | 1.33 |

So four unrelated signals of 0.7 make 1.4. Eight signals that all pay in the same market stress
(correlation 0.5) make only 0.93 from 0.7 each. **Unrelated matters as much as good.**

**Where we stand** (repaired data, 2017-2026, on paper):

| Signal | Sharpe | Evidence |
|---|---|---|
| Stat arb in volatile markets, filled at the opening auction | about 0.7 | t 2.0, after 21 looks |
| Momentum against its universe | information ratio 0.49 | t 1.5 |
| Trend following | 0.0 in this decade, 0.37 over a century | Insurance, not profit |

**How long a signal takes to prove itself.** The t-statistic of a Sharpe ratio grows with the square
root of time:

$$t \approx \text{SR}\times\sqrt{\text{years}} \qquad\Rightarrow\qquad \text{years for } t=2 \;=\; \left(\frac{2}{\text{SR}}\right)^2$$

| True Sharpe | Years of record to reach t = 2 |
|---|---|
| 0.4 | 25 |
| 0.5 | 16 |
| 0.7 | 8.2 |
| 1.0 | 4 |
| 1.4 | 2 |

One signal at 0.5 cannot be proved on our decade. A book at 1.4 can be judged in about two years.
This is why long histories and many signals both matter.

**The cost of looking many times.** If nothing works and we try $N$ ideas, the best one still looks
good by luck:

| Looks | Best t-statistic expected from luck alone | Chance the best one beats t = 2 |
|---|---|---|
| 1 | 0.0 | 2% |
| 5 | 1.2 | 11% |
| 10 | 1.5 | 21% |
| 21 | 1.9 | 38% |
| 50 | 2.3 | 68% |
| 100 | 2.5 | 90% |

Our stat-arb rule has t 2.0 after 21 looks. Luck alone would give about 1.9. That is why it is called
thin, and why every candidate below gets **one** test, written down first. (The 21 looks overlap, so
the true number of separate looks is smaller, and the table is the pessimistic reading.)

---

## Part 2. The toolkit

**Returns.** With $O_t$ the opening price and $C_t$ the closing price on day $t$:

$$r_t = \frac{C_t}{C_{t-1}}-1 \qquad r^{\text{night}}_t = \frac{O_t}{C_{t-1}}-1 \qquad r^{\text{day}}_t = \frac{C_t}{O_t}-1$$

$$(1+r^{\text{night}}_t)(1+r^{\text{day}}_t) = 1+r_t$$

**A stock's own move (its residual).** Take out what the market and the stock's sector explain:

$$r_i = \alpha_i + \beta^m_i\, r_{\text{SPY}} + \beta^s_i\,(r_{\text{sector}} - r_{\text{SPY}}) + e_i$$

- $\beta^m_i$: how much the stock moves with the market. $\beta^s_i$: how much with its sector beyond
  the market. Both come from the last 60 sessions.
- $e_i$: the residual, the part that is the stock's own.

**The signal.** A stock's residuals added up over the last $k$ days:

$$s_i = \sum_{j=0}^{k-1} e_{i,\,t-j}$$

**Picking.** Rank the stocks on $s_i$. Buy the fraction $f$ with the lowest values, sell short the
fraction $f$ with the highest. With $n$ names a side and a share $w$ of capital a side:

$$w_i = +\frac{w}{n}\ \text{(bought)} \qquad w_i = -\frac{w}{n}\ \text{(sold short)}$$

**Hedging.** ETF positions that cancel what is left of the market and sector exposure:

$$h_{\text{sector}} = -\sum_{i\in\text{sector}} w_i\,\beta^s_i \qquad h_{\text{SPY}} = -\sum_i w_i\,\beta^m_i + \sum_i w_i\,\beta^s_i$$

**A trade's result.** Each stock's hedged return over the holding period:

$$R^h_i = R_i - \beta^m_i R_{\text{SPY}} - \beta^s_i\,(R_{\text{sector}} - R_{\text{SPY}})$$

The spread is what the bought stocks earned over the sold ones, and the net is the spread after costs:

$$g = \overline{R^h}_{\text{bought}} - \overline{R^h}_{\text{sold}} \qquad \text{net} = g - (4c + c_{\text{hedge}} + c_{\text{borrow}})$$

- $c$: the cost of one stock trade. It is paid four times: buy and sell the longs, sell and buy back
  the shorts.

**Break-even cost.** The most one stock trade can cost before the edge is gone:

$$c^{*} = \frac{g - c_{\text{hedge}} - c_{\text{borrow}}}{4}$$

**Is it real? The t-statistic.** Over $n$ trades with average net result $\bar x$ and standard
deviation $\sigma_x$:

$$t = \frac{\bar x}{\sigma_x/\sqrt{n}}$$

Above 2 is the usual bar. Trades that overlap in time are not independent, so the tests widen the
denominator for that (the Newey-West correction).

**Ranking skill and breadth.** The information coefficient (IC) is the correlation between a
signal's ranking and what happened next. Grinold and Kahn's rule of thumb:

$$\text{IR} \approx \text{IC}\times\sqrt{\text{independent bets a year}}$$

A weak ranking used on many independent bets beats a strong one used rarely. A signal that fires ten
times a year needs many stocks per firing to be judged at all.

---

## Part 3. A worked example, as questions and answers

**The numbers below are invented** to show the arithmetic. It is one good cohort; in the real
backtest about half of all cohorts lose.

**Q1. It is Monday morning and VIX closed above 20 on Friday. Ten stocks are in the universe, five in
technology and five in financials. What do we look at?**

Each stock's own move over the last five days, $s_i$, with its two betas:

| Stock | Sector ETF | Own move, last 5 days ($s_i$) | Market beta | Sector beta |
|---|---|---|---|---|
| T1 | XLK | −6.0% | 1.2 | 0.8 |
| T2 | XLK | −1.0% | 1.0 | 1.0 |
| T3 | XLK | +0.5% | 1.1 | 0.9 |
| T4 | XLK | +2.0% | 0.9 | 1.0 |
| T5 | XLK | +7.0% | 1.3 | 1.1 |
| F1 | XLF | −4.5% | 1.0 | 0.9 |
| F2 | XLF | −0.5% | 0.9 | 1.0 |
| F3 | XLF | +1.0% | 1.1 | 1.0 |
| F4 | XLF | +3.0% | 1.0 | 0.8 |
| F5 | XLF | +5.0% | 1.2 | 1.2 |

**Q2. What do we buy and sell?**

A fifth of ten stocks is two. The two that fell most on their own are T1 and F1: we buy them. The
two that rose most are T5 and F5: we sell them short. With 20% of capital a side, each is 10%.

| | T1 | F1 | T5 | F5 |
|---|---|---|---|---|
| Weight | +10% | +10% | −10% | −10% |

**Q3. What hedge goes with it?**

- Technology: $h_{\text{XLK}} = -(0.10\times0.8 - 0.10\times1.1) = +0.03$
- Financials: $h_{\text{XLF}} = -(0.10\times0.9 - 0.10\times1.2) = +0.03$
- Market: $h_{\text{SPY}} = -(0.12+0.10-0.13-0.12) + (0.08+0.09-0.11-0.12) = 0.03 - 0.06 = -0.03$

So we buy 3% of capital in XLK and in XLF, and sell 3% in SPY. The hedge is small here because the
longs and shorts have similar betas.

**Q4. Five sessions later the market is up: SPY +1.0%, XLK +2.0%, XLF +0.5%. The stocks returned
T1 +3.0%, F1 +1.4%, T5 +1.5%, F5 −0.2%. Did we make money, or did the market?**

Take the market and sector out of each stock:

| Stock | Its return | Minus market: beta × 1.0% | Minus sector: beta × (sector − market) | Hedged return $R^h$ |
|---|---|---|---|---|
| T1 | +3.0% | 1.2 | 0.8 × (2.0 − 1.0) = 0.8 | **+1.00%** |
| F1 | +1.4% | 1.0 | 0.9 × (0.5 − 1.0) = −0.45 | **+0.85%** |
| T5 | +1.5% | 1.3 | 1.1 × 1.0 = 1.1 | **−0.90%** |
| F5 | −0.2% | 1.2 | 1.2 × (−0.5) = −0.6 | **−0.80%** |

$$g = \frac{1.00+0.85}{2} - \frac{-0.90-0.80}{2} = 0.925 + 0.850 = 1.775\%$$

The bought stocks beat the sold ones by 1.775% after the market and sectors are removed. T5 rose
1.5% and still counts as a win for the short, because its market and sector alone explain +2.4%.

**Q5. Does the money add up?**

- Stocks: $0.10\times3.0 + 0.10\times1.4 - 0.10\times1.5 - 0.10\times(-0.2) = 0.31\%$ of capital.
- Hedge: $-0.03\times1.0 + 0.03\times2.0 + 0.03\times0.5 = 0.045\%$ of capital.
- Together 0.355%, which is $0.2\times1.775\%$: the spread, earned on the 20% of capital at work.

**Q6. What is left after costs?**

| | Market orders at 09:35 | Opening auction |
|---|---|---|
| Cost of one stock trade ($c$) | 10.8 bp (measured) | 1 bp (assumed) |
| Cost of the cohort: $4c + 5 + 1$ | 49.2 bp | 10 bp |
| Net: 177.5 bp − cost | 128.3 bp | 167.5 bp |
| On $500,000 of capital, 20% a side | $1,283 | $1,675 |

Here the spread is so large that the cost hardly matters. In the real backtest the average spread
is 51 bp, so a cost of 49 leaves almost nothing and a cost of 10 leaves 41. **On an average cohort,
the cost is the whole story.**

**Q7. One cohort made 1.7%. Is the rule good?**

One cohort says nothing. In the backtest a cohort's net result has a standard deviation of about
350 bp around an average of 41 bp, and 52% of cohorts make money. The average only shows up over
hundreds of them:

$$t = \frac{41}{350/\sqrt{779}} \approx 3.3 \text{ if the cohorts were independent}$$

They are not: each overlaps the next four. With that allowed for, t is 2.0.

**Q8. What does that make as a Sharpe ratio?**

Adding the cohorts up by month, the auction-priced rule earns about 6% a year on capital with 9%
volatility: a Sharpe of about 0.7, and it is idle in four months out of ten.

**Q9. How far is that from 1.4?**

Halfway, if it is real. By the combining formula we need about four such signals that do not win and
lose together. That is the reason for the shortlist.

---

## Part 4. The shortlist

Six candidates, chosen so that:
- each has a stated condition, and someone on the other side with a reason to pay;
- together they fire at different intervals, from daily to eight times a year;
- each can trade at the opening or closing auction, where no spread is paid;
- each needs only Alpaca data, records we build ourselves, or the outside histories already on hand.

| # | Signal | Fires | Kind of bet | Needs | My rough odds it passes |
|---|---|---|---|---|---|
| A | Sector-stress reversal | Most weeks | Many stocks, long and short | On hand | 30% |
| B | Reversal before earnings | Daily in earnings seasons | Many stocks, long and short | Earnings dates, built in-house | 25% |
| C | Momentum held overnight only | Every night | Many stocks, long | On hand | 30% |
| D | Turn of the month | 12 times a year | The index | On hand, a century | 30% |
| E | Fed announcement days | 8 times a year | The index | A list of dates | 20% |
| F | Bounce after a share offering | A few times a week | Single stocks, long | Our scored news | 15% |

The odds are judgement, not measurement. If they are about right, one or two of the six will pass.

**The same rules for every test:**
- One configuration, written down before the data is opened. No second version if the first fails.
- The repaired price panel, point-in-time universes, and both halves of the sample.
- Costs measured at the signal's own trading time, or 1 bp a trade at an auction.
- **Pass:** net profit after costs with t of at least 2, and positive in both halves.
- **Then:** a shadow slot. The live record is the judge.

### A. Sector-stress reversal

**In one sentence.** The stat-arb rule we have, switched on sector by sector when that sector is
under stress, even if the whole market is calm.

**Who pays us.** The same people as in the VIX rule: anyone forced to trade a stock quickly when the
firms that normally take the other side have stepped back. When one sector is hit (banks in March
2023, chip makers on export news), that happens inside the sector while VIX stays low.

**The condition.** A sector is stressed when its move beyond the market over five days is unusually
large for that sector:

$$x_s = \Big|\sum_{j=0}^{4}\big(r_{s,\,t-j} - r_{\text{SPY},\,t-j}\big)\Big| \qquad \text{stressed if } x_s \ge \text{its 90th percentile over the last 252 sessions}$$

**The trade.** Inside a stressed sector only: buy the fifth of its stocks with the lowest $s_i$, sell
the fifth with the highest, hedge, hold five sessions. Enter and exit at the opening auction.

**How often.** Each sector is stressed about a tenth of the time by construction, and there are
eleven sectors, so some sector qualifies in most weeks.

**The test.** The quintile spread on sector-stressed days **when VIX is below 20**. Those are days
the rule we have does not trade, so a pass means something new, not the same fish twice.

**What could go wrong.** A sector falls for a reason that lasts (a new regulation, a collapse), and
the stocks that fell most keep falling. There are also fewer names per trade than in the market-wide
rule, so each result is noisier.

### B. Reversal before earnings

**In one sentence.** In the three days before a company reports, its stock's short-term moves reverse
more than usual; trade that, and be out before the report.

**Who pays us.** Firms that make markets hold less of a stock just before its earnings, because the
announcement could move it sharply against them. Anyone who must trade in those days pays more for
it (So and Wang 2014).

**The condition.** The company's report is one to three sessions away.

**The trade.** Among stocks in that window, buy the fifth with the lowest $s_i$ and sell the fifth
with the highest, hedged. Exit at the **closing auction before the report**. Never hold through it.

$$\text{hold from the open of day } t \text{ to the close of day } T-1, \quad T = \text{report day}, \quad 1 \le T-t \le 3$$

**How often.** Daily for about six weeks in each quarter.

**Needs.** Report dates known in advance. Our scored news already tags "earnings-date notice"
headlines and the releases themselves from 2019. A calendar is built from those in-house.

**The test.** The spread per trade, against the same rule on stocks with no report near.

**What could go wrong.** A wrong date means holding through earnings, which is the one thing this
rule must not do. The history is short (2019 on), and reversal on ordinary days is already known to
be too small to trade.

### C. Momentum held overnight only

**In one sentence.** Own recent winners from the close to the next open, and nothing during the day.

**Who pays us.** Published work finds that momentum's profit is earned almost entirely overnight,
and that the same stocks give some of it back during the day (Lou, Polk and Skouras 2019). Why is
debated. The usual account is that different kinds of investor set prices at the open and during
the day.

**The condition.** None by day: it trades every night. It is here because it trades only at the two
auctions and so tests cheaply.

**The trade.** Each afternoon rank stocks on their return over the last twelve months, skipping the
most recent one. Buy the top 30% at the closing auction and sell them at the next opening auction.

$$\text{nightly result} = \overline{r^{\text{night}}}_{\text{winners}} - \overline{r^{\text{night}}}_{\text{universe}} - 2c$$

**The cost decides it.** Two trades a night at 1 bp each is 2 bp a night, or about 5% a year. The
winners must beat the universe by clearly more than that every night on average.

**The test.** The winners' overnight return beyond the universe's. **Pass only if it is at least
4 bp a night.** The data is on hand: the daily open and close for every stock in the panel.

**What could go wrong.** The overnight edge may be smaller than 4 bp in the most-traded stocks. Real
closing-auction fills cannot be checked on a paper account. And it is momentum again, so it will
win and lose with the momentum book we already have.

### D. Turn of the month

**In one sentence.** Hold the index for four days around each month-end, and cash otherwise.

**Who pays us.** Money arrives at month-end on a schedule: pension contributions, salaries into
retirement funds, funds tidying their books. That buying is not sensitive to price (Ariel 1987;
Lakonishok and Smidt 1988; McConnell and Xu 2008).

**The condition.** The calendar: the last trading day of a month and the first three of the next.

**The trade.** Buy SPY at the close two days before month-end, sell at the close of the third
trading day of the new month.

$$R_{\text{turn}} = \prod_{t\,\in\,\{-1,\,+1,\,+2,\,+3\}} (1+r_t) - 1$$

**How often.** Twelve times a year, about 48 days in the market.

**The test.** A century of daily US market returns is already on hand (Ken French, from 1926). The
average return on those four days against all other days, over the whole period, each half, and
since 2000.

**What could go wrong.** It has been public since the 1980s and may have faded. One instrument and
twelve bets a year make it a slow signal to prove live. And it holds the market, so on those days it
is the same bet as any stock book.

### E. Fed announcement days

**In one sentence.** Hold the index over the day before each scheduled Federal Reserve announcement.

**Who pays us.** Investors who do not want to hold stocks into a scheduled risk sell beforehand, and
those who hold through it are paid for it. A large share of the stock market's long-run return has
been earned on scheduled announcement days (Savor and Wilson 2013), most of all in the 24 hours
before Fed announcements (Lucca and Moench 2015).

**The condition.** A scheduled Fed announcement tomorrow. The dates are published a year ahead.

**The trade.** Buy SPY at the close the day before, sell at the close on the day.

$$r_{\text{Fed}} = \frac{C_d}{C_{d-1}} - 1 \quad \text{on announcement days } d$$

**How often.** Eight times a year. This is the one-day kind of signal.

**The test.** About 260 scheduled announcements since 1994, on the S&P 500 history on hand. The paper
was published in 2015, so **the years since are a test the authors never saw**: the average return on
announcement days before and after 2015.

**What could go wrong.** Published effects often shrink once they are known (McLean and Pontiff
2016). Eight bets a year take a long time to judge live.

### F. Bounce after a share offering

**In one sentence.** When a company sells new shares at a discount and its price drops, buy the next
morning and hold a week.

**Who pays us.** The company wants a large block placed in one night, so it is priced below the
market to find buyers quickly (Corwin 2003). If the drop is only the pressure of that sale, the
price should come back part of the way.

**The condition.** A headline our news scoring tags as a share offering, and a fall of at least 5%
that day.

**The trade.** Buy at the next opening auction, hedge with SPY and the sector ETF, sell at the
opening auction five sessions later.

$$\text{result} = R^h_i\big(\text{open}_{d+1} \rightarrow \text{open}_{d+6}\big) - 2c$$

**How often.** A few times a week across the market.

**Needs.** The news already scored: about 4,300 offering headlines from 2019 to 2026.

**What could go wrong.** An offering can be bad news in itself (the company needed cash), and our
own news study found that stocks with bad news kept drifting lower. Companies that raise money this
way are often smaller and weaker, where our cost assumptions are least reliable. It has the lowest
odds of the six.

---

## Already fished

| Idea | Result |
|---|---|
| One-minute streaks (the original Wave Rider) | Noise. 62 settings, none profitable |
| Index momentum inside the day | Not in 2016-2026 |
| Opening-range breakout | Loses after costs |
| Overnight and intraday reversal, bought only | No ranking power |
| News as a direction signal | Nothing, on 357,000 scored headlines |
| Drift after earnings | Right shape, too small to trade |
| Put spreads | Failed a 36-year test |
| Reversal on all days | Too small to pay its costs |
| Trend following | Insurance, not profit |
| Momentum | The best lead, unproven |
| Reversal when VIX is 20 or above, filled at the opening auction | Passes, thinly; in shadow |

## Looked at and left off the list

- **Stocks joining an index:** a known effect that has faded, and too few events a year.
- **Pairs inside a sector:** the same machinery as reversal, and published returns have declined.
- **Option-expiry week:** needs option-volume history that we only started recording today.
- **Short interest and borrowing fees:** needs an outside source.
- **Anything inside the trading day:** our own tests found noise there.

## Suggested order

1. **D and E first.** Each is an afternoon: the data is on hand and reaches back decades.
2. **C next.** The prices are in the panel.
3. **A after that.** It reuses the stat-arb code.
4. **B and F last.** Each needs an in-house calendar built from the scored news first.

D and E are index bets and will not reach 1.4 by themselves. They are worth testing first because
they are cheap, they use long histories, and they pay on days chosen by the calendar, which makes
them unrelated to the stock signals.

---

## Candidate G (added 10 November 2026): news about one company carrying its related stocks

**Proposed by the owner.** Example: a lab announces a new AI model and the chip and infrastructure
companies rise over the following hours or days. We need not be first; the aim is to enter after the
move has started and before it has finished. **Nothing below has been tested. This is a proposal,
and its test still has to be written down in full.**

**Who pays us.** Investors who are slow to work out what news about one company means for another.
Published work finds this for customers and suppliers (Cohen and Frazzini 2008, "Economic links and
predictable returns") and for industry leaders and followers (Hou 2007): the related stock moves
late, over days. These references are from memory and are to be checked before a test.

**What our own results say.**
- **Against:** news as a signal for the *same* company has failed every test here (357,000 scored
  headlines). Positive news gave no edge inside the day.
- **For:** signal A's test, 10 November. In calm markets, when a sector moved sharply, its hardest-hit
  stocks kept falling and its strongest kept rising over the next five sessions. That is news being
  absorbed slowly across related stocks. It was seen in a test of the opposite idea, so it is a lead
  and not a result.

**Three traps to design around.**
1. **Choosing the basket with hindsight.** Everyone knows today which stocks are "AI infrastructure".
   The basket has to be built from data available at the time: for example the stocks whose returns
   moved most closely with the named company's over the year before.
2. **Assuming the sign.** A new model can be bad for chip makers (January 2025, when a cheaper model
   sent them down). The rule should follow the related stocks' first move, not assume "release
   means up".
3. **Few events.** Major AI releases number a few dozen. A rule about "news of any large company and
   its related stocks" has thousands of events and can be judged; the AI case is then one use of it.

**A first test that could be run on data we hold.**
- **Event:** a stock in the 100 most traded has a material, relevant headline (already scored) and
  moves more than twice its usual daily amount that day.
- **Related stocks:** the ten whose daily returns followed it most closely over the previous year,
  the stock itself left out.
- **Signal:** the related stocks' own move that day, after the market is taken out.
- **Trade:** if they have moved the same way but less, buy (or short) them at the next open, hedged,
  for one to three sessions.
- **Pass:** the usual rule. One configuration, net of costs, t of at least 2, both halves.

**What it would need beyond that.** A live version has to read news during the day. Alpaca's news
stream and the scoring model are both available; the bot does not use them yet.

**Tested the same evening** (docs/research/2026-11-10-signals-b-g.md, section 6), in a slightly
different form from the sketch above: every event traded in the news stock's direction, ten related
stocks, next open to three sessions later. **It fails:** −0.1 bp per event after costs (t 0.5) over
3,208 events. But the related stocks moved 76 bp in the news stock's direction **on the news day
itself**. The link is real; the daily version arrives too late. The open question is the one inside
the day, which needs minute prices and headline times and has not been designed.

**A correction to candidate B above.** The paper behind it (So and Wang 2014) measures the reversal
over the days around the report, the report day included. "Never hold through it" was this page's
mistake. The test followed the paper and also reported the out-before version; neither earned
anything.
