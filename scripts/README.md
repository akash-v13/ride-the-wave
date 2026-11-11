# scripts

Entry points. Each is a thin wrapper that loads config and calls into `ridethewave`.

- `check_env.py`: verifies keys, prints paper account equity. (phase 2)
- `run_bot.py`: the live paper-trading loop. (phase 5)
- `run_backtest.py`: replay a date range and print/store a report. (phase 6)
- `run_ui.py`: convenience launcher for the Streamlit dashboard. (phase 7)
- `download_history.py`: bulk-fill the minute-bar cache for a date range and universe. (phase 10)
- `sweep.py`: parameter grid sweeps and hour-of-day / exit-reason breakdowns over cached history. (phase 10)
- `build_features.py`: prospects/candidates feature dataset with forward labels -> data/features/*.parquet. (phase 12)
- `analyze_features.py`: bucket each feature against strategy P/L to find filters. (phase 12)
- `diagnose_returns.py`: autocorrelation / stationarity / conditional forward-return diagnostics on cached bars. Answers "is there anything to predict?" before building a model. (phase 13)
- `export_live_features.py`: flatten live-recorded feature rows (IEX feed) to parquet in the research layout. (phase 12)
- `report.py <kind>`: write a check-in page (premarket, morning, midday, close, research). (phase 17)
- `alerts_check.py`: market-hours health check with macOS notifications, and phone pushes when `NTFY_TOPIC` is set. (phase 17)
- `notify_test.py`: sends one test push to the phone through ntfy and says whether it was delivered; never prints the topic.
- `nightly.py`: cache today's bars, export live features, research digest. (phase 17)
- `install_launchd.py install|remove|status`: schedule everything with launchd. (phase 17)
- `study_spy_intraday.py`: ten-year test of SPY first-half-hour → last-half-hour momentum. (research)
- `study_news_jev.py fetch|score|analyze`: does Jev's reading of a headline predict forward returns? Fetches Alpaca news for the universe, scores with Jev (resumable), labels from cached bars, and tests against candidate entries. (research)
- `operator_tick.py`: the five-minute operator tick: watchdog (starts the bot after a reboot in trading hours, or when the 06:30 ET morning start did not run), health check, then any due report or nightly job, decided in Eastern time. (phase 17)
- `study_xs_signals.py`: cross-sectional diagnostic for the Kakushadze day-trade signals (overnight reversal, previous-day momentum, intraday reversal): quintile forward returns with day-block bootstrap, daily rank IC, gap buckets. (research)
- `download_daily.py`: ten-year daily bars for a symbol list or named universe, raw or adjusted (`--adjust all` -> feed tag `sip-day-adj`). (phase 25)
- `run_daily_backtest.py`: replay a daily portfolio strategy (momentum, mean reversion, rotation, trend, vol targeting, MA rules) with benchmark and equal-weight comparison; `--pit-top N --pool ...` for point-in-time universes; `--save` stores the run. (phase 25)
- `download_external.py`: free outside histories (Ken French factors from 1926, Cboe S&P 500 / VIX / option-strategy indexes, FRED Treasury yields and T-bills) into `data/external/`; `--list`, `--only`. Research only. (feature 23)
- `research_trend.py`: the trend-following study: the 21-ETF book through the daily engine (2017-2026) and the same rule on US stocks and the 10-year Treasury back to 1927 and 1963. (feature 23)
- `research_ken_french.py`: momentum and short-term reversal over 1927-2026 from Ken French's library: six pre-registered series, Sharpe by period and decade, crash episodes, break-even trading costs. (research)
- `research_statarb_stage1.py`: stat arb stage 1: residual reversal over 1 to 5 days (after SPY and each stock's sector ETF) on a point-in-time top 300, from the next open; IC, quintile spreads, Newey-West t, halves, VIX regimes, break-even cost, and a kill test. (research)
- `repair_daily_panel.py`: adds the delisted stocks the daily price panel lacks (2026-11-09). `list` downloads Massive's list of delisted tickers once; `download` asks Alpaca for each missing stock's bars as its symbol stood before it left, drops old names of companies already held, and writes `bars_delisted_*.parquet`; `report` counts what was added by year.
- `research_statarb_auction.py`: the VIX-gated reversal priced at the opening auction: each pick's largest opening print from Alpaca's auction history against the daily open the backtest used, on every gated session. (research)
- `research_turn_of_month.py`, `research_overnight_momentum.py`, `research_sector_stress.py`: shortlist signals D, C and A (2026-11-10), each one pre-set test: turn days against other days on Ken French's century; the top 30% on 12-1 momentum held from the close to the next open against its universe; residual reversal inside stressed sectors when VIX is below 20. Results in `data/research/signals/`; docs/research/2026-11-10-signals-a-c-d.md. (`research_statarb_auction.py --hedges auction` prices the ETF hedges at their auctions too.)
- `research_fed_days.py`, `research_offering_bounce.py`: shortlist signals E and F (2026-11-10): scheduled Fed announcement days against other days on Ken French's data; hedged five-session return after a scored offering headline with a fall of 5% or more. docs/research/2026-11-10-signals-e-b-f.md.
- `build_fomc_dates.py`: builds `config/calendars/fomc_scheduled.csv`, every scheduled Fed announcement date from 1994, from the Fed's own pages. Run once a year.
- `research_statarb_costs.py`: what the VIX-gated reversal really pays to trade: the picks' hedged move from the open to 09:35 on every gated session (minute bars), and their time-weighted quoted half-spread on 60 gated and 30 calm sessions (quote history); re-prices the backtest. `--part wait|spread|summary`. (research)
- `record_market_state.py`: the daily recording (feature 25): borrow flags for every active stock and option quotes for the stat-arb universe, into `data/recordings/`. Run by the operator tick at 15:45 ET; `--force` replaces today's files.
- `research_statarb_volgated.py`: stat arb stage 2a: the VIX ≥ 20 residual reversal as a tradable rule with costs (cohorts entered at the open, held 5 sessions, hedged), with and without a news-jump filter. (research)
- `research_momentum_overlay.py`: `pm_actives`' rule with and without a volatility-scaled overlay (SPY plus L × the book's return beyond SPY) on the survivorship-free top 100. (research)
- `research_sleeves.py`: combines the sleeves' daily return series (put spread, trend, stocks) at equal risk and a 10% volatility target; reports drawdowns against the 15% budget and the crisis episodes. (feature 23)
