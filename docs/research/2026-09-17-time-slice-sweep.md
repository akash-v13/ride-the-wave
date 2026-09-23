# Time-slice and parameter sweep of Wave Rider v1

**Data:** 2026-06-01 to 2026-09-16, 75 trading days, SIP minute bars, regular session only.
**Universe:** point-in-time top 50 by trailing 20-session dollar volume, recomputed daily (80 distinct symbols over the period). No lookahead except survivorship (today's asset list).
**Fill model:** next-bar fills, 0.05% slippage each way, safety stop at the open on gaps.
**Tooling:** `scripts/download_history.py`, `scripts/sweep.py`. Raw CSVs in `data/sweeps/`.

## Base configuration (settings.example.yaml defaults)

1,816 trades, win rate 47%, profit factor 0.76, net -$1,714 on a $10,000 allocation, max drawdown $1,801, average hold 50 minutes.

By entry half-hour (ET):

| Entry | Trades | Win rate | PF |
|---|---|---|---|
| 09:30 | 534 | 48% | 0.85 |
| 10:00 | 308 | 49% | 0.93 |
| 10:30 to 12:30 | 653 | 45 to 54% | 0.70 to 0.88 |
| 13:00 | 100 | 40% | 0.59 |
| 13:30 | 84 | 35% | 0.36 |
| 14:00 | 81 | 33% | 0.28 |
| 14:30 | 56 | 48% | 0.72 |

By exit reason:

| Exit | Trades | Win rate | Avg P/L |
|---|---|---|---|
| wave_exit | 690 | 96% | +0.79% |
| timeout | 234 | 75% | +0.39% |
| server_stop | 838 | 0% | -1.00% |
| close_flatten | 53 | 34% | -0.20% |

## Single-parameter grids (best and worst of each)

| Grid | Best | PF | Worst | PF |
|---|---|---|---|---|
| Entry window | 09:31 to 11:30 | 0.86 | 11:00 to 15:00 | 0.69 |
| Streak / min gain | 3 bars, 1.0% | 0.84 | 10 bars, 1.0% | 0.54 |
| Trail / gain floor | 1.5% / 0.5% | 0.82 | 0.3% / 0.2% | 0.71 |
| Hold / hard stop | 120 min / 2.0% | 0.80 | 30 min / 0.5% | 0.70 |

## Combined best-of-each (8 combinations)

Entry 09:31, streak 3, min gain 1.0%, trail 1.5%, floor 0.5%, plus:

| Entry end | Stop | Hold | Trades | Win rate | PF | Net |
|---|---|---|---|---|---|---|
| 11:30 | 1.0% | 60 | 1,219 | 36% | **0.91** | -$615 |
| 13:00 | 2.0% | 120 | 930 | 50% | 0.90 | -$737 |
| 13:00 | 1.0% | 60 | 1,334 | 36% | 0.88 | -$834 |
| others | | | | | 0.85 to 0.86 | |

## Conclusions

1. **Time of day is a real effect.** Entries after 13:00 ET lose roughly three times as fast as morning entries. Ending the entry window at 11:30 or 13:00 is a free improvement.
2. **No parameter combination reaches break-even.** The best of 62 configurations is profit factor 0.91. The strategy as designed (buy after a streak, trail from the peak, fixed stop) loses because the stop fires on nearly half of entries, and each stop costs more than the average wave exit earns.
3. **Long streaks are worse, not better.** Waiting for confirmation means buying after the move is spent.
4. **Hold time barely matters.** Stop distance matters more than any exit knob, but a wider stop only converts losers into smaller, more frequent losers.
5. **What is missing is an entry filter, not a better exit.** The next experiments should change *which* streaks get bought: relative volume, trade count, distance from VWAP, and market-wide direction (SPY trend at entry). That is the volume-feature dataset already planned.
6. These are SIP numbers. IEX would show fewer streaks and thinner fills; absolute results would be worse, the direction of the findings should hold.

## Suggested defaults going forward

`entry_end: 11:30`, `green_streak_minutes: 3`, `min_streak_gain_pct: 1.0`, `trail_pct: 1.5`, `min_gain_pct: 0.5`. Not applied yet; the owner decides.
