"""Verify the environment: settings load, secrets load, paper account reachable, data reachable.

Run: uv run python scripts/check_env.py
"""

from __future__ import annotations

import sys

from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockSnapshotRequest

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.storage import Database


def detect_data_plan(clients) -> str:
    """Basic (free) refuses SIP bars from the last 15 minutes; Algo Trader Plus serves them."""
    from datetime import datetime, timedelta, timezone

    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    now = datetime.now(timezone.utc)
    try:
        clients.data.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=["SPY"],
                timeframe=TimeFrame.Minute,
                start=now - timedelta(minutes=10),
                end=now,
                feed=DataFeed.SIP,
                limit=None,
            )
        )
        return "Algo Trader Plus (recent SIP allowed): set alpaca.data_feed: sip in settings"
    except Exception as e:  # noqa: BLE001
        if "subscription" in str(e).lower():
            return "Basic / free (recent SIP refused): keep alpaca.data_feed: iex"
        return f"could not determine ({str(e)[:80]})"


def main() -> int:
    settings = load_settings()
    print(
        f"settings ok      feed={settings.alpaca.data_feed} universe={settings.universe.source}/{settings.universe.top}"
    )
    secrets = load_secrets()
    print("secrets ok       (paper keys loaded from .env)")
    clients = make_clients(secrets, settings)

    acct = clients.trading.get_account()
    print(f"account ok       status={acct.status} equity=${float(acct.equity):,.2f} cash=${float(acct.cash):,.2f}")
    clock = clients.trading.get_clock()
    print(f"clock ok         market_open={clock.is_open} next_open={clock.next_open} next_close={clock.next_close}")

    snap = clients.data.get_stock_snapshot(
        StockSnapshotRequest(symbol_or_symbols=["SPY"], feed=DataFeed(settings.alpaca.data_feed))
    )
    spy = snap["SPY"]
    print(f"data ok          SPY last={spy.latest_trade.price} at {spy.latest_trade.timestamp}")
    print(f"data plan        {detect_data_plan(clients)}")

    db = Database(settings.storage.resolved_db_path())
    db.state.set("check_env", "ok")
    print(f"storage ok       {db.path}")
    db.close()
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
