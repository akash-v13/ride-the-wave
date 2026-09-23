# 11 · Entry filters (volume, context and market features)

**What it does.** After the streak rule says "buy", a set of optional gates can still say "no". Each
gate compares one feature of the current bar against a threshold from `config/settings.yaml`
under `entry.filters`. A gate set to `null` is off. All gates off means no feature computation at
all, so the strategy behaves exactly as before.

**The features** (computed by `src/ridethewave/features/compute.py` from the current session's bars
only, so live and backtest agree):

| Feature | Meaning |
|---|---|
| `rvol_20` | this minute's volume divided by the average of the previous 20 minutes |
| `streak_vol_ratio` | average volume during the streak divided by the 20 minutes before it |
| `trade_count_ratio` | same for number of trades. Low means fewer, larger trades made the move |
| `vwap_dist_pct` | how far the price is above the session's volume-weighted average price |
| `session_ret_pct` | how far the stock is up on the day already |
| `range_pct_20` | the stock's normal minute-to-minute range, in percent (its "noise") |
| `gain_vs_range` | the streak's gain measured in units of that noise |
| `spy_ret_5m_pct`, `spy_ret_session_pct` | what the whole market (SPY) did in the last 5 minutes and since the open |
| `minutes_since_open` | |

**How thresholds were chosen.** `scripts/build_features.py` records every minute of every universe
stock in the entry window (446,233 rows over June to September 2026) with these features and with
what happened next, including the P/L our own exit rules would have produced.
`scripts/analyze_features.py` buckets each feature against that P/L. A search over single gates
and combinations, with the period split chronologically into halves so a gate must work on both,
found three that reinforce each other:

- `min_spy_ret_session_pct: 0.1`: only buy when the market itself is up on the day.
- `max_session_ret_pct: 0.6` to `1.0`: skip stocks that have already run.
- `max_trade_count_ratio: 0.7`: prefer streaks made by fewer, larger trades.

In the replay engine the three together gave profit factor 1.25 on 116 trades over June to
September 2026 (about 1.5 trades a day), positive on each half of the period separately and on
IEX data. They are the defaults as of 2026-09-17. Details and caveats in
[docs/research/2026-09-17-feature-analysis.md](../research/2026-09-17-feature-analysis.md).

**Settings.** `entry.filters.*` in settings.yaml. Sweep them with
`scripts/sweep.py --param entry.filters.max_session_ret_pct=0.6,1.0 ...`.

**Live requirement.** SPY is always polled alongside the universe so the market features exist.

**Code:** `src/ridethewave/features/`, `src/ridethewave/strategy/wave_rider.py` (`_filter_reject`).
