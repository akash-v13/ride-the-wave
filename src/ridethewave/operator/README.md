# operator

The part of the system that lets it run without someone watching.

- `risk.py`: kill switches. `RiskMonitor.check_pnl` (daily and open loss limits as a percent of
  allocation) and `check_winrate` (Beta posterior of the live win rate over recent trades against
  break-even). Pure; the runner flattens and halts entries on its say-so.
- `reports.py`: builds the five daily check-in pages (pre-market, morning, midday, close, research)
  as Markdown from the database, plus the alert checks (stale heartbeat, empty universe, skipped portfolio or
  options decisions, halts, API errors).
- `dispatch.py`: which scheduled task is due now, by Eastern time, and not yet done today. Pure.
- `notify.py`: notifications. A macOS banner (no-op elsewhere) plus a phone push through ntfy when
  `NTFY_TOPIC` is set in `.env`. Never raises; the topic is never logged.
- `watchdog.py`: starts the bot's launchd job in trading hours (weekdays 07:00 to 15:45 ET) when the bot
  has not run since the Mac's boot or this morning's 06:30 ET start, whichever is later (last heartbeat
  older than that). Covers a mid-session restart and a morning calendar start that never ran.
  `decide` is pure; the system calls (`sysctl`, `pgrep`, `launchctl`) time out and fail towards "do
  not start". Run from the operator tick.

Scripts that drive it: `scripts/operator_tick.py` (every 5 min: watchdog, health check, due tasks),
`scripts/report.py`, `scripts/alerts_check.py`, `scripts/notify_test.py` (one test push to the phone),
`scripts/nightly.py`, `scripts/install_launchd.py`. Feature doc: docs/features/14-operator.md.
