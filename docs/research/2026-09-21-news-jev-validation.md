# Does Jev's reading of a headline predict the stock? News validation study

**Question.** Before building a news filter, test whether TypeSafe's Jev model, asked six typed
questions about a headline, produces scores that predict the stock's forward return, and whether
those scores would have improved the base strategy's entries.

**Data.** Alpaca (Benzinga) news for the 81 symbols that were in the point-in-time universe between
1 June and 16 September 2026: 11,735 headlines, 21,081 headline-symbol pairs, scored by Jev
(jev-1.13.0) with the questions in `src/ridethewave/signals/jev_questions.py` (direction, positive,
materiality, kind, stale, toxic). 179 calls failed (0.8%). Cost $0.85, 20.2 million input tokens,
about six minutes. Labels from cached SIP minute bars: entry at the first bar after publication (or
the next open), forward returns at 30, 60 and 180 minutes, to the close and to the next close, plus
the move from the prior close to entry ("pre-move", how much was already in the price). 19,833 pairs
labelled; 45% were published in session hours. Script: `scripts/study_news_jev.py`; outputs under
`data/research/news/`.

## Jev reads headlines consistently

The signs line up: items it calls "up" had a pre-move of +2.0%, items it calls "down" −2.1%. The
stale flag catches roundups and lists (76% of pairs were stale or tagged with more than eight
symbols). Categories are sensible. As a classifier of headlines it works.

## But positive news has no forward edge intraday, and hurts our entries

Fresh items (stale < 0.5, at most eight symbols), direction with confidence ≥ 0.6, mean forward
return in basis points:

| Direction | n | +30m | +60m | +180m | to close | next close | pre-move |
| --- | --- | --- | --- | --- | --- | --- | --- |
| up | 2,826 | +3.1 | +5.9 | +0.6 | −6.6 | −15.3 | +2.03% |
| down | 652 | −16.5 | −14.1 | −15.6 | −17.1 | +33.6 | −2.10% |
| none | 77 | −6.0 | −10.9 | −10.6 | −5.8 | +0.5 | −0.53% |

"Major" items of either direction are followed by negative returns (−25 bp at 30 minutes): the
reaction is over by the time a bar exists. Fresh, material, positive items (n = 294) show
−5.5 ± 46 bp at 180 minutes with a pre-move of +4.0%.

For the base strategy's 8,370 candidate entries, the strategy's own P/L by news in the prior six
hours:

| Candidates | n | Win rate | Mean P/L | Profit factor |
| --- | --- | --- | --- | --- |
| No fresh news | 7,220 | 36.3% | −0.08% | 0.88 |
| Fresh news, direction up | 885 | 35.3% | −0.18% | 0.74 |
| Fresh news, down or legal | 203 | 40.4% | −0.03% | 0.96 |
| With the three live gates | 321 | 44.2% | +0.36% | 1.63 |
| Gated, fresh up news | 14 | 28.6% | −0.34% | 0.55 |
| Gated, no fresh news | 294 | 45.9% | +0.41% | 1.73 |

A streak in a stock with fresh positive news is more often an exhaustion point than a continuation.
Excluding such entries raises the gated result from 1.63 to about 1.7, on 14 trades, so the
practical gain is small.

## Pockets, checked on each half

| Pocket | n | +180m (all) | First half | Second half | Reading |
| --- | --- | --- | --- | --- | --- |
| Direction down, any kind | 652 | −15.6 ± 19 | −12.7 | −18.2 | Consistent drift lower; risk hygiene for a long-only book |
| Legal or regulatory, any direction | 315 | −50.7 ± 28 | −73.4 | −22.1 | Consistent and large; exclude |
| Product news, direction up | 1,176 | −31.1 ± 16 | −37.8 | −23.4 | Positive product news is followed by reversal |
| Analyst or opinion, direction up | 943 | +40.2 ± 20 | +21.9 (close −6.5) | +62.3 (close +84.6, pre-move +7.4%) | Unstable; second half is names already up a lot |
| Earnings or guidance, direction up | 370 | +13.1 ± 36 | +8.2 | +15.3 | Nothing intraday; +79 bp to the next close suggests a multi-day drift |

Many pockets were compared (kinds × directions × horizons), so the one positive pocket that is
stable in sign (analyst up) should be treated as a lead, not a result, until more data arrives.

## Decision

1. **No news filter as an entry confirmer.** Positive news does not predict continuation at our
   horizon and is a mild negative for streak entries.
2. **A news exclusion is cheap and directionally right** (drop entries in names with fresh
   down, legal or regulatory news), but on this data it changes almost nothing, so it is low
   priority rather than a build.
3. **Keep collecting.** Scoring the universe's daily headlines costs cents a day and turns the
   analyst-note and post-earnings pockets into testable strategies within a few months. The
   post-earnings drift belongs with the multi-day strategies on the roadmap, not the intraday bot.
4. Jev itself behaved as advertised: fast, cheap, consistent, and easy to interrogate. Its place
   in this system is as a labelled feature source for research, until a use passes the protocol.

Reproduce: `uv run python scripts/study_news_jev.py fetch|score|analyze --start 2026-06-01 --end 2026-09-16`.
