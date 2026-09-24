"""Build the list of symbols the bot watches today."""

from __future__ import annotations

import re

from alpaca.data.enums import DataFeed, MarketType, MostActivesBy
from alpaca.data.requests import MarketMoversRequest, MostActivesRequest, StockSnapshotRequest
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest
from loguru import logger

from ridethewave.clients import AlpacaClients
from ridethewave.config import UniverseSettings

# Asset names that mark ETFs, ETNs, leveraged products and commodity/crypto trusts. Cross-sectional stock
# strategies rank company stocks against each other; a 3x semiconductor ETF or a bitcoin trust in that
# ranking is noise. Matched case-insensitively on whole words.
FUND_PATTERN = re.compile(
    r"\b(etf|etn|ishares|spdr|proshares|direxion|invesco|vaneck|vanguard|schwab|wisdomtree|global x|"
    r"graniteshares|yieldmax|grayscale|fund|index|2x|3x|leveraged|bitcoin trust|ether trust|ethereum trust|"
    r"gold trust|silver trust|trust, series|united states oil|united states natural gas)\b",
    re.IGNORECASE,
)


def is_fund(name: str | None) -> bool:
    """True when an Alpaca asset name looks like a fund, ETF/ETN, leveraged product or commodity/crypto trust."""
    return bool(name) and FUND_PATTERN.search(name) is not None


class UniverseBuilder:
    def __init__(self, clients: AlpacaClients, cfg: UniverseSettings, data_feed: str = "iex"):
        self.clients = clients
        self.cfg = cfg
        self.feed = DataFeed(data_feed)
        self._assets: dict[str, object] | None = None

    # ----- candidates -----
    def candidates(self) -> list[str]:
        if self.cfg.source == "static":
            return list(self.cfg.static_symbols)
        if self.cfg.source == "most_actives":
            resp = self.clients.screener.get_most_actives(MostActivesRequest(top=self.cfg.top, by=MostActivesBy.VOLUME))
            return [m.symbol for m in resp.most_actives]
        if self.cfg.source == "movers":
            resp = self.clients.screener.get_market_movers(
                MarketMoversRequest(top=min(self.cfg.top, 50), market_type=MarketType.STOCKS)
            )
            return [m.symbol for m in resp.gainers]
        raise ValueError(self.cfg.source)

    # ----- filters -----
    def _load_assets(self) -> dict[str, object]:
        if self._assets is None:
            assets = self.clients.trading.get_all_assets(
                GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
            )
            self._assets = {a.symbol: a for a in assets}
            logger.debug("loaded {} active US equity assets", len(self._assets))
        return self._assets

    def fund_symbols(self, symbols: list[str] | None = None) -> set[str]:
        """Symbols (of the given list, or all assets) whose asset name marks them as a fund."""
        assets = self._load_assets()
        pool = symbols if symbols is not None else list(assets)
        return {s for s in pool if s in assets and is_fund(getattr(assets[s], "name", None))}

    def filter_tradable(self, symbols: list[str]) -> list[str]:
        assets = self._load_assets()
        allowed = {e.upper() for e in self.cfg.exchanges}
        keep = []
        for s in symbols:
            a = assets.get(s)
            if a is None or not a.tradable:
                continue
            exch = str(getattr(a.exchange, "value", a.exchange)).upper()
            if exch not in allowed:
                continue
            keep.append(s)
        return keep

    def filter_price(self, symbols: list[str]) -> list[str]:
        if not symbols:
            return []
        keep = []
        for i in range(0, len(symbols), 200):
            batch = symbols[i : i + 200]
            snaps = self.clients.data.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=batch, feed=self.feed))
            for s in batch:
                sn = snaps.get(s)
                if sn is None:
                    continue
                price = None
                if sn.latest_trade is not None:
                    price = float(sn.latest_trade.price)
                elif sn.daily_bar is not None:
                    price = float(sn.daily_bar.close)
                if price is None:
                    continue
                if self.cfg.min_price <= price <= self.cfg.max_price:
                    keep.append(s)
        return keep

    def build(self) -> list[str]:
        cands = self.candidates()
        tradable = self.filter_tradable(cands) if self.cfg.source != "static" else cands
        priced = self.filter_price(tradable)
        logger.info(
            "universe: {} candidates -> {} tradable -> {} in price band", len(cands), len(tradable), len(priced)
        )
        return priced
