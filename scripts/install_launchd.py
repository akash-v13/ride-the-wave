"""Install (or remove) the macOS launchd agents that run the system unattended.

    uv run python scripts/install_launchd.py install    # writes plists to ~/Library/LaunchAgents and loads them
    uv run python scripts/install_launchd.py remove     # unloads and deletes them
    uv run python scripts/install_launchd.py status

Schedule:
  06:30 system time weekdays   run_bot.py    (waits for the open; exits at the close; restarted only on crash;
                                              also started once at load, where it waits for the next open)
  always (KeepAlive)           web/dist/server.js: the TypeScript API and web UI on http://127.0.0.1:8787
  every 5 min                  operator_tick.py: health check, then any due task by Eastern time:
                               reports 09:00 / 11:30 / 14:00 / 16:15 / 21:00 ET, nightly 20:30 ET
launchd fires calendar jobs in the timezone it booted with, which can differ from the system setting until
the next reboot; the interval design above does not care. Logs: data/logs/launchd-*.log
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[1]
AGENTS = Path.home() / "Library" / "LaunchAgents"
LABEL = "com.ridethewave"
ET = ZoneInfo("America/New_York")


def _python() -> list[str]:
    """The project virtualenv's interpreter. `uv run` is avoided on purpose: under launchd's bare
    environment it was observed to block on its own lock before ever starting Python."""
    venv = PROJECT / ".venv" / "bin" / "python"
    if venv.exists():
        return [str(venv)]
    for cand in ("/opt/homebrew/bin/uv", str(Path.home() / ".local/bin/uv")):
        if Path(cand).exists():
            return [cand, "run", "python"]
    return ["uv", "run", "python"]


def system_zone() -> ZoneInfo:
    """launchd schedules in the SYSTEM timezone (System Settings), not the shell's TZ. Read it from
    /etc/localtime; a shell TZ export (this machine has one) would otherwise silently shift every job."""
    try:
        target = os.readlink("/etc/localtime")
        name = target.split("zoneinfo/", 1)[1]
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def _local(hh: int, mm: int) -> tuple[int, int]:
    """Convert an ET wall-clock time to the system timezone for today."""
    et = datetime.now(ET).replace(hour=hh, minute=mm, second=0, microsecond=0)
    loc = et.astimezone(system_zone())
    return loc.hour, loc.minute


def _plist(
    name: str,
    args: list[str],
    calendar: list[dict] | None = None,
    interval: int | None = None,
    keepalive_on_crash: bool = False,
) -> dict:
    d: dict = {
        "Label": f"{LABEL}.{name}",
        "ProgramArguments": [*_python(), *args],
        "WorkingDirectory": str(PROJECT),
        "EnvironmentVariables": {"PATH": f"/opt/homebrew/bin:{Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin"},
        "StandardOutPath": str(PROJECT / "data" / "logs" / f"launchd-{name}.log"),
        "StandardErrorPath": str(PROJECT / "data" / "logs" / f"launchd-{name}.log"),
        "RunAtLoad": False,
    }
    if calendar:
        d["StartCalendarInterval"] = calendar
    if interval:
        d["StartInterval"] = interval
    if keepalive_on_crash:
        d["KeepAlive"] = {"SuccessfulExit": False}
    return d


def agents() -> dict[str, dict]:
    weekdays = [1, 2, 3, 4, 5]

    def cal(hh, mm):
        lh, lm = _local(hh, mm)
        return [{"Weekday": w, "Hour": lh, "Minute": lm} for w in weekdays]

    # The bot waits for the open itself, so an early calendar start is harmless even if launchd's clock is off
    # (observed: launchd kept its boot-time timezone, two hours behind the system setting). Everything else runs
    # from one interval job that checks Eastern time itself (operator_tick.py).
    out = {
        "bot": _plist("bot", ["scripts/run_bot.py"], calendar=cal(6, 30), keepalive_on_crash=True),
        "operator": _plist("operator", ["scripts/operator_tick.py"], interval=300),
        "api": _api_plist(),
    }
    return out


def _api_plist() -> dict:
    """The TypeScript API + web UI (web/), kept alive always; serves http://127.0.0.1:8787."""
    node = next((c for c in ("/opt/homebrew/bin/node", "/usr/local/bin/node") if Path(c).exists()), "node")
    return {
        "Label": f"{LABEL}.api",
        "ProgramArguments": [node, str(PROJECT / "web" / "dist" / "server.js")],
        "WorkingDirectory": str(PROJECT / "web"),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "RTW_PROJECT_ROOT": str(PROJECT),
        },
        "StandardOutPath": str(PROJECT / "data" / "logs" / "launchd-api.log"),
        "StandardErrorPath": str(PROJECT / "data" / "logs" / "launchd-api.log"),
        "RunAtLoad": True,
        "KeepAlive": True,
    }


LEGACY = ["nightly", "alerts", "report-premarket", "report-morning", "report-midday", "report-close", "report-research"]


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    AGENTS.mkdir(parents=True, exist_ok=True)
    (PROJECT / "data" / "logs").mkdir(parents=True, exist_ok=True)
    uid = os.getuid()
    if cmd == "install":
        for name in LEGACY:  # agents from the first version of the schedule
            path = AGENTS / f"{LABEL}.{name}.plist"
            if path.exists():
                subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(path)], capture_output=True)
                path.unlink()
                print(f"removed legacy {path.name}")
        for name, d in agents().items():
            path = AGENTS / f"{LABEL}.{name}.plist"
            subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(path)], capture_output=True)
            with path.open("wb") as f:
                plistlib.dump(d, f)
            r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(path)], capture_output=True, text=True)
            print(f"{'loaded' if r.returncode == 0 else 'FAILED'} {path.name} {r.stderr.strip()}")
        print(f"\nSchedule in the system timezone ({system_zone().key}); ET in brackets:")
        for name, d in agents().items():
            if "StartCalendarInterval" in d:
                c = d["StartCalendarInterval"][0]
                et = datetime.now(system_zone()).replace(hour=c["Hour"], minute=c["Minute"]).astimezone(ET)
                print(f"  {name:16s} {c['Hour']:02d}:{c['Minute']:02d} weekdays  [{et:%H:%M} ET]")
            elif "StartInterval" in d:
                print(f"  {name:16s} every {d['StartInterval'] // 60} min")
            else:
                print(f"  {name:16s} always (kept alive)")
    elif cmd == "remove":
        for name in [*agents(), *LEGACY]:
            path = AGENTS / f"{LABEL}.{name}.plist"
            subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(path)], capture_output=True)
            path.unlink(missing_ok=True)
            print(f"removed {path.name}")
    else:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        rows = [line for line in r.stdout.splitlines() if LABEL in line]
        print("\n".join(rows) if rows else "no ridethewave agents loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
