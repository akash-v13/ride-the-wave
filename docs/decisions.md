# Decision log

One entry per technical decision, newest at the bottom. Format: what was decided, the alternatives, why.

## 2026-09-17 — Python 3.12 managed by uv
Alternatives: system Python 3.9, Homebrew Python, conda. The Alpaca SDK requires 3.10+, so the system interpreter is out. uv installs and pins Python versions per project, creates the virtualenv, and resolves dependencies fast. Homebrew is still recommended to install uv itself.

## 2026-09-17 — alpaca-py as the only broker/data SDK
Alternatives: raw `requests` against the REST API, the deprecated `alpaca-trade-api`. alpaca-py is the maintained SDK (0.44.0, Aug 2026), typed with pydantic, and covers trading, data, screener and streaming. Raw REST is kept as a fallback in the API docs so the team can debug without the SDK.

## 2026-09-17 — REST snapshot polling for market data in v1
Alternatives: IEX websocket, historical bars endpoint polling. Free plan allows only 30 websocket symbols and withholds the last 15 minutes of SIP history. Multi-symbol snapshots with `feed=iex` return the latest trade and current minute bar for hundreds of symbols in one call, well within the 200/min budget.

## 2026-09-17 — Client-side exit logic with server-side safety stop
Alternatives: Alpaca native trailing stop. Native trailing stop cannot enforce a gain floor relative to entry. Client-side logic matches the brief exactly and is reusable in backtests. A plain stop-loss on the server covers the bot-crash case.

## 2026-09-17 — SQLite as the only datastore
Alternatives: Postgres, Parquet files, CSV. Single writer (bot), single reader (UI), small data volume, already installed. Parquet is the escape hatch for bars if needed.

## 2026-09-17 — Streamlit for the dashboard
Alternatives: FastAPI + React, Textual TUI, Dash. Streamlit needs no JavaScript toolchain and does tables and charts well. Runs as a separate process reading SQLite, so it cannot interfere with trading.

## 2026-09-17 — Strategy code is pure (no I/O)
So the same code runs in backtest and live, and so it can be unit tested with lists of bars.

## 2026-09-17 — Hard stop-loss added to the brief's rules
The brief only describes selling at a gain. Without a stop, a bad entry sits at a loss all day. Default 1% below entry, owner can change or disable.

## 2026-09-17 — Backtest fill model is slightly pessimistic
Nothing fills on the decision bar; limit buys need the next bar's low to reach the limit; stops fill at the open on a gap; slippage applied both ways. Paper trading is optimistic, so the backtester leans the other way to bracket reality.

## 2026-09-17 — Ledger and trades keyed by run_id
`daily_ledger` primary key is (run_id, date) and `trades` carries run_id + mode, so many backtests coexist with the live record in one database and the dashboard can show any of them.

## 2026-09-17 — Backtest peak tracking uses the bar high
Live, the bot sees ticks every 15 seconds and the peak reflects intra-minute highs. In replay only bars exist, so the peak is updated from each bar's high before the close is checked for an exit. Exits still fill on the next bar's open.

## 2026-09-17 — Ruff rule set
E, F, I, B, UP at line length 120. UP017 (datetime.UTC alias) ignored for readability.

## 2026-09-17 — Jev (TypeSafe) reserved for judgment, not strategy math
Jev returns calibrated probabilities for typed questions and cannot count, compare numbers or generate text. It will be used as a news / sentiment universe filter behind a `NewsSignal` interface with mock and null implementations, so the bot runs unchanged without a key. Raw answers are stored as features so thresholds can change without re-inference and the backtester can replay them. Owner is on the waitlist; the design and a verified API reference live in `.claude/skills/typesafe-jev/`.

## 2026-09-17 — Defaults moved to the sweep's best configuration; originals kept as a profile
Entry window 09:31 to 11:30 (was 09:40 to 15:00), streak 3 at 1.0% (was 5 at 0.5%), trail 1.5% with 0.5% floor (was 0.5% / 0.3%), max hold 60 min (was 120). Still a losing configuration (PF 0.91), adopted as the least-bad base for the entry-filter work. The original set is `config/profiles/v1-original.yaml`; the strategy doc has a parameter-history table.

## 2026-09-17 — Three entry filters adopted; volatility-scaled exits implemented but off
From a 446k-row feature dataset with a chronological train/test split, then confirmed in the replay engine: require SPY up >= 0.1% on the day, stock up <= 0.6% on the day, and streak trade-count ratio <= 0.7. PF 1.25 on 116 trades (SIP), 1.17 on IEX, positive on both halves. First profitable configuration; thin. Volatility-scaled exits gave PF 0.95 alone and 0.85 stacked on the filters, so they stay off. Pre-filter set kept as `config/profiles/v2-sweep-2026-09-17.yaml`.

## 2026-09-17 — Modelling protocol adopted from Dixon, Halperin & Bilokon
Before any classifier: run `scripts/diagnose_returns.py`. Validation is walk-forward by day with a verification slice; nothing is tuned on test days. Model ladder for ~8k rows: regularised logistic (reference is the three-gate rule), shallow trees, at most one tanh layer; no deep nets, RNNs or deep RL. Probabilities must be calibrated on the verification slice; claims of improvement need a Bayes factor or posterior, not a single split. Exits may be studied as optimal stopping on logged paths. Rationale and page references: `.claude/skills/dixon-ml-finance/`.

## 2026-09-17 — Streak trigger found non-predictive on 1-minute bars
Minute returns are white noise at lags 1–3; after the candidate trigger, forward return is −10.7 ± 9.2 bp at 60 minutes. The strategy's thin profit comes from the filters and the asymmetric exit. Next experiments target slower bars and pullback entries rather than trigger parameters. `docs/research/2026-09-17-streak-autocorrelation.md`.

## 2026-09-21 — Live feature recording added to the bot
Every completed minute bar in the entry window becomes a feature row in `features_live`, labelled after the close from the day's IEX bars. Wrapped so it can never affect trading. Rationale: the research dataset is SIP; the bot trades IEX; paper days are free labelled data on the right feed.

## 2026-09-21 — 15-minute bars identified as the first timescale with a streak signal
The diagnostic that killed the 1-minute streak was rerun on 5- and 15-minute bars. 5-minute bars showed the same reversal; 15-minute bars showed +22 ± 12 bp over 180 minutes after a 3-bar 1% streak, positive in both halves and monotonic in the gain threshold. Decision: the next strategy work is a 15-minute variant tested in the engine (IEX first), not more 1-minute tuning. Selection caveat recorded in the research note.

## 2026-09-21 — Upgraded to Alpaca Algo Trader Plus; bot moved to the SIP feed
Owner subscribed ($99/mo). Verified with `scripts/check_env.py` (recent SIP bars now served). `config/settings.yaml` sets `data_feed: sip`; the example file keeps `iex` so the repo stays runnable on a Basic account. Live polling, warm-up and feature labelling all follow the setting. Consequences: the 15-minute research (done on SIP) now matches the live feed; websocket streaming of the whole universe is possible; the "IEX check first" gate on the 15-minute variant is moot.

## 2026-09-21 — Operator layer: kill switches, five check-in reports, alerts, launchd scheduling
Chosen over a long-running supervisor process: launchd is native, survives reboots, and restarts the bot only on a crash (`KeepAlive: SuccessfulExit false`), since a clean exit at the close is the normal end of the day. Reports are Markdown files so they are readable anywhere and show in the dashboard. Kill switches live inside the bot (daily loss, open loss, Beta-posterior win-rate floor) so they work even if the scheduler does not. Notifications are macOS-only and used only for alerts and report readiness.

## 2026-09-21 — Multi-strategy slots with shadow mode; SPY intraday momentum rejected
Each configured strategy gets its own book, order manager, allocation and ledger; live slots share the Alpaca broker, shadow slots use the backtest SimBroker fed by live ticks. Chosen over one shared book because per-strategy P/L is what the allocator and the incubation decision need. Symbol exclusivity across live slots avoids two strategies fighting over one Alpaca position. The SPY first-to-last half-hour study over 2016-2026 found no effect (slightly reversed, negative after costs at every threshold); the strategy is kept as a template and disabled.

## 2026-09-21 — News filter not built after validation; Jev kept as a research feature source
21,081 headline-symbol pairs scored with Jev and labelled with forward returns. Jev classifies consistently, but fresh positive news is followed by no continuation intraday (+0.6 bp at 180 min) and streak entries with fresh positive news do worse (PF 0.74 vs 0.88). Negative and legal news drift lower on both halves. Decision: no entry confirmer; a down/legal exclusion is cheap but changes little; keep scoring daily headlines to grow the dataset for the analyst-note and post-earnings pockets. Questions live in `src/ridethewave/signals/jev_questions.py`.

## 2026-09-22 — Scheduling moved to a five-minute dispatcher; two bugs from the first full day fixed
First full paper day: the bot woke on time at 09:28 ET but its market-open check ran before the bell and ended the day at 09:29; and every launchd calendar job fired two hours late because launchd keeps the timezone it booted with (machine up since August, timezone changed since). Fixes: the bot now waits for the exact open after setup and only believes "closed" after the open has passed; scheduled tasks run from one interval job (`operator_tick.py`) that reads Eastern time itself and records what it has done per day; the bot's calendar start moved to 06:30 system time since it waits for the bell; `caffeinate` holds the Mac awake during a session. The day's ledger and 800 feature labels were recovered by hand. A missing `strategy` argument on the trade repository (the shutdown crash) was fixed.

## 2026-09-22 — Two strategies added in shadow mode despite failing backtests
The 15-minute Wave Rider (PF 1.00 with the market gate) and a long-only opening-range breakout (PF 0.93) do not pass the protocol, but shadow mode risks nothing and the owner wants live-price observation. Both are configured `mode: shadow`, labelled observation only, and are not candidates for allocation until an engine result clears the gates. Infrastructure added for them stays: per-strategy bar resampling, daily-bar session context, strategy-specific sizing and stops, and a fix to end-of-day liquidation in the simulator.

## 2026-09-23 — TypeScript API and web UI beside the Python core
Owner wanted to move "the API layer" to TypeScript. Chosen shape: a Fastify service (`web/`) that reads the bot's SQLite file and queues control requests (pause, resume, flatten, halt) the bot applies each tick; the Python engine, backtester and research stack are untouched. Rejected: rewriting the Alpaca/TypeSafe client layer in TypeScript, which would put an IPC hop on the trading path for no gain. Node's built-in SQLite module is used instead of a native package after the native build failed under Node 26.

## 2026-09-23 — *151 Trading Strategies* mapped; its open-to-close alphas built, tested and parked in shadow
The owner added Kakushadze & Serur's catalogue and asked what we can run on Alpaca. Verdict recorded in `docs/research/2026-09-23-kakushadze-151-feasibility.md`: the option, fixed-income, FX, futures, credit and real-asset chapters are out of reach; the stock and ETF chapters are usable, but most of them need one of three things we do not have yet: short selling (every dollar-neutral construction), overnight holds (monthly-rebalance portfolios) or outside data (earnings, book value, Fama-French factors). The two Appendix-A alphas and the intraday reversal were built as a long-only family (`xs_daytrade`, feature 19). Following the research protocol, a cross-sectional diagnostic came first: no score has ranking power in June to September 2026 (rank-IC t-statistics −0.4, −0.9, +0.3) and 16 backtest combinations all lose. Decision: run the two least-bad variants in shadow as observation only, as the owner asked for a live look, and do not allocate. The finding that liquid stocks drifted down between open and close in the sample (−16 bp a day) is the case for building short selling next: it is the ingredient that makes the book's stock strategies dollar-neutral and testable as written.

## 2026-09-23 — Strategy sizing and stop hooks wired; ORB evidence corrected; per-strategy stocks-only universe
Found while building feature 19: neither the runner nor the backtester passed the strategy object to the order manager, so the `qty_for` and `stops` hooks added on 22 September never ran and the ORB's 0.1-ATR stop had silently been the global 1% stop. Both are now wired. Re-run with the intended stop, the ORB's profit factor is 0.74 (207 of 258 trades stopped), not the 0.93 reported; its shadow settings were adjusted to the best row of a stop sweep and the docs corrected. `scripts/run_backtest.py` now supplies daily bars like the sweep script. A `stocks_only` flag on a strategy makes the runner and the point-in-time universe drop ETFs, ETNs, leveraged products and crypto trusts (name-based detection, `is_fund`) for that strategy only, so the live universe of the Wave Rider is unchanged.
