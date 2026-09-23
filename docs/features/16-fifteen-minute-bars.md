# 16 · Strategies on slower bars

**What it does.** Any strategy can declare the bar size it wants (`bar_minutes`). The bot and the
backtester keep working on 1-minute bars underneath and roll them up per strategy, anchored at
09:30 ET, so a 15-minute strategy sees bars for 09:30, 09:45, 10:00 and so on, each complete only
when the next bucket's first minute arrives. Price ticks still reach the strategy every 15 seconds
for exits.

**Why.** The diagnostic of 21 September found no streak signal on 1- or 5-minute bars and a small
one on 15-minute bars. This makes that testable and tradeable without touching the strategy code.

**How to use it.** In settings, a strategy entry with `params: {bar_minutes: 15}`; the Wave Rider
registry factory reads it. In a backtest, `--param-json '{"bar_minutes": 15}'`. The 15-minute Wave
Rider currently runs in shadow mode (observation only) with the parameters from
[research/2026-09-22-fifteen-minute-and-orb-backtests.md](../research/2026-09-22-fifteen-minute-and-orb-backtests.md).

**Limits.** Features that need 20 prior bars (the trade-count and relative-volume filters) are not
available early in the day on slow bars and are left off for them. The warm-up bars are rolled up
too, so a strategy starting mid-session has history.

**Code:** `src/ridethewave/data/resample.py`; `bar_minutes` on `Strategy`; the resampler inside
`TradingEngine`.
