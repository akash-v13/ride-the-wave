"""Factory for the Alpaca SDK clients. The only place API keys are handed to the SDK."""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.screener import ScreenerClient
from alpaca.trading.client import TradingClient
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ridethewave.config import Secrets, Settings

PAPER_HOST = "paper-api.alpaca.markets"
CONNECT_TIMEOUT, READ_TIMEOUT = 10, 30  # seconds; without these a dead connection stalls the bot for the OS's ~15 min
RETRY_ATTEMPTS = 4  # per request, on a failed connection; read-only requests also on a dropped response
RETRY_BACKOFF = 1.0  # seconds; urllib3 waits 0, 2, 4, 8 s between attempts (capped at RETRY_BACKOFF_MAX)
RETRY_BACKOFF_MAX = 10.0


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


def with_retries(client, attempts: int = RETRY_ATTEMPTS, backoff: float = RETRY_BACKOFF):
    """Retry a request whose connection fails or is dropped, instead of failing the call.

    Why: the Mac sleeps and wakes during a session. After a wake the pooled keep-alive connection is dead,
    and the first call on it fails with "Remote end closed connection without response". In October 2026
    that one failure emptied the day's universe, again and again. alpaca-py only retries HTTP 429 and 504;
    requests itself retries nothing.

    What is retried:
    - a connection that could not be opened, for every method (the request never left the machine);
    - a response that never arrived, for GET and HEAD only. A POST that may already have reached Alpaca,
      such as an order, is never sent twice.
    HTTP status codes are not retried here; alpaca-py keeps handling 429 and 504 itself. Returns the client.
    """
    session = getattr(client, "_session", None)
    if session is None or not hasattr(session, "mount") or getattr(session, "_rtw_retries", False):
        return client
    retry = Retry(
        total=attempts,
        connect=attempts,
        read=2,
        status=0,
        other=0,
        allowed_methods=frozenset({"GET", "HEAD"}),
        backoff_factor=backoff,
        backoff_max=RETRY_BACKOFF_MAX,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session._rtw_retries = True
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
        with_retries(c)
    return AlpacaClients(trading=trading, data=data, screener=screener, options=options)
