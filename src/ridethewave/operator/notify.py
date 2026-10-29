"""Notifications: a macOS banner on this machine, and a push to the owner's phone through ntfy.

Why both: the banner is only seen by someone sitting at the Mac. Once the system runs on a Mac mini that nobody
looks at, alerts must reach a phone. ntfy (https://ntfy.sh) is a free push service: the ntfy phone app subscribes to
a topic name, and anything POSTed to https://ntfy.sh/<topic> shows up as a notification. There is no account, so the
topic name is the only protection: it is kept in .env (NTFY_TOPIC) and never logged or printed.

Nothing here raises. A failed notification is logged and the caller carries on; an alert must never break the
health check or a report.
"""

from __future__ import annotations

import base64
import platform
import subprocess

import requests
from loguru import logger

DEFAULT_NTFY_SERVER = "https://ntfy.sh"
NTFY_TIMEOUT_S = 10
_MAX_BODY_CHARS = 3500  # ntfy turns a body over 4,096 bytes into a file attachment; stay well under


def ntfy_topic() -> str | None:
    """The ntfy topic from .env, or None when it is not set or .env cannot be loaded.

    The exception text is never logged: pydantic's validation errors can quote the values they read from .env."""
    try:
        from ridethewave.config import load_secrets

        return (load_secrets().ntfy_topic or "").strip() or None
    except Exception as e:  # noqa: BLE001
        logger.warning("could not load .env for phone alerts ({}); sending none", type(e).__name__)
        return None


def _header_value(text: str) -> str:
    """One-line header value. Non-ASCII text (an emoji, an accented name) is sent as an RFC 2047 encoded word,
    which ntfy decodes; `requests` would otherwise fail on any character outside Latin-1."""
    text = " ".join(text.split())
    if text.isascii():
        return text
    return "=?UTF-8?B?" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "?="


def publish(
    title: str,
    message: str,
    topic: str,
    server: str = DEFAULT_NTFY_SERVER,
    priority: str = "high",
    tags: str | None = "warning",
) -> int | None:
    """POST one message to ntfy. Returns the HTTP status, or None when the request did not complete.

    Headers per https://docs.ntfy.sh/publish/ (checked 2026-10-28): Title, Priority (min, low, default, high,
    urgent, or 1 to 5), Tags (comma-separated; names of emoji like `warning` show as icons)."""
    headers = {"Title": _header_value(title), "Priority": priority}
    if tags:
        headers["Tags"] = tags
    url = f"{server.rstrip('/')}/{topic}"
    try:
        r = requests.post(url, data=message[:_MAX_BODY_CHARS].encode("utf-8"), headers=headers, timeout=NTFY_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001
        # Only the exception's type: its text contains the URL, and the URL contains the topic.
        logger.warning("ntfy push failed: {}", type(e).__name__)
        return None
    if not 200 <= r.status_code < 300:
        logger.warning("ntfy push rejected: HTTP {}", r.status_code)
    return r.status_code


def push(
    title: str,
    message: str,
    topic: str | None,
    server: str = DEFAULT_NTFY_SERVER,
    priority: str = "high",
    tags: str | None = "warning",
) -> bool:
    """Send a phone push. True only when ntfy accepted it (HTTP 2xx). Never raises."""
    if not topic:
        return False
    status = publish(title, message, topic, server, priority=priority, tags=tags)
    return status is not None and 200 <= status < 300


def _desktop(title: str, message: str) -> None:
    """macOS banner; does nothing on other systems."""
    if platform.system() != "Darwin":
        return
    safe_title = title.replace('"', "'")
    safe_msg = message.replace('"', "'")[:200]
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"'],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("notification failed: {}", e)


def notify(
    title: str,
    message: str,
    enabled: bool = True,
    *,
    topic: str | None = None,
    server: str = DEFAULT_NTFY_SERVER,
    priority: str = "high",
    tags: str | None = "warning",
) -> None:
    """The macOS banner as before, plus a phone push when a topic is given. `enabled` (settings.operator.notify)
    switches both off."""
    if not enabled:
        return
    _desktop(title, message)
    if topic:
        push(title, message, topic, server, priority=priority, tags=tags)
