"""Option chain snapshots and quotes from Alpaca's options data API (OPRA on Algo Trader Plus).

Verified 2026-09-23: the paper account is options level 3, ``get_option_chain`` on the OPRA feed
returns quotes, implied volatility and greeks per contract. Our own Black-Scholes fills in greeks
when the feed omits them. See docs/api/options.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from alpaca.data.enums import OptionsFeed
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, OptionLatestQuoteRequest
from loguru import logger

from ridethewave.options.greeks import bs_greeks, implied_vol

# OCC symbol: ROOT + YYMMDD + C/P + strike*1000 (8 digits), e.g. SPY261016P00708000
OCC_RE = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")


def is_option_symbol(symbol: str) -> bool:
    return bool(OCC_RE.match(symbol))


def parse_occ(symbol: str) -> tuple[str, date, str, float]:
    """(underlying, expiry, 'C' | 'P', strike)."""
    m = OCC_RE.match(symbol)
    if not m:
        raise ValueError(f"not an OCC option symbol: {symbol}")
    root, ymd, right, strike = m.groups()
    return root, datetime.strptime(ymd, "%y%m%d").date(), right, int(strike) / 1000.0


@dataclass
class OptionContract:
    symbol: str  # OCC
    underlying: str
    expiry: date
    right: str  # "C" | "P"
    strike: float
    bid: float
    ask: float
    delta: float | None
    iv: float | None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.bid or self.ask


@dataclass
class ChainSnapshot:
    underlying: str
    spot: float
    ts: datetime
    contracts: list[OptionContract]

    @property
    def today(self) -> date:
        return self.ts.date()

    def expiries(self) -> list[date]:
        return sorted({c.expiry for c in self.contracts})

    def slice(self, expiry: date, right: str) -> list[OptionContract]:
        return sorted((c for c in self.contracts if c.expiry == expiry and c.right == right), key=lambda c: c.strike)

    def atm_iv(self, n: int = 6) -> float | None:
        """Mean implied volatility of the ``n`` contracts nearest the spot (both rights, all expiries)."""
        with_iv = [c for c in self.contracts if c.iv]
        if not with_iv:
            return None
        nearest = sorted(with_iv, key=lambda c: abs(c.strike - self.spot))[:n]
        return sum(c.iv for c in nearest) / len(nearest)


class OptionsChainService:
    def __init__(self, client: OptionHistoricalDataClient, feed: str = "opra"):
        self.client = client
        self.feed = OptionsFeed(feed)
        self.calls = 0

    def snapshot(
        self,
        underlying: str,
        spot: float,
        dte_min: int = 20,
        dte_max: int = 50,
        strike_band_pct: float = 0.12,
        today: date | None = None,
    ) -> ChainSnapshot:
        """The chain around the money for a DTE window. One API call."""
        today = today or datetime.now(timezone.utc).date()
        req = OptionChainRequest(
            underlying_symbol=underlying,
            feed=self.feed,
            expiration_date_gte=today + timedelta(days=dte_min),
            expiration_date_lte=today + timedelta(days=dte_max),
            strike_price_gte=round(spot * (1 - strike_band_pct), 2),
            strike_price_lte=round(spot * (1 + strike_band_pct), 2),
        )
        self.calls += 1
        raw = self.client.get_option_chain(req)
        contracts: list[OptionContract] = []
        for symbol, snap in raw.items():
            try:
                _, expiry, right, strike = parse_occ(symbol)
            except ValueError:
                continue
            quote = snap.latest_quote
            if quote is None:
                continue
            bid, ask = float(quote.bid_price or 0), float(quote.ask_price or 0)
            greeks = getattr(snap, "greeks", None)
            delta = float(greeks.delta) if greeks is not None and greeks.delta is not None else None
            iv = float(snap.implied_volatility) if getattr(snap, "implied_volatility", None) else None
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else (bid or ask)
            if delta is None and mid > 0:
                t_years = max((expiry - today).days / 365.0, 1e-4)
                iv = iv or implied_vol(mid, spot, strike, t_years, right == "C")
                if iv:
                    delta = bs_greeks(spot, strike, t_years, iv, right == "C").delta
            contracts.append(OptionContract(symbol, underlying, expiry, right, strike, bid, ask, delta, iv))
        logger.debug(
            "chain {}: {} contracts, {}-{} dte, {} feed", underlying, len(contracts), dte_min, dte_max, self.feed.value
        )
        return ChainSnapshot(underlying=underlying, spot=spot, ts=datetime.now(timezone.utc), contracts=contracts)

    def quotes(self, symbols: list[str]) -> dict[str, tuple[float, float]]:
        """(bid, ask) per OCC symbol, one call for the whole list."""
        if not symbols:
            return {}
        self.calls += 1
        raw = self.client.get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=symbols, feed=self.feed))
        return {s: (float(q.bid_price or 0), float(q.ask_price or 0)) for s, q in raw.items()}
