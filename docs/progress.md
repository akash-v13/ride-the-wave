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

## 2026-10-29 (evening) — Close report fixed; a backup for the morning start

**The 16:15 close report was out of date.** It ran before the evening fixes, so it showed the QQQ
covered call at $0.00 and Wave Rider with "1 open, 2 trades". The corrected report is
`data/reports/2026-10-29/1802-close.md` (no phone push sent). The 16:18 report is kept as it was.

**Report fixes** (from tomorrow's reports):

1. Every trade row names its strategy. CDE appeared twice because two shadow strategies held it.
   Fixing this exposed that trades and ledger rows read back from the database had lost their
   strategy and all said `wave_rider`. Nothing that trades used that field, so no money or
   allocation was affected.
2. Positions held over several days show their entry date ("15 Oct 16:28"). Before, they looked as
   if they closed before they opened.
3. A credit option structure's P/L % had the wrong sign. The +$303.25 bull put spread showed −90%.
   It now shows +90%. The one stored row and its ledger average were corrected (old value −90.12).
4. Average hold keeps day trades and overnight holds apart ("day trades 239 min (18); held overnight
   or longer 19.0 days (6)"). The single figure of 7017 minutes was meaningless.
5. The close report has a table of every strategy's ledger, the books of record. The one-line summary
   came from the bot's last tick, so it missed anything corrected after the bot stopped.

**Morning start: confirmed, and now with a backup.** The bot had never yet been started by its
06:30 ET calendar job on the Mac mini. The system log shows the job fired on time this morning
(05:30:03 Central). It started nothing, because the bot was already running from last night's
restart test. As insurance, the watchdog now also starts the bot from 07:00 ET if the morning
start did not run, and sends a phone alert. Also checked for running unattended: automatic login
is on, FileVault is off, the Mac never sleeps and restarts after a power cut, 160 GB is free,
Tailscale connects the Mac mini and the laptop, and macOS will not install updates by itself.

155 tests pass. Details: `docs/features/14-operator.md`, section 4.

## 2026-10-29 — First session on the Mac mini; one execution bug found and fixed

**The session ran cleanly.** The bot started at 09:28 ET with a 62-stock universe on the first try, and
every 30-minute rebuild succeeded. Ticks were steady with no gaps. Every report and phone push went out,
and no alerts fired. Live Wave Rider made three trades, GOOG, IOVA and NUWE. All three were stopped out,
for −$32.93.

**Bug: the bot could try to sell shares the protective stop had already sold.** Alpaca's stop sold NUWE at
11:27:12 ET. Six seconds later the bot's own exit sent a market sell for the same 151 shares. Alpaca refused
it only because NUWE cannot be shorted; on a stock that can be, it would have opened a short. The bot also
kept NUWE as held, and the $15.10 loss was missing from its records. Fixed: the bot now checks the stop
before selling, books the stop's fill if it got there first, and a live slot never sells more shares than
Alpaca holds. The missing NUWE trade is recorded. A one-off job removes the leftover NUWE position once
today's bot exits. Details: `docs/features/07-order-execution.md`.

**Also fixed: the watchdog could not read the boot time** under launchd, because `sysctl` was not on the job's
PATH. And a correction: after a restart, launchd itself starts the bot again at login, as the 28 October
restart test showed. The watchdog is a backup, not the only cover.

All fixes are on the Mac mini, with 142 tests passing there. The running session was not touched. The order
fix applies from the 30 October start, and the watchdog fix from the next five-minute check.

**At the close.** The account was flat at $99,937.81, with no positions or open orders. The NUWE cleanup ran,
and the live ledger shows −$32.93 on three trades. The shadow `bps_qqq` closed a day before expiry for +$303.25.
`pm_actives` rebalanced for the first time since 19 October. The day-trade shadow slots closed at 15:55:
`xs_overnight` −$14.20, `xs_combo` −$50.66, the opening-range breakout −$12.27.

**Bug: the shadow QQQ covered call was booked at $0.00. The real figure was −$1,892.13.** Its short call
was quoted bid 0 / ask 0.02. The shadow fill rule needed a bid on every leg, and its fallback, the last
mark, had been lost in last night's restart, so the books took the entry price. Fixed: a close now
accepts a quote with an ask and no bid. Missing prices fall back to mid, then the saved last mark, then
exercise value, and the fallback used is logged. Marks now survive restarts. The record was re-priced the
same evening (database backup `data/ridethewave.db.bak-cc_qqq-20261029163032`). `bps_spy` would have hit
the same thing at its 5 November close. 146 tests pass on the Mac mini. Details:
`docs/features/22-options-engine.md`.

## 2026-10-28 (evening) — Moved to the Mac mini

The system now runs on the Mac mini, not the laptop.

| Item | State |
| --- | --- |
| Machine | The Mac mini, user `admin` |
| Project folder | `/Users/admin/Projects/Finance/Ride The Wave` |
| Checks on the Mac mini | Connection check all passed, 136 + 3 tests, dry run with a 61-stock universe, test push delivered |
| Scheduled jobs | Installed; the bot is waiting for the open on 29 October |
| Laptop | Scheduled jobs removed; keys file renamed, so it cannot trade |

**Before you travel:** install Tailscale on the Mac mini and the laptop, signed in to the same account,
and turn off key expiry for the Mac mini. Then from anywhere: `ssh admin@<the Mac mini's Tailscale name>`.
Subscribe to the ntfy topic on your phone. The name is in `.env` on the Mac mini, and it was given in the
session.

**First thing to check on 29 October:** the 09:00 pre-market push, then that the universe has stocks and
the log has no gaps after the close.

## 2026-10-28 — A month of mostly empty sessions, found and fixed

**What happened between 25 September and 28 October.** The bot started on all 24 trading days. Only 30
September and 5 October ran a full session with stocks to scan. Two causes:

- **The Mac was asleep.** The power log shows the laptop on battery and asleep through most market hours.
  It woke for a few seconds at a time for macOS maintenance. The bot's `caffeinate` assertion cannot stop
  sleep on battery or with the lid closed. No wake schedule is set. Each time the Mac woke, the first call
  to Alpaca failed on a dead connection, and on most days that call was the universe build.
- **A new exchange broke the asset list.** From 20 October Alpaca listed ten stocks on the Texas Stock
  Exchange (`TXSE`). alpaca-py rejects that code and drops the entire list, so every universe build failed
  from 20 to 28 October. The intraday strategies had nothing to scan, and the momentum portfolio skipped
  its decisions. The health check said "healthy" throughout.

**Results over the month.** These cannot be used to judge any strategy, because most sessions were empty.

| Slot | Mode | Result to 28 Oct |
| --- | --- | --- |
| Wave Rider | live | 8 trades, 2 wins, −$19.68; paper account $99,970.74 |
| pm_actives (momentum) | shadow | $9,338 from $10,000; frozen since 19 Oct |
| vt_spy (volatility targeting) | shadow | $10,022 |
| bps_qqq, bps_spy (bull put spreads) | shadow | +$294 and +$174 open |
| cc_qqq (covered call) | shadow | −$1,284 open, mostly the QQQ shares |

**Fixed today** (106 tests pass; a dry run against the paper account built a 61-stock universe and ran every slot):

1. The asset list is read as raw data, so an unknown exchange code can no longer break it (`data/assets.py`).
2. Every Alpaca call retries a failed or dropped connection. Read-only calls also retry a lost response,
   and orders are never sent twice.
3. The start-up universe build gets three attempts. While the universe is empty, the bot retries every 2
   minutes. Stocks that arrive late get their history.
4. New alerts: an empty universe, and a portfolio or options decision that was skipped.
5. The report's positions table now shows which strategy holds each position. The column was missing.

**Needed from you.** Keep the Mac on power and awake from before the open until after the close on
weekdays. Set the wake schedule once: `sudo pmset repeat wakeorpoweron MTWRF 08:05:00`. If the lid has to
stay closed, `sudo pmset -a disablesleep 1` keeps the Mac awake, but it then never sleeps. An always-on
machine, such as a Mac mini or a small cloud server, would remove the problem for good.

**Decided: a Mac mini becomes the always-on machine.** Setup and handover steps, including remote
access from anywhere through Tailscale, are in `docs/mac-mini-setup.md`. Until it arrives, keep the laptop
plugged in and awake in market hours. Built the same evening: phone alerts through the free ntfy app.
Every alert, plus a short push when each check-in report is ready, reaches your phone. The machine is a Mac mini M1 (2020) with 8 GB and 256 GB.
That is enough: about 7 GB at peak with research running, and the database grows about 1 GB a year. It
needs macOS 15 or later for Homebrew. Also built: a watchdog that restarts the bot if the Mac restarts
during market hours (corrected the next day: launchd already restarts it at login, so the watchdog is a backup). A bot you stop by hand stays
stopped. 136 tests pass.

**Also noticed, not changed.** The SPY bull put spread opened on a weekly expiry (6 November). The
backtest only tested monthly expiries, so this slot is not running exactly what was tested. The two QQQ
positions expire on 30 October. Their close rule runs on the 29th at 15:40 ET, but only if the Mac is
awake.

## 2026-09-24 (session review) — First live trade; two operational fixes

- **Session.** Wave Rider's first live trade: 30 SRZN at $32.48 at 10:42 ET, stopped out a minute later at
  $32.11 (−$11.10) by the 1% server stop. All shadow strategies flat. The volatility-targeting portfolio
  bought 13 SPY at 15:50 and holds overnight (the first overnight position in the system). Options gates
  closed on SPY and QQQ (implied minus realised volatility 2.0 to 2.7 points, threshold 3). Ledgers written
  for all ten slots; four check-in reports.
- **Stall.** The bot froze for seven minutes at 14:09 ET inside a network call and recovered on its own.
  Cause: alpaca-py sends requests without a timeout. Fixed: every Alpaca client now carries connect and
  read timeouts (10 s / 30 s).
- **Empty universe.** The 08:43 universe build failed on a dropped connection; the intraday slots picked
  up the 30-minute rebuild, the momentum portfolio did not and decided on an empty universe at 15:50.
  Fixed: portfolio universes follow every rebuild and a decision retries the build if the universe is empty.

## 2026-09-24 (morning) — Options backtest: the first family that holds up on risk

**Completed**

- Downloaded daily bars for every SPY, QQQ and IWM option on the monthly expiries since March 2024,
  including expired contracts and the holiday-shifted expiries. Built a backtester that rebuilds each
  past day's chain and runs the bot's own options slot through it (`docs/research/2026-09-24-options-backtest.md`).
- 144 configurations. Iron condors lose (the inherited 2% strikes lost everything on SPY in a rising
  market). The bull put spread with strikes 5% and 10% out, entered only when options are expensive
  relative to realised volatility, held to expiry, matched or beat each index's risk-adjusted return
  with about a third of its drawdown, positive in both halves on all three. It sat out the April 2025
  crash because the gate was closed, then entered when premiums were richest.
- Caveat: one bull market, one crash, about 20 trades each. A candidate to observe, not a proven edge.
- The shadow options slots now run exactly these tested settings: `bps_spy`, `bps_qqq`, `cc_qqq`.
- Two engine fixes: the strike distance is now a setting (it was fixed at 1% per step), and structures
  are sized from current equity instead of starting capital.

**Next**: momentum leaning into high-volatility markets; fill reconciliation before any options slot
goes live.

**Also (24 September, small hours).** Two short-side questions from the owner answered with data:
shorting large caps on negative news loses in nearly every event category (they bounce); post-earnings
drift in ranks 101 to 1000 has the textbook shape (−58 bp a month after a crash of over 8%, +33 bp after a
jump of over 8%) but t-statistics near zero and hit rates of 52 to 55%, so it is not tradable here
either. Both recorded in `docs/research/2026-09-24-news-daily-jev.md`. Jev spend so far: $30.43.

## 2026-09-24 (early morning) — News study done and rejected; a benchmark bug found and fixed

**Completed**

- **News as a daily feature** (`docs/research/2026-09-24-news-daily-jev.md`): Jev scored 357,240
  headline-symbol pairs from 2019 to 2026 with the new question set (relevance, event type, surprise,
  durability added); $23.14, zero errors. All four pre-registered tests fail: news volume does not help
  forecast volatility, sentiment does not predict returns, it does not improve momentum, and a
  news-ranked universe does not beat the ordinary one. Negative or legal news tends to recover over the
  next month, which is why excluding it hurt. No news feature is adopted; the scores are kept.
- **Benchmark bug fixed.** The daily engine's "hold the universe" comparison averaged every stock that
  was ever in the universe, including those that got in later because they had risen. Corrected to
  point-in-time with a test. On the honest benchmark the universe earned 16.8% a year (not 22.4%), and
  long-only price momentum beats it by 5 to 9 points a year in both halves (information ratio 0.51,
  t 1.6): the leading daily candidate, still short of the t ≥ 2 gate.
- The momentum shadow portfolio now uses the live most-active universe (`pm_actives`) instead of the
  hindsight list of 20 mega caps.

**Next**: the options backtester; a momentum variant that leans into high-volatility markets (the one
result with t above 2); fill reconciliation before any options slot goes live.

## Handoff of 2026-09-23, late evening (superseded by the entry above)

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
