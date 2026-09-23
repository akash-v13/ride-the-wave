# operator

The part of the system that lets it run without someone watching.

- `risk.py`: kill switches. `RiskMonitor.check_pnl` (daily and open loss limits as a percent of
  allocation) and `check_winrate` (Beta posterior of the live win rate over recent trades against
  break-even). Pure; the runner flattens and halts entries on its say-so.
- `reports.py`: builds the five daily check-in pages (pre-market, morning, midday, close, research)
  as Markdown from the database, plus the alert checks (stale heartbeat, halts, API errors).
- `dispatch.py`: which scheduled task is due now, by Eastern time, and not yet done today. Pure.
- `notify.py`: macOS notification helper; no-op elsewhere.

Scripts that drive it: `scripts/operator_tick.py` (every 5 min), `scripts/report.py`, `scripts/alerts_check.py`,
`scripts/nightly.py`, `scripts/install_launchd.py`. Feature doc: docs/features/14-operator.md.
