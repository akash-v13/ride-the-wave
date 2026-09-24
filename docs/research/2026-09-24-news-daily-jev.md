# News as a daily feature: 357,000 headlines scored with Jev, four pre-registered tests, all fail

**Run 24 September 2026.** Design pre-registered in the handoff of 23 September (`docs/progress.md`):
question set, universe, features, four tests and their kill criteria were written before any score
existed. Script `scripts/study_news_daily.py` (subcommands universe, fetch, pairs, score, features,
test); data under `data/research/news_daily/`; full report `data/research/news_daily/report.md`.

## What was done

- **Universe.** The survivorship-free monthly top 100 by dollar volume (active and delisted stocks),
  2019-01 to 2026-09: 93 months, 380 distinct names.
- **Headlines.** Every Alpaca/Benzinga item tagged with those names, 2019 to 2026: 376,675 items.
  Pairs kept when the company was in that month's universe and the item tags at most eight tickers:
  **357,240 headline-symbol pairs.**
- **Jev**, question set `2026-09-24.1`: the six September questions unchanged (direction, positive,
  materiality, kind, stale, toxic) plus relevance, a twelve-way event type, surprise and durability.
  About 1,540 input tokens per pair; **$23.14, zero errors**, 31 minutes at 195 pairs a second.
- **Features per symbol and trading day** (news after 16:00 ET counts for the next day; trades at the
  next open): relevant-headline counts (1 and 5 days), abnormal news volume (5-day count against the
  name's own trailing 120-day rate), impact-weighted sentiment ((p_up − p_down) × (materiality + 0.5) ×
  (durability + 0.2), 2-day half-life), material news over 21 days, negative or legal flags, earnings
  and guidance up or down.

Of the pairs, 58% were judged relevant to the company; half of all items reported no event at all.
Event types: product or contract 53k, analyst action 50k, macro 23k, earnings release 16k,
regulatory 15k, M&A 7.6k, earnings-date notice 4.8k, guidance change 4.4k, offering 4.3k.

## Results

Universe: 194,100 symbol-days, 55,624 with relevant news that day. Halves split at 2022-11-10.

| Test (pre-registered) | Kill criterion | Result | Verdict |
| --- | --- | --- | --- |
| 1. Abnormal news volume predicts next-5-day realised volatility beyond past 20-day volatility (cross-sectional) | relative R² gain < 10% | R² 0.378 → 0.379 (+0.2%), same in both halves; coefficient slightly negative | **fails** |
| 2. Sentiment quintiles predict 1, 5, 20-day excess return over the universe | no Q5 − Q1 with t ≥ 2, same sign both halves | −2.4 bp (t −1.2), −8.6 bp (t −0.4), −7.9 bp (t −0.7) | **fails** |
| 3. Momentum improved by excluding fresh negative/legal news or tilting to earnings-up names | IR gain < 0.2 | baseline IR 0.53 → 0.19 with the exclusion, 0.49 with the tilt | **fails** (the exclusion hurts) |
| 4. The most-newsworthy half of the universe beats the universe | same-sign excess in both halves | IR −0.16; −2.2% / +1.1% by half | **fails** |

Event pockets (excess return over the universe, basis points, +20 days t with a √20 overlap correction):

| Event on day d | n | +1 d | +5 d | +20 d | t | 1st / 2nd half +20 d |
| --- | --- | --- | --- | --- | --- | --- |
| Earnings or guidance, up | 3,885 | +3.2 | −1.7 | −4.9 | 0.2 | −4.9 / −4.9 |
| Earnings or guidance, down | 2,452 | +3.4 | +3.4 | −30.6 | −0.2 | −37.1 / −24.5 |
| Negative or legal (last 3 days) | 47,392 | +2.3 | +5.5 | +24.9 | 0.9 | +35.0 / +15.0 |
| Abnormal news volume, top decile | 13,050 | −2.3 | −11.8 | −13.7 | −0.1 | −9.0 / −18.6 |

## Reading

1. **In the 100 most-traded US stocks, public news carries no daily-horizon edge we can find**, in
   direction, volatility or selection. These are the most analysed companies in the world; the
   September finding (the price moves before the headline) extends from minutes to weeks.
2. **The one pattern with a consistent sign is the opposite of the intuition**: names with negative
   or legal news recovered over the following month (+25 bp, both halves positive, t 0.9). That is
   why excluding them hurt momentum. It is reversal of over-reaction, too weak to trade alone.
3. **Post-earnings drift is absent here**, where the literature finds it. The literature's effect
   lives in small and mid caps with slow analyst coverage; our universe is the opposite. The +79 bp
   pocket from September did not survive seven years.
4. **The earnings calendar exists as a by-product** (`earnings_calendar.json`: 297 names), though it
   records about two releases per symbol-year because only months inside the universe were scored.
   It is usable for option-risk hygiene (avoiding short premium through earnings), not as a signal.

## Decisions

- No news feature enters any strategy or the universe. The scores are kept (they are the cheapest
  event database we will ever have) and the question set stays at `2026-09-24.1`.
- If news is revisited, it is in the places this test did not cover and the literature points to:
  small and mid caps, and news as an options-volatility input around events.
- Cost discipline held: $23 of an agreed $40, capped at $40 in code.
