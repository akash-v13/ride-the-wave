# config/universes

Fixed symbol lists a slot can use with `universe: file:config/universes/<name>.txt` (comma- or
line-separated).

- `liquid_stocks_254.txt`: the 254 company stocks (no funds) with the highest dollar volume as of
  22 September 2026. It is the pool from the daily research engine (originally the top 320 names,
  minus funds). The stat-arb slot `sa_volrev` trades it. It is a snapshot, so refresh it every few
  months: names drift in and out of the most-traded list.
