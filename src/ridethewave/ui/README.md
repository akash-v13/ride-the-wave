# ui

Streamlit dashboard, read-only view of the SQLite database. Runs as its own process.

- `app.py`: page layout: header (equity, cash, allocation, bot heartbeat), open positions table (symbol, qty, entry, current, peak, exit trigger, unrealized P/L and %, time held), today's closed trades, daily ledger, equity chart.
- `queries.py`: the SQL the pages use.

Launch: `uv run streamlit run src/ridethewave/ui/app.py`
