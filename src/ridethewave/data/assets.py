"""Alpaca's asset list, read without the SDK's strict models.

alpaca-py checks every asset's ``exchange`` against a fixed list of exchange codes. When Alpaca starts
sending a code the installed SDK does not know, the whole list fails to load, not just that one row. On
2026-10-20 Alpaca began listing stocks on the Texas Stock Exchange (code ``TXSE``). alpaca-py 0.44.0, the
latest release at the time, rejected it, and every universe build failed for six sessions.

This module asks the same endpoint for the raw JSON and reads it field by field. An unknown exchange code
is kept as plain text, so the exchange filter treats it like any other code it was not told to allow. A
malformed row is skipped and counted, so it cannot sink the other 14,000 rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.enums import AssetExchange
from loguru import logger

KNOWN_EXCHANGES = frozenset(e.value for e in AssetExchange)  # what the installed SDK would accept


@dataclass(frozen=True, slots=True)
class AssetInfo:
    """One row of Alpaca's /v2/assets list, with plain-text codes."""

    symbol: str
    name: str | None
    exchange: str  # upper case as Alpaca sends it, e.g. "NASDAQ", "NYSE", "TXSE"
    status: str  # "active" or "inactive"
    asset_class: str  # "us_equity", "us_option", "crypto"
    tradable: bool
    marginable: bool
    shortable: bool
    easy_to_borrow: bool
    fractionable: bool

    @classmethod
    def from_raw(cls, row: dict) -> AssetInfo:
        symbol = row["symbol"]
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("asset row without a symbol")
        return cls(
            symbol=symbol,
            name=row.get("name") or None,
            exchange=str(row.get("exchange") or "").upper(),
            status=str(row.get("status") or "").lower(),
            asset_class=str(row.get("class") or row.get("asset_class") or "").lower(),
            tradable=bool(row.get("tradable", False)),
            marginable=bool(row.get("marginable", False)),
            shortable=bool(row.get("shortable", False)),
            easy_to_borrow=bool(row.get("easy_to_borrow", False)),
            fractionable=bool(row.get("fractionable", False)),
        )


def parse_assets(raw) -> list[AssetInfo]:
    """Turn the raw JSON list into AssetInfo rows, skipping (and counting) rows that cannot be read."""
    if not isinstance(raw, list):
        raise ValueError(f"unexpected /assets response: {type(raw).__name__}")
    out: list[AssetInfo] = []
    bad = 0
    for row in raw:
        try:
            out.append(AssetInfo.from_raw(row))
        except (KeyError, TypeError, ValueError, AttributeError):
            bad += 1
    if bad:
        logger.warning("assets: skipped {} malformed rows of {}", bad, len(raw))
    unknown = sorted({a.exchange for a in out if a.exchange} - KNOWN_EXCHANGES)
    if unknown:
        logger.debug("assets: exchange codes the SDK does not know, kept as text: {}", ", ".join(unknown))
    return out


def fetch_assets(trading, status: str = "active", asset_class: str = "us_equity") -> list[AssetInfo]:
    """GET /v2/assets through the SDK client, so its keys, paper host, timeouts and retries all apply,
    but without the SDK's strict parsing. ``status`` is "active" or "inactive"."""
    raw = trading.get("/assets", {"status": status, "asset_class": asset_class})
    return parse_assets(raw)
