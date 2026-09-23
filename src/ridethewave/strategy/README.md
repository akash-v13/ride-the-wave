# strategy

Pure decision logic. No imports from `alpaca`, `sqlite3`, `requests` or anything that does I/O. Everything comes in through `on_bar(bar, context)` and goes out as `Signal` objects.

- `base.py`: `Strategy` interface, `Signal` (buy/sell with reason), `Context` (bar history, positions, capital).
- `wave_rider.py`: the v1 strategy specified in docs/strategy.md. Streak detection for entries, trailing-from-peak with gain floor for exits, hard stop, timeout.
- `indicators.py`: small helpers (streak length, streak gain, streak volume).

- `spy_intraday.py`: market intraday momentum on SPY / SH, one timed decision a day; manages its own exit.
- `orb.py`: opening-range breakout on stocks in play, long-only; uses `on_session_start` daily context and its own stops and sizing.
- `registry.py`: name → factory; `build(kind, settings, params)`. Kinds: wave_rider (with `bar_minutes`), spy_intraday, orb.

Adding a strategy: subclass `Strategy` (override `symbols()` for a fixed instrument list, set `flatten_at_close` / `uses_protective_stop` as needed), add a factory to `registry.py`, list it under `strategies:` in settings with `mode: shadow` first.
