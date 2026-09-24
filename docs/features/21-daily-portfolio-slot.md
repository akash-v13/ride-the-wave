# 21 · Daily portfolio slots (overnight holds, long or short; shadow)

**What it does.** A second kind of slot beside the intraday strategies. Each entry under
`portfolios:` in the settings names a daily-bar strategy from the research engine (feature 20), a
universe, a capital share and a decision time (15:50 ET by default). At that time each day the bot
fetches ten months of adjusted daily history for the universe plus today's bar so far, asks the
strategy for target weights (a fraction of equity per symbol, negative for short), turns them into
whole-share orders and fills them at the current price plus slippage. Positions are held overnight
and across bot restarts; nothing is flattened at the close. Round trips are booked as trades when a
position closes or flips, and a ledger row is written per slot at shutdown, exactly as for the
intraday slots, so the reports, the web page and the leaderboard see them.

**Shadow only.** Fills are simulated against live prices; nothing reaches Alpaca. Short selling
and overnight holds on the paper account are the next step once these have been observed for a
while; the config refuses any mode but `shadow` until then.

**Rules borrowed from TraderPro.** Whole shares; a same-side adjustment smaller than 1% of the
slot's capital is skipped so a portfolio does not churn on rounding; opening, closing and flipping
always go through; gross exposure is capped at `max_gross` (1.0 = no leverage).

**Worked example.** `pm_megacaps`: 12-1 price momentum on the 20 mega caps, top 30% equal-weight,
$10,000. At 15:50 the six highest-momentum names get a 16.7% target each; a $1,667 target on a $250
stock is 6 shares, filled at the ask plus 0.05%. Tomorrow the ranking is recomputed; if the same six
names lead, a 1-share difference from price drift is inside the dead band and nothing trades.

**Settings.** `portfolios:` list with `id`, `kind` (daily registry name), `universe` (named list,
comma-separated symbols, or `scan` for the bot's own universe with funds removed), `weight`,
`rebalance_days`, `decision_time`, `slippage_bps`, `max_gross`, `params`. Ids share the same space
as `strategies:` ids.

**How to check.** `uv run python scripts/run_bot.py --dry-run` prints each portfolio's targets as of
now without saving anything. During a session the heartbeat carries a `portfolios` block (positions,
shorts, equity, cash, whether today's decision has been made); positions appear in the `positions`
table with the slot's id and a negative quantity for shorts.

**Evidence.** None of these portfolios has shown an edge over its own universe in the point-in-time
tests (research page of 23 September); they run for observation and to exercise the overnight and
short-selling plumbing the book's dollar-neutral strategies need.

**Code:** `src/ridethewave/portfolio/daily_slot.py`; runner hooks `_build_portfolios`,
`_portfolio_decisions`, `_decide_portfolio`; config `PortfolioSpec`; tests `tests/test_daily_slot.py`.
