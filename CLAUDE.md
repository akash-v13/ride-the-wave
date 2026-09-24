# CLAUDE.md — Ride The Wave

This file is the running source of truth for the project. Claude reads it at the start of every session and keeps it current. If something here disagrees with the code, fix one of them.

## What this project is

A momentum trading bot on Alpaca's **paper trading** account ("Ride The Wave"). It scans a universe of stocks, buys ones that have been rising for a configurable streak, holds while the price keeps climbing ("riding the wave"), and sells on a pullback from the peak while locking in at least a small gain. A backtest suite replays past days through the same strategy code. A dashboard shows positions, entry price, current price and profit.

The owner's full brief is in [outline.md](outline.md). The owner is comfortable with code but wants every feature documented in plain English.

## Current status

| Phase | State | Notes |
|---|---|---|
| 0. Research and design | Done 2026-09-17 | Architecture, strategy spec, API docs, requirements written |
| 1. Environment setup | Done 2026-09-17 | Homebrew 7.0.4, uv 0.12.15, Python 3.12.14, alpaca-py 0.44.0, `.env` created |
| 2. Core: config, Alpaca client wrapper, storage | Done 2026-09-17 | `scripts/check_env.py` passes |
| 3. Data: universe builder, snapshot poller, bar store | Done 2026-09-17 | 100 most-actives -> 65 tradable in band; 1 snapshot call per poll |
| 4. Strategy: streak detector, wave rider exit | Done 2026-09-17 | Pure; 13 unit tests |
| 5. Execution: order manager, position tracker, live runner | Done 2026-09-17 | OTO limit+stop verified on paper account. **Not yet run through a live session** |
| 6. Backtest: replay engine, simulated broker, report | Done 2026-09-17 | First result: PF 0.50 (SIP) / 1.00 (IEX), not tradable as configured |
| 7. UI: Streamlit dashboard | Done 2026-09-17 | Live / Ledger / Backtests tabs; headless render test |
| 8. Daily ledger and reinvestment | Done 2026-09-17 | Written at bot shutdown and per backtest day |
| 9. First live paper session | **Next** | Run `scripts/run_bot.py` on a market day, watch the dashboard, fix what breaks |
| 10. Longer backtests, point-in-time universe, sweeps | Done 2026-09-17 | 62 configs over 75 days: best PF 0.91, none profitable. See docs/research/2026-09-17-time-slice-sweep.md |
| 12. Feature dataset, entry filters, vol-scaled exits | Done 2026-09-17 | 3 gates adopted as defaults: PF 1.25 / +$168 (SIP), 1.17 (IEX), positive both halves. Vol-scaled exits implemented, off. docs/research/2026-09-17-feature-analysis.md |
| 13. Classifier on the feature dataset | Planned, protocol set | Follow `.claude/skills/dixon-ml-finance/references/ride-the-wave-plan.md`: day folds, logistic reference, calibration, engine eval, Bayes factor. Diagnostic 2026-09-17: 1-min returns are white noise; streak is not the edge (docs/research/2026-09-17-streak-autocorrelation.md) |
| 9. First live paper session | 2026-09-22: ran 11:15 to 16:00 ET | Woke on time but exited at 09:29 (pre-open clock check, fixed); launchd calendar jobs 2h late (boot-time timezone; scheduling moved to a 5-min dispatcher). 8 streak candidates, all blocked by the SPY gate on a down day (-0.11%). No trades. 800 feature rows labelled |
| 15. Slower-bar diagnostic | Done 2026-09-21 | 5-min: nothing. 15-min: streak≥3 & gain≥1% → +22 ± 12 bp at 180 min, positive both halves, grows with threshold. docs/research/2026-09-21-slower-bars.md |
| 16. 15-minute Wave Rider variant | Proposed | Aggregator `bar_minutes`, exits re-swept at 3h horizon, IEX check first |
| 18. Multi-strategy core: slots, shadow mode, allocator, registry | Done 2026-09-21 | docs/features/15-multi-strategy.md; DB migrated; scheduled bot restarted on it |
| 19. SPY intraday momentum study | Done 2026-09-21, rejected | docs/research/2026-09-21-spy-intraday-momentum.md |
| 20. Opening-range breakout (long-only) and 15-minute Wave Rider | Built 2026-09-22; both in shadow as observation only | Backtests: WR-15m PF 1.00 with the market gate; ORB 0.93 was measured with the global 1% stop (hook unwired), corrected 2026-09-23 to 0.74 at 0.1 ATR and 0.91 at 0.25 ATR, shadow now 0.25 ATR. `bar_minutes` resampling and `on_session_start` daily context added. docs/research/2026-09-22-fifteen-minute-and-orb-backtests.md |
| 23. *151 Trading Strategies* (Kakushadze & Serur) mapped; cross-sectional day-trade family | Done 2026-09-23 | Feasibility map: docs/research/2026-09-23-kakushadze-151-feasibility.md. `xs_daytrade` (feature 19: overnight reversal, previous-day momentum, intraday reversal, combo; long-only, stocks only): no ranking power (rank-IC t −0.4 / −0.9 / +0.3), every backtest combination loses (PF 0.52 to 0.91). `xs_overnight` and `xs_combo` in shadow from 2026-09-24 as observation only. Side fixes: strategy sizing/stop hooks wired in runner and backtester; `run_backtest.py` supplies daily bars; per-strategy `stocks_only` universe |
| 24. TraderPro (owner's July 2026 platform) inventoried and extracted | Done 2026-09-23 | docs/research/2026-09-23-traderpro-extraction.md. Its 2019-26 results replicated on adjusted data with benchmarks: the returns were the hindsight mega-cap universe, not the rules; on point-in-time universes no daily stock ranking beats holding its universe and every long-short version is flat or negative. Regime classifier ported (`daily/regime.py`) |
| 25. Daily portfolio research engine | Done 2026-09-23 | `src/ridethewave/daily/` (feature 20): 13 book strategies on adjusted daily bars (`sip-day-adj`, ten years, 320-name pool cached), next-open fills, shorts, benchmark + equal-weight curves, IR, halves, point-in-time universes. `scripts/download_daily.py`, `scripts/run_daily_backtest.py`. Not wired to live execution (needs the daily slot with shorts and overnight holds) |
| 26. Daily portfolio slots (overnight holds, long or short) | Built 2026-09-23, shadow only | `portfolios:` in settings; `portfolio/daily_slot.py`; decision at 15:50 ET, simulated fills, positions persist across restarts, ledger per slot. Two observation slots from 2026-09-24: `pm_megacaps` (12-1 momentum) and `vt_spy` (vol targeting). docs/features/21-daily-portfolio-slot.md. Fixed on the way: each intraday slot wiped the whole positions table when persisting |
| 27. Options engine and options slots | Built 2026-09-23, shadow only | `src/ridethewave/options/` (feature 22): 57 structure templates, Black-Scholes, OPRA chain snapshots, resolver, sizing and exit rules, options slots with shadow fills or live multi-leg orders (paper account is options level 3, verified; docs/api/options.md). Three observation slots from 2026-09-24: `ic_spy` (iron condor, VRP gate), `bps_qqq` (bull put spread), `cc_aapl` (covered call). No backtester yet |
| 28. News as a daily feature (Jev, 2019-2026) | Done 2026-09-24, rejected | 357,240 pairs scored with question set 2026-09-24.1 ($23.14, 0 errors); all four pre-registered tests fail in the survivorship-free top 100. docs/research/2026-09-24-news-daily-jev.md |
| 29. Daily engine benchmark correction | Done 2026-09-24 | The equal-weight universe averaged every name ever selected (hindsight). Now point-in-time, with a test. Corrected: universe 16.8%/yr 2017-26 (was 22.4%); long-only price momentum beats it by 5.0/8.9 pts by half, IR 0.51 (t 1.6); residual momentum in high-vol chop t 2.4; long-short still loses. `pm_megacaps` replaced by `pm_actives` (live most-actives universe). Research page section 5d |
| 30. Options backtester | Done 2026-09-24 | Chains rebuilt from Alpaca daily option bars (Feb 2024 on, SPY/QQQ/IWM monthlies), replayed through the production OptionsSlot; 144 configurations. Best defined-risk: bull put spread 5%/10% OTM, vrp gate, hold: QQQ Sharpe 1.56 (index 1.08), SPY 1.13 (1.16), DD a third of the index's; ~20 trades each. Iron condors lose. Shadow slots now `bps_spy`, `bps_qqq`, `cc_qqq`. docs/research/2026-09-24-options-backtest.md |
| 22. TypeScript API + web UI | Done 2026-09-23 | `web/`: Fastify on Node 26, reads SQLite, control requests queued for the bot; launchd agent `com.ridethewave.api`, http://127.0.0.1:8787. 3 vitest + 70 pytest pass. Pause/resume/flatten take effect from the first bot start after 2026-09-23. docs/features/18-typescript-api.md |
| 21. Next engine experiments | Planned | Short selling and overnight holds on the **paper account** (the shadow daily slot exists; promote after observation); a survivorship-free pool before trusting any long-only ranking; regime classifier as a gate; ORB on a broader universe with a catalyst flag; the book's dollar-neutral strategies as daily slots |
| 17. Operator: kill switches, check-in reports, alerts, launchd schedule | Done 2026-09-21 | docs/features/14-operator.md. Installed with `scripts/install_launchd.py install` |
| 14. Live feature recording | Done 2026-09-21 | Every paper day writes labelled IEX feature rows. docs/features/13-live-feature-recording.md. Active from the next bot start |
| 11. News / sentiment filter via Jev | Validated 2026-09-21: not built | 21k pairs scored ($0.85). Positive news: no intraday edge, negative for streak entries. Down/legal news drifts lower. Decision: no confirmer; exclusion low priority; keep scoring daily headlines for the analyst and post-earnings pockets. docs/research/2026-09-21-news-jev-validation.md |

## Key decisions (details in docs/decisions.md)

- **Python 3.12 + uv**, single package `ridethewave` under `src/`. No Docker. Node 26 is used only for the `web/` API layer.
- **alpaca-py 0.44.x** is the only broker/data SDK. Paper endpoint always; live is a config flag that stays off. Options: the paper account is level 3 and the data plan serves OPRA chains with greeks (verified 2026-09-23); option structures run through `options:` slots, shadow first.
- **Data plan: Algo Trader Plus since 2026-09-21** ($99/mo): all US exchanges (SIP) in real time, no history hold-back, unlimited websocket symbols, 10,000 REST calls/min. `config/settings.yaml` (gitignored, this machine) sets `data_feed: sip`; the committed example keeps `iex` as the safe default for a Basic account. Code written for the free tier (snapshot polling, one call per 200 symbols) still works and is now far from any limit; websocket streaming is unblocked.
- **REST snapshot polling, not websockets, for v1.** One multi-symbol snapshot call per poll covers the whole universe. Websockets come later for held positions.
- **Same strategy code runs live and in backtest.** The strategy only sees `Bar` and `Position` objects and emits `Signal`s. Only the data source and broker are swapped.
- **Several strategies run as slots** (`strategies:` in settings): own book, orders, ledger, allocation; `mode: shadow` = simulated fills on live prices for incubation. Every trade/position/ledger row carries a `strategy` id. **Daily portfolio slots** (`portfolios:`) hold overnight and may go short; shadow only until observed.
- **SQLite** (`data/ridethewave.db`) is the single store for bars, orders, trades, positions and the daily ledger. The bot process writes; the UI process reads.
- **Streamlit** dashboard, separate process from the bot; a **TypeScript API + web UI** (`web/`, port 8787) now sits beside it and is the base for the future UI. The Python core stays the owner of trading and data; TypeScript only reads the database and queues control requests.
- **Exits are computed client-side** (trailing-from-peak with a minimum-gain floor). A server-side stop-loss order is placed as a safety net in case the bot dies.
- **Secrets live in `.env`**, never in code or docs. `alpaca_key.txt` must be moved into `.env` and deleted.

## Folder map

Every folder has its own README.md saying what belongs in it.

```
CLAUDE.md               this file
web/                    TypeScript API + web UI (Node 26, Fastify); reads the SQLite file, queues controls
outline.md              owner's original brief
README.md               how to install and run
pyproject.toml          package + dependencies (uv)
.env.example            template for secrets
config/                 strategy settings (YAML)
docs/                   architecture, strategy, API docs, requirements, per-feature docs; progress.md is the owner's log
src/ridethewave/        the Python package
  data/                 universe selection, market data fetching, bar aggregation
  strategy/             entry/exit logic (pure, no I/O)
  execution/            order submission, fills, position tracking against Alpaca
  portfolio/            capital allocation, daily ledger, reinvestment
  backtest/             replay engine, simulated broker, reports
  storage/              SQLite schema and repositories
  ui/                   Streamlit dashboard
  daily/                daily-bar portfolio strategies, research engine, regime classifier (feature 20)
  options/              the 57 option structures, chain data, resolver, lifecycle, options slots (feature 22)
scripts/                entry points: run_bot, run_backtest, run_ui
tests/                  pytest suites
data/                   runtime files (SQLite db, caches). Gitignored.
```

## How to run (after `uv sync`)

```bash
uv run python scripts/check_env.py                       # connection + storage check
uv run python scripts/run_bot.py                         # paper bot; waits for the open
uv run python scripts/run_backtest.py --start 2026-09-08 --end 2026-09-12 --symbols AAPL,TSLA,NVDA
uv run python scripts/run_ui.py                          # dashboard on :8501
uv run python scripts/report.py close                    # a check-in page -> data/reports/
uv run python scripts/install_launchd.py status          # scheduled agents: bot + operator tick (install | remove)
uv run python scripts/operator_tick.py                   # what the 5-minute tick does (health check, due tasks)
uv run python scripts/run_daily_backtest.py --strategy price_momentum --universe mega_caps_20 --start 2019-01-01 --end 2026-07-24
uv run python scripts/backtest_options.py                 # options grid on rebuilt chains (download_option_history.py first)
uv run pytest -q                                         # 93 tests
uv run ruff check src scripts tests && uv run ruff format --check src scripts tests
```

## Project skills

`.claude/skills/dixon-ml-finance/` distils Dixon, Halperin & Bilokon, *Machine Learning in Finance*
(2020) into rules for this project: diagnostics before modelling, day-level walk-forward with a
verification slice, the small-data model ladder (logistic → shallow trees → one tanh layer), calibrated
probabilities and Bayes-factor evidence, interpretability, HMM regimes, and exits as optimal stopping.
Load it for any model, validation, backtest-evidence, RL or exit-rule work. Ships `scripts/evalkit.py`.

`.claude/skills/typesafe-jev/` documents TypeSafe AI's Jev decision model (verified 2026-09-17,
typesafe-sdk 0.6.0 installed under the `jev` dependency group) and the plan for using it as a news /
sentiment universe filter. Owner is on the early-access waitlist; no key yet. Load the skill whenever
Jev, TypeSafe, headline scoring, or a news filter comes up.

## Where the last session stopped

**2026-09-24, early morning.** The news study ran and failed all four pre-registered tests (phase 28). A
benchmark bug in the daily engine was found and fixed (phase 29); on the corrected benchmark long-only
price momentum is the leading daily candidate (IR 0.51, t 1.6, both halves positive) and runs in shadow as
`pm_actives`. The options backtester is done (phase 30): the vrp-gated bull put spread is the best defined-risk
result and runs in shadow on SPY and QQQ. Next in order: a gated momentum variant (lean into
high-volatility chop), fill reconciliation before any options slot goes live, a sizer fix for
undefined-risk structures.
Handoff detail: top of `docs/progress.md`.

## Strategy intake and Alpaca capabilities

The owner hands strategies over as briefs in `docs/strategies/inbox/` (format: `docs/strategy-intake.md`);
every brief goes through the pipeline there and gets a verdict page under `docs/strategies/`. What the
Alpaca account and data plan enable, what is used and what is not: `docs/alpaca-capabilities.md`
(probed 2026-09-23: shorting, margin 4x, fractional, crypto, options level 3, extended hours, tick data,
corporate actions, websocket streams are all available; only stocks/ETFs long, snapshots, bars, news,
screener and options chains are used).

## Handbook

`docs/handbook.md` is the owner's all-in-one reference and the version to share; it is exported from the
shareable Claude doc "Ride The Wave Handbook". When a strategy, formula, result or process changes,
update the handbook chapter as well as the feature or research page.

## Working rules for Claude

1. Update the status table above, `docs/decisions.md` and the owner's log `docs/progress.md` whenever a phase or a decision changes.
2. Every new feature gets a plain-English page in `docs/features/` before the phase is marked done.
3. Every new folder gets a README.md.
4. Never print or commit API keys. Never point the bot at `api.alpaca.markets` (live).
5. Strategy code in `src/ridethewave/strategy/` must stay free of network and database calls so backtests stay honest.
6. Run `uv run pytest` before marking any phase done.
7. Verify Alpaca facts against docs.alpaca.markets when in doubt; the API docs in `docs/api/` record the verification date.

## Direction (owner, 2026-09-21)

**End goal:** an autonomous simulated quant trader on this machine, about five check-ins a day, no
low-latency ambitions, many strategies drawn from books, papers and news with AI doing research,
orchestration and reporting. North star: [docs/vision-autonomous-quant.md](docs/vision-autonomous-quant.md).
Ride The Wave is the **base** strategy, not the destination; strategy candidates and ordering:
[docs/roadmap-advanced-strategies.md](docs/roadmap-advanced-strategies.md). Build order: operator
(scheduling, watchdog, kill switches, check-in reports) → multi-strategy core and allocator →
strategy pipeline → nightly research automation → knowledge intake. Ride The Wave keeps running
on paper as the reference and live-feed data collector.

## Roadmap beyond v1 (owner's direction, 2026-09-17)

The v1 streak strategy is deliberately simple boilerplate. Once it runs end to end, the owner wants to optimise stock selection and hit rate with:

- News and trend signals (Alpaca News API, sentiment scoring) to pick the universe and confirm entries.
- Impulse / momentum-strength metrics and market-sentiment ("empathy") style indicators.
- Techniques from Ernest Chan (*Quantitative Trading*, *Algorithmic Trading*: mean reversion, cointegration, Kelly sizing, backtest pitfalls) and Grinold & Kahn (*Active Portfolio Management*: information ratio, fundamental law of active management, alpha forecasting, risk models).

Architectural consequence: keep the `Strategy` interface and the universe builder pluggable, and make the backtester report information ratio and hit rate from day one so later strategies can be compared on the same footing.

## Parameter sets

Current defaults (settings.example.yaml and the pydantic defaults in config.py, kept in sync) are the
2026-09-17 sweep's best row (entry 09:31 to 11:30, streak 3 at 1.0%, trail 1.5% / floor 0.5%, stop 1%,
hold 60) plus three entry filters (SPY session return >= 0.1%, stock session return <= 0.6%, trade-count
ratio <= 0.7). Profiles: `v1-original.yaml` (owner's brief), `v2-sweep-2026-09-17.yaml` (sweep best, no filters). Every previous set is preserved as a runnable file under `config/profiles/` (`v1-original.yaml`
is the owner's brief). Never edit a profile; add a new one and a row to the parameter-history table in
docs/strategy.md.

## Reference books

`docs/books/` (PDFs gitignored; README lists them): Tsay *Analysis of Financial Time Series* 2nd ed.,
Dixon/Halperin/Bilokon *Machine Learning in Finance* (distilled into a skill 2026-09-17), Rao/Jelvis
*Foundations of RL with Applications in Finance*, Kakushadze/Serur *151 Trading Strategies* (mapped against
Alpaca 2026-09-23; owner used some of these with good profit factors elsewhere, which ones is still to ask). `brew install poppler` enables PDF page rendering;
`pdftotext -layout` extracts text. Companion code for Dixon: github.com/mfrdixon/ML_Finance_Codes.

## Data facts (measured 2026-09-17)

SIP minute bars back to Jan 2016 (extended hours included), IEX from ~2021 (regular hours only). On
Algo Trader Plus there is no recency hold-back. `limit` on bar requests is a hard cap: always pass `None`.

## Open questions for the owner

- Overnight holds: flatten everything at 3:55pm ET (default), or allow holding?
- Stop-loss: the brief only describes selling at a gain. Default is a 1% hard stop below entry. Confirm or change.
- Universe: start from Alpaca's most-active list (default) or a hand-picked ticker list?
