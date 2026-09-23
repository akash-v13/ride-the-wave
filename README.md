# Ride The Wave

A momentum trading bot for Alpaca paper trading. Buys stocks on a streak of rising minutes, rides the move, sells on a pullback from the peak while keeping a minimum gain. Includes a backtester and a dashboard.

- Brief: [outline.md](outline.md)
- Running status and decisions: [CLAUDE.md](CLAUDE.md)
- Design: [docs/architecture.md](docs/architecture.md)
- Trading rules: [docs/strategy.md](docs/strategy.md)
- Machine setup: [docs/requirements.md](docs/requirements.md)

## Quick start (once the environment is set up)

```bash
uv sync
cp .env.example .env            # add paper keys
cp config/settings.example.yaml config/settings.yaml
uv run python scripts/run_bot.py          # trade (paper) during market hours
uv run python scripts/run_backtest.py --start 2026-09-08 --end 2026-09-12
uv run streamlit run src/ridethewave/ui/app.py
```

The scripts above are built in phases 2 through 7; see CLAUDE.md for what exists today.
