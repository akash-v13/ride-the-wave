"""Factory for the Alpaca SDK clients. The only place API keys are handed to the SDK."""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.screener import ScreenerClient
from alpaca.trading.client import TradingClient

from ridethewave.config import Secrets, Settings

PAPER_HOST = "paper-api.alpaca.markets"


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
    return AlpacaClients(trading=trading, data=data, screener=screener, options=options)
