# Environment requirements and setup

Written for: the owner, setting up a brand-new Apple Silicon Mac (macOS 26.6, arm64) so Claude can install, run and test the bot.

## What is already on the machine (checked 2026-09-17)

| Tool | Present | Version | Usable? |
|---|---|---|---|
| Xcode Command Line Tools | yes | 2416 | yes |
| git | yes | 2.50.1 | yes |
| sqlite3 | yes | 3.51 | yes |
| python3 | yes | 3.9.6 (system) | **no**, alpaca-py needs 3.10+ |
| Homebrew | no | | needed |
| uv | no | | needed |
| Node, Docker | no | | not needed |

## Step 1: Homebrew

Open Terminal and run the official installer:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It asks for your password. When it finishes it prints two or three lines starting with `echo` and `eval` to add Homebrew to your shell. Run those, then open a new terminal and check:

```bash
brew --version
```

## Step 2: uv (Python version and package manager)

```bash
brew install uv
uv --version
```

## Step 3: Python 3.12

```bash
uv python install 3.12
```

You do not need to touch the system Python 3.9.

## Step 4: Project environment

From the project folder:

```bash
cd "/Users/akashvenkatesan/Desktop/Projects/Finance/Ride The Wave"
uv sync
```

This reads `pyproject.toml`, creates `.venv/` with Python 3.12, and installs every dependency. After that, any command runs inside the environment with `uv run`, for example `uv run pytest`.

## Step 5: Secrets

1. Copy `.env.example` to `.env`.
2. Paste the key and secret from `alpaca_key.txt` into `.env` as `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`.
3. Delete `alpaca_key.txt`. It is listed in `.gitignore` as a precaution, but the file should not exist.

Make sure the keys are **paper** keys (generated from the paper account page on app.alpaca.markets). The bot refuses to start against the live endpoint.

## Step 6: Check

```bash
uv run python -c "import alpaca; print(alpaca.__version__)"
uv run python scripts/check_env.py
```

The second command (written in phase 2) will load `.env`, call the paper account endpoint, and print your equity.

## Dependencies the project will install (via pyproject.toml)

| Package | Why |
|---|---|
| alpaca-py ≥ 0.44 | Trading, market data, screener, streams |
| pydantic, pydantic-settings | Typed config from YAML + .env |
| pyyaml | Read settings.yaml |
| pandas, numpy | Bar manipulation, backtest reports |
| streamlit | Dashboard |
| plotly | Charts in the dashboard |
| python-dotenv | Load `.env` |
| tenacity | Retry with backoff on API errors |
| loguru | Logging |
| pytest, pytest-asyncio | Tests |
| ruff | Lint/format |

No system libraries beyond what Xcode CLT provides. Everything is pure Python or ships arm64 wheels.

## Market data plan

The account is on Alpaca **Algo Trader Plus** ($99/month, subscribed 2026-09-21): full US tape, no
history hold-back, unlimited websocket symbols. `config/settings.yaml` sets `data_feed: sip`. On a
fresh machine, copy the example settings and set the feed to `sip`; on a Basic (free) account leave
it at `iex`. `uv run python scripts/check_env.py` reports which plan the keys are on.

## Optional: TypeSafe Jev (news filter, later phase)

`uv sync --group jev` installs `typesafe-sdk`. Add `TYPESAFE_API_KEY` to `.env` once the waitlist grants access. Nothing in the bot requires it.

## Optional but recommended

- `brew install gh` if the project goes on GitHub.
- Turn on "Prevent automatic sleeping when the display is off" in System Settings → Energy so the bot keeps running during market hours.
- Set the Mac's timezone normally; the bot converts everything to US/Eastern internally.
