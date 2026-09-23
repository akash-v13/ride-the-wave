# Does the streak work on slower bars? 5- and 15-minute diagnostic

**Follows** [2026-09-17-streak-autocorrelation.md](2026-09-17-streak-autocorrelation.md), which found
1-minute returns are white noise and the 1-minute streak is not predictive. Same data (SIP,
2026-06-01 to 09-16, point-in-time top 50, 82 symbols, 75 days), same script with `--bar-minutes`.
Streaks are counted in consecutive rising closes of the aggregated bars; the entry window is
09:30 to 11:30 ET on the bar's start; the candidate rule is streak ≥ 3 and 3-bar gain ≥ 1%.

## 5-minute bars: still nothing

| Condition | n | +5m | +10m | +15m | +30m | +60m |
|---|---|---|---|---|---|---|
| Unconditional | 87,975 | 0.0 | -0.2 | -0.5 | -1.2 | -2.2 |
| Up-streak = 3 | 5,132 | +1.1 | +1.7 | +1.3 | -0.8 | -2.3 |
| Candidate rule | 2,751 | +1.8 | -0.9 | -0.8 | -1.6 | **-13.5 ± 7.6** |

Basis points, mean forward log-return. Same shape as 1-minute bars: a few basis points for a few
minutes, then reversal. Pooled autocorrelation at lags 1 to 3 inside the ±0.0048 band.

## 15-minute bars: a signal

| Condition | n | +15m | +30m | +45m | +90m | +180m |
|---|---|---|---|---|---|---|
| Unconditional | 26,775 | -0.7 | -0.8 | -1.6 | -1.6 | +0.6 |
| Up-streak = 3 | 1,406 | +0.4 | +1.2 | +3.0 | +8.3 | +10.7 |
| Up-streak = 4 | 592 | +4.2 | +3.3 | +12.3 | +20.1 | +24.8 |
| Candidate rule (gain ≥ 1.0%) | 977 | +3.4 | +4.4 | +7.8 | +18.4 | **+22.0 ± 12.0** |

Positive and growing with horizon, which is what a momentum trigger needs and what neither faster
bar size showed. The effect scales with the gain threshold:

| Gain threshold | n | +180m |
|---|---|---|
| ≥ 0.5% | 1,530 | +17.1 ± 8.3 |
| ≥ 1.0% | 977 | +22.0 ± 12.0 |
| ≥ 1.5% | 602 | +30.9 ± 17.5 |

And it holds in both halves of the period, with different baselines:

| Period | n | Candidate +180m | Unconditional +180m | Margin |
|---|---|---|---|---|
| Jun 1 to Jul 14 | 435 | +29.4 ± 20.8 | -10.0 | +39 |
| Jul 15 to Sep 16 | 542 | +16.0 ± 13.9 | +7.7 | +8 |

## Reading

1. **Intraday momentum in single stocks exists at the 15-minute scale in this sample, not at 1 or
   5 minutes.** A 45-minute run of rising closes with a 1% gain continues, on average, for the next
   one to three hours.
2. **It is small.** About 20 basis points over three hours on average, against 10 basis points of
   assumed round-trip slippage. A strategy built on it needs the exits to keep most of the winners'
   run and the filters to raise the hit rate, exactly the two things the 1-minute version already
   relies on. The margin over baseline in the second half (+8 bp) is well inside the noise.
3. **Selection caveat.** Three bar sizes were tested and one came out positive; the book's
   model-selection warnings apply (Rashomon, p. 63; Example 2.4, p. 68). The two-halves check and
   the monotonic gain-threshold response are the evidence against a fluke, not proof. The IEX feed
   has not been tested at this bar size yet.
4. **Timing consequences.** Three 15-minute bars from 09:30 means the earliest entry is 10:15 ET,
   and a 3-hour horizon from an 11:30 entry runs to 14:30. The entry window and the 15:55 flatten
   still fit; the 60-minute timeout does not.

## What to build next (proposed, not started)

A 15-minute variant of Wave Rider in the replay engine: aggregate bars in the aggregator with a
`bar_minutes` setting, keep the strategy code unchanged (it already works on bars), re-sweep exits
at the slower scale (trail, floor, stop and a 3-hour timeout), then apply the three filters and
compare with the 1-minute version on the same days, SIP and IEX. Run the diagnostic on IEX bars
first; if the effect vanishes on the feed the bot trades, stop there.

Reproduce: `uv run python scripts/diagnose_returns.py --start 2026-06-01 --end 2026-09-16 --bar-minutes 15 --window 09:30-11:30`
and the same with `--start 2026-06-01 --end 2026-07-14`, `--start 2026-07-15 --end 2026-09-16`,
`--streak-gain 0.5`, `--streak-gain 1.5`. Logs in `data/research/`.
