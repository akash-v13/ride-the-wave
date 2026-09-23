"""Local notifications. macOS only; silently does nothing elsewhere or when disabled."""

from __future__ import annotations

import platform
import subprocess

from loguru import logger


def notify(title: str, message: str, enabled: bool = True) -> None:
    if not enabled or platform.system() != "Darwin":
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
