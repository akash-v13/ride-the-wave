# Progress log for the owner

A running, plain-English record of what has been completed, how to check it, and what is next. Newest
first. The status table in `CLAUDE.md` is the terse version; `docs/handbook.md` is the full reference.

## How to check the system on any day

| Question | Where to look |
| --- | --- |
| Is the bot running right now? | `http://127.0.0.1:8787` (TypeScript web page) or `curl localhost:8787/api/health` |
| What happened today? | `data/reports/<date>/` pages (pre-market, morning, midday, close, evening) or the web page's Reports tab |
| Per-strategy trades and P/L | Web page, or `uv run python scripts/report.py close` |
| Are the scheduled jobs loaded? | `uv run python scripts/install_launchd.py status` (bot, operator tick, API) |
| Which strategies are configured? | `config/settings.yaml`, `strategies:` block; `mode: live` trades real paper money, `mode: shadow` only simulates on live prices |
| Run the tests | `uv run pytest -q` (Python) and `cd web && npm test` (TypeScript) |

## 2026-09-23 (late) — Capability map and strategy intake

- `docs/alpaca-capabilities.md`: everything the account and data plan enable versus what the bot uses.
  Unused and available: short selling, extended hours, fractional and dollar orders, crypto (73 pairs),
  websocket streams, tick history, corporate actions, bracket and trailing-stop orders, option history
  since February 2024.
- `docs/strategy-intake.md`: the brief template and the seven-stage pipeline every idea goes through;
  briefs go in `docs/strategies/inbox/`.
- Survivorship-free daily history (7,786 active and delisted stocks since 2016) downloaded to
  `data/daily_panel/`; the "started in 2017" replay of the daily strategies runs on it.

## 2026-09-23 (night) — Options engine ported and wired to Alpaca's options API

**Completed**

- Verified the upgraded provisions: paper account at options level 3 with $100k options buying
  power; OPRA real-time chains with quotes, implied volatility and greeks (`docs/api/options.md`).
- Ported TraderPro's options engine (feature 22): the 57 Chapter-2 structures as leg templates,
  Black-Scholes and implied volatility, chain snapshots, the resolver, sizing and exit rules, and a
  new options slot kind (`options:` in settings) that keeps one structure open per underlying and
  decides at 15:40 ET. Shadow fills against live quotes; live mode places multi-leg orders on the
  paper account (implemented, not yet exercised).
- Three observation slots run in shadow from 24 September: an iron condor on SPY gated on the
  volatility risk premium, a bull put spread on QQQ, a covered call on AAPL.

**Next**: watch the first structures open and close; a chain-reconstruction backtester from Alpaca's
historical option bars; fill reconciliation before any slot goes live; a structures tab on the web page.

## 2026-09-23 (evening) — TraderPro extracted; daily portfolio engine built; the book's rankings tested honestly

**Completed**

- Inventoried the owner's July 2026 platform TraderPro (85 book strategies, own backtester, options
  engine, regime/sentiment selector, React UI): `docs/research/2026-09-23-traderpro-extraction.md`.
- Built the daily portfolio research engine (`src/ridethewave/daily/`, feature 20) and ported 13
  price-only book strategies plus TraderPro's regime classifier. Ten years of adjusted daily bars
  cached for 43 named symbols and a 320-name pool.
- Replicated TraderPro's champions on the same universe and period: ranking reproduces, levels are
  higher because TraderPro's data was unadjusted (splits looked like crashes); but holding its 20
  mega caps equal-weight earned 28.7% a year, so the rules added little.
- Point-in-time test (top 50/100 by dollar volume from a 254-stock pool, 2017 to 2026): no stock
  ranking beats holding its own universe; all long-short versions flat or negative. ETF and index
  rules do not beat SPY on return; volatility targeting and the 200-day rule halve the drawdown.

**What this means.** The "really good profit factors" came from a hindsight universe measured
without a benchmark. What is worth keeping from TraderPro is infrastructure and the risk controls.

**Also built tonight**: the daily portfolio slot (feature 21). Two observation portfolios run in
shadow from 24 September, deciding at 15:50 ET and holding overnight: `pm_megacaps` (12-1 momentum on
the 20 mega caps) and `vt_spy` (volatility targeting on SPY). Positions and cash survive restarts;
shorts are allowed; nothing reaches Alpaca.

**Next**: observe the two portfolios, then short selling and overnight holds on the paper account; a
survivorship-free pool before trusting any long-only ranking.

## 2026-09-23 — *151 Trading Strategies* mapped; cross-sectional day trades built and tested; two shadow slots for 24 Sep

**Completed**

- Read the Kakushadze & Serur paper and mapped all 20 chapters against what Alpaca gives us:
  `docs/research/2026-09-23-kakushadze-151-feasibility.md`. Only the stock and ETF chapters are usable
  today, and most of those need short selling, overnight holds or outside data.
- Built the book's open-to-close alphas as a long-only strategy family (`xs_daytrade`: overnight
  reversal, previous-day momentum, intraday reversal, combo). Feature page:
  `docs/features/19-cross-sectional-daytrade.md`.
- Ran the research protocol: a diagnostic (`scripts/study_xs_signals.py`) found no ranking power in any
  score; 37 backtest configurations all lose (profit factors 0.52 to 0.91). Two least-bad variants
  (`xs_overnight`, `xs_combo`) run in **shadow** from 24 September as observation only.
- Fixed two plumbing bugs: strategy-specific stops and sizing never reached the broker (the ORB's real
  result is PF 0.74 at its 0.1-ATR stop, 0.91 at 0.25 ATR, now used); the backtest script gave
  strategies no daily bars.
- Added a per-strategy `stocks_only` switch that drops ETFs, leveraged products and crypto trusts.
- Handbook (shared doc and `docs/handbook.md`) gained section 4.9, a results row and the reference.

**What runs on 24 September**: Wave Rider live; 15-minute Wave Rider, ORB (0.25 ATR), `xs_overnight`
and `xs_combo` in shadow. Nothing from the book has capital.

**Next**: short selling in the execution layer (unlocks the book's dollar-neutral stock strategies),
then a daily-portfolio executor with overnight holds for monthly-rebalance strategies.

## 2026-09-23 — TypeScript API and web UI

- `web/` (Fastify on Node 26) reads the bot's SQLite file and serves `http://127.0.0.1:8787`: status
  tiles, per-strategy figures with pause / resume / flatten buttons, positions, trades, reports.
- Control requests are queued in the database and applied by the bot each tick (from the first bot start
  after 23 September). Streamlit on port 8501 still runs alongside.
- First git commit made locally; pushing needs `gh auth login` then
  `gh repo create ride-the-wave --private --source=. --remote=origin --push`.

## 2026-09-22 — Two strategies in shadow, first full paper day lessons

- 15-minute Wave Rider (PF 1.00 with the market gate) and long-only opening-range breakout built, both
  in shadow. Engine gained per-strategy bar resampling and daily-bar session context.
- First full day (22 Sep): bot exited at 09:29 on a pre-open clock check (fixed), launchd calendar jobs
  fired two hours late (scheduling moved to a five-minute dispatcher), shutdown crash fixed.

## Earlier (17 to 21 September)

Phases 0 to 19 in the `CLAUDE.md` status table: environment, core, data, strategy, execution, backtester,
dashboard, ledger; sweeps and entry filters (first thin profitable configuration, PF 1.25); Dixon skill and
research protocol; Algo Trader Plus data plan; operator layer; multi-strategy core; SPY intraday momentum
rejected; news via Jev validated and not adopted as a filter.
