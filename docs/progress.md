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

## Where the last session stopped (2026-09-23, late evening) — read this first

**State of the system.** Everything is committed locally (no GitHub remote yet). 91 tests pass, lint
clean. Tomorrow 24 September the bot runs from launchd: Wave Rider live; in shadow: 15-minute Wave
Rider, ORB (0.25 ATR), `xs_overnight`, `xs_combo`, two daily portfolios (`pm_megacaps`, `vt_spy`,
deciding 15:50 ET, holding overnight) and three options structures (`ic_spy` with the VRP gate,
`bps_qqq`, `cc_aapl`, deciding 15:40 ET). Check with `curl localhost:8787/api/health` or the reports.

**What the evidence says so far.** No strategy tested has an edge: intraday patterns are noise on
our data; the book's daily stock rankings do not beat their own universe, on a survivorship-free
point-in-time universe from 2017, in the 2023-26 window, or by regime (momentum's only pocket is
high-volatility chop, t 1.0 to 1.6; shorting the bottom of a momentum ranking loses 17-21 points a
year in bull trends, t -2.6 to -3.2). TraderPro's profit factors were a hindsight universe. Risk
overlays (vol targeting, 200-day rule) halve drawdowns at equal Sharpe. Details:
`docs/research/2026-09-23-traderpro-extraction.md` sections 3 to 5c.

**The discussion in progress when the session ended.** The owner asked whether news sentiment could
drive the universe and what other non-financial influences exist; the answer given (news predicts
volatility and attention, not direction, except multi-day pockets such as post-earnings drift and
negative/legal news) and the ranked list of other influences are in the chat only, so the essentials
are repeated here:

- Other influences worth testing, by evidence and availability: macro calendar (pre-FOMC drift, CPI),
  calendar effects (turn of month, quarter end, expiration), options-implied features (IV rank, skew,
  volatility risk premium; we hold the data), short interest (FINRA), insider transactions (EDGAR),
  earnings calendar (outside feed; unlocks post-earnings drift), attention (search, Reddit; reversal),
  credit spread and cross-asset regime inputs. Principle: separate "what moves" (volatility, attention)
  from "which way" (direction); most non-financial data is the first kind and belongs in the selector.
- **Pending decision (the owner has loaded Jev credits):** the news study design. Proposed: keep the six
  existing Jev questions (version 2026-09-21.1, `src/ridethewave/signals/jev_questions.py`) unchanged,
  add two ("durable": does the information change the outlook over the coming weeks; "surprise": was
  it anticipated), bump the version, score the Alpaca news archive (reaches back to 2015) for the
  survivorship-free monthly top-100 universe 2019-2026 (about $40), re-score the September pairs with
  the new set for comparability, and build daily per-symbol features: headline counts (1 and 5 days,
  relative to the name's own history), impact-weighted sentiment with a 5-day decay, share of
  negative/legal items, earnings flag.
- Four pre-registered tests with kill criteria: (1) does abnormal news volume predict next-5-day realised
  volatility beyond past volatility (drop if under 10% added explanatory power); (2) does sentiment
  predict 1/5/20-day excess return over the universe by quintile (drop if no spread reaches t 2 in both
  halves); (3) do the exclusion (fresh negative/legal) and the tilt (earnings-up) lift momentum's IR
  against its universe by at least 0.2; (4) does a universe ranked by news materiality beat the
  dollar-volume universe. Then the zero-cost tests: calendar effects and options-implied features on
  data already held.
- **Reframing agreed in the last exchange:** Jev is the right tool for turning text into typed events
  cheaply and the wrong tool for forecasting direction (the September test showed direction is priced
  before the headline exists). So the news study's questions should be event extraction first:
  relevance (is the company the subject or only mentioned), a finer event type (earnings release,
  guidance change, upcoming-earnings-date announcement, M&A, FDA/regulatory decision, offering or
  dilution, analyst action, product, macro), surprise, durability, materiality, negative/legal, toxic.
  Two uses that fall out of it are worth more than sentiment: an earnings calendar reconstructed from
  the archive (Alpaca has none; unlocks post-earnings drift) and a market-wide macro-event-day feature
  for the regime classifier. Counts, volatility and returns do the predicting; Jev does the reading.
- After that, in order: the options backtester from Alpaca's option bars (February 2024 onward),
  the overnight-effect brief in `docs/strategy-intake.md`, fill reconciliation before any options slot
  goes live.

**Owner items still open.** `gh auth login` then
`gh repo create ride-the-wave --private --source=. --remote=origin --push` (five local commits waiting);
`sudo pmset repeat wakeorpoweron MTWRF 08:05:00`; strategy briefs go in `docs/strategies/inbox/`.

## 2026-09-23 (late) — Capability map and strategy intake

- `docs/alpaca-capabilities.md`: everything the account and data plan enable versus what the bot uses.
  Unused and available: short selling, extended hours, fractional and dollar orders, crypto (73 pairs),
  websocket streams, tick history, corporate actions, bracket and trailing-stop orders, option history
  since February 2024.
- `docs/strategy-intake.md`: the brief template and the seven-stage pipeline every idea goes through;
  briefs go in `docs/strategies/inbox/`.
- Survivorship-free daily history (7,786 active and delisted stocks since 2016) downloaded to
  `data/daily_panel/`; the "started in 2017" replay of ten daily strategies on a monthly point-in-time
  top 100 confirms the earlier verdict: none beats holding its universe (IR −1.1 to +0.2), all
  long-short versions flat or negative (research page, section 5b). A 2023-26-only window and a
  regime breakdown (section 5c) add: momentum's edge sits in high-volatility chop (t 1.0 to 1.6);
  shorting the bottom of the ranking loses 17 to 21 points a year in bull trends (t −2.6 to −3.2).

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
