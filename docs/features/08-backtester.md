# 08 · Backtester

**What it does.** Replays past trading days minute by minute through the same strategy and order-management code the live bot uses, against a simulated broker. Prints a report and stores everything so the dashboard can show it.

**Run it.**
```bash
uv run python scripts/run_backtest.py --start 2026-09-08 --end 2026-09-12 --symbols AAPL,TSLA,NVDA
uv run python scripts/run_backtest.py --start 2026-09-08 --end 2026-09-12 --feed iex --symbols AAPL,TSLA,NVDA
uv run python scripts/run_backtest.py --start 2026-09-15 --end 2026-09-16 --top 50   # smoke test only
```

**Which data.** `--feed sip` is the full market tape and shows what the market actually did. `--feed iex` is what the live bot sees. **Run both.** If a strategy only works on SIP, it will not work live on the free plan.

**Fill model.** Nothing fills on the bar the decision was made on. A limit buy fills on the next bar if that bar's low reaches the limit, at the better of limit and open, plus `slippage_pct`. A market sell fills at the next open minus slippage. A protective stop fills when a bar's low touches it; a gap down fills at the open, not the stop. Intra-minute highs update the peak, as live ticks would.

**Point-in-time universe (`--pit-top N`).** For each backtest day, rank every tradable US stock by
its average daily dollar volume over the prior 20 sessions and take the top N in the price band. Only
data available before that day's open is used, so there is no lookahead. Residual bias: the pool is
today's asset list, so stocks delisted before today are missing (survivorship).

**Filling the cache.** `uv run python scripts/download_history.py --start ... --end ... --pit-top 50`
downloads regular-session minute bars once; every later backtest or sweep over those dates is a
cache hit. About 3.5 months of a 50-stock universe is roughly 1.5 million bars.

**Sweeps and time-of-day analysis.** `scripts/sweep.py` runs the strategy over a grid of parameters
against the in-memory cache and prints a results table plus, with `--breakdown`, trades bucketed by
entry half-hour and by exit reason. Named grids: `time`, `streak`, `exit`, `hold`; or any
`--param dotted.key=v1,v2`.

**Lookahead warning.** Using today's most-actives list for last week's backtest is cheating: you did not know those names then. Use `--symbols` with a list you would have chosen in advance, and treat `--top` runs as smoke tests.

**Report.** Trades, win rate, net P/L, profit factor (gross wins divided by gross losses; below 1.0 means losing), max drawdown, average hold, exit-reason counts, per-day ledger, and a one-line verdict.

**First real result (2026-09-14 to 09-16, ten liquid names, default settings):** SIP feed: 24 trades, 50% wins, profit factor 0.50, net -$50. IEX feed: 21 trades, 62% wins, profit factor 1.00, net -$0.07. Ten of the 24 SIP exits were the safety stop. As configured, the strategy is not yet profitable. Next step is a parameter sweep.

**Code:** `src/ridethewave/backtest/`, `scripts/run_backtest.py`.
