"""Point-in-time universe: which stocks would the bot have watched on a past day?

Using today's most-active list for last month's backtest is cheating: we did not know those names
then. Instead, for each backtest day, rank every tradable US stock by its average daily dollar
volume over the previous ``lookback`` sessions and take the top N inside the price band. Only data
available before that day's open is used.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest
from loguru import logger

from ridethewave.clients import AlpacaClients
from ridethewave.config import UniverseSettings
from ridethewave.data.market_data import DailyBars
from ridethewave.data.universe import is_fund
from ridethewave.storage import Database


class PointInTimeUniverse:
    def __init__(self, clients: AlpacaClients, db: Database | None, cfg: UniverseSettings, lookback: int = 20):
        self.clients = clients
        self.cfg = cfg
        self.lookback = lookback
        self.daily = DailyBars(clients.data, db)
        self._pool: list[str] | None = None
        self._funds: set[str] = set()
        self._frame: pd.DataFrame | None = None
        self._loaded: tuple[date, date] | None = None

    def pool(self) -> list[str]:
        """Active, tradable US equities on the configured exchanges. Note: today's asset list, so
        symbols that were delisted before today are missing (survivorship bias, documented)."""
        if self._pool is None:
            assets = self.clients.trading.get_all_assets(
                GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
            )
            allowed = {e.upper() for e in self.cfg.exchanges}
            self._pool = sorted(
                a.symbol
                for a in assets
                if a.tradable
                and str(getattr(a.exchange, "value", a.exchange)).upper() in allowed
                and a.symbol.isalpha()  # skip warrants/units/preferreds with . or / in the symbol
            )
            self._funds = {a.symbol for a in assets if is_fund(getattr(a, "name", None))}
            logger.info("point-in-time pool: {} symbols", len(self._pool))
        return self._pool

    def preload(self, start: date, end: date) -> None:
        """Fetch daily bars for the pool covering [start - lookback*2 calendar days, end]."""
        lo = start - timedelta(days=self.lookback * 2 + 5)
        bars = self.daily.fetch(self.pool(), lo, end)
        self._frame = pd.DataFrame(
            [(b.symbol, b.ts.date(), b.close, b.volume) for b in bars], columns=["symbol", "day", "close", "volume"]
        )
        self._frame["dollar_volume"] = self._frame["close"] * self._frame["volume"]
        self._loaded = (lo, end)
        logger.info(
            "point-in-time daily bars: {} rows, {} symbols, {} API calls",
            len(self._frame),
            self._frame["symbol"].nunique(),
            self.daily.calls,
        )

    def fund_symbols(self) -> set[str]:
        self.pool()
        return set(self._funds)

    def universe_for(self, day: date, top: int | None = None, exclude_funds: bool = False) -> list[str]:
        """Top ``top`` names by trailing dollar volume; with ``exclude_funds`` the top ``top`` company stocks."""
        top = top or self.cfg.top
        if self._frame is None or self._loaded is None or not (self._loaded[0] <= day <= self._loaded[1]):
            self.preload(day, day)
        df = self._frame[self._frame["day"] < day]
        # last `lookback` sessions before `day`
        sessions = sorted(df["day"].unique())[-self.lookback :]
        if len(sessions) < max(5, self.lookback // 2):
            logger.warning("{}: only {} prior sessions loaded", day, len(sessions))
        win = df[df["day"].isin(sessions)]
        g = win.groupby("symbol")
        stats = pd.DataFrame(
            {
                "avg_dv": g["dollar_volume"].mean(),
                "n": g["day"].count(),
                "last_close": g.apply(lambda x: x.sort_values("day")["close"].iloc[-1], include_groups=False),
            }
        )
        stats = stats[
            (stats["n"] >= len(sessions) - 2)
            & (stats["last_close"] >= self.cfg.min_price)
            & (stats["last_close"] <= self.cfg.max_price)
        ]
        if exclude_funds:
            funds = self.fund_symbols()
            stats = stats[~stats.index.isin(funds)]
        chosen = stats.sort_values("avg_dv", ascending=False).head(top).index.tolist()
        return chosen
