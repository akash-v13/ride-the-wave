# Progress log for the owner

A running, plain-English record of what has been completed, how to check it, and what is next. Newest
first. The status table in `CLAUDE.md` is the terse version; `docs/handbook.md` is the full reference.

## How to check the system on any day

| Question | Where to look |
| --- | --- |
| Is the bot running right now? | `http://127.0.0.1:8787` (TypeScript web page) or `curl localhost:8787/api/health` |
| What happened today? | `data/reports/<date>/` pages (pre-market, morning, midday, close, evening) or the web page's Reports tab |
| Per-strategy trades and P/L | Web page, or `uv run python scripts/report.py close` |
| Are the scheduled jobs loaded? | `uv run python scripts/install_launchd.py status` (bot, operator tick, API) |
| Which strategies are configured? | `config/settings.yaml`, `strategies:` block; `mode: live` trades real paper money, `mode: shadow` only simulates on live prices |
| Run the tests | `uv run pytest -q` (Python) and `cd web && npm test` (TypeScript) |

## 2026-11-10 — Three signals tested: two rejected, one near miss; an auction reading error fixed

**The session.** Clean. Live Wave Rider: 4 trades, −$21.64. `sa_volrev`: $495,275 (+$546 on the
day), holding the cohorts of 3, 5 and 6 November. The 15:45 recording ran (14,405 assets, 266
underlyings). PR #3 was merged on 9 November; the machine is back on `main` code, on a new branch
for this work.

**An error of mine, found on the first auction-priced session.** Only 114 of 266 symbols were
priced at the auction at 09:35; every NYSE stock fell back to the day's first trade.
- **Cause:** for NYSE and ARCA symbols Alpaca returns the day before as the first row on winter days
  (a late closing print stamped after midnight UTC). The reader took the first row.
- **Fix:** rows are matched on their date. Two tests added.
- **The study it affected** (9 November) said 92% of picks had a print and that the ETFs had none
  in later years. Both were this error. Re-run: 99.9% priced, **+40.6 bp per cohort (t 2.0),
  unchanged**; +40.7 with the hedges at their auctions too. The verdict stands.
- **Today's fills** are left as booked: the 52 fallback fills differed from the auction by about
  1 bp of their value in total.

**The owner's answers.** The 1.4 target is a yearly Sharpe ratio, ideally above 2. Test A, C and D
first, then B, E and F.

**Results** (docs/research/2026-11-10-signals-a-c-d.md; each test was written down first and run once):

| Signal | Result | Verdict |
|---|---|---|
| A. Sector-stress reversal | −28.6 bp per cohort in calm markets (t −2.1) | Rejected. Stocks hit hardest in a stressed sector kept falling |
| C. Momentum held overnight | Winners beat the universe by +3.76 bp a night (t 4.3); +1.76 after costs (t 2.0); both halves positive | Fails its 4 bp bar by 0.24 bp. A lead, not promoted |
| D. Turn of the month | +14.6 bp a day over 1926-2005 (t 8.0); +0.8 bp over 2006-2026 (t 0.2) | Rejected. Gone since it was published |

- **Worth knowing from C:** winners earned +9.2 bp a night and +0.1 bp a day; the whole universe
  +5.5 bp a night and +0.8 bp a day. In 2017-2026 the return came overnight.
- **How to check:** `uv run python scripts/research_turn_of_month.py`,
  `research_overnight_momentum.py`, `research_sector_stress.py`; results in `data/research/signals/`.
- **Tests:** 216 pass.

**Next:** signals E (Fed days), B (before earnings) and F (share offerings). Owner to decide whether
C is observed in a shadow slot anyway. Nothing is committed yet.

## 2026-11-09 (late) — At the opening auction the stat-arb rule earns +41 bp per cohort, not +8

**Asked:** go ahead with the opening-auction test.

**The question.** With market orders at 09:35 the rule pays the spread four times per cohort and
nets +7.5 bp. The opening auction crosses every stock at one price with no spread. What would the
rule earn if every trade were filled there? The design was written down first
(docs/research/2026-11-09-statarb-auction-fills.md).

**What was measured.** Alpaca keeps a history of auction prints. For all 92,081 picks on the 779
volatile sessions, the auction price was compared with the open the backtest used.
- **Stock by stock they often differ** (40% of the time, by 9 bp on average).
- **Long against short they cancel:** 0.0 bp at entry and −0.2 bp at exit per cohort. So the
  backtest's prices were fair for an auction fill.

**Result, per cohort:**

| | Market orders at 09:35 | At the opening auction |
|---|---|---|
| Cost | 49 bp | 10 bp |
| Net | +7.5 bp (t 0.4) | **+40.6 bp (t 2.0)** |
| Halves | +14.0 / +1.4 | +47.7 / +33.7 |

About +5.9% a year on capital. It passes the test set in advance.

**Why it is still thin.**
- t 2.0 after 21 looks at one decade; 2020 and 2025 carry it, and 2019 and 2021 lost.
- From 2022 Alpaca's history lacks the print for a quarter of New York Stock Exchange stocks.
- "1 bp a trade" and "our order is in the auction" are assumptions a paper account cannot prove.

**Approved by the owner and done the same night:** from 10 November the shadow slot books each fill at
that stock's opening auction price plus 1 bp, sized on yesterday's close. The picks do not change. A
dry run priced 264 of 266 symbols at their auction price. The slot's record changes basis on that day.
209 tests.

**The owner's long-term target:** a Sharpe ratio of 1.4, reached by hunting for signals that repeat
under stated conditions, each used only when its conditions hold (docs/decisions.md).

**Shortlist report written:** docs/strategies/2026-11-09-signal-shortlist.md. Six candidates, none
tested yet, with every formula, a worked example as questions and answers, and what 1.4 asks for:
about four unrelated signals as good as the auction-priced stat-arb rule (Sharpe about 0.7).

## 2026-11-09 (night) — The price panel is repaired; every study re-run

**Asked:** start the repair, using the owner's Massive key. Keep Alpaca as the primary source, limit
other sources, and build records in-house where we can.

**How the sources are used.**
- **Massive (formerly Polygon.io), once.** The owner's key is on the free plan: two years of prices and
  5 requests a minute, but its list of delisted stocks back to 2003 is not restricted. That list was
  downloaded once into `data/reference/`. Nothing calls Massive again.
- **Alpaca for every price.** Each missing stock was asked for by its old symbol.
- **In-house from now on.** Alpaca's asset list is saved daily since today, and a stock that is in one
  day's file and not the next has been delisted.

**What was added:** 2,708 delisted stocks. Another 1,235 listed tickers were only old names of
companies already held (FB is META), and were left out. Up to 8% of a year's 300 most-traded stocks
had been missing, most in the early years.

**Every study re-run unchanged** (docs/research/2026-11-09-panel-survivorship-gap.md, section 5):

| Study | Before | After |
|---|---|---|
| Stat-arb rule, at the assumed 5 bp cost | +29.7 bp per cohort (t 1.5) | +24.9 bp (t 1.2) |
| Stat-arb rule, as the slot trades | +11.9 bp (t 0.6) | **+7.5 bp (t 0.4)** |
| Momentum against its universe | 0.51 | 0.49 |
| Momentum with the overlay, against SPY | 0.43 | 0.39 |

- **Every number fell a little; no verdict changed.**
- **The stat-arb rule has no edge as it trades:** +7.5 bp per cohort, and +1.4 bp in the second half.
- **Momentum barely moved** and is still the best lead.
- **Mostly takeovers were missing, not collapses.**

**Still not covered:** 351 tickers Alpaca had no prices for; what a stock was worth after its last
trading day; and the list is one vendor's, not checked against a second.

**Checks:** 206 tests pass. The old results are kept in `data/research/pre-repair-2026-11-09/`.

**Next, for the owner to choose:** test opening-auction fills for the stat-arb rule; a shadow slot for
the momentum overlay; whether one month of Massive's 20-year plan is worth it to test before 2016.

## 2026-11-09 (evening) — Real trading costs measured; daily recordings start; a gap found in the price panel

**Asked:** go ahead with the cost measurement and the daily recording.

**1. What the stat-arb rule really pays to trade** (docs/research/2026-11-09-statarb-costs.md). The
design was written down before any data was fetched.
- **The spread.** From Alpaca's quote history on 60 volatile and 30 calm sessions: the stocks the
  rule picks cost **10.9 bp** each way at 09:35. The backtest assumed 5. Calm sessions are nearly as
  wide (9.7 bp), so it is the kind of stock the rule picks, not the stress.
- **The wait.** The backtest trades at the open; the slot trades at 09:35. From minute bars on all
  779 volatile sessions: by 09:35 the stocks it buys have fallen a further 6 bp against the ones it
  sells. So waiting gains about 5.7 bp per cohort. It does not cost.
- **Re-priced as the slot trades:** +11.9 bp per cohort (t 0.6), against +29.7 in the backtest.
  About +1.7% a year on capital, not +4.3%. It is still positive in both halves, by a margin of
  3 bp of spread. **As it trades today, the rule has no demonstrable edge.**
- **A lead, not a result:** the opening auction has no spread. If the picks can be filled there at
  about the backtest's price, a cohort costs about 6 bp, not 50. That needs its own test.
- **Unchanged:** the rule, the slot and its settings.

**2. Daily recordings** (docs/features/25-market-state-recording.md), from 10 November:
- **Every simulated fill of a daily slot is stored with its bid and ask** (table `portfolio_fills`),
  so the shadow records can be re-priced at real spreads.
- **Borrow flags** for every active stock, and **option quotes with implied volatility** for the 254
  stat-arb names and 14 ETFs, saved each day at 15:45 ET by the operator
  (`data/recordings/`). Today's files were written after the close as the first day.
- **First day's finding:** one stat-arb name (ONDS) cannot be shorted, and two (KVUE, WBD) have been
  delisted since the list was made in September.

**3. Found on the way: the price panel is missing delisted stocks**
(docs/research/2026-11-09-panel-survivorship-gap.md).
- **What:** Alpaca's asset list drops a stock when it is delisted. The panel was built from that
  list, so it has delistings for 2018 to 2022 and almost none after. Twitter, Activision, VMware,
  Splunk, Pioneer, US Steel, Hess, Discover, Juniper, Ansys and Walgreens are all absent.
- **Size:** about 50 to 60 liquid stocks missing from 2023 on, of the 300 the stat-arb study draws
  from each month.
- **Meaning:** every 2017-2026 result was measured partly on survivors. By how much is not known
  until the panel is repaired.
- **A free repair exists:** Alpaca's corporate-actions feed lists the mergers and removals from
  2020, and Alpaca serves those stocks' prices by symbol. Not started; it needs the owner's go-ahead
  because it will change published numbers.

**4. Repaired: three documentation files.** On 2 November a faulty helper cut `docs/decisions.md`,
`docs/features/README.md` and `docs/research/README.md` down to their last entry. All three were
rebuilt from the last commit plus the recorded changes, and checked line for line against what
survived. Nine decisions entries from 2 November are back.

**Checks:** 203 tests pass; a dry run of the bot is clean; the operator ran the new recording task
by itself at 17:10 ET.

**Next, waiting on the owner:** repair the panel and re-run the frozen studies; then the
opening-auction test.

## 2026-11-09 — First week of `sa_volrev`: −1.1%; a stranded live position found and fixed

**Asked:** the status.

**Sessions 5, 6 and 9 November ran.** The bot started and shut down on time each day. The watchdog
restarted nothing.
- **VIX:** 16.61 on 4 Nov, 28.18 on 5 Nov, 25.64 on 6 Nov. So `sa_volrev` added cohorts on 6 and
  9 Nov and now holds four: those from 2, 3, 5 and 6 Nov.
- **The dead-band fix worked.** On 5 Nov the slot made 87 fills, topping up the names in two cohorts.
  The book now matches its targets: stocks about 64% long and 65% short against 67% and 66%. Only
  11 targets under one share are missing.

**Results** (closing marks, simulated except Wave Rider):

| Slot | 4 Nov | 5 Nov | 6 Nov | 9 Nov | Capital |
|---|---|---|---|---|---|
| `sa_volrev` | $500,191 | $504,625 | $500,122 | **$494,729** | $500,000 |
| `tf_etfs` | $49,412 | $49,606 | $49,967 | $49,274 | $50,000 |
| `pm_actives` | $8,495 | $7,944 | $8,245 | $8,562 | $10,000 |
| `vt_spy` | $9,986 | $9,543 | $9,571 | $9,728 | $10,000 |
| `bps_spy` / `bps_qqq` | $20,211 / $20,469 | $19,961 / $19,581 | $20,018 / $19,827 | $20,265 / $20,292 | $20,000 each |
| `cc_qqq` | $78,717 | $74,566 | $75,524 | $77,643 | $80,000 |

**Live Wave Rider** (paper account):

| Day | Trades | P/L | Note |
|---|---|---|---|
| 4 Nov | 15 | −$54.64 | |
| 5 Nov | 0 | $0 | Down day, so the market gate kept it out |
| 6 Nov | 11 | −$44.07 | |
| 9 Nov | 7 | +$92.31 | Includes the WULF shares below |

**Found and fixed: a live position stranded over the weekend.**
- **6 Nov.** WULF's protective stop was still filling when the bot read it, so the bot's sell asked for
  36 of the 32 shares left and Alpaca refused.
- **Why it stayed stranded.** The position stayed marked as exiting with no order behind it, so
  neither the strategy nor the 15:55 flatten touched it. The 32 shares (about $330) sat without a stop
  until Monday's start-up reconcile adopted them. They were sold at 09:32 for +$36.58.
- **Fix:** the stop is read only once it has settled, and a refused sell clears the mark so the bot
  retries. Two tests; 190 pass. docs/features/07-order-execution.md. In effect from the 10 Nov start.

**Reading the first `sa_volrev` week.**
- **The result:** −1.1% in the volatile week it was built for (VIX peaked at 28).
- **Why it says little:** the first two days carried the dead-band error, and one week is an anecdote.
  The backtest's worst month was −5.0%, so this is well within its range. No change to the rule.

**Later the same day: what stat arb needs next.** The owner asked what would improve the strategies
and will look for outside resources. The assessment and wish list are at the top of
docs/roadmap-advanced-strategies.md. In short:
- **Most valuable resource:** daily stock prices before 2016, delisted stocks included, so the frozen
  rule can be tested once on stress episodes it has never seen.
- **Work needing nothing new:** measure real trading costs from Alpaca's quote history, start recording
  borrow flags and option volatility, and test the sleeves as one book.

## 2026-11-04 — `sa_volrev` traded both days; its second cohort was half-built, fixed

**Asked:** the status of the bot.

**Sessions 3 and 4 November ran cleanly.** Bot started on time both days. Every slot resumed its book.
The watchdog found nothing to restart. No alerts.
- **Live Wave Rider:** −$1.06 on 3 Nov (3 trades), −$54.64 on 4 Nov to 14:40 ET (15 trades, 5 winners, most
  stopped out within minutes). Flat now.
- **VIX closed above 20 on both days** (21.15 on Monday 2 Nov, 20.83 on Tuesday 3 Nov), so `sa_volrev`
  opened a cohort each morning: 49 long and 50 short each.

**Found and fixed: the second cohort was half-built.** The daily slot skips same-side adjustments
smaller than 1% of capital, a rule meant to stop a few-name book from churning on rounding. For
`sa_volrev` that is $5,000, while each name in a cohort is 0.4% ($2,000).
- **What went wrong:** 79 names were picked on both days. Each should have gone from 0.4% to 0.8%,
  but none was added. The ETF hedges were sized for the full book.
- **Result on 4 Nov:** stocks held at 24% long and 22% short against targets of 40% each, while the
  hedges were at full size (SPY −52%, XLK +44%). That left an unintended position of roughly 20% of
  capital: short the market, long technology.
- **Fix:** the band is now a per-slot setting (`dead_band_pct`, default 1%, unchanged for the other
  slots), and `sa_volrev` uses 0.1% ($500). It takes effect at the next bot start (5 Nov, 06:30 ET).
  The 09:35 decision then tops up the 79 names. Test added: 188 pass.
- **What it means for the record:** the 4 November `sa_volrev` mark is not a clean observation of the
  rule. 3 November (one cohort) is.

**Worth watching:** the hedges are about as large as the stock book, much larger than on the backtest
check date (9 April 2025). Most shorts are chip and AI-hardware names, which move more with XLK than
with SPY. So the hedge buys XLK and sells SPY. The rule does this by design. It also means the 5 bp hedge cost in the
backtest is light for weeks like this.

## 2026-11-02 (evening) — Ken French's century: momentum scaled by volatility passes; reversal (stat arb's base) is gone

**Asked:** start with the Ken French data, and plan statistical arbitrage.

**Done:** six series fixed in advance and run over 1927-2026 (docs/research/2026-11-02-momentum-and-reversal-century.md).
- **Momentum scaled by its own volatility** roughly doubled its Sharpe (0.51 to 0.99) and halved its
  crashes (2009: −50% to −18%). The long-only version, closest to `pm_actives`, beat the market with an
  information ratio of 0.83 (t 8.5), and 0.38 (t 2.0) since 2000. It passes, though it has faded since
  2010 (0.24).
- **Short-term reversal**, the effect stat arb trades, earned Sharpe 1.1 to 1.6 a decade until the
  1980s. Since 2000: 0.12, large caps 0.02. A trade can cost at most 1 to 3 bp before it is gone; we
  pay about 5.
- **Caught on the way:** Ken French's daily reversal files re-sort every day and include yesterday's
  bid-ask bounce (an untradable Sharpe of 3.8). Switched to the monthly files and recorded the
  change. The parser now reads monthly files too.

**Stat arb plan** (docs/roadmap-advanced-strategies.md, item 3):
1. A diagnostic first: does a stock's own move (after removing its market and sector moves)
   reverse over 1 to 5 days on our 2017-2026 data, from the next open? It has a kill test.
2. The strategy only if that passes: s-scores (Avellaneda and Lee), dollar- and beta-neutral, real
   costs and borrow.
3. Shadow, then paper with real shorts.

**Then, same evening (owner: "go ahead"): both tests run.**

1. **Stat arb, stage 1** (docs/research/2026-11-02-statarb-stage1.md). Does a stock's own move,
   after removing its market and sector moves, reverse over 1 to 5 days? Point-in-time top 300,
   2017-2026, measured from the next open.
   - **Always-on: the kill test fails.** At best +17 bp per 5-day round trip, never t ≥ 2 in both
     halves, and a trade can cost at most 4.3 bp before it is gone. We pay about 5.
   - **When VIX ≥ 20: +51 bp per round trip** (t 2.6), positive in both halves, and a trade could
     cost up to 13 bp. Zero on calm days. It leans on 2020 (+98 bp) and the 2025 tariff drop
     (+148 bp). It is the best of 18 looks, so it gets its own pre-registered strategy test before
     anything is built.
2. **Momentum with a volatility-scaled overlay** (docs/research/2026-11-02-momentum-overlay.md).
   - **It passes.** Information ratio against SPY 0.43 (plain book 0.48), positive in both halves.
   - **Risk is what it improves:** the worst run of losses against SPY fell from −37.6% to −19.6%,
     and the November 2020 momentum crash from −4.6% to −0.6%.
   - **It costs upside:** 2026 so far +29.7% instead of +74.5%.
   - Nine years cannot prove the edge (t 1.3). The century study is the evidence.

New code: `src/ridethewave/daily/residuals.py` (sector assignment, rolling betas, residuals; 4 tests).
180 tests pass.

**Then (owner: "a lot of volatility this week, can stat arb use it?"):**

The volatile-market reversal was made into a rule the bot can follow and tested with costs
(docs/research/2026-11-02-statarb-volatility-gated.md).
- **The rule:**
  - signal to yesterday's close;
  - only after a VIX close of 20 or above;
  - buy the most-fallen fifth, short the most-risen fifth, hedged;
  - enter at the open, hold 5 sessions;
  - 26 bp of costs.
- **Result:** +29.7 bp per cohort after costs, positive in both halves, +4.3% a year on capital, Sharpe
  0.48, worst drawdown −11.2%, invested 42% of the time.
- **Thin:** t 1.5, and 2020 and the April 2025 tariff drop did most of the work.
- **It passes the bar set in advance, so it goes to shadow as `sa_volrev` from Tuesday 3 November,
  09:35 ET** ($500,000 simulated, nothing sent to Alpaca).
  - VIX closed at 19.42 on Friday, so it trades only if a close this week is 20 or above.
  - It does not trade on our forecast. It cannot trade new listings.
- The live rebuild of cohorts picked exactly the same stocks as the backtest on 9 April 2025.
- Dry run clean; the 09:35 decision takes about 7 seconds. 187 tests pass.
- Feature page: docs/features/24-statarb-volatility-gated.md.

**Next:** watch `sa_volrev` this week. Then a shadow slot for the momentum overlay.

## 2026-11-02 — New direction started: four slots retired, trend sleeve built, the put spread fails a 36-year test

**The last three sessions (29 Oct, 30 Oct, 2 Nov) ran cleanly on the Mac mini.**
- Every start was on time, including Monday, the first day after the clocks went back. No errors,
  no alerts.
- The new sell guard fired six times, all on shadow ORB trades: each time it booked the protective
  stop's fill and sent no second sell.
- **Live Wave Rider: +$42 on 9 trades.** Friday had no trades: SPY stayed below zero all morning, so
  the market gate blocked all 197 candidates. Monday made +$75, mostly from two leveraged funds (TSLG,
  SOXS) held to the 60-minute limit.
- The market fell over the three sessions (SPY −2.6%, QQQ −6.1%, chips worst). The shadow momentum
  book fell 8.6% (INTC −35%, MRVL −32%). The put spreads lost less than half a percent.

**What the owner chose** (all five of the 29 October questions):
1. **Start with trend following plus a long-history test of the put spread.**
2. **Risk budget:** a 10% volatility target, a 15% drawdown limit, and defined-risk option selling
   only. These are defaults, and see finding 4 below.
3. **Outside data allowed:** Ken French, Cboe, FRED.
4. **Which of the 151 strategies worked before:** still to answer.
5. **Retire the failed intraday shadow slots.**

**Done today.**
- **Retired** `wave_rider_15m`, `orb`, `xs_overnight` and `xs_combo` (`enabled: false`). Their code
  and history are kept. A dry run confirmed the bot starts with Wave Rider as its only intraday slot.
  The live slot's capital does not change, because only live weights are pooled.
- **Outside histories** (feature 23): `scripts/download_external.py` fetches ten datasets into
  `data/external/`. US stocks go back to 1926, the S&P 500 to 1975, VIX to 1990, Treasury yields to
  1962.
- **Trend following** (`trend_following`): long or short across 21 ETFs in four classes, each class
  an equal share of risk, the book at 10% volatility. Tested on the ETFs (2017-2026) and on a century
  of stocks and bonds. From tomorrow it runs as the shadow slot `tf_etfs`.
- **A long-history test of the put spread**, priced from S&P 500 and VIX history with a skew curve
  fitted to 55,360 real SPY put prices.
- **A combination study**: the three sleeves at equal risk and a 10% target, 1990-2026.
- **Fixed**: daily portfolio slots ignored `rebalance_days`. They now honour it.
- 175 tests pass. Ruff is clean.

**What the tests found.**
1. **The put spread fails.**
   - Over 1990-2026: 2.4% a year above T-bills (Sharpe 0.25), a −52% drawdown at its current size.
   - It lost as much as the market in 2000-02. The volatility gate helps in fast crashes, not slow
     declines.
   - It is mostly a leveraged bet that stocks stay calm. Not promoted.
   - docs/research/2026-11-02-put-spread-long-history.md
2. **Trend following is insurance, not an alpha.**
   - It earned the T-bill rate over 2017-2026, and a Sharpe of 0.37 over a century.
   - But it made money in the stock market's worst months: 1929-32 +63%, 1973-74 +45%, 2008-09 +13%,
     2022 +26% on the ETFs.
   - It fails in sell-offs that reverse within weeks (April 2025) and in the year after a big trend
     year (2023: −11.7%).
   - docs/research/2026-11-02-trend-following.md
3. **Trend does not rescue the put spread.** Together they still drew down 34% at 10% volatility.
   Trend did nothing in 2000-02, where the put spread lost slowly.
4. **The risk budget's two numbers conflict.** Over 1990-2026, every book holding stock risk drew
   down 26% to 39% at 10% volatility. To stay inside 15% it needed about 4% to 6.5%.
5. **The simplest sleeve did best:** the stock market held at a constant 10% volatility, with a
   Sharpe of 0.63 against 0.51 for buy and hold. That is what `vt_spy` does.

**Decisions for the owner.**
- Risk budget: about 6% volatility with a 15% drawdown, or 10% with about 25-30%?
- The put-spread slots: retire them, or observe at 5% risk per spread (drawdown −11.7% in the test)?
- Which *151 Trading Strategies* worked for you before?

**Next:** momentum on a century of data. It is our only stock-ranking lead, and the first candidate
that could be an alpha rather than a premium (docs/roadmap-advanced-strategies.md).

## 2026-10-29 (evening) — Close report fixed; a backup for the morning start

**The 16:15 close report was out of date.** It ran before the evening fixes, so it showed the QQQ
covered call at $0.00 and Wave Rider with "1 open, 2 trades". The corrected report is
`data/reports/2026-10-29/1802-close.md` (no phone push sent). The 16:18 report is kept as it was.

**Report fixes** (from tomorrow's reports):

1. Every trade row names its strategy. CDE appeared twice because two shadow strategies held it.
   Fixing this exposed that trades and ledger rows read back from the database had lost their
   strategy and all said `wave_rider`. Nothing that trades used that field, so no money or
   allocation was affected.
2. Positions held over several days show their entry date ("15 Oct 16:28"). Before, they looked as
   if they closed before they opened.
3. A credit option structure's P/L % had the wrong sign. The +$303.25 bull put spread showed −90%.
   It now shows +90%. The one stored row and its ledger average were corrected (old value −90.12).
4. Average hold keeps day trades and overnight holds apart ("day trades 239 min (18); held overnight
   or longer 19.0 days (6)"). The single figure of 7017 minutes was meaningless.
5. The close report has a table of every strategy's ledger, the books of record. The one-line summary
   came from the bot's last tick, so it missed anything corrected after the bot stopped.

**Morning start: confirmed, and now with a backup.** The bot had never yet been started by its
06:30 ET calendar job on the Mac mini. The system log shows the job fired on time this morning
(05:30:03 Central). It started nothing, because the bot was already running from last night's
restart test. As insurance, the watchdog now also starts the bot from 07:00 ET if the morning
start did not run, and sends a phone alert. Also checked for running unattended: automatic login
is on, FileVault is off, the Mac never sleeps and restarts after a power cut, 160 GB is free,
Tailscale connects the Mac mini and the laptop, and macOS will not install updates by itself.

155 tests pass. Details: `docs/features/14-operator.md`, section 4.

## 2026-10-29 — First session on the Mac mini; one execution bug found and fixed

**The session ran cleanly.** The bot started at 09:28 ET with a 62-stock universe on the first try, and
every 30-minute rebuild succeeded. Ticks were steady with no gaps. Every report and phone push went out,
and no alerts fired. Live Wave Rider made three trades, GOOG, IOVA and NUWE. All three were stopped out,
for −$32.93.

**Bug: the bot could try to sell shares the protective stop had already sold.** Alpaca's stop sold NUWE at
11:27:12 ET. Six seconds later the bot's own exit sent a market sell for the same 151 shares. Alpaca refused
it only because NUWE cannot be shorted; on a stock that can be, it would have opened a short. The bot also
kept NUWE as held, and the $15.10 loss was missing from its records. Fixed: the bot now checks the stop
before selling, books the stop's fill if it got there first, and a live slot never sells more shares than
Alpaca holds. The missing NUWE trade is recorded. A one-off job removes the leftover NUWE position once
today's bot exits. Details: `docs/features/07-order-execution.md`.

**Also fixed: the watchdog could not read the boot time** under launchd, because `sysctl` was not on the job's
PATH. And a correction: after a restart, launchd itself starts the bot again at login, as the 28 October
restart test showed. The watchdog is a backup, not the only cover.

All fixes are on the Mac mini, with 142 tests passing there. The running session was not touched. The order
fix applies from the 30 October start, and the watchdog fix from the next five-minute check.

**At the close.** The account was flat at $99,937.81, with no positions or open orders. The NUWE cleanup ran,
and the live ledger shows −$32.93 on three trades. The shadow `bps_qqq` closed a day before expiry for +$303.25.
`pm_actives` rebalanced for the first time since 19 October. The day-trade shadow slots closed at 15:55:
`xs_overnight` −$14.20, `xs_combo` −$50.66, the opening-range breakout −$12.27.

**Bug: the shadow QQQ covered call was booked at $0.00. The real figure was −$1,892.13.** Its short call
was quoted bid 0 / ask 0.02. The shadow fill rule needed a bid on every leg, and its fallback, the last
mark, had been lost in last night's restart, so the books took the entry price. Fixed: a close now
accepts a quote with an ask and no bid. Missing prices fall back to mid, then the saved last mark, then
exercise value, and the fallback used is logged. Marks now survive restarts. The record was re-priced the
same evening (database backup `data/ridethewave.db.bak-cc_qqq-20261029163032`). `bps_spy` would have hit
the same thing at its 5 November close. 146 tests pass on the Mac mini. Details:
`docs/features/22-options-engine.md`.

## 2026-10-28 (evening) — Moved to the Mac mini

The system now runs on the Mac mini, not the laptop.

| Item | State |
| --- | --- |
| Machine | The Mac mini, user `admin` |
| Project folder | `/Users/admin/Projects/Finance/Ride The Wave` |
| Checks on the Mac mini | Connection check all passed, 136 + 3 tests, dry run with a 61-stock universe, test push delivered |
| Scheduled jobs | Installed; the bot is waiting for the open on 29 October |
| Laptop | Scheduled jobs removed; keys file renamed, so it cannot trade |

**Before you travel:** install Tailscale on the Mac mini and the laptop, signed in to the same account,
and turn off key expiry for the Mac mini. Then from anywhere: `ssh admin@<the Mac mini's Tailscale name>`.
Subscribe to the ntfy topic on your phone. The name is in `.env` on the Mac mini, and it was given in the
session.

**First thing to check on 29 October:** the 09:00 pre-market push, then that the universe has stocks and
the log has no gaps after the close.

## 2026-10-28 — A month of mostly empty sessions, found and fixed

**What happened between 25 September and 28 October.** The bot started on all 24 trading days. Only 30
September and 5 October ran a full session with stocks to scan. Two causes:

- **The Mac was asleep.** The power log shows the laptop on battery and asleep through most market hours.
  It woke for a few seconds at a time for macOS maintenance. The bot's `caffeinate` assertion cannot stop
  sleep on battery or with the lid closed. No wake schedule is set. Each time the Mac woke, the first call
  to Alpaca failed on a dead connection, and on most days that call was the universe build.
- **A new exchange broke the asset list.** From 20 October Alpaca listed ten stocks on the Texas Stock
  Exchange (`TXSE`). alpaca-py rejects that code and drops the entire list, so every universe build failed
  from 20 to 28 October. The intraday strategies had nothing to scan, and the momentum portfolio skipped
  its decisions. The health check said "healthy" throughout.

**Results over the month.** These cannot be used to judge any strategy, because most sessions were empty.

| Slot | Mode | Result to 28 Oct |
| --- | --- | --- |
| Wave Rider | live | 8 trades, 2 wins, −$19.68; paper account $99,970.74 |
| pm_actives (momentum) | shadow | $9,338 from $10,000; frozen since 19 Oct |
| vt_spy (volatility targeting) | shadow | $10,022 |
| bps_qqq, bps_spy (bull put spreads) | shadow | +$294 and +$174 open |
| cc_qqq (covered call) | shadow | −$1,284 open, mostly the QQQ shares |

**Fixed today** (106 tests pass; a dry run against the paper account built a 61-stock universe and ran every slot):

1. The asset list is read as raw data, so an unknown exchange code can no longer break it (`data/assets.py`).
2. Every Alpaca call retries a failed or dropped connection. Read-only calls also retry a lost response,
   and orders are never sent twice.
3. The start-up universe build gets three attempts. While the universe is empty, the bot retries every 2
   minutes. Stocks that arrive late get their history.
4. New alerts: an empty universe, and a portfolio or options decision that was skipped.
5. The report's positions table now shows which strategy holds each position. The column was missing.

**Needed from you.** Keep the Mac on power and awake from before the open until after the close on
weekdays. Set the wake schedule once: `sudo pmset repeat wakeorpoweron MTWRF 08:05:00`. If the lid has to
stay closed, `sudo pmset -a disablesleep 1` keeps the Mac awake, but it then never sleeps. An always-on
machine, such as a Mac mini or a small cloud server, would remove the problem for good.

**Decided: a Mac mini becomes the always-on machine.** Setup and handover steps, including remote
access from anywhere through Tailscale, are in `docs/mac-mini-setup.md`. Until it arrives, keep the laptop
plugged in and awake in market hours. Built the same evening: phone alerts through the free ntfy app.
Every alert, plus a short push when each check-in report is ready, reaches your phone. The machine is a Mac mini M1 (2020) with 8 GB and 256 GB.
That is enough: about 7 GB at peak with research running, and the database grows about 1 GB a year. It
needs macOS 15 or later for Homebrew. Also built: a watchdog that restarts the bot if the Mac restarts
during market hours (corrected the next day: launchd already restarts it at login, so the watchdog is a backup). A bot you stop by hand stays
stopped. 136 tests pass.

**Also noticed, not changed.** The SPY bull put spread opened on a weekly expiry (6 November). The
backtest only tested monthly expiries, so this slot is not running exactly what was tested. The two QQQ
positions expire on 30 October. Their close rule runs on the 29th at 15:40 ET, but only if the Mac is
awake.

## 2026-09-24 (session review) — First live trade; two operational fixes

- **Session.** Wave Rider's first live trade: 30 SRZN at $32.48 at 10:42 ET, stopped out a minute later at
  $32.11 (−$11.10) by the 1% server stop. All shadow strategies flat. The volatility-targeting portfolio
  bought 13 SPY at 15:50 and holds overnight (the first overnight position in the system). Options gates
  closed on SPY and QQQ (implied minus realised volatility 2.0 to 2.7 points, threshold 3). Ledgers written
  for all ten slots; four check-in reports.
- **Stall.** The bot froze for seven minutes at 14:09 ET inside a network call and recovered on its own.
  Cause: alpaca-py sends requests without a timeout. Fixed: every Alpaca client now carries connect and
  read timeouts (10 s / 30 s).
- **Empty universe.** The 08:43 universe build failed on a dropped connection; the intraday slots picked
  up the 30-minute rebuild, the momentum portfolio did not and decided on an empty universe at 15:50.
  Fixed: portfolio universes follow every rebuild and a decision retries the build if the universe is empty.

## 2026-09-24 (morning) — Options backtest: the first family that holds up on risk

**Completed**

- Downloaded daily bars for every SPY, QQQ and IWM option on the monthly expiries since March 2024,
  including expired contracts and the holiday-shifted expiries. Built a backtester that rebuilds each
  past day's chain and runs the bot's own options slot through it (`docs/research/2026-09-24-options-backtest.md`).
- 144 configurations. Iron condors lose (the inherited 2% strikes lost everything on SPY in a rising
  market). The bull put spread with strikes 5% and 10% out, entered only when options are expensive
  relative to realised volatility, held to expiry, matched or beat each index's risk-adjusted return
  with about a third of its drawdown, positive in both halves on all three. It sat out the April 2025
  crash because the gate was closed, then entered when premiums were richest.
- Caveat: one bull market, one crash, about 20 trades each. A candidate to observe, not a proven edge.
- The shadow options slots now run exactly these tested settings: `bps_spy`, `bps_qqq`, `cc_qqq`.
- Two engine fixes: the strike distance is now a setting (it was fixed at 1% per step), and structures
  are sized from current equity instead of starting capital.

**Next**: momentum leaning into high-volatility markets; fill reconciliation before any options slot
goes live.

**Also (24 September, small hours).** Two short-side questions from the owner answered with data:
shorting large caps on negative news loses in nearly every event category (they bounce); post-earnings
drift in ranks 101 to 1000 has the textbook shape (−58 bp a month after a crash of over 8%, +33 bp after a
jump of over 8%) but t-statistics near zero and hit rates of 52 to 55%, so it is not tradable here
either. Both recorded in `docs/research/2026-09-24-news-daily-jev.md`. Jev spend so far: $30.43.

## 2026-09-24 (early morning) — News study done and rejected; a benchmark bug found and fixed

**Completed**

- **News as a daily feature** (`docs/research/2026-09-24-news-daily-jev.md`): Jev scored 357,240
  headline-symbol pairs from 2019 to 2026 with the new question set (relevance, event type, surprise,
  durability added); $23.14, zero errors. All four pre-registered tests fail: news volume does not help
  forecast volatility, sentiment does not predict returns, it does not improve momentum, and a
  news-ranked universe does not beat the ordinary one. Negative or legal news tends to recover over the
  next month, which is why excluding it hurt. No news feature is adopted; the scores are kept.
- **Benchmark bug fixed.** The daily engine's "hold the universe" comparison averaged every stock that
  was ever in the universe, including those that got in later because they had risen. Corrected to
  point-in-time with a test. On the honest benchmark the universe earned 16.8% a year (not 22.4%), and
  long-only price momentum beats it by 5 to 9 points a year in both halves (information ratio 0.51,
  t 1.6): the leading daily candidate, still short of the t ≥ 2 gate.
- The momentum shadow portfolio now uses the live most-active universe (`pm_actives`) instead of the
  hindsight list of 20 mega caps.

**Next**: the options backtester; a momentum variant that leans into high-volatility markets (the one
result with t above 2); fill reconciliation before any options slot goes live.

## Handoff of 2026-09-23, late evening (superseded by the entry above)

**State of the system.** Everything is committed locally (no GitHub remote yet). 91 tests pass, lint
clean. Tomorrow 24 September the bot runs from launchd: Wave Rider live; in shadow: 15-minute Wave
Rider, ORB (0.25 ATR), `xs_overnight`, `xs_combo`, two daily portfolios (`pm_megacaps`, `vt_spy`,
deciding 15:50 ET, holding overnight) and three options structures (`ic_spy` with the VRP gate,
`bps_qqq`, `cc_aapl`, deciding 15:40 ET). Check with `curl localhost:8787/api/health` or the reports.

**What the evidence says so far.** No strategy tested has an edge: intraday patterns are noise on
our data; the book's daily stock rankings do not beat their own universe, on a survivorship-free
point-in-time universe from 2017, in the 2023-26 window, or by regime (momentum's only pocket is
high-volatility chop, t 1.0 to 1.6; shorting the bottom of a momentum ranking loses 17-21 points a
year in bull trends, t -2.6 to -3.2). TraderPro's profit factors were a hindsight universe. Risk
overlays (vol targeting, 200-day rule) halve drawdowns at equal Sharpe. Details:
`docs/research/2026-09-23-traderpro-extraction.md` sections 3 to 5c.

**The discussion in progress when the session ended.** The owner asked whether news sentiment could
drive the universe and what other non-financial influences exist; the answer given (news predicts
volatility and attention, not direction, except multi-day pockets such as post-earnings drift and
negative/legal news) and the ranked list of other influences are in the chat only, so the essentials
are repeated here:

- Other influences worth testing, by evidence and availability: macro calendar (pre-FOMC drift, CPI),
  calendar effects (turn of month, quarter end, expiration), options-implied features (IV rank, skew,
  volatility risk premium; we hold the data), short interest (FINRA), insider transactions (EDGAR),
  earnings calendar (outside feed; unlocks post-earnings drift), attention (search, Reddit; reversal),
  credit spread and cross-asset regime inputs. Principle: separate "what moves" (volatility, attention)
  from "which way" (direction); most non-financial data is the first kind and belongs in the selector.
- **Pending decision (the owner has loaded Jev credits):** the news study design. Proposed: keep the six
  existing Jev questions (version 2026-09-21.1, `src/ridethewave/signals/jev_questions.py`) unchanged,
  add two ("durable": does the information change the outlook over the coming weeks; "surprise": was
  it anticipated), bump the version, score the Alpaca news archive (reaches back to 2015) for the
  survivorship-free monthly top-100 universe 2019-2026 (about $40), re-score the September pairs with
  the new set for comparability, and build daily per-symbol features: headline counts (1 and 5 days,
  relative to the name's own history), impact-weighted sentiment with a 5-day decay, share of
  negative/legal items, earnings flag.
- Four pre-registered tests with kill criteria: (1) does abnormal news volume predict next-5-day realised
  volatility beyond past volatility (drop if under 10% added explanatory power); (2) does sentiment
  predict 1/5/20-day excess return over the universe by quintile (drop if no spread reaches t 2 in both
  halves); (3) do the exclusion (fresh negative/legal) and the tilt (earnings-up) lift momentum's IR
  against its universe by at least 0.2; (4) does a universe ranked by news materiality beat the
  dollar-volume universe. Then the zero-cost tests: calendar effects and options-implied features on
  data already held.
- **Reframing agreed in the last exchange:** Jev is the right tool for turning text into typed events
  cheaply and the wrong tool for forecasting direction (the September test showed direction is priced
  before the headline exists). So the news study's questions should be event extraction first:
  relevance (is the company the subject or only mentioned), a finer event type (earnings release,
  guidance change, upcoming-earnings-date announcement, M&A, FDA/regulatory decision, offering or
  dilution, analyst action, product, macro), surprise, durability, materiality, negative/legal, toxic.
  Two uses that fall out of it are worth more than sentiment: an earnings calendar reconstructed from
  the archive (Alpaca has none; unlocks post-earnings drift) and a market-wide macro-event-day feature
  for the regime classifier. Counts, volatility and returns do the predicting; Jev does the reading.
- After that, in order: the options backtester from Alpaca's option bars (February 2024 onward),
  the overnight-effect brief in `docs/strategy-intake.md`, fill reconciliation before any options slot
  goes live.

**Owner items still open.** `gh auth login` then
`gh repo create ride-the-wave --private --source=. --remote=origin --push` (five local commits waiting);
`sudo pmset repeat wakeorpoweron MTWRF 08:05:00`; strategy briefs go in `docs/strategies/inbox/`.

## 2026-09-23 (late) — Capability map and strategy intake

- `docs/alpaca-capabilities.md`: everything the account and data plan enable versus what the bot uses.
  Unused and available: short selling, extended hours, fractional and dollar orders, crypto (73 pairs),
  websocket streams, tick history, corporate actions, bracket and trailing-stop orders, option history
  since February 2024.
- `docs/strategy-intake.md`: the brief template and the seven-stage pipeline every idea goes through;
  briefs go in `docs/strategies/inbox/`.
- Survivorship-free daily history (7,786 active and delisted stocks since 2016) downloaded to
  `data/daily_panel/`; the "started in 2017" replay of ten daily strategies on a monthly point-in-time
  top 100 confirms the earlier verdict: none beats holding its universe (IR −1.1 to +0.2), all
  long-short versions flat or negative (research page, section 5b). A 2023-26-only window and a
  regime breakdown (section 5c) add: momentum's edge sits in high-volatility chop (t 1.0 to 1.6);
  shorting the bottom of the ranking loses 17 to 21 points a year in bull trends (t −2.6 to −3.2).

## 2026-09-23 (night) — Options engine ported and wired to Alpaca's options API

**Completed**

- Verified the upgraded provisions: paper account at options level 3 with $100k options buying
  power; OPRA real-time chains with quotes, implied volatility and greeks (`docs/api/options.md`).
- Ported TraderPro's options engine (feature 22): the 57 Chapter-2 structures as leg templates,
  Black-Scholes and implied volatility, chain snapshots, the resolver, sizing and exit rules, and a
  new options slot kind (`options:` in settings) that keeps one structure open per underlying and
  decides at 15:40 ET. Shadow fills against live quotes; live mode places multi-leg orders on the
  paper account (implemented, not yet exercised).
- Three observation slots run in shadow from 24 September: an iron condor on SPY gated on the
  volatility risk premium, a bull put spread on QQQ, a covered call on AAPL.

**Next**: watch the first structures open and close; a chain-reconstruction backtester from Alpaca's
historical option bars; fill reconciliation before any slot goes live; a structures tab on the web page.

## 2026-09-23 (evening) — TraderPro extracted; daily portfolio engine built; the book's rankings tested honestly

**Completed**

- Inventoried the owner's July 2026 platform TraderPro (85 book strategies, own backtester, options
  engine, regime/sentiment selector, React UI): `docs/research/2026-09-23-traderpro-extraction.md`.
- Built the daily portfolio research engine (`src/ridethewave/daily/`, feature 20) and ported 13
  price-only book strategies plus TraderPro's regime classifier. Ten years of adjusted daily bars
  cached for 43 named symbols and a 320-name pool.
- Replicated TraderPro's champions on the same universe and period: ranking reproduces, levels are
  higher because TraderPro's data was unadjusted (splits looked like crashes); but holding its 20
  mega caps equal-weight earned 28.7% a year, so the rules added little.
- Point-in-time test (top 50/100 by dollar volume from a 254-stock pool, 2017 to 2026): no stock
  ranking beats holding its own universe; all long-short versions flat or negative. ETF and index
  rules do not beat SPY on return; volatility targeting and the 200-day rule halve the drawdown.

**What this means.** The "really good profit factors" came from a hindsight universe measured
without a benchmark. What is worth keeping from TraderPro is infrastructure and the risk controls.

**Also built tonight**: the daily portfolio slot (feature 21). Two observation portfolios run in
shadow from 24 September, deciding at 15:50 ET and holding overnight: `pm_megacaps` (12-1 momentum on
the 20 mega caps) and `vt_spy` (volatility targeting on SPY). Positions and cash survive restarts;
shorts are allowed; nothing reaches Alpaca.

**Next**: observe the two portfolios, then short selling and overnight holds on the paper account; a
survivorship-free pool before trusting any long-only ranking.

## 2026-09-23 — *151 Trading Strategies* mapped; cross-sectional day trades built and tested; two shadow slots for 24 Sep

**Completed**

- Read the Kakushadze & Serur paper and mapped all 20 chapters against what Alpaca gives us:
  `docs/research/2026-09-23-kakushadze-151-feasibility.md`. Only the stock and ETF chapters are usable
  today, and most of those need short selling, overnight holds or outside data.
- Built the book's open-to-close alphas as a long-only strategy family (`xs_daytrade`: overnight
  reversal, previous-day momentum, intraday reversal, combo). Feature page:
  `docs/features/19-cross-sectional-daytrade.md`.
- Ran the research protocol: a diagnostic (`scripts/study_xs_signals.py`) found no ranking power in any
  score; 37 backtest configurations all lose (profit factors 0.52 to 0.91). Two least-bad variants
  (`xs_overnight`, `xs_combo`) run in **shadow** from 24 September as observation only.
- Fixed two plumbing bugs: strategy-specific stops and sizing never reached the broker (the ORB's real
  result is PF 0.74 at its 0.1-ATR stop, 0.91 at 0.25 ATR, now used); the backtest script gave
  strategies no daily bars.
- Added a per-strategy `stocks_only` switch that drops ETFs, leveraged products and crypto trusts.
- Handbook (shared doc and `docs/handbook.md`) gained section 4.9, a results row and the reference.

**What runs on 24 September**: Wave Rider live; 15-minute Wave Rider, ORB (0.25 ATR), `xs_overnight`
and `xs_combo` in shadow. Nothing from the book has capital.

**Next**: short selling in the execution layer (unlocks the book's dollar-neutral stock strategies),
then a daily-portfolio executor with overnight holds for monthly-rebalance strategies.

## 2026-09-23 — TypeScript API and web UI

- `web/` (Fastify on Node 26) reads the bot's SQLite file and serves `http://127.0.0.1:8787`: status
  tiles, per-strategy figures with pause / resume / flatten buttons, positions, trades, reports.
- Control requests are queued in the database and applied by the bot each tick (from the first bot start
  after 23 September). Streamlit on port 8501 still runs alongside.
- First git commit made locally; pushing needs `gh auth login` then
  `gh repo create ride-the-wave --private --source=. --remote=origin --push`.

## 2026-09-22 — Two strategies in shadow, first full paper day lessons

- 15-minute Wave Rider (PF 1.00 with the market gate) and long-only opening-range breakout built, both
  in shadow. Engine gained per-strategy bar resampling and daily-bar session context.
- First full day (22 Sep): bot exited at 09:29 on a pre-open clock check (fixed), launchd calendar jobs
  fired two hours late (scheduling moved to a five-minute dispatcher), shutdown crash fixed.

## Earlier (17 to 21 September)

Phases 0 to 19 in the `CLAUDE.md` status table: environment, core, data, strategy, execution, backtester,
dashboard, ledger; sweeps and entry filters (first thin profitable configuration, PF 1.25); Dixon skill and
research protocol; Algo Trader Plus data plan; operator layer; multi-strategy core; SPY intraday momentum
rejected; news via Jev validated and not adopted as a filter.
