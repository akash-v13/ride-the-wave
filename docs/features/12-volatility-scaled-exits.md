# 12 · Volatility-scaled exits

**The problem it solves.** With fixed percentages, a 1% stop is the same distance for a stock that
normally moves 0.3% a minute and one that moves 1.2% a minute. In the June to September dataset
the median candidate moved 0.63% per minute, so a 1% stop was about a minute and a half of
ordinary noise, and the stop fired on 52% of entries in the quietest quarter of stocks but 69% in
the noisiest.

**What it does.** When `exit.vol_scaled: true`, the trail, the minimum-gain floor and the hard
stop are multiples of the stock's per-minute range measured at entry (`range_pct_20`, the average
high-to-low range over the previous 20 minutes):

    trail    = range × trail_range_mult        (default 2.5)
    floor    = range × gain_floor_range_mult   (default 1.0)
    stop     = range × stop_range_mult         (default 2.0)

with `range` clamped between `noise_floor_pct` (0.2) and `noise_cap_pct` (2.0) so a dead-quiet or
wild stock cannot produce absurd distances. The measured range travels with the order: the
protective stop sent to Alpaca is placed at the scaled distance, and the position remembers its
noise so exits stay consistent for its whole life.

**Positions adopted after a restart** have no recorded noise and fall back to the fixed
percentages.

**Settings.** `exit.vol_scaled`, `exit.trail_range_mult`, `exit.gain_floor_range_mult`,
`exit.stop_range_mult`, `exit.noise_floor_pct`, `exit.noise_cap_pct`. Off by default until the
sweep in docs/research says otherwise.

**Code:** `ExitSettings.effective()` in `src/ridethewave/config.py`; used by the strategy and the
order manager.
