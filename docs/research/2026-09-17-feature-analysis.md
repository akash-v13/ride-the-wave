# Feature dataset, entry filters and volatility-scaled exits

**Data:** same as the time-slice sweep: 2026-06-01 to 2026-09-16, 75 days, SIP minute bars, point-in-time top-50 universe, plus SPY for market context. Base parameters = the sweep's best (entry 09:31 to 11:30, streak 3 at 1.0%, trail 1.5%, floor 0.5%, stop 1%, hold 60).

## The dataset

`scripts/build_features.py` recorded every minute of every universe stock inside the entry window: **446,233 prospect rows**, of which **8,370** met the streak rule (candidates). Each row has the features in `src/ridethewave/features/compute.py` and labels from `labels.py`: best and worst excursion within 60 bars, whether +1% was hit before -1%, and the P/L our own exit rules would have produced from that bar.

Headline numbers for the candidate rows versus every prospect:

| | Rows | Win rate | Profit factor | Stop rate |
|---|---|---|---|---|
| Every bar in the window | 446,233 | 43% | 0.77 | 38% |
| Bars the streak rule would buy | 8,370 | 36% | 0.86 | 62% |

The streak rule adds a little over buying at random, and it doubles the stop rate: it selects bars right after a fast move, which is when the pullback comes.

**Noise.** Median candidate per-minute range is 0.63%. A 1% stop is 1.6 "normal minutes" away. Stop rate rises with noise: 52% in the quietest quartile, 69% in the noisiest. Mean best excursion within an hour is +1.8%, mean worst is -1.9%: the price swings both ways well beyond our exit distances.

## Single features (quintile buckets on candidates)

No single feature separates winners from losers strongly; spreads between best and worst quintile are 0.07% to 0.27% per trade, and most are not monotonic. Full tables in `data/features/analysis-candidates.txt`. Nothing here is usable on its own.

## Combinations, with a chronological train/test split

Split at 2026-07-14. A gate combination had to have at least 150 trades in each half. Of 2,717 combinations, the top ones all shared three ingredients:

| Gate | Meaning |
|---|---|
| `spy_ret_session_pct >= 0.1` | the market itself is up on the day |
| `session_ret_pct <= 0.6` (to 1.0) | the stock has not already run |
| `trade_count_ratio <= 0.7` | the streak was made by fewer, larger trades than the minutes before it |

Dataset approximation for the three together: train profit factor 1.44, test 1.50.

## Confirmation in the replay engine (real slot limits, one entry per symbol per day, next-bar fills)

24-combination grid over the three thresholds. Every row with both `spy >= 0.1` and `trade_count_ratio <= 0.7` was profitable; every row without both was not.

| SPY gate | Session gate | Trade-count gate | Trades | Win rate | PF | Net |
|---|---|---|---|---|---|---|
| 0.1 | 0.6 | 0.7 | 116 | 35% | **1.25** | +$168 |
| 0.1 | 2.0 | 0.7 | 168 | 34% | 1.20 | +$185 |
| 0.1 | off | 0.7 | 222 | 35% | 1.16 | +$192 |
| 0.1 | 1.0 | 0.7 | 134 | 31% | 1.09 | +$71 |
| 0.0 | 0.6 | 0.7 | 203 | 36% | 0.99 | -$13 |
| 0.1 | 0.6 | 0.8 | 179 | 31% | 0.98 | -$21 |
| off | off | off | 697 | 35% | 0.84 | -$635 |

Robustness of the top row:

| Slice | Trades | PF | Net |
|---|---|---|---|
| First half, Jun 1 to Jul 14, SIP | 65 | 1.20 | +$72 |
| Second half, Jul 15 to Sep 16, SIP | 51 | 1.31 | +$94 |
| Full period, **IEX feed** (what the bot sees live) | 47 | 1.17 | +$38 |

By hour for the top row: 09:30 to 10:00 carries it (79 trades, PF 1.33); 10:00 to 10:30 is negative (22 trades, PF 0.62); later buckets are too small to read.

## Volatility-scaled exits

Trail, floor and stop as multiples of the stock's per-minute range at entry (`exit.vol_scaled`). Alone, best of 12 combinations was PF 0.95 (trail 4x, floor 1x, stop 2x) versus 0.91 fixed: a small gain. Stacked on the filters it **hurt**: PF 0.85 versus 1.25 with fixed exits. Left implemented but off.

## Conclusions

1. The three gates are the first configuration that is profitable in the engine, positive on both halves, and positive on the live feed. Adopted as defaults on 2026-09-17; the pre-filter set is `config/profiles/v2-sweep-2026-09-17.yaml`.
2. It is thin: about 1.5 trades a day, +$168 over 3.5 months on $10k, roughly 0.7% a month before the effects paper trading hides. The margin over break-even is real but small, and 116 trades is not a large sample. Treat it as "worth paper trading", not "proven".
3. The market gate does the most work. When SPY is not up on the day, the streak strategy should not trade at all.
4. The biggest structural weakness remains: 62% of candidate entries hit the stop. Filters reduce how often we enter; they do not change the stop-versus-target geometry. Ideas not yet tested: enter on the *first* pullback after the streak instead of at its top; require the streak to start from below VWAP; a time-of-day cutoff at 10:00 given the hour breakdown.
5. With the dataset in place, a classifier (logistic regression or gradient boosting on all features, trained on the first half, tested on the second) is the natural next step, and it will tell us whether there is more edge than three hand-picked gates capture.
