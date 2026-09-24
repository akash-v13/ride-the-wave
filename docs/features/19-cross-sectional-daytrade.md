# 19 · Cross-sectional day trades from *151 Trading Strategies* (long-only, shadow)

**Where it comes from.** Kakushadze & Serur (2018) describe stock strategies that rank a whole
universe against itself rather than looking at one chart: mean-reversion within a group (§3.9),
"alpha combos" (§3.20), and, in Appendix A, the two alphas their own backtest code trades from the
open to the close of the same day: *delay-0 mean-reversion* on the overnight move and *delay-1
momentum* on the previous day's open-to-close move. This feature is the long half of those ideas,
adapted to what our stack can execute (no short selling, no industry map).

**What it does.** Once per session, on the first completed minute bar at or after `entry_time`
(09:31 or 09:35 ET), every company stock in the universe that has a 09:30 bar and yesterday's daily
bar gets a score. Scores are log returns with the universe average subtracted, so a day when
everything gaps down does not make everything look cheap. The `top_n` highest scores above
`min_score_pct` are bought with equal dollars (or dollars in proportion to 1/volatility), each with
a hard stop `stop_pct` below entry (checked by the bot and placed as a server-side stop leg) and an
optional target, and everything is sold at `exit_time` (15:55). Names whose overnight move is larger
than `max_gap_pct` are skipped, because the news study showed such gaps keep drifting. Funds,
leveraged products and crypto trusts are excluded from the ranking (`stocks_only`).

**The four scores.**

| `signal` | Score (higher = buy) | Meaning |
| --- | --- | --- |
| `overnight_reversal` | −(r_on − mean r_on), r_on = ln(open today ÷ close yesterday) | buy the names that fell most overnight relative to peers |
| `prev_day_momentum` | +(r_pd − mean r_pd), r_pd = ln(close yesterday ÷ open yesterday) | buy yesterday's relative intraday winners |
| `intraday_reversal` | −(r_id − mean r_id), r_id = ln(price now ÷ open today) | at a later `entry_time`, buy the relative laggards since the open |
| `combo` | overnight_reversal + prev_day_momentum | the book's two Appendix-A alphas, equal weight |

`invert: true` trades the opposite side of any ranking (for example overnight continuation).

**Worked example.** 48 stocks scored at 09:31. The average overnight move is −0.4%. A stock that
opened −2.9% has r_on − mean = −2.5%, so its overnight-reversal score is +2.5%, rank 1 of 48. With
`min_score_pct: 0.5` and `top_n: 5` it is bought at the ask plus 0.1% (say $97.10), the stop leg
goes in at $94.19 (3% below), and unless the stop or a target hits, it is sold at 15:55.

**Evidence (June to September 2026, top-50 point-in-time universe, full tape).** The signal
diagnostic (`scripts/study_xs_signals.py`, write-up in
`docs/research/2026-09-23-kakushadze-151-feasibility.md`) found no ranking power in any of the three
scores: daily rank correlations with the open-to-close return have t-statistics of −0.4, −0.9 and
+0.3, and the "buy" quintile is the worst-performing one for two of them. Backtests agree: 16
signal-by-entry-time combinations all lose (profit factors 0.52 to 0.90); with a 3% stop, a third
of the trades stop out for −2.5% each while trades that reach the close win 66% of the time at
+1.2%. The sample's liquid stocks drifted down between the open and the close on average (−16 bp a
day), which a long-only leg cannot escape; the book's version is dollar-neutral. Runs in shadow as
observation only. Not a candidate for allocation.

**Settings.** A `strategies:` entry with `kind: xs_daytrade` and params `signal`, `entry_time`,
`exit_time`, `top_n`, `min_score_pct`, `max_gap_pct`, `stop_pct`, `target_pct`, `weight_by`
(`equal` | `inv_vol`), `min_price`, `min_universe`, `vol_lookback`, `demean`, `invert`,
`stocks_only`. `top_n` is also capped by `entry.max_positions`.

**What it needed from the rest of the bot.** The strategy sizing and stop hooks (`qty_for`,
`stops`) are now handed to the order manager by both the runner and the backtester (they were not
before, so the ORB's ATR stops had been the global 1% stop); the backtest script now supplies daily
bars to strategies; a `stocks_only` flag on any strategy makes the runner and the point-in-time
universe drop funds for that strategy alone (`is_fund` in `src/ridethewave/data/universe.py`).

**Code:** `src/ridethewave/strategy/xs_daytrade.py`; tests in `tests/test_xs_daytrade.py`.
