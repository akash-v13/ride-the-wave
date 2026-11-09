# The "survivorship-free" price panel is missing delisted stocks, mostly from 2023 on

**Found 9 November 2026,** while checking the stat-arb universe for the new daily recordings
(feature 25). Nothing has been repaired yet. This page records the evidence and a repair plan.

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
