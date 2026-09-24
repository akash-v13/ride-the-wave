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

## Follow-up: shorting on bad news (asked by the owner, 2026-09-24)

Forward excess return over the equal-weight universe after each kind of negative, relevant, fresh
item (the direction question says "down"), from the next open. Positive numbers mean the stock
*rose* relative to its peers, so a short would have lost.

| Negative event | n | +1 d bp | +5 d bp | +20 d bp | t (+20 d) | halves +20 d |
| --- | --- | --- | --- | --- | --- | --- |
| earnings release, down | 3,706 | +2 | +6 | −32 | −0.3 | −56 / −10 |
| guidance change, down | 1,632 | +3 | +15 | 0 | −0.1 | +61 / −55 |
| regulatory decision, down | 5,774 | +5 | +7 | +95 | +0.8 | +117 / +76 |
| offering or dilution | 1,571 | +24 | +42 | +43 | +0.4 | −38 / +116 |
| M&A, down | 1,028 | −11 | −21 | −53 | 0.0 | −94 / −21 |
| management change, down | 1,033 | −12 | +7 | +23 | +0.2 | −8 / +48 |
| analyst action, down | 12,355 | +9 | +13 | +4 | −0.3 | +12 / −3 |
| product or contract, down | 6,203 | +5 | +20 | +62 | +0.4 | +70 / +54 |
| any material negative event | 10,781 | +2 | +4 | +22 | +0.2 | +18 / +25 |
| material, confident (p_down > 0.7) and unexpected | 2,236 | +8 | −11 | +9 | 0.0 | −11 / +25 |
| toxic flag (fraud, restatement, going concern, dilution) | 983 | +24 | +27 | −22 | 0.0 | −94 / +37 |
| durable and down (p_durable > 0.7) | 12,097 | +4 | +8 | +26 | +0.4 | +37 / +16 |

In the 100 most-traded stocks, a short opened at the next open after bad news lost on average in
every category except the two smallest (earnings releases down: −32 bp over a month, halves −56 and
−10, t −0.3; M&A down: −53 bp, t 0.0). Regulatory bad news and product bad news were followed by
recoveries of 60 to 95 bp. The market over-reacts to bad news in large caps by the open, and the
month after is a partial bounce. Shorting on sentiment in this universe is a losing strategy; the
only candidate is post-earnings drift on the downside, which is too weak here to trade and, in the
literature, lives in smaller companies.
## Follow-up: post-earnings drift below the top 100 (asked by the owner, 2026-09-24)

The one short-side pocket that survived above was earnings; the literature puts post-earnings drift
in smaller, thinly covered companies. Universe: ranks 101 to 1000 by dollar volume, monthly and
point-in-time (2,149 distinct names, active and delisted). 686,000 headlines fetched, 113,173
earnings-related headline-symbol pairs scored with Jev ($7.29, zero errors), 25,754 earnings releases
identified on 1,782 symbols, 2019 to 2026. Drift measured from the next open after the reaction day,
in excess of the band's equal-weight return; t uses day clusters and a square-root-of-horizon
correction. Script: `scripts/study_news_daily.py pead`; data `data/research/news_pead/`.

| Reaction-day return | n | +5 d bp | +20 d bp | +40 d bp | t (+20 d) | halves +20 d | share negative at +20 d |
| --- | --- | --- | --- | --- | --- | --- | --- |
| below −8% | 2,684 | −14 | −58 | −97 | −0.2 | −80 / −43 | 55% |
| −8% to −4% | 3,246 | −2 | +25 | +16 | +0.3 | +35 / +15 | 52% |
| −4% to −1% | 4,625 | −4 | −4 | +16 | +0.2 | −17 / +10 | 52% |
| −1% to +1% | 4,187 | −2 | −11 | −43 | −0.2 | +9 / −37 | 52% |
| +1% to +4% | 4,762 | −8 | +5 | −11 | −0.2 | +37 / −32 | 51% |
| +4% to +8% | 3,484 | +2 | +5 | +8 | +0.1 | +33 / −22 | 51% |
| above +8% | 2,766 | +15 | +33 | +46 | 0.0 | +75 / +1 | 52% |

By Jev's reading of the release rather than the price: "down" releases +13 bp at 20 days (t 0.2,
halves +58 / −35); "down" with a reaction below −4%: −17 bp at 20 days, −37 at 40 (t −0.1);
"up" with a reaction above +4%: +17 and +20 bp (t 0.0).

**Reading.** The shape is the textbook one, drift continues in the direction of the reaction at the
extremes (−58 bp after a crash of more than 8%, +33 bp after a jump of more than 8% at 20 days, both
growing to 40 days), and the size is a fraction of what the older literature reports. It is not
statistically distinguishable from zero in this sample (t 0.2 at best) and the hit rate is 52 to
55%. After spreads and borrow on small caps, which are wider than the 5 bp assumed here, the short
side of this is not a strategy either; the long side after big positive surprises is the better
half of it and still thin. Verdict: post-earnings drift exists in this universe in the expected
shape but is too small and too noisy to trade with these tools.

## Decisions

- No news feature enters any strategy or the universe. The scores are kept (they are the cheapest
  event database we will ever have) and the question set stays at `2026-09-24.1`.
- If news is revisited, it is in the places this test did not cover and the literature points to:
  small and mid caps, and news as an options-volatility input around events.
- Cost discipline held: $23 of an agreed $40, capped at $40 in code.
