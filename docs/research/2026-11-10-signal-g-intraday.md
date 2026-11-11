# Signal G inside the day: do related stocks follow slowly enough to trade?

**Sections 1 to 3 were written on the night of 10 November 2026, before any minute price was
fetched.** The daily test of G (2026-11-10-signals-b-g.md, section 6) found that when a stock moves
on news its ten related stocks move 76 bp the same way on the same day, and nothing afterwards. This
test asks the question that left open: after the news stock has visibly moved, is there still time
to trade the related ones before the close? One configuration, one pass test. Look 30 of the
project.

## 1. The rule

**The news.** A headline about stock $A$ that our scoring called relevant, not stale and material
(expected materiality of at least 1 on the 0-to-2 scale), published between 09:40 and 15:00 New York
time on a trading day. The scored news covers the 100 most-traded stocks, 2019 to 2026. There are
15,765 such headlines on 12,347 stock-days (counted before any price was read).

**The trigger.** Let $t_0$ be the minute of the headline. $A$'s move over the ten minutes from
$t_0-5$ to $t_0+5$, with the market taken out:

$$m_A = \frac{P_A(t_0+5)}{P_A(t_0-5)} - 1 \;-\; \beta_A\left(\frac{P_{\text{SPY}}(t_0+5)}{P_{\text{SPY}}(t_0-5)} - 1\right)$$

The event counts when $|m_A|$ is at least **half of $A$'s usual daily own-move** (the standard
deviation of its daily residuals over the 60 sessions before). The window starts five minutes
before the headline because the feed's timestamp can trail the news itself. Everything in it is
known by $t_0+5$. Only a stock's first event of the day counts.

**The related stocks.** As in the daily test: the ten of the top 300 whose daily returns beyond the
market followed $A$'s most closely over the 252 sessions before that day.

**The trade.** In the direction of $m_A$: buy the ten after a jump, short them after a fall.
- **In:** during the minute that starts at $t_0+5$, at that minute's average traded price.
- **Out:** at the close (the last regular minute's closing price).
- **Hedge:** SPY over the same minutes, at each stock's market beta known the day before.

**Costs.** 7 bp per event: 5 bp for a market order going in (the project's standing assumption for
one; the stat-arb picks cost 10.8 bp at 09:35, calmer names in the middle of the day less), 1 bp at
the closing auction, 1 bp for the hedge.

## 2. The test

**Result per event.** The ten stocks' average market-hedged return from entry to the close, signed
by $A$'s direction, less 7 bp. An event needs prices for at least five of its ten stocks.

**Pass, all four:**
1. At least 300 events. Fewer is "too few to judge".
2. The average net result is above zero.
3. Its t is at least 2 (events on the same day averaged first; Newey-West, 4 lags).
4. Above zero in both halves: 2019-2022 and 2023-2026.

**Reported for context, not for choosing:**
- how far the related stocks had already moved inside the trigger window;
- their move 30 and 60 minutes after entry;
- the news stock's own move from entry to the close;
- jumps and falls separately;
- the cost per event at which the average is zero.

## 3. What this test cannot settle

- **The real cost.** 5 bp going in is an assumption. Spreads on related stocks may be wider in the
  minutes after news. If the test passes, the next step is to measure the quoted spread at each
  entry, as was done for the stat-arb rule, before anything else.
- **The fill.** A minute's average price stands in for a market order sent in that minute.
- **The clock.** The feed's timestamp is when the headline was published there, which can be after
  the news reached faster readers.
- **Outside market hours.** Much company news comes before the open or after the close (earnings
  above all). Those events are not in this test.

---

## 4. Result (run 10 November 2026, after sections 1 to 3)

`scripts/research_related_news_intraday.py`. 15,699 headlines on 12,311 stock-days were checked
against minute bars; **750 triggered** (a ten-minute move of at least half the stock's usual day),
747 with prices for the related stocks, on 586 days. All ten related stocks were priced in nearly
every event.

**What the related stocks did, in the news stock's direction, market taken out:**

| Inside the ten-minute window (before we could act) | 30 minutes after entry | 60 minutes after | Entry to the close |
|---|---|---|---|
| **+21.8 bp** | +2.1 bp | −1.9 bp | **+4.4 bp** |

The news stock itself moved 149 bp in the window on average.

| | Events | Before costs | After 7 bp | Median | t | Won | Halves (net) |
|---|---|---|---|---|---|---|---|
| **All events (the test)** | 747 | +4.4 bp | **−2.6 bp** | −7.3 | −0.6 | 44% | −1.3 / −3.7 |
| Context: after a jump | 387 | +8.3 | +1.3 | −3.4 | 0.5 | 48% | +3.5 / −0.7 |
| Context: after a fall | 360 | +0.3 | −6.7 | −12.3 | −1.3 | 41% | −6.4 / −7.1 |

| Test | Needed | Got | |
|---|---|---|---|
| Events | at least 300 | 747 | Passes |
| Average net | above zero | −2.6 bp | **Fails** |
| t | at least 2 | −0.6 | **Fails** |
| Both halves above zero | yes | −1.3 / −3.7 | **Fails** |

- **By year (net):** −15, −4, −12, +26, +4, +5, −13, −13 bp (2019 to 2026).
- **The average is zero at a cost of 4.4 bp per event.** One market order in ten stocks already costs
  about that.
- **The news stock itself** went a further +11.7 bp its own way by the close, before costs. That was
  context, not the question.

**Verdict: fails.**

## 5. Reading

1. **The related stocks follow within the same minutes.** In four events out of five they were
   already moving the same way inside the ten-minute window, by 22 bp on average. After that there
   are 4 bp left to the close.
2. **So the answer to "can we enter before it normalises" is: not five minutes later.** The catching
   up is done by traders who act in seconds. That is a speed contest, and this project has ruled
   those out.
3. **Together with the daily test, the picture is complete for stocks that normally move together:**
   they move 76 bp with the news stock on the day, almost all of it at once.
4. **What this does not cover:**
   - **Links that are not in past prices.** The ten related stocks are the ones that usually move
     with the news stock, which is why the market links them instantly. A new kind of news can
     matter for companies that never moved with the source before (the owner's example: a model
     release and, say, power or cooling suppliers). Nothing here tests that. There are few such
     events and no history of them, so a backtest cannot judge it; it would have to be recorded
     forward as it happens.
   - **News outside market hours,** where the reaction is in the next open and cannot be traded
     before it.
