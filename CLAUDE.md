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
| 31. October outage found and fixed | Done 2026-10-28 | 25 Sep to 28 Oct: only 2 of 24 sessions ran with a universe. Mac asleep on battery most market hours; from 20 Oct Alpaca's `TXSE` exchange code broke alpaca-py's `get_all_assets`. Fixes: raw asset reader (`data/assets.py`), connection retries on every client (GET-only for dropped responses), start-up universe retries plus a 2-minute retry while empty, late-symbol warm-up, alerts for an empty universe and skipped decisions. 106 tests. Owner: power and `pmset` wake schedule. Month's shadow results void. Progress log 2026-10-28 |
| 32. Mac mini host; first session there | Done 2026-10-29 | Moved 2026-10-28 (`docs/mac-mini-setup.md`). 29 Oct: clean session. Fixed a race in which the protective stop sold first and the bot's market sell would have opened a short; live slots now never sell more than Alpaca holds. Watchdog tools called by full path. Options closes priced from a one-sided quote, then mid, the saved last mark or exercise value, never silently at entry (the shadow QQQ covered call was booked at $0.00 instead of −$1,892.13, re-priced). Evening: close report per strategy (trades and ledgers read back had lost their strategy), credit-spread P/L % sign, watchdog also covers a missed 06:30 ET start. 155 tests |
| 33. Strategy re-think: sleeves, long histories | Done 2026-11-02 | Owner chose all five proposals. Retired `wave_rider_15m`, `orb`, `xs_overnight`, `xs_combo`. Outside histories (feature 23: Ken French 1926+, Cboe S&P 500/VIX/option indexes, FRED). `trend_following` (long-short, 21 ETFs, 10% vol): Sharpe 0.00 over cash 2017-26, 0.37 over a century, positive in long bear markets → shadow `tf_etfs` from 2026-11-03 as insurance. Put spread 1990-2026: Sharpe 0.25, DD −52%, fails 3 of 4 criteria → not promoted. Combined: no stock-holding book inside a 15% DD at 10% vol (needs ~4-6.5%). Daily slots now honour `rebalance_days`. docs/research/2026-11-02-*.md. 175 tests |
| 34. Ken French century: momentum and reversal | Done 2026-11-02 | Vol-scaled momentum: Sharpe 0.99 1927-2026, 0.55 since 2000, crashes halved; long-only scaled IR 0.83 (0.38 since 2000): passes. Short-term reversal (stat arb's base): Sharpe 0.12 since 2000, large caps 0.02, break-even 1-3 bp: gone. Ken French daily reversal files re-sort daily (bid-ask bounce): use the monthly ones. Stat arb planned in 3 stages, a residual-reversal diagnostic first (roadmap item 3). docs/research/2026-11-02-momentum-and-reversal-century.md |
| 35. Stat arb stage 1; momentum overlay | Done 2026-11-02 | Residual reversal (after SPY + sector ETF), top 300 PIT, 2017-26, from the next open: always-on +17 bp per 5-day trip, break-even 4.3 bp, kill test FAIL; with VIX ≥ 20 +51 bp (t 2.6, both halves), break-even 13 bp, a lead for its own test. `pm_actives` with a vol-scaled overlay: IR 0.43 (plain 0.48), worst stretch vs SPY halved: passes as risk control. `daily/residuals.py`. docs/research/2026-11-02-statarb-stage1.md, -momentum-overlay.md. 180 tests |
| 36. Stat arb in volatile markets (shadow `sa_volrev`) | Built 2026-11-02 | VIX ≥ 20 residual reversal as a rule (signal to yesterday's close, gate on yesterday's VIX from Cboe, enter 09:35, hold 5, hedged with SPY + sector ETFs): +29.7 bp per cohort after 26 bp costs, both halves positive, Sharpe 0.48, DD −11.2%, t 1.5. Shadow from 2026-11-03, $500k simulated, 254-stock universe file. Engine: `extra_symbols` / `external_series` on daily strategies, `universe: file:`, condensed report rows. docs/features/24-statarb-volatility-gated.md. 187 tests. 2026-11-04: traded 3 and 4 Nov (VIX 21.15, 20.83); the 1% dead band skipped every second-cohort add while hedges were full size, now per slot (`dead_band_pct`, sa_volrev 0.1). 188 tests |
| 37. Stat-arb costs measured; daily recordings; price-panel gap | Done 2026-11-09 | **Costs** (docs/research/2026-11-09-statarb-costs.md): the picks' quoted half-spread at 09:35 is 10.9 bp, not the 5 assumed; waiting from the open to 09:35 gains 5.7 bp per cohort. Re-priced as the slot trades: +11.9 bp per cohort (t 0.6) against +29.7; positive in both halves by a 3 bp margin. Lead: the opening auction has no spread. **Recordings** (feature 25): each daily-slot fill is stored with its bid and ask (`portfolio_fills`); `scripts/record_market_state.py` saves borrow flags and option quotes to `data/recordings/` at 15:45 ET from the operator tick. **Panel gap** (docs/research/2026-11-09-panel-survivorship-gap.md): Alpaca's asset list drops delisted stocks, so the "survivorship-free" panel lacks delistings from late 2022 on and in 2016-17; every 2017-26 result inherits it; a free repair from the corporate-actions feed is proposed, not started. Also restored `docs/decisions.md`, `docs/features/README.md` and `docs/research/README.md`, which a faulty append on 2 Nov had cut to their last entry. 203 tests |
| 38. Price panel repaired; studies re-run | Done 2026-11-09 | 2,708 delisted stocks added: named by Massive's list of delisted tickers (one-time backfill, owner's free-plan key), priced by Alpaca by old symbol; 1,235 ticker changes removed (`scripts/repair_daily_panel.py`, `data/delistings.py`). Up to 8% of a year's top 300 had been missing. Re-run unchanged: `sa_volrev` rule +24.9 bp per cohort at assumed costs (was +29.7), **+7.5 bp (t 0.4) as it trades**; momentum IR 0.49 (was 0.51); overlay 0.39 (0.43); no verdict changed. Old results in `data/research/pre-repair-2026-11-09/`. Owner's direction: Alpaca stays the primary source, other sources are limited to one-time backfills, and records are built in-house where possible. docs/research/2026-11-09-panel-survivorship-gap.md section 5. 206 tests |
| 39. Stat arb at the opening auction | Done 2026-11-09, a proposal for the owner | Alpaca's auction history (`/v2/stocks/auctions`) gives each stock's opening auction prints. On all 779 gated sessions the backtest's daily open matches the auction long against short (gaps 0.0 and −0.2 bp per cohort). Priced at the auction with a 1 bp allowance a trade: **+40.6 bp per cohort (t 2.0)**, halves +47.7 / +33.7, against +7.5 bp with market orders at 09:35. Passes the pre-set test. Thin: 21 looks, 2020 and 2025 carry it, a quarter of NYSE prints missing from 2022. **Approved and done:** from 10 Nov `sa_volrev` books fills at each stock's opening auction price plus 1 bp, sized on yesterday's close (`fill_at: open_auction`, per slot; `data/market_data.opening_auctions`; `basis` column in `portfolio_fills`). docs/research/2026-11-09-statarb-auction-fills.md. 209 tests |
| 40. Auction reader corrected; first auction-priced session | Done 2026-11-10 | At 09:35 on 10 Nov only 114 of 266 symbols were priced at the auction. Cause: a one-day request returns the day before first for NYSE and ARCA symbols on winter days (late closing print stamped after midnight UTC) and the reader took row 0. Now matched on date (`daily/costs.auction_day`). The 9 Nov study's "92% coverage" and "ETFs have no prints" were this error; re-run: 99.9% priced, +40.6 bp per cohort (t 2.0) unchanged, +40.7 with hedges at their auctions. 10 Nov fills left as booked (fallback differed by ~1 bp). docs/research/2026-11-09-statarb-auction-fills.md section 6 |
| 41. Shortlist signals A, C, D tested | Done 2026-11-10; none passes | One pre-set test each (docs/research/2026-11-10-signals-a-c-d.md; `daily/signals.py`). **A** sector-stress reversal, calm markets: −28.6 bp per cohort (t −2.1), rejected. **D** turn of the month: +14.6 bp a day 1926-2005 (t 8.0), +0.8 bp 2006-2026 (t 0.2), rejected. **C** momentum held overnight: winners beat the universe by +3.76 bp a night (t 4.3, every year positive), +1.76 after costs (t 2.0), both halves positive, but under its 4 bp bar: a lead, not promoted. 24 looks. 216 tests |
| 42. Shadow slots for A, C, D; signals E, F tested | Done 2026-11-10; slots trade from 2026-11-11 | **Observation only, none passed** (docs/features/26-shortlist-shadow-slots.md): `mom_night` (C; buys ~75 winners at 15:50, re-booked at the official close next morning, sold at the opening auction; new per-slot `flatten_time`), `sa_sector` (A; mirror of `sa_volrev`, cohorts only after VIX < 20), `tom_spy` (D). **E** Fed days: +34.3 bp 1994-2011 (t 3.4), +5.8 bp 2012-2026 (t 0.6), rejected. **F** offering bounce: 170 events, mean +90.7 bp, median −74.5, t 0.9, fails. **B** not run: needs report dates (proposed: SEC 8-K item 2.02; owner to give a contact address for the request header). Fed dates in `config/calendars/fomc_scheduled.csv` (`data/fomc.py`). Candidate G (news carrying related stocks, owner's idea) proposed at the end of the shortlist. docs/research/2026-11-10-signals-e-b-f.md. 27 looks. 224 tests |
| 43. Earnings dates from the SEC; signals B and G tested | Done 2026-11-10; both fail | Report days from EDGAR 8-K item 2.02 filings with acceptance times (`data/edgar.py`, `scripts/download_earnings_dates.py`; `SEC_CONTACT` in `.env` only, never in the repo; company numbers from Massive's ticker list): 36,161 filings, 1,031 of 1,151 universe stocks. **B** reversal held through the report (as So & Wang measure it; the shortlist's "out before" misread the paper): 3,513 trades, +1.3 bp net (t 1.0), halves −32.6 / +35.6; fails. **G** (owner's idea) ten most-correlated stocks traded in a news stock's direction, next open for 3 sessions: 3,208 events, −0.1 bp (t 0.5); fails; the related stocks move +76 bp on the news day itself. Intraday G is a new candidate, not designed. docs/research/2026-11-10-signals-b-g.md. 29 looks. 227 tests |
| 44. Candidate G inside the day | Done 2026-11-10; fails | Material headline 09:40-15:00 and a ≥ 0.5× usual-day move by the stock in the ten minutes around it (750 events, minute bars); ten most-correlated stocks traded in that direction from 5 min after the headline to the close, SPY-hedged, 7 bp costs: related stocks had already moved +21.8 bp inside the window, +4.4 bp after entry, **−2.6 bp net (t −0.6)**, both halves negative. Related stocks follow within minutes; news through correlated baskets is closed at tradable horizons. `daily/signals.py` (`price_at`, `news_move`), `scripts/research_related_news_intraday.py`, docs/research/2026-11-10-signal-g-intraday.md. 30 looks. 228 tests |
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
- **Research may use free outside histories** (Ken French, Cboe, FRED; `ridethewave.data.external`, owner approved 2026-11-02) to test before 2016. Trading and marks use Alpaca data only.
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
uv run python scripts/download_external.py               # outside histories for research (Ken French, Cboe, FRED)
uv run python scripts/research_trend.py                  # trend study; research_sleeves.py combines the sleeves
uv run python scripts/record_market_state.py             # today's borrow flags and option quotes -> data/recordings/ (the operator runs it at 15:45 ET)
uv run python scripts/repair_daily_panel.py report       # delisted stocks added to the price panel (list | download | report)
uv run pytest -q                                         # 228 tests
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

**2026-11-10, late night: G tested inside the day; PR #5 open** (phase 44). Branch `signals-b-g` holds B, G (daily) and G (intraday); the machine stays on it until PR #5 is merged, then switches to `main` outside market hours. Intraday G fails: related stocks follow a news stock within the same ten minutes. **The shortlist is exhausted: 30 looks, nothing passes, C (shadow `mom_night`) is the one lead.** **Next:** watch 11 Nov (three new slots) and 12 Nov (`mom_night`'s first morning sale); early-close handling before 27 Nov; propose a second shortlist drawn from where tests found life (cross-sectional stock signals at the auctions; market-stress conditions). Untested and not backtestable: news reaching companies that never moved with the source (would need forward recording of events from Alpaca's news stream).

**2026-11-10, night: PR #4 merged; B and G tested** (phase 43). This machine is on branch `signals-b-g` (cut from `main` after the merge), **not committed**; the owner has not yet asked for a PR. The whole shortlist is tested: none of A to G passes; C is the one lead (shadow `mom_night`). G's daily test shows related stocks follow a news stock on the same day (+76 bp) and not after, so the open question is intraday. **Waiting on the owner:** whether to design and run G inside the day (minute bars, headline times, real spreads); commit and PR for this branch. **Still to do:** watch 11 Nov (three new slots) and 12 Nov (`mom_night`'s first morning sale); early-close handling before 27 Nov. The owner's contact line for the SEC is in `.env` (`SEC_CONTACT`); never write it anywhere else.

**2026-11-10, evening: shadow slots for A, C, D; E and F tested** (phase 42; progress log 2026-11-10). The owner said yes to the PR and to C in shadow, and asked for A and D in shadow too. **PR #4** (branch `signal-tests-a-c-d`) holds all of 10 November's work; this machine stays on that branch until it is merged, then switches to `main` outside market hours. Three observation slots trade from 11 Nov: `mom_night`, `sa_sector`, `tom_spy` (dry run clean). E rejected, F fails, B waits on earnings dates. **Check on 11 Nov:** `[sa_volrev]`/`[sa_sector]` "fills priced at the open" nearly all at the auction; `[mom_night]` buys at 15:50; on 12 Nov "purchases re-booked at the close" and "sold ... at the open". **Waiting on the owner:** a contact address for the SEC request header (then B); whether to write candidate G's test (news carrying related stocks; signal A's failure is evidence for it). **To fix before 27 Nov:** early closes (13:00) are not handled; no 15:50 decision runs on a half day, and `tom_spy`'s first purchase falls on one.

**2026-11-10: three signals tested, an auction reading error fixed** (phases 40, 41; progress log 2026-11-10). PR #3 is merged; this machine is on branch `signal-tests-a-c-d` (cut from `main`), **nothing committed yet**. The owner confirmed the target is a **yearly Sharpe of 1.4, ideally above 2**, and chose A, C, D first. Results: A and D rejected; C (momentum overnight) missed its 4 bp bar by 0.24 bp and is a lead. The first auction-priced session exposed a reader error (NYSE and ARCA prints lost on winter days); fixed, study re-run, +40.6 bp unchanged. Session itself clean: Wave Rider −$21.64, `sa_volrev` $495,275. **Next:** signals E (Fed dates from the Fed's site), B (earnings dates: our scored news first, a web calendar as a one-time backfill, the owner allows scraping), F (scored news). **Waiting on the owner:** whether C is observed in a shadow slot (needs a slot that trades at the close and the next open); a commit and PR for this work. Check on 11 Nov that the log line "fills priced at the open" shows nearly all symbols at the auction.

**2026-11-09, night: the price panel is repaired** (phase 38). The owner gave a Massive key (free plan: two years of prices, 5 requests a minute, but the full list of delisted tickers) and asked that Alpaca stay the primary source, with other sources limited and records built in-house. Massive supplied the names once; Alpaca supplied the prices. All studies were re-run unchanged: every number fell a little and no verdict changed. `sa_volrev` as it trades is now +7.5 bp per cohort, t 0.4: no edge. Momentum is still the best lead (IR 0.49). Then the auction test (phase 39): filled at the opening auction the same picks earn +40.6 bp per cohort (t 2.0) against +7.5 bp at 09:35, so execution decides it. The owner approved, and from 10 Nov `sa_volrev` fills at the opening auction price (dry run clean). **Owner's long-term target (2026-11-09): Sharpe 1.4, by hunting for signals that repeat under stated conditions** (some several times a week, some a few times a year); see docs/decisions.md. **Shortlist written** for the owner: six untested conditional signals with formulae and a worked example (docs/strategies/2026-11-09-signal-shortlist.md); suggested order D (turn of the month), E (Fed days), C (overnight momentum), A (sector-stress reversal), B (pre-earnings), F (offerings). **Next:** watch the first auction-priced session; the owner picks which signals to test; a shadow slot for the momentum overlay; whether to pay for Massive's 20-year plan. PR #2 was merged on 9 November before this work. The repair, the auction test, the slot change and the shortlist are in **PR #3** (branch `panel-repair-auction-fills-shortlist`); this machine stays on that branch until the owner merges it, then switches to `main` outside market hours.

**2026-11-09, evening: costs measured, recordings started, a data gap found** (phase 37; progress log 2026-11-09 evening). The owner approved the cost measurement and the daily recording. Results: the stat-arb picks cost 10.9 bp a trade at 09:35 (assumed 5), so `sa_volrev` re-prices to +11.9 bp per cohort (t 0.6): no demonstrable edge as it trades now. Recordings run from 10 Nov (fill quotes in the bot, borrow flags and option quotes at 15:45 ET). **Found on the way:** the price panel is not survivorship-free after 2022, because Alpaca's asset list drops delisted stocks. **Waiting on the owner:** go-ahead to (1) repair the panel from Alpaca's corporate-actions feed and re-run the frozen studies, (2) test opening-auction execution for `sa_volrev`. The slot's rule and settings are unchanged. Bot dry run clean. **PR #2** held all work since PR #1 up to this point and was merged the same day.

**2026-11-09: status check.** Sessions 5, 6 and 9 Nov ran. VIX 28.18 on 5 Nov and 25.64 on 6 Nov, so `sa_volrev` holds four cohorts. The dead-band fix worked (book matches targets). First week: $494,729, −1.1%, within the backtest's range. Live Wave Rider: −$44 on 6 Nov, +$92 on 9 Nov. Bug fixed in `order_manager._sell`: a stop still filling when read made a sell ask for more than Alpaca held. The refused sell left WULF ×32 marked as exiting with no order and no stop over the weekend, until Monday's reconcile adopted it. The stop is now read only once terminal, and a refused sell clears the mark so the bot retries. 190 tests. Progress log 2026-11-09. Still uncommitted. **Same day:** the owner is looking for outside resources, mostly for stat arb. The assessment, wish list (pre-2016 survivorship-free daily prices first) and reading list are at the top of docs/roadmap-advanced-strategies.md. Nothing from it is built yet.

**2026-11-04: status check.** Sessions on 3 and 4 Nov were clean. Live Wave Rider: −$1 and −$55. VIX closed above 20 on 2 and 3 Nov, so `sa_volrev` formed two cohorts. Bug found: the 1% dead band skipped all 79 second-cohort adds while the hedges were sized in full (stocks 24%/22% held against 40%/40%). Fixed with a per-slot `dead_band_pct` (sa_volrev 0.1%), live from the 5 Nov start. The 4 Nov `sa_volrev` mark is not clean. Progress log 2026-11-04. Still uncommitted, still waiting on the three owner decisions below.

**2026-11-02: the new direction started** (phase 33; progress log 2026-11-02). Sessions 29 Oct to 2 Nov ran cleanly; live Wave Rider +$42 over 9 trades. Owner approved all five proposals. Retired the four failed intraday shadow slots, added outside histories, built trend following (shadow `tf_etfs` from 3 Nov) and tested the put spread over 1990-2026: it fails (Sharpe 0.25, −52% DD), and trend does not rescue it. **Waiting on the owner:** risk budget (about 6% vol for a 15% DD, or 10% vol with 25-30%); retire the put-spread slots or observe them at 5% risk per spread; which 151 strategies worked before. **Evening:** Ken French century study (phase 34): volatility-scaled momentum passes; monthly reversal (stat arb's base) is gone since 2000. Then stat arb stage 1 (always-on fails its kill test; the VIX ≥ 20 version is a lead) and the momentum overlay (passes as risk control) (phase 35). Then the VIX-gated reversal passed its strategy test and runs as shadow slot `sa_volrev` from 3 Nov 09:35 ET (phase 36; VIX was 19.42 on Friday, so it trades only after a close ≥ 20). **Next:** watch `sa_volrev` this week; then a shadow slot for the momentum overlay. Changes are **not committed**; the owner reviews PRs on GitHub (gh CLI is set up on the Mac mini).

**2026-10-29: first session on the Mac mini ran cleanly**, with one execution bug fixed (phase 32; progress log
2026-10-29). Live Wave Rider: 3 trades, all stopped out, −$32.93. After the close, an options close-pricing bug was fixed and the shadow `cc_qqq` record re-priced. Evening: close report fixed (per-strategy ledger table, strategy column, dates on multi-day holds, credit P/L % sign); the watchdog now also starts the bot if the 06:30 ET calendar start did not run (the log shows it fired on time on 29 Oct). Owner asked to re-think the strategy direction (brainstorm 2026-10-29). Next: watch 30 October with the new sell guard.

**2026-10-28, evening: the system now runs on the Mac mini** (user `admin`, project at
`/Users/admin/Projects/Finance/Ride The Wave`). Any copy on the laptop is stale, and its `.env` is disabled.
What was set up: `docs/mac-mini-setup.md`, section "Done on 2026-10-28". First full session on the Mac mini: 2026-10-29.

**Earlier on 2026-10-28, after the close.** First session since 2026-09-28. The status check found a month of mostly
empty sessions (phase 31): the Mac slept through market hours on battery, and from 20 October a new
exchange code (`TXSE`) broke the asset list in alpaca-py. Both code-side causes are fixed, tested and
dry-run against the paper account. **The changes are not committed**; the owner commits on request. The owner is buying a **Mac mini** as the always-on machine. Runbook: `docs/mac-mini-setup.md`, covering
setup, handover with never two bots at once, and Tailscale remote access. Until it arrives, the laptop must stay
powered and awake (`sudo pmset repeat wakeorpoweron MTWRF 08:05:00`). Built the same evening for the move: a
watchdog in the operator tick that restarts the bot after a mid-session reboot, and phone alerts through ntfy.
The topic is in `.env` only, never in docs, because the repo is public. 136 tests. Shadow results from September and October cannot be used as
evidence. Observation restarts from the first full session. Next, in order: confirm a full session runs
clean; then the gated momentum variant (lean into high-volatility chop); fill reconciliation before any
options slot goes live; a sizer fix for undefined-risk structures. Also noted: `bps_spy` picks weekly
expiries live, but the backtest only tested monthlies.
Detail: top of `docs/progress.md`.

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

**Alpaca's asset list is not a record of delisted stocks (found 2026-11-09).** A stock delisted now drops
out of the list; it does not move to the inactive part. Alpaca still serves its prices when asked by
symbol. `data/daily_panel/` was repaired the same day: 2,708 delisted stocks were added by symbol, named
by Massive's list of delisted tickers (docs/research/2026-11-09-panel-survivorship-gap.md, section 5).
Known remaining holes: 351 tickers Alpaca had no prices for, and prices after a stock's last trading day.
After rebuilding the panel, always run `scripts/repair_daily_panel.py download`.

## Open questions for the owner

- Overnight holds: flatten everything at 3:55pm ET (default), or allow holding?
- Stop-loss: the brief only describes selling at a gain. Default is a 1% hard stop below entry. Confirm or change.
- Universe: start from Alpaca's most-active list (default) or a hand-picked ticker list?
