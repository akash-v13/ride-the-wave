"""Send one test push to the phone through ntfy, and say whether ntfy accepted it.

    uv run python scripts/notify_test.py

Needs NTFY_TOPIC in .env and the ntfy phone app subscribed to the same topic. The topic is never printed: anyone
who knows it can read the alerts. Exit code 0 when ntfy accepted the message (HTTP 2xx), 1 otherwise.
"""

from __future__ import annotations

import socket
import sys

from ridethewave.config import load_secrets, load_settings
from ridethewave.operator.notify import publish


def main() -> int:
    settings = load_settings()
    server = settings.operator.ntfy_server
    try:
        topic = (load_secrets().ntfy_topic or "").strip()
    except Exception as e:  # noqa: BLE001
        # Only the type: pydantic's error text can quote values read from .env.
        print(f"could not load .env ({type(e).__name__}); check that the file exists and has the Alpaca keys")
        return 1
    if not topic:
        print("NTFY_TOPIC is not set in .env; add it (see .env.example) and run this again")
        return 1
    host = socket.gethostname()
    status = publish(
        f"Ride The Wave: test alert from {host}",
        "If you can read this on your phone, alerts from the bot will reach you.",
        topic,
        server,
        priority="high",
        tags="white_check_mark",
    )
    if status is None:
        print(f"not delivered: the request to {server} did not complete (no network, or the server is down)")
        return 1
    if 200 <= status < 300:
        print(f"delivered: {server} accepted the push (HTTP {status}). Check the phone.")
        return 0
    print(f"not delivered: {server} answered HTTP {status}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
