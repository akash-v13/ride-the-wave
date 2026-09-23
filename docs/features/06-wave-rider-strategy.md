# 06 · Wave Rider strategy

**What it does.** Decides when to buy and when to sell. It is the code form of [docs/strategy.md](../strategy.md); read that first for the reasoning and the worked example.

**Buy** when a stock has closed higher for `green_streak_minutes` consecutive bars, the total rise is at least `min_streak_gain_pct`, the volume over the streak is at least `min_streak_volume`, the time is inside the entry window, a slot is free, and the symbol has not been traded today already.

**Sell** (checked on every price tick, in this order):
1. **Wave exit.** Price has fallen `trail_pct` from its peak since entry, and selling now still keeps at least `min_gain_pct` over the entry price.
2. **Hard stop.** Price is `hard_stop_pct` below entry.
3. **Timeout.** Held longer than `max_hold_minutes` and (by default) in profit.
4. **Close flatten.** It is `flatten_time` ET or later.

**Pure code.** The strategy reads bars and positions passed to it and returns signals. It never talks to Alpaca or the database, so the identical code runs in backtests and it is tested with hand-built bar sequences (`tests/test_wave_rider.py`).

**Adding a strategy.** Subclass `Strategy` in `src/ridethewave/strategy/base.py`, implement `on_bar` and `on_tick`, and swap it in the runner. The universe, execution and dashboard stay unchanged.

**Code:** `src/ridethewave/strategy/`.
