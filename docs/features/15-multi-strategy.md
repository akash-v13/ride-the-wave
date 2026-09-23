# 15 · Multi-strategy core

**What it does.** The bot now runs several strategies at once. Each entry under `strategies:` in
`config/settings.yaml` becomes a *slot* with its own strategy object, position book, order manager,
allocation and daily ledger. Trades, orders, positions and ledger rows all carry the strategy's id,
so every page and table can be read per strategy or in total.

```yaml
strategies:
  - id: wave_rider          # accounting key
    kind: wave_rider        # registry name (src/ridethewave/strategy/registry.py)
    mode: live              # live: real paper orders. shadow: simulated fills on live prices, no orders
    weight: 1.0             # share of the daily allocation among live strategies
  - id: spy_intraday
    kind: spy_intraday
    enabled: false
    mode: shadow
    params: {threshold_bp: 10}
```

**Live and shadow.** Live slots share the real Alpaca broker. Shadow slots get a shadow broker: the
backtester's simulated broker fed by live ticks, so a market order fills at the next tick and a limit
buy fills when a tick prints at or below the limit. Shadow trades are recorded with mode `shadow`
and their own ledger, appear on the check-in pages and the dashboard, and never reach Alpaca. This
is the incubation stage: a strategy runs in shadow until its live-price record earns an allocation.

**Allocation.** Each live slot's allocation starts at `base_allocation × weight / sum of live
weights` and then compounds through its own ledger by the reinvestment rule. Shadow slots use
`base_allocation × weight`. The global kill switches watch the sum of the live slots.

**Symbol exclusivity.** A symbol held or pending in one live slot cannot be bought by another. On
restart, each broker position is handed back to the slot that recorded it; anything untracked goes
to the first live slot.

**Strategy interface additions.** `symbols(universe)` lets a strategy trade a fixed list (market
timing) instead of the scanned universe. `flatten_at_close` lets it opt out of the 15:55 flatten and
manage its own exit. `uses_protective_stop` controls the server-side stop leg on entries.

**Validating a deploy.** `uv run python scripts/run_bot.py --dry-run` starts everything, runs one
tick and exits, without waiting for the open or writing a ledger. Run it before restarting the
scheduled bot after a code change.

**Backtesting a registered strategy.** `scripts/run_backtest.py --strategy spy_intraday --symbols SPY,SH`
with `--param-json` for parameters.

**Code:** `src/ridethewave/runner.py` (slots), `src/ridethewave/strategy/registry.py`,
`src/ridethewave/execution/shadow_broker.py`, `strategy` columns in `src/ridethewave/storage/`.
