# 14 · Operator: running unattended

**What it does.** Lets the system run a trading day and its housekeeping without anyone watching,
and tells you what happened at five fixed check-in times. Five parts: kill switches, reports and
alerts, the launchd schedule, a watchdog that restarts the bot after the Mac restarts, and alerts
on your phone.

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
| 16:15 | Close report | Wave Rider's ledger row, a table of every strategy's ledger, every trade with its strategy, average hold (day trades and overnight holds apart), exit reasons, anything still open |
| 21:00 | Research digest | Feature rows recorded, data days, research queue (fills in when phase D lands) |

`scripts/alerts_check.py` runs every five minutes and raises a notification the first time each of
these appears in a day: a macOS banner, and a push to your phone once that is set up (section 5):

| Alert | Meaning | When it is checked |
|---|---|---|
| `heartbeat stale` | No tick for 90 seconds | Market hours only |
| `universe empty` | The bot is running but has no stocks to scan, so no intraday strategy can trade | Whenever today's heartbeat says so |
| `decision skipped [slot]` | A portfolio or options slot reached its decision time but could not decide. The reason is given, for example `universe empty`, `no daily history` or `decision failed: ConnectionError` | Whenever today's heartbeat says so |
| `risk halt active` | A kill switch stopped new entries | Always |
| `api errors this session` | Alpaca calls failed | Always |

The universe and decision alerts were added on 28 October 2026. Between 20 and 28 October the
universe build failed in every session, and the momentum portfolio skipped its decisions. The check
still printed "healthy" because it looked at nothing but the heartbeat's age. The new alerts are
also checked after the close, so the close report shows the day's problems. The next morning,
yesterday's heartbeat no longer counts.

One limit remains: the check cannot run while the Mac is asleep. A sleeping Mac shows up as a
stale heartbeat once it wakes, and as gaps in the bot log.

### Network failures

Every Alpaca client retries a request whose connection fails or is dropped. This is set in
`src/ridethewave/clients.py` by `with_retries`, beside the 10 s connect and 30 s read timeouts.

- A connection that cannot be opened is retried up to four times for any request, waiting 0, 2, 4
  and 8 seconds. The request never left the machine, so retrying is always safe.
- A response that never arrives is retried twice, for read-only requests only. Those are GET
  requests: prices, bars, the asset list, the screener. An order is a POST and is never sent twice,
  because the first one may already have reached Alpaca.

Why: after the Mac sleeps, its pooled keep-alive connections are dead. The first call after waking
used to fail with "Remote end closed connection without response". In October 2026 that single
failure regularly emptied the day's universe. A test reproduces it with a local server that hangs
up on the first request (`tests/test_client_timeouts.py`).

## 3. Scheduling (launchd)

`uv run python scripts/install_launchd.py install` writes three user-level launch agents and loads them:

| Agent | When | Runs |
|---|---|---|
| bot | 06:30 ET on weekdays (written in system time); not at load | `run_bot.py`: waits for the 09:30 ET open, trades, exits at the close; relaunched by launchd if it crashes, and by the watchdog (section 4) if the Mac restarted |
| operator | every 5 minutes | `operator_tick.py`: the watchdog, the health check, then any task that is due by Eastern time and not yet done today: reports at 09:00, 11:30, 14:00, 16:15 and 21:00 ET, the nightly job at 20:30 ET |
| api | always (kept alive) | `web/dist/server.js`: the TypeScript API and web page on http://127.0.0.1:8787 (feature 18) |

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

## 4. Watchdog: starting the bot when it should be running and is not

**What.** Every five minutes, before the health check, the operator tick checks two things on a
trading day. Did the Mac restart, with the bot not run since? Or did the 06:30 ET morning start not
happen at all? In either case it starts the bot's launchd job and sends an alert, for example "bot
restarted by watchdog: the Mac booted at 10:42 ET and the bot had not run since", or "bot restarted
by watchdog: the 06:30 ET scheduled start did not run (last heartbeat Thu 29 Oct 16:00 ET)".

**Why the missed-start check (added 2026-10-29).** Before 30 October the bot had never been started
by its morning calendar job on the Mac mini. On 29 October it was already running from the
restart test the evening before. On the laptop, launchd once fired calendar jobs two hours late,
and if a morning start never came, nothing would have started the bot. The 09:00 report would
have said "stopped", and the stale-heartbeat alert would have come at 09:30. The system log
shows the calendar job firing on time on the Mac mini (05:30:03 Central on 29 October, which is
06:30 ET). This check is insurance, so a missed start costs half an hour before the open rather
than the day.

**Why, corrected 2026-10-29.** The watchdog was built on the belief that a restart mid-session would leave
the bot down until the next morning. That was wrong. The bot's launchd job uses `KeepAlive` with
`SuccessfulExit: false`, which, per `man launchd.plist`, implies `RunAtLoad`. So launchd starts the bot
whenever its agent loads, and agents load when the Mac logs in. The restart test on 2026-10-28 showed
it: the bot was back within a minute of the reboot. The watchdog is therefore a second layer. It covers
the case where launchd does not bring the bot back after a boot.

**A bug found on the first Mac mini session (2026-10-29).** The launch agents' PATH has no `/usr/sbin`, so
the watchdog's bare `sysctl` call failed every five minutes and it could never read the boot time.
It now calls `/usr/sbin/sysctl`, `/usr/bin/pgrep` and `/bin/launchctl` by full path, and a test pins that.

**When it starts the bot.** Only when all of these hold:

| Condition | Why |
|---|---|
| A weekday, 07:00 to 15:45 ET | The morning job starts the bot at 06:30 ET, so on a normal day it is running by 07:00. After 15:45 there is nothing left to trade |
| The bot's launchd agent is loaded | Removing the agents is how you switch the system off, and the watchdog respects that |
| No `run_bot.py` process exists | Never a second bot |
| The bot's last heartbeat is older than the Mac's boot or this morning's 06:30 ET start, whichever is later | The bot has not run since the restart, or the morning start never happened |

The last row is what matters. A bot that has run since then and is not running now was stopped
on purpose, or finished its day, so the watchdog leaves it alone. A bot started the evening
before (after a restart, say) counts as running, because it writes a heartbeat every few seconds
while it waits for the open. The same rule prevents restart loops, because a started bot writes a
heartbeat within seconds. As a second guard the watchdog tries only once per boot or per morning.
If that one attempt fails, the alert says so and asks you to start the bot by hand.

Holidays need no special case: a bot started on a holiday waits for the next open by itself. If
launchd's morning job fires late or not at all (the timezone problem in section 3), the watchdog
starts the bot at 07:00 ET. If the boot time cannot be read, a reboot cannot be detected, but a
missed morning start still is. The 06:30 ET start time is defined once, in `watchdog.py`, and
`scripts/install_launchd.py` reads it, so the two cannot drift apart.

Every question it asks the system has a 10-second timeout: the boot time (`sysctl
kern.boottime`), whether the bot runs (`pgrep`), whether the agent is loaded (`launchctl list`).
If one fails, the watchdog takes the answer that does not start the bot. It starts the job with
`launchctl kickstart` without `-k`, which cannot kill a bot that is already running. Each attempt
is recorded in the database (`bot_state` key `watchdog`).

On the tick that restarts the bot, the health check is skipped. The heartbeat is stale by
definition at that moment, and each alert is sent only once a day, so raising it then would
silence a real stale heartbeat later in the day.

What it cannot do: run while the Mac waits at a login screen. The operator tick is a user agent and
starts only after login, so automatic login has to be on (`docs/mac-mini-setup.md`, step 2.4).

**Setting:** `operator.watchdog: true` (the default). Set it to `false` to turn the watchdog off.
**Code and tests:** `src/ridethewave/operator/watchdog.py`, `tests/test_watchdog.py`. To see it
work for real, restart the Mac mini on a weekday between 07:00 and 15:45 ET. About five minutes
after it logs in, the alert reaches your phone.

## 5. Phone alerts (ntfy)

**What.** Every alert, every watchdog message and the five "report ready" notices also go to your
phone as push notifications, through ntfy (https://ntfy.sh), a free push service. The macOS banner
still appears as before.

**Why.** On the Mac mini nobody looks at the screen, so a banner there tells no one. ntfy needs no
account and no password on the Mac: the phone app subscribes to a topic name, and the bot sends to
that name over HTTPS. Why not iMessage or email: `docs/decisions.md`, 2026-10-28.

**The topic name works like a password.** Anyone who knows it can read your alerts and send you
fake ones. So make it long and random, keep it in `.env` as `NTFY_TOPIC`, and never commit it. The
code never logs or prints it. The alerts themselves are short status lines with no keys in them.

**Set up (once, on the Mac mini):**

1. Install the ntfy app on the phone (App Store or Google Play).
2. Make up a topic name: `python3 -c "import secrets; print('rtw-' + secrets.token_urlsafe(16))"`.
3. In the app, subscribe to that topic on the default server, ntfy.sh.
4. Add the line `NTFY_TOPIC=<the name>` to `.env`.
5. Run `uv run python scripts/notify_test.py`. It prints `delivered: ... (HTTP 200)`, and the phone
   shows "Ride The Wave: test alert from <the Mac's name>". If it says not delivered, it names the
   HTTP status or says the request did not complete.

**How loud.** Alerts and watchdog messages go at high priority, so the phone makes a sound. The
"report ready" notices go at default priority. Five of them on a trading day are also a sign of
life: if they stop, so has the Mac.

**Settings:** `operator.notify` (default `true`) switches off the banner and the push together.
`operator.ntfy_server` (default `https://ntfy.sh`) is only for a self-hosted ntfy server. Without
`NTFY_TOPIC` nothing is pushed and everything else works as before.

**When the push fails** (no network, ntfy down): the failure is logged after at most 10 seconds
and the health check carries on. The alert still counts as sent for the day, so it is not
repeated. **Code and tests:** `src/ridethewave/operator/notify.py`, `scripts/notify_test.py`,
`tests/test_notify.py`.

## What you do

Open the dashboard or `data/reports/latest.md` at the check-in times. Act only on an alert or a
halt. Positions keep their server-side stops whichever way the bot stops.

- **Stop the bot for the rest of the day:** `pkill -f run_bot.py`. The bot finishes its tick and
  exits cleanly, so launchd does not relaunch it. The watchdog does not restart it either, because
  the bot has run since this morning's start. It starts again the next weekday morning as usual. If the
  Mac restarts later that day, that is a new boot, and the watchdog would start the bot again.
- **Stop it for good, or for several days:** `uv run python scripts/install_launchd.py remove`.
  This removes the operator agent as well, so no watchdog is left to restart anything.

**Code:** `src/ridethewave/operator/` (`risk.py`, `reports.py`, `dispatch.py`, `notify.py`,
`watchdog.py`), `scripts/operator_tick.py`, `scripts/report.py`, `scripts/alerts_check.py`,
`scripts/notify_test.py`, `scripts/nightly.py`, `scripts/install_launchd.py`, Reports tab in
`src/ridethewave/ui/app.py`.
