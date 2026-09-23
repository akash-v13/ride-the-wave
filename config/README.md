# config

Strategy and runtime settings as YAML. `settings.example.yaml` is committed; copy it to `settings.yaml` (gitignored) and edit. Secrets never go here; they live in `.env` at the project root.

Loaded by `ridethewave.config.Settings` (phase 2), validated with pydantic so a typo fails at startup rather than mid-trade.

`profiles/` keeps every previous parameter set as a complete, runnable settings file, so old behaviour can be re-run for comparison. Never edit a profile; add a new one.
