# 14 · Operator: running unattended

**What it does.** Lets the system run a trading day and its housekeeping without anyone watching,
and tells you what happened at five fixed check-in times. Three parts.

## 1. Kill switches (inside the bot)

Checked every tick. Settings under `risk:` in `config/settings.yaml`.

| Switch | Default | What happens |
|---|---|---|
| Daily loss limit | 2% of today's allocation, realised | Flatten all positions, cancel pending buys, no new entries for the rest of the day |
| Open loss limit | 3% of allocation, realised plus unrealised | Same |
| Win-rate floor | on; judged after 30 live trades over the last 60 | If the posterior probability that the live win rate is below break-even exceeds 0.9, stop entering (positions are still managed to their exits, nothing is flattened) |

Break-even is derived from the average winner and loser of the same trades (avg loss ÷ (avg win +
avg loss)) unless you set `winrate_breakeven`. A halt is recorded in the database (`risk` state) and
appears on every report and in the dashboard's alerts until the next day.

## 2. Check-in reports and alerts

`scripts/report.py <kind>` writes a Markdown page to `data/reports/<date>/` and `latest.md`, and
the dashboard's Reports tab shows them.

| Time (ET) | Page | What is on it |
|---|---|---|
| 09:00 | Pre-market brief | Yesterday's ledger, today's strategy, filters, risk limits, universe size |
| 11:30 | Morning check-in | Open positions with exit triggers, closed trades, realised so far |
| 14:00 | Midday check-in | Same |
| 16:15 | Close report | Ledger row, every trade, average hold, exit reasons, anything still open |
| 21:00 | Research digest | Feature rows recorded, data days, research queue (fills in when phase D lands) |

`scripts/alerts_check.py` runs every five minutes in market hours and raises a macOS notification
the first time each of these appears in a day: stale heartbeat (no tick for 90 seconds while the
market is open), an active risk halt, API errors. Outside market hours it stays quiet.

## 3. Scheduling (launchd)

`uv run python scripts/install_launchd.py install` writes two user-level launch agents and loads them:

| Agent | When | Runs |
|---|---|---|
| bot | 06:30 system time, weekdays; also once at load | `run_bot.py`: waits for the 09:30 ET open, trades, exits at the close; relaunched only if it crashes |
| operator | every 5 minutes | `operator_tick.py`: the health check, then any task that is due by Eastern time and not yet done today: reports at 09:00, 11:30, 14:00, 16:15 and 21:00 ET, the nightly job at 20:30 ET |

Why an interval job decides the time of day itself: launchd fires calendar jobs in the timezone it
booted with. On 22 September every calendar job on this Mac fired two hours late, because the
machine had been up since August and its timezone had changed since. The bot's early start is
harmless (it waits for the bell), and the dispatcher reads Eastern time from the system clock, so
neither depends on launchd's idea of the hour. A task missed by more than four hours (Mac asleep)
is skipped rather than run stale.

`install_launchd.py status` lists loaded agents; `remove` unloads and deletes them, including the
older per-report agents. Logs go to `data/logs/launchd-<agent>.log`.

**Keeping the Mac awake.** While a session runs the bot holds a `caffeinate` assertion, so the
machine will not idle-sleep mid-day. Waking a sleeping Mac before the open needs one command, once:
`sudo pmset repeat wakeorpoweron MTWRF 08:05:00` (system time; 09:05 ET on this machine). Also set
System Settings, Energy: prevent automatic sleeping on power, and keep the Mac on power.

## What you do

Open the dashboard or `data/reports/latest.md` at the check-in times. Act only on an alert or a
halt. If you need to stop trading for the day: `uv run python scripts/install_launchd.py remove`
stops the schedule; `pkill -f run_bot.py` stops a running bot (positions keep their server-side
stops).

**Code:** `src/ridethewave/operator/` (`risk.py`, `reports.py`, `dispatch.py`, `notify.py`),
`scripts/operator_tick.py`, `scripts/report.py`, `scripts/alerts_check.py`, `scripts/nightly.py`,
`scripts/install_launchd.py`, Reports tab in `src/ridethewave/ui/app.py`.
