"""Factory for the Alpaca SDK clients. The only place API keys are handed to the SDK."""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.screener import ScreenerClient
from alpaca.trading.client import TradingClient

from ridethewave.config import Secrets, Settings

PAPER_HOST = "paper-api.alpaca.markets"
CONNECT_TIMEOUT, READ_TIMEOUT = 10, 30  # seconds; without these a dead connection stalls the bot for the OS's ~15 min


def with_timeouts(client, connect: float = CONNECT_TIMEOUT, read: float = READ_TIMEOUT):
    """alpaca-py sends requests without a timeout (verified 0.44, alpaca/common/rest.py). Wrap the client's
    session so every call carries one unless the caller set its own. Returns the client."""
    session = getattr(client, "_session", None)
    if session is None or getattr(session, "_rtw_timeouts", False):
        return client
    original = session.request

    def request(method, url, **kwargs):
        kwargs.setdefault("timeout", (connect, read))
        return original(method, url, **kwargs)

    session.request = request
    session._rtw_timeouts = True
    return client


@dataclass(slots=True)
class AlpacaClients:
    trading: TradingClient
    data: StockHistoricalDataClient
    screener: ScreenerClient
    options: OptionHistoricalDataClient


def make_clients(secrets: Secrets, settings: Settings) -> AlpacaClients:
    if not (settings.alpaca.paper and secrets.alpaca_paper):
        raise RuntimeError("Refusing to create clients: paper trading is the only supported mode")
    trading = TradingClient(secrets.alpaca_api_key, secrets.alpaca_secret_key, paper=True)
    # Belt and braces: verify the SDK really targets the paper host.
    raw = getattr(trading, "_base_url", "")
    base = str(getattr(raw, "value", raw) or "")
    if base and PAPER_HOST not in base:
        raise RuntimeError(f"TradingClient base URL is not the paper host: {base}")
    data = StockHistoricalDataClient(secrets.alpaca_api_key, secrets.alpaca_secret_key)
    screener = ScreenerClient(secrets.alpaca_api_key, secrets.alpaca_secret_key)
    options = OptionHistoricalDataClient(secrets.alpaca_api_key, secrets.alpaca_secret_key)
    for c in (trading, data, screener, options):
        with_timeouts(c)
    return AlpacaClients(trading=trading, data=data, screener=screener, options=options)
