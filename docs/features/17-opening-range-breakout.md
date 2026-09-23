# 17 · Opening-range breakout on stocks in play (long-only, shadow)

**What it does.** At the open, each stock's first 15 minutes set an opening range. A stock is "in
play" if that span traded at least 3 times its normal volume for 15 minutes (normal = its 14-day
average daily volume scaled to 15 of 390 minutes). After the range closes, the first 1-minute close
above the range high buys. The stop sits 0.1 average true ranges (14 sessions, from daily bars)
below entry and travels with the order as a server-side stop; the position is sized to risk 1% of
the strategy's allocation between entry and stop, capped by the slot; it is sold at the stop or at
15:55. One entry per stock per day, at most five open.

**Formula.** In play if `V_range ≥ rvol_min × V̄_daily × range_minutes / 390`. Entry when
`close > H_range`. Stop `= entry − stop_atr × ATR14`. Quantity `= risk_pct × allocation / (entry − stop)`.

**Daily context.** Before each session the bot hands every strategy its symbols' last 40 calendar
days of daily bars (`on_session_start`), from which this one computes average volume and ATR. The
backtester does the same per day, from cached daily bars.

**Evidence.** Backtest June to September 2026 on the top-50 universe: best profit factor 0.93 on
253 trades; winners that reach the close average +2.2% but only 22% of entries win. Runs in
shadow mode as observation only. The published strategy also shorts breaks below the range and
draws its universe from the whole market; both are open items.

**Settings.** `strategies:` entry with `kind: orb` and params `range_minutes`, `rvol_min`,
`stop_atr`, `risk_pct`, `entry_until`, `exit_time`, `max_positions`, `min_price`.

**Code:** `src/ridethewave/strategy/orb.py`; the sizing and stop hooks in the order manager.
