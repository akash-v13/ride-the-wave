"""Watchdog: start the bot when it should be running on a trading day and is not.

Why it exists. launchd starts the bot once each weekday morning (06:30 ET) and relaunches it after a crash or at
login. Two gaps remain, and the operator tick runs this every five minutes to cover both:
  1. the Mac restarted mid-session and launchd did not bring the bot back;
  2. the morning calendar start did not run at all (added 2026-10-29: on the laptop launchd once fired calendar
     jobs two hours late, and nothing else would have noticed a start that never came).

How it tells a missing bot apart from a deliberate stop. The bot writes a heartbeat (`bot_state` key "heartbeat") on
every tick, and every minute while waiting for the open. The bot should have run since the later of two moments:
the Mac's boot, and this morning's scheduled start. If its last heartbeat is older than that, start it. If the bot
has run since then and is not running now, someone stopped it (`pkill`) or it finished its day: leave it alone. The
same rule stops restart loops, because a started bot writes a heartbeat within seconds; and the watchdog tries at
most once per boot or morning in case it never does.

Rules (all must hold to start): the watchdog is enabled; a weekday between 07:00 and 15:45 Eastern; the bot's launchd
agent is loaded (removing the agents is how the owner switches the system off); no bot process is running; and no
heartbeat since the boot or the scheduled start, whichever is later. Holidays are fine: a bot started on a holiday
waits for the next open by itself.

Every system call has a timeout and never raises. When a call fails, the answer is the one that does NOT start the
bot. `kickstart` deliberately omits launchctl's `-k`, so it can never kill a running bot.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from loguru import logger

from ridethewave.config import Settings
from ridethewave.operator.reports import _heartbeat
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")
BOT_LABEL = "com.ridethewave.bot"  # scripts/install_launchd.py: LABEL + ".bot"
# Full paths: the launch agents run with PATH=/opt/homebrew/bin:~/.local/bin:/usr/local/bin:/usr/bin:/bin, which
# has no /usr/sbin, so a bare "sysctl" was not found and the boot time was never read (found 2026-10-29).
SYSCTL = "/usr/sbin/sysctl"
PGREP = "/usr/bin/pgrep"
LAUNCHCTL = "/bin/launchctl"
SCHEDULED_START = time(6, 30)  # ET; the bot's launchd calendar start (scripts/install_launchd.py reads this)
WINDOW_START = time(7, 0)  # ET; half an hour after the scheduled start, a normal day has a heartbeat
WINDOW_END = time(15, 45)  # ET; too late to trade after this, and the bot flattens at 15:55
RESTARTED = "bot restarted by watchdog"  # prefix of the message when the bot was started
STATE_KEY = "watchdog"
_TIMEOUT_S = 10

_BOOT_RE = re.compile(r"\bsec\s*=\s*(\d+)(?:\s*,\s*usec\s*=\s*(\d+))?")


# ---------------------------------------------------------------- pure
def _aware(dt: datetime | None) -> datetime | None:
    """Treat a naive timestamp as UTC (every timestamp this system writes is UTC)."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def in_window(now_utc: datetime) -> bool:
    """Weekday, 07:00 <= Eastern time < 15:45."""
    et = now_utc.astimezone(ET)
    return et.weekday() < 5 and WINDOW_START <= et.time() < WINDOW_END


def _et_label(dt: datetime, now_utc: datetime) -> str:
    et = dt.astimezone(ET)
    same_day = et.date() == now_utc.astimezone(ET).date()
    return et.strftime("%H:%M ET") if same_day else et.strftime("%a %d %b %H:%M ET")


def scheduled_start_utc(now_utc: datetime) -> datetime:
    """This morning's scheduled bot start (06:30 ET on `now_utc`'s Eastern date), in UTC."""
    return datetime.combine(now_utc.astimezone(ET).date(), SCHEDULED_START, tzinfo=ET).astimezone(timezone.utc)


def decide(
    now_utc: datetime,
    boot_utc: datetime | None,
    last_heartbeat_utc: datetime | None,
    process_running: bool,
    agent_loaded: bool,
    enabled: bool,
    last_restart_utc: datetime | None = None,
) -> tuple[bool, str]:
    """Should the watchdog start the bot now? Returns (start, reason). Pure.

    The bot should have run since `since`: the Mac's boot if that came after this morning's scheduled start, else
    the scheduled start. `boot_utc` None means the boot time could not be read; then only the scheduled start
    counts, so a reboot is not detected but a missed morning start still is. `last_restart_utc` is when the
    watchdog last started the bot; one attempt per `since`, so a bot that keeps exiting before its first heartbeat
    is reported once instead of being restarted every five minutes."""
    now_utc = _aware(now_utc)
    boot_utc = _aware(boot_utc)
    last_heartbeat_utc = _aware(last_heartbeat_utc)
    last_restart_utc = _aware(last_restart_utc)
    if not enabled:
        return False, "watchdog disabled (operator.watchdog: false)"
    if not in_window(now_utc):
        return False, "outside the restart window (weekdays 07:00 to 15:45 ET)"
    if not agent_loaded:
        return False, f"launchd agent {BOT_LABEL} is not loaded, so the schedule was switched off"
    if process_running:
        return False, "the bot is running"
    start_today = scheduled_start_utc(now_utc)
    rebooted = boot_utc is not None and boot_utc > start_today
    since = boot_utc if rebooted else start_today
    if last_heartbeat_utc is not None and last_heartbeat_utc >= since:
        after = "the Mac booted" if rebooted else "this morning's scheduled start"
        return False, f"the bot has run since {after}, so it was stopped on purpose or finished its day"
    if last_restart_utc is not None and last_restart_utc >= since:
        return False, "already started once and the bot has written no heartbeat since; not retrying"
    if rebooted:
        booted = _et_label(boot_utc, now_utc)
        if last_heartbeat_utc is None:
            return True, f"the Mac booted at {booted} and the bot has no heartbeat on record"
        return True, f"the Mac booted at {booted} and the bot had not run since"
    missed = f"the {SCHEDULED_START:%H:%M} ET scheduled start did not run"
    if last_heartbeat_utc is None:
        return True, f"{missed} and the bot has no heartbeat on record"
    return True, f"{missed} (last heartbeat {_et_label(last_heartbeat_utc, now_utc)})"


def parse_boottime(text: str) -> datetime | None:
    """Parse `sysctl -n kern.boottime`, e.g. "{ sec = 1761683100, usec = 123456 } Wed Oct 28 16:25:00 2026"."""
    m = _BOOT_RE.search(text or "")
    if not m:
        return None
    try:
        sec = int(m.group(1))
        if sec <= 0:
            return None
        return datetime.fromtimestamp(sec, tz=timezone.utc) + timedelta(microseconds=int(m.group(2) or 0))
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------- system calls
def _run(cmd: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_S, check=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("watchdog: {} failed: {}", cmd[0], type(e).__name__)
        return None


def boot_time_utc() -> datetime | None:
    """When this Mac last booted, or None if it cannot be read (not macOS, sysctl failed)."""
    r = _run([SYSCTL, "-n", "kern.boottime"])
    if r is None or r.returncode != 0:
        return None
    return parse_boottime(r.stdout)


def bot_process_running() -> bool:
    """True if a run_bot.py process exists. On any error, True: an unknown answer must not start a second bot."""
    r = _run([PGREP, "-f", "scripts/run_bot.py"])
    if r is None:
        return True
    if r.returncode == 0:
        return True
    if r.returncode == 1:  # pgrep: no process matched
        return False
    logger.warning("watchdog: pgrep exited {}", r.returncode)
    return True


def agent_loaded(label: str) -> bool:
    """True if launchd has the agent loaded (`launchctl list <label>` succeeds). On any error, False."""
    r = _run([LAUNCHCTL, "list", label])
    return r is not None and r.returncode == 0


def kickstart(label: str) -> bool:
    """Start the launchd job. No `-k`: if the job is already running, launchctl leaves it alone."""
    r = _run([LAUNCHCTL, "kickstart", f"gui/{os.getuid()}/{label}"])
    if r is None:
        return False
    if r.returncode != 0:
        logger.warning("watchdog: launchctl kickstart exited {}: {}", r.returncode, (r.stderr or "").strip()[:200])
        return False
    return True


# ---------------------------------------------------------------- entry point
def run_watchdog(db: Database, settings: Settings, now: datetime | None = None) -> str | None:
    """One watchdog pass. Starts the bot if `decide` says so and returns a message for the owner, else None."""
    now = _aware(now) or datetime.now(timezone.utc)
    enabled = settings.operator.watchdog
    if not enabled or not in_window(now):
        return None  # decide() would say no; skip the system calls
    _, hb_ts = _heartbeat(db)
    last = db.state.get(STATE_KEY) or {}
    try:
        last_restart = datetime.fromisoformat(last["started_at"]) if last.get("started_at") else None
    except (TypeError, ValueError):
        last_restart = None
    start, reason = decide(
        now,
        boot_time_utc(),
        hb_ts,
        bot_process_running(),
        agent_loaded(BOT_LABEL),
        enabled,
        last_restart,
    )
    if not start:
        logger.debug("watchdog: no restart ({})", reason)
        return None
    ok = kickstart(BOT_LABEL)
    db.state.set(STATE_KEY, {"started_at": now.isoformat(), "ok": ok, "reason": reason})
    if ok:
        return f"{RESTARTED}: {reason}"
    return f"watchdog could not restart the bot (launchctl kickstart failed; start it by hand): {reason}"
