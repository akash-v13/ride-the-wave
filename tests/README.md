# tests

pytest suites, mirrored on the package layout (`tests/strategy/`, `tests/execution/`, ...).

Rules:
- Strategy tests use hand-built bar lists and assert exact signals. No network.
- Execution tests use a fake `Broker`. No network.
- Anything that talks to Alpaca lives under `tests/integration/` and is skipped unless `RTW_INTEGRATION=1` is set, because it needs paper keys and market data.

Run: `uv run pytest`
