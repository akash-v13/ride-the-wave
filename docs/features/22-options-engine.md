# 22 · Options engine and options slots (shadow)

**What it is.** Chapter 2 of *151 Trading Strategies* as running code: the 57 option structures
(covered calls, verticals, calendars, straddles and strangles, butterflies, condors, seagulls) as
declarative leg templates, a resolver that turns a template into concrete contracts against a live
chain, sizing and exit rules, and a slot that keeps one structure open per underlying and decides
once a day. The engine came from the owner's TraderPro project; here it runs on Alpaca's real-time
options data (OPRA, greeks and implied volatility included) and on a paper account approved at
options level 3. Verified facts and sample responses: `docs/api/options.md`.

**How a structure is built.** A template says, for example, "buy a put about 4% out, sell a put
about 2% out, sell a call about 2% out, buy a call about 4% out" (the long iron condor). The
resolver takes a chain snapshot around the money for the target days-to-expiry (35 by default),
keeps only two-sided quotes with a sane spread, picks the expiry nearest the target and the strikes
nearest each rule (one step = 1% of the spot, so SPY's $1 strike grid does not collapse the
structure), prices the package at mid and, for defined-risk single-expiry structures, computes the
exact max profit and max loss from the terminal payoff.

**Sizing and exits.** Units are sized so the estimated max loss (or the debit) is 20% of the slot's
capital, capped at 60%; a structure that cannot be afforded is refused. Every day, in this order: a
structure within 7 days of expiry is closed; one that has earned 50% of its max profit is closed;
one that has lost twice its baseline (max profit, or the entry net) is closed. Optional entry gate:
`vrp` enters only when the chain's at-the-money implied volatility exceeds 20-day realised
volatility by a threshold, the classic volatility-risk-premium condition (§7.4 of the book).

**Shadow and live.** In shadow, each leg is filled against the live quote paying a quarter of the
half-spread, and the books (cash, open structures, closed trades, a ledger per slot) live in our
database; nothing reaches Alpaca. In live mode the same legs go to the paper account as one
multi-leg market order (stock legs first); the config refuses live for the 17 templates with a
naked short leg. All three configured slots run in shadow.

**Worked example.** `ic_spy`, $20,000 capital, SPY at 710. Puts at 682 and 696, calls at 724 and
738, 35 days out; credit $2.10 per share, max loss $11.90. 20% of capital is $4,000, so 3 units
(max loss $3,570). Nine days later the package is worth $1.00 to close: P&L $1.10 per share, 52% of
the max, so the profit-target rule closes it for +$330 before spreads.

**Settings.** `options:` list with `id`, `template`, `underlying`, `mode`, `weight`, `dte_target`,
`far_dte_offset`, `profit_target_pct`, `stop_mult`, `close_dte`, `risk_fraction`, `max_risk_pct`,
`entry_gate` (`none` | `vrp`), `vrp_threshold`, `decision_time` (15:40 ET), `spread_fraction`.

**How to check.** `uv run python scripts/run_bot.py --dry-run` resolves each slot's structure
against the live chain and prints what it would open, without saving. The heartbeat carries an
`options` block; open structures are in the `structures` table; closed ones appear as trades with
the symbol `UNDERLYING:template`.

**Backtests.** `scripts/download_option_history.py` then `scripts/backtest_options.py`: chains rebuilt
from daily option bars since February 2024, replayed through this same slot code. Results in
`docs/research/2026-09-24-options-backtest.md`; the shadow slots use the best defined-risk settings from it.

**Not yet.** Fill reconciliation for live orders (the books assume mid); the web page has no
structures tab yet.

**Code:** `src/ridethewave/options/` (structures, greeks, chain, resolver, lifecycle, slot); runner
hooks `_build_options`, `_options_decisions`, `_decide_options`; `AlpacaBroker.submit_structure`;
tests `tests/test_options.py`.
