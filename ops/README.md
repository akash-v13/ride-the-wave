# ops

Operational glue that is not Python package code.

- `launchd/`: nothing checked in; `scripts/install_launchd.py` generates the agent plists into
  `~/Library/LaunchAgents/com.ridethewave.*.plist` and loads them. `remove` unloads and deletes.
