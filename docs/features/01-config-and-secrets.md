# 01 · Configuration and secrets

**What it does.** All tunable numbers live in one YAML file, `config/settings.yaml`. API keys live in `.env`. Both are checked when the bot starts, so a typo or a missing key fails immediately with a clear message instead of halfway through a trading day.

**How to use it.**
- Copy `config/settings.example.yaml` to `config/settings.yaml` and edit. If `settings.yaml` does not exist the example is used.
- `.env` holds `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` and `ALPACA_PAPER=true`.
- Every parameter is explained in [docs/strategy.md](../strategy.md).

**Safety rails.** `alpaca.paper` must be `true` and `ALPACA_PAPER` must be `true`. The code refuses to build a client against the live endpoint, and double-checks the SDK's base URL is the paper host.

**Unknown keys are errors.** If you misspell `green_streak_minutes` the bot will not silently use the default; it stops and tells you the key it did not recognise.

**Code:** `src/ridethewave/config.py`, `src/ridethewave/clients.py`.
