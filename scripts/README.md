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
- `alerts_check.py`: market-hours health check with macOS notifications. (phase 17)
- `nightly.py`: cache today's bars, export live features, research digest. (phase 17)
- `install_launchd.py install|remove|status`: schedule everything with launchd. (phase 17)
- `study_spy_intraday.py`: ten-year test of SPY first-half-hour → last-half-hour momentum. (research)
- `study_news_jev.py fetch|score|analyze`: does Jev's reading of a headline predict forward returns? Fetches Alpaca news for the universe, scores with Jev (resumable), labels from cached bars, and tests against candidate entries. (research)
- `operator_tick.py`: the five-minute operator tick: health check plus any due report or nightly job, decided in Eastern time. (phase 17)
- `study_xs_signals.py`: cross-sectional diagnostic for the Kakushadze day-trade signals (overnight reversal, previous-day momentum, intraday reversal): quintile forward returns with day-block bootstrap, daily rank IC, gap buckets. (research)
- `download_daily.py`: ten-year daily bars for a symbol list or named universe, raw or adjusted (`--adjust all` -> feed tag `sip-day-adj`). (phase 25)
- `run_daily_backtest.py`: replay a daily portfolio strategy (momentum, mean reversion, rotation, trend, vol targeting, MA rules) with benchmark and equal-weight comparison; `--pit-top N --pool ...` for point-in-time universes; `--save` stores the run. (phase 25)
