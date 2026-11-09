# The "survivorship-free" price panel is missing delisted stocks, mostly from 2023 on

**Found 9 November 2026,** while checking the stat-arb universe for the new daily recordings
(feature 25). **Repaired the same evening:** section 5 has what was added and every study's result
before and after. Sections 1 to 4 are the finding as first written.

## 1. What the panel was meant to be

`data/daily_panel/` holds adjusted daily prices from 2016 for 7,729 US stocks. It was built on
23 September 2026 by `scripts/download_universe_history.py` from Alpaca's asset list, active and
inactive, so that stocks which were later delisted would be in it. Every 2017-2026 study draws its
point-in-time universes from it: momentum, the momentum overlay, the news studies, both stat-arb
stages and the cost study.

## 2. What is wrong

**Alpaca's asset list does not include every delisted stock.** When a stock is delisted now, it
drops out of the list. It does not move to the inactive part.

Evidence:
1. **Well-known delisted stocks are absent.** TWTR (2022), ATVI and VMW (2023), SPLK, PXD and CTLT
   (2024), X, HES, DFS, JNPR, ANSS and WBA (2025): none is in the list, active or inactive, and
   none is in the panel. The failed banks of 2023 (filed by Alpaca as SIVBQ and FRCB) and BBBYQ are
   not in the panel either.
   - Alpaca knows each of them when asked by name, and serves its full price history. Only the
     list leaves them out.
2. **The panel's delistings stop in 2022.** Stocks in the panel whose prices end in each year:

   | 2016-17 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
   |---|---|---|---|---|---|---|---|---|---|
   | 0 | 112 | 271 | 209 | 407 | 235 | 13 | 9 | 16 | 15 |

3. **The same for the stat-arb universe.** Stocks that were in the monthly top 300 within a year of
   their prices ending: 9, 20, 20, 17 and 12 in 2018 to 2022, then none in 2023, 2024, 2025 or 2026.
   At 12 to 20 a year, roughly 50 to 60 liquid stocks are missing from 2023 on.
4. **It is still happening.** Of the panel's stocks that were active on 23 September, 108 are in
   neither part of the list seven weeks later. None moved to inactive. Two of them, KVUE and WBD,
   are in the live stat-arb universe file.

## 3. What it means

- **The panel is free of survivorship bias for 2018 to 2022 only,** and not fully even then (TWTR
  left in October 2022 and is missing). For 2023 to 2026 it holds survivors, plus a few dozen
  exceptions. Stocks delisted in 2016 or 2017 are missing too.
  - **Corrected after the repair:** this understated it. A stock delisted in 2024 was missing from
    every earlier year as well, so all years were affected, the early ones most (section 5).
- **Every 2017-2026 result carries the gap.** How much each one changes is not known until the
  panel is repaired and the studies are re-run. In which direction, by kind of stock:
  - **Takeover targets** jump on the news and then barely move. Leaving them out probably matters
    little to a reversal book and removes some winners from a momentum book.
  - **Collapses** matter more. A rule that buys the stocks that fell most is the one most exposed
    to a stock that keeps falling to nothing. Whether any such stock was in the top 300 on a day
    the rule traded is not known until the repair.
- **The live bot is not affected.** It trades from the current asset list. The two dead names in
  the stat-arb universe file cannot be picked, because their prices have stopped.

## 4. A free repair exists

Alpaca's corporate-actions feed lists mergers and removals, with volume from 2020 on:

| Year | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Mergers and removals listed (up to 1,000 a request) | 0 | 2 | 0 | 36 | 835 | 840 | 664 | 982 | 932 | 806 | 969 |

It contains every example above that was a merger (TWTR, X, HES, DFS, JNPR, ANSS, WBA).

**Proposed repair, not started:**
1. Collect every symbol removed by a merger, a removal or a symbol change since 2020 from the feed.
2. Download their prices and add them to the panel, with the date each stopped trading.
3. Re-run the frozen studies unchanged (stat-arb stage 1 and the VIX-gated rule first, then
   momentum and its overlay) and report old against new. No rule is altered, so this adds no new
   look at the data.

**What it will not fix:** stocks delisted in 2016 and 2017, and any the feed itself leaves out.
An outside source of delisted stocks (the first item on the owner's wish list) would close those
and check the rest.

## 5. Repaired, 9 November 2026

**How.** `scripts/repair_daily_panel.py`, `src/ridethewave/data/delistings.py`.
1. **The names came from Massive** (formerly Polygon.io), once: its list of 6,994 delisted US common
   stocks and ADRs with their last trading dates. The owner's key is on the free plan, which serves
   this list but only two years of prices.
2. **The prices came from Alpaca.** Each missing stock was asked for by the symbol it had ten days
   before it left. Alpaca served 3,943 of 4,294.
3. **Ticker changes were removed.** 1,235 of those were only an old name of a company the panel
   already held under its new symbol (FB is META, ABC is COR). They were found by matching each
   one's last ten days of volume against the panel.
4. **2,708 delisted stocks were added,** as `bars_delisted_*.parquet` beside the old files. Their
   prices end in: 2016 155, 2017 262, 2018 176, 2019 92, 2020 83, 2021 35, 2022 254, 2023 553,
   2024 455, 2025 388, 2026 242.

**Nothing depends on Massive from here on.** The list is a file under `data/reference/`. Alpaca's
own asset list is now saved every day (feature 25), and `left_the_list` reads a delisting from two
days of it, so the record continues in-house.

**How much was missing from the stat-arb universe.** 140 of the added stocks were in the monthly top
300 at some time. Share of each year's top 300 that had been missing:

| 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| 8.1% | 5.7% | 4.7% | 4.2% | 4.0% | 4.0% | 3.4% | 1.5% | 0.8% | 0.5% |

The early years were hit hardest: a stock delisted in 2024 had been missing since 2017.

**Every study, re-run unchanged.** Old results are kept in `data/research/pre-repair-2026-11-09/`.

| Study | Measure | Before | After |
|---|---|---|---|
| Stat arb stage 1, 5-day reversal, all days | Spread per round trip (t) | +17.3 bp (2.2) | +16.2 bp (2.0). Kill test still fails |
| Stat arb stage 1, VIX ≥ 20 | Spread per round trip (t) | +50.9 bp (2.6) | +45.1 bp (2.3) |
| VIX-gated rule, at the assumed 5 bp | Net per cohort (t) | +29.7 bp (1.5) | **+24.9 bp (1.2)** |
| | Halves | +37.4 / +22.3 | +32.1 / +17.9 |
| | A year on capital; Sharpe; drawdown | +4.3%; 0.48; −11.2% | +3.6%; 0.42; −13.3% |
| VIX-gated rule, at measured spreads, as the slot trades | Net per cohort (t) | +11.9 bp (0.6) | **+7.5 bp (0.4)** |
| | Halves | +18.8 / +5.4 | +14.0 / +1.4 |
| Momentum, long-only top 100 | Information ratio against the universe (t) | 0.51 (1.6) | 0.49 (1.5) |
| | Universe return a year | 16.8% | 16.2% |
| | Excess over the universe by half | 5.0 / 8.9 points | 4.0 / 8.9 points |
| Momentum, long-short | Information ratio against the universe | −0.51 | −0.50 |
| Momentum with the overlay | Information ratio against SPY, plain / overlay | 0.48 / 0.43 | 0.44 / 0.39 |
| | Worst stretch against SPY, overlay | −19.6% | −21.6%. Still passes |

The cost study was run again on the new picks: half-spread 10.8 bp at 09:35 (was 10.9), and waiting
until 09:35 still gains 5.7 bp per cohort.

**Reading.**
- **Every result moved down, none changed its verdict.** The gap flattered the numbers by about a
  tenth to a sixth.
- **The stat-arb rule is weaker again.** As the slot trades, it earns +7.5 bp per cohort, t 0.4, and
  the second half is +1.4 bp. That is no edge.
- **Momentum barely moved.** It remains the best lead, still unproven over nine years.
- **Takeovers were most of what was missing, not collapses.** Only 42 of about 93,500 picks on
  volatile days were of a stock that stopped trading within the five-day hold. All were takeovers
  (Twitter, Xilinx, Raytheon). The studies leave such picks out, and that made no difference here.

**What the repair does not cover.**
- **351 listed tickers that Alpaca had no prices for.**
- **A ticker used by two companies that both left** keeps only the later one.
- **About 200 tickers with no date in the list** were looked up year by year, which can pick the
  wrong company for a reused ticker.
- **What a stock was worth after its last trading day** (a bankrupt company's shares on the
  over-the-counter market) is not in the prices.
- **The list itself is one vendor's.** It has not been checked against a second source.
