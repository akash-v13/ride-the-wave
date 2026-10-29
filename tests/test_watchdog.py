"""Watchdog: start the bot after a reboot in trading hours or a missed morning start, never after a deliberate stop.
No real launchctl."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from ridethewave.config import Settings
from ridethewave.operator import watchdog as wd

ET = ZoneInfo("America/New_York")


def et(h, m, day=28):  # 2026-10-28 is a Wednesday
    return datetime(2026, 10, day, h, m, tzinfo=ET).astimezone(timezone.utc)


NOW = et(10, 47)
BOOT = et(10, 42)


def call(**kw):
    args = dict(
        now_utc=NOW,
        boot_utc=BOOT,
        last_heartbeat_utc=BOOT - timedelta(minutes=10),  # the bot ran before the reboot
        process_running=False,
        agent_loaded=True,
        enabled=True,
    )
    args.update(kw)
    return wd.decide(**args)


# ---------------------------------------------------------------- decide()
def test_reboot_in_window_starts_the_bot():
    start, reason = call()
    assert start
    assert reason == "the Mac booted at 10:42 ET and the bot had not run since"


def test_heartbeat_after_boot_means_stopped_on_purpose():
    assert call(last_heartbeat_utc=BOOT + timedelta(minutes=1))[0] is False


def test_process_running():
    assert call(process_running=True)[0] is False


def test_agent_not_loaded():
    assert call(agent_loaded=False)[0] is False


def test_weekend():
    sat = et(10, 47, day=31)
    assert sat.astimezone(ET).weekday() == 5
    assert call(now_utc=sat, boot_utc=sat - timedelta(minutes=5))[0] is False


def test_after_window():
    assert call(now_utc=et(15, 50))[0] is False
    assert call(now_utc=et(15, 45))[0] is False
    assert call(now_utc=et(15, 44))[0] is True


def test_before_window():
    hb = et(15, 59, day=27)  # yesterday's last tick
    assert call(now_utc=et(6, 0), boot_utc=et(5, 50), last_heartbeat_utc=hb)[0] is False
    assert call(now_utc=et(7, 0), boot_utc=et(5, 50), last_heartbeat_utc=hb)[0] is True


def test_disabled():
    assert call(enabled=False)[0] is False


def test_no_heartbeat_ever_starts():
    start, reason = call(last_heartbeat_utc=None)
    assert start and "no heartbeat" in reason


def test_unknown_boot_time_still_catches_a_missed_morning_start():
    # the bot ran this morning before the (unreadable) boot: a reboot cannot be detected, so no start
    assert call(boot_utc=None)[0] is False
    # but a bot that has not run since 06:30 ET is caught without the boot time
    start, reason = call(boot_utc=None, last_heartbeat_utc=et(15, 59, day=27))
    assert start and reason.startswith("the 06:30 ET scheduled start did not run")


def test_one_attempt_per_boot():
    assert call(last_restart_utc=NOW - timedelta(minutes=5))[0] is False
    # an attempt before this boot does not count
    assert call(last_restart_utc=BOOT - timedelta(hours=3))[0] is True


# ---------------------------------------------------------------- missed morning start (added 2026-10-29)
OLD_BOOT = et(19, 26, day=27)  # booted the evening before, as the Mac mini did on 2026-10-28
YESTERDAY_CLOSE = et(16, 0, day=27)


def test_missed_morning_start_starts_the_bot():
    start, reason = call(now_utc=et(7, 0), boot_utc=OLD_BOOT, last_heartbeat_utc=YESTERDAY_CLOSE)
    assert start
    assert reason == "the 06:30 ET scheduled start did not run (last heartbeat Tue 27 Oct 16:00 ET)"


def test_missed_morning_start_with_no_heartbeat_ever():
    start, reason = call(now_utc=et(9, 0), boot_utc=OLD_BOOT, last_heartbeat_utc=None)
    assert start and reason == "the 06:30 ET scheduled start did not run and the bot has no heartbeat on record"


def test_morning_start_ran_then_stopped_by_hand_stays_stopped():
    start, reason = call(now_utc=et(11, 0), boot_utc=OLD_BOOT, last_heartbeat_utc=et(10, 15))
    assert start is False and "since this morning's scheduled start" in reason
    # a bot started the evening before and waiting overnight counts as having run (it heartbeats while waiting)
    assert call(now_utc=et(7, 0), boot_utc=OLD_BOOT, last_heartbeat_utc=et(6, 59))[0] is False


def test_missed_morning_start_gets_one_attempt():
    kw = dict(now_utc=et(7, 30), boot_utc=OLD_BOOT, last_heartbeat_utc=YESTERDAY_CLOSE)
    assert call(**kw, last_restart_utc=et(7, 0))[0] is False
    # yesterday's attempt does not count against today
    assert call(**kw, last_restart_utc=et(7, 0, day=27))[0] is True


def test_scheduled_start_follows_eastern_time_across_the_clock_change():
    # 06:30 ET is 10:30 UTC in daylight time and 11:30 UTC after the change on Sunday 1 November 2026
    assert wd.scheduled_start_utc(et(9, 0, day=30)) == datetime(2026, 10, 30, 10, 30, tzinfo=timezone.utc)
    nov2 = datetime(2026, 11, 2, 9, 0, tzinfo=ET).astimezone(timezone.utc)
    assert wd.scheduled_start_utc(nov2) == datetime(2026, 11, 2, 11, 30, tzinfo=timezone.utc)


def test_naive_timestamps_are_treated_as_utc():
    naive = (BOOT + timedelta(minutes=1)).replace(tzinfo=None)
    assert call(last_heartbeat_utc=naive)[0] is False


# ---------------------------------------------------------------- boot time parser
def test_parse_boottime():
    out = "{ sec = 1761683100, usec = 123456 } Tue Oct 28 16:25:00 2025\n"
    assert wd.parse_boottime(out) == datetime(2025, 10, 28, 20, 25, 0, 123456, tzinfo=timezone.utc)


def test_parse_boottime_without_usec_and_garbage():
    assert wd.parse_boottime("{ sec = 1761683100 }") == datetime.fromtimestamp(1761683100, tz=timezone.utc)
    assert wd.parse_boottime("") is None
    assert wd.parse_boottime("sysctl: unknown oid 'kern.boottime'") is None
    assert wd.parse_boottime("{ usec = 5 }") is None  # "usec" alone must not be read as the seconds
    assert wd.parse_boottime("{ sec = 0, usec = 0 }") is None


# ---------------------------------------------------------------- run_watchdog()
@pytest.fixture
def fake_system(monkeypatch):
    """Replace every system call. `calls` counts kickstarts."""
    sys_state = {"boot": BOOT, "running": False, "loaded": True, "kick_ok": True, "kicks": []}
    monkeypatch.setattr(wd, "boot_time_utc", lambda: sys_state["boot"])
    monkeypatch.setattr(wd, "bot_process_running", lambda: sys_state["running"])
    monkeypatch.setattr(wd, "agent_loaded", lambda label: sys_state["loaded"])

    def kick(label):
        sys_state["kicks"].append(label)
        return sys_state["kick_ok"]

    monkeypatch.setattr(wd, "kickstart", kick)
    return sys_state


def _heartbeat(db, ts):
    db.state.set("heartbeat", {"ts": ts.isoformat(), "tick": 12})


def test_run_watchdog_kickstarts_once_when_due(db, fake_system):
    _heartbeat(db, BOOT - timedelta(minutes=10))
    msg = wd.run_watchdog(db, Settings(), now=NOW)
    assert msg == "bot restarted by watchdog: the Mac booted at 10:42 ET and the bot had not run since"
    assert fake_system["kicks"] == ["com.ridethewave.bot"]
    assert db.state.get("watchdog")["ok"] is True
    # five minutes later the bot has not written a heartbeat yet: no second attempt
    assert wd.run_watchdog(db, Settings(), now=NOW + timedelta(minutes=5)) is None
    assert len(fake_system["kicks"]) == 1


def test_run_watchdog_never_kicks_when_not_due(db, fake_system):
    _heartbeat(db, BOOT + timedelta(minutes=2))  # bot ran after the boot, then was stopped by hand
    assert wd.run_watchdog(db, Settings(), now=NOW) is None
    fake_system["running"] = True
    _heartbeat(db, BOOT - timedelta(minutes=10))
    assert wd.run_watchdog(db, Settings(), now=NOW) is None
    fake_system["running"] = False
    fake_system["loaded"] = False
    assert wd.run_watchdog(db, Settings(), now=NOW) is None
    fake_system["loaded"] = True
    assert wd.run_watchdog(db, Settings(), now=et(16, 30)) is None
    off = Settings.model_validate({"operator": {"watchdog": False}})
    assert wd.run_watchdog(db, off, now=NOW) is None
    assert fake_system["kicks"] == []


def test_run_watchdog_covers_a_missed_morning_start(db, fake_system):
    fake_system["boot"] = OLD_BOOT
    _heartbeat(db, YESTERDAY_CLOSE)
    msg = wd.run_watchdog(db, Settings(), now=et(7, 0))
    assert (
        msg
        == "bot restarted by watchdog: the 06:30 ET scheduled start did not run (last heartbeat Tue 27 Oct 16:00 ET)"
    )
    assert fake_system["kicks"] == ["com.ridethewave.bot"]
    assert wd.run_watchdog(db, Settings(), now=et(7, 5)) is None  # one attempt; from 09:30 the stale alert fires
    assert len(fake_system["kicks"]) == 1


def test_run_watchdog_reports_a_failed_kickstart(db, fake_system):
    fake_system["kick_ok"] = False
    msg = wd.run_watchdog(db, Settings(), now=NOW)
    assert msg is not None and not msg.startswith(wd.RESTARTED) and "kickstart failed" in msg
    assert fake_system["kicks"] == ["com.ridethewave.bot"]


# ---------------------------------------------------------------- system-call helpers never raise
def test_helpers_fail_safe(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("no such tool")

    monkeypatch.setattr(wd.subprocess, "run", boom)
    assert wd.boot_time_utc() is None
    assert wd.bot_process_running() is True  # unknown -> do not start a second bot
    assert wd.agent_loaded("x") is False
    assert wd.kickstart("x") is False


@pytest.mark.parametrize(("code", "running"), [(0, True), (1, False), (2, True)])
def test_pgrep_exit_codes(monkeypatch, code, running):
    class R:
        returncode = code
        stdout = stderr = ""

    monkeypatch.setattr(wd.subprocess, "run", lambda cmd, **k: R())
    assert wd.bot_process_running() is running


def test_kickstart_never_uses_kill_flag(monkeypatch):
    seen = []

    class R:
        returncode = 0
        stdout = stderr = ""

    def fake_run(cmd, **k):
        seen.append(cmd)
        return R()

    monkeypatch.setattr(wd.subprocess, "run", fake_run)
    assert wd.kickstart("com.ridethewave.bot") is True
    assert seen[0][:2] == ["/bin/launchctl", "kickstart"] and "-k" not in seen[0]
    assert seen[0][2].endswith("/com.ridethewave.bot") and seen[0][2].startswith("gui/")


def test_system_commands_use_full_paths(monkeypatch):
    """The launch agents' PATH has no /usr/sbin; a bare "sysctl" was not found on the Mac mini (2026-10-29)."""
    calls = []

    class R:
        returncode, stdout, stderr = 0, "{ sec = 1761683100, usec = 0 } Wed Oct 28 19:25:00 2026", ""

    monkeypatch.setattr(wd.subprocess, "run", lambda argv, **kw: calls.append(argv) or R())
    wd.boot_time_utc()
    wd.bot_process_running()
    wd.agent_loaded(wd.BOT_LABEL)
    wd.kickstart(wd.BOT_LABEL)
    assert [c[0] for c in calls] == ["/usr/sbin/sysctl", "/usr/bin/pgrep", "/bin/launchctl", "/bin/launchctl"]
    assert "-k" not in calls[-1]  # kickstart never kills a running bot
