"""Fetching prices from Alpaca: live snapshots and historical bars (with SQLite caching)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from ridethewave.models import Bar, Tick
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")


def regular_session_utc(day: date) -> tuple[datetime, datetime]:
    """[09:30, 16:00) ET for a calendar day, as UTC. The replay engine, cache and downloader all use this."""
    start = datetime.combine(day, datetime.min.time(), ET).replace(hour=9, minute=30)
    end = datetime.combine(day, datetime.min.time(), ET).replace(hour=16, minute=0)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


SNAPSHOT_BATCH = 200
BARS_SYMBOL_BATCH = 100


def _to_bar(symbol: str, b) -> Bar:
    return Bar(
        symbol=symbol,
        ts=b.timestamp.astimezone(timezone.utc),
        open=float(b.open),
        high=float(b.high),
        low=float(b.low),
        close=float(b.close),
        volume=int(b.volume),
        trade_count=int(b.trade_count or 0),
        vwap=float(b.vwap or 0.0),
    )


@dataclass(slots=True)
class SnapshotResult:
    tick: Tick
    minute_bar: Bar | None
    daily_bar: Bar | None
    prev_daily_bar: Bar | None


class SnapshotPoller:
    """One call per 200 symbols, returns the latest trade + minute bar for each."""

    def __init__(self, client: StockHistoricalDataClient, feed: str = "iex"):
        self.client = client
        self.feed = DataFeed(feed)
        self.calls = 0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=8), reraise=True)
    def _fetch(self, symbols: list[str]):
        self.calls += 1
        return self.client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=symbols, feed=self.feed))

    def poll(self, symbols: Iterable[str]) -> dict[str, SnapshotResult]:
        symbols = list(symbols)
        out: dict[str, SnapshotResult] = {}
        for i in range(0, len(symbols), SNAPSHOT_BATCH):
            batch = symbols[i : i + SNAPSHOT_BATCH]
            try:
                snaps = self._fetch(batch)
            except Exception as e:  # noqa: BLE001
                logger.warning("snapshot batch failed ({} symbols): {}", len(batch), e)
                continue
            for sym, sn in snaps.items():
                if sn is None or sn.latest_trade is None:
                    continue
                lt = sn.latest_trade
                lq = sn.latest_quote
                tick = Tick(
                    symbol=sym,
                    ts=lt.timestamp.astimezone(timezone.utc),
                    price=float(lt.price),
                    bid=float(lq.bid_price) if lq and lq.bid_price else None,
                    ask=float(lq.ask_price) if lq and lq.ask_price else None,
                )
                out[sym] = SnapshotResult(
                    tick=tick,
                    minute_bar=_to_bar(sym, sn.minute_bar) if sn.minute_bar else None,
                    daily_bar=_to_bar(sym, sn.daily_bar) if sn.daily_bar else None,
                    prev_daily_bar=_to_bar(sym, sn.previous_daily_bar) if sn.previous_daily_bar else None,
                )
        return out


class HistoricalBars:
    """Minute bars from Alpaca with a SQLite cache so backtests re-run without re-downloading."""

    def __init__(self, client: StockHistoricalDataClient, db: Database | None, feed: str = "sip"):
        self.client = client
        self.db = db
        self.feed = feed
        self.calls = 0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=8), reraise=True)
    def _fetch(self, symbols: list[str], start: datetime, end: datetime) -> list[Bar]:
        self.calls += 1
        # Alpaca treats ``end`` as inclusive; the cache query is exclusive. Trim one second so they agree.
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end - timedelta(seconds=1),
            feed=DataFeed(self.feed),
            limit=None,  # None: SDK paginates. A number is a hard cap and silently truncates.
        )
        resp = self.client.get_stock_bars(req)
        bars: list[Bar] = []
        data = resp.data if hasattr(resp, "data") else resp
        for sym, lst in data.items():
            bars.extend(_to_bar(sym, b) for b in lst)
        return bars

    def fetch(self, symbols: Iterable[str], start: datetime, end: datetime, use_cache: bool = True) -> list[Bar]:
        symbols = sorted(set(symbols))
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        result: list[Bar] = []
        to_download: list[str] = []
        if use_cache and self.db is not None:
            for sym in symbols:
                cached = self.db.bars.range(sym, start, end, self.feed)
                if cached:
                    result.extend(cached)
                else:
                    to_download.append(sym)
        else:
            to_download = symbols

        for i in range(0, len(to_download), BARS_SYMBOL_BATCH):
            batch = to_download[i : i + BARS_SYMBOL_BATCH]
            try:
                fetched = self._fetch(batch, start, end)
            except Exception as e:  # noqa: BLE001
                logger.warning("bars fetch failed for {} symbols: {}", len(batch), e)
                continue
            if self.db is not None and fetched:
                self.db.bars.upsert_many(fetched, feed=self.feed)
            result.extend(fetched)
            logger.debug("downloaded {} bars for {} symbols ({} feed)", len(fetched), len(batch), self.feed)

        result.sort(key=lambda b: (b.ts, b.symbol))
        return result

    def warmup(self, symbols: Iterable[str], minutes: int, now: datetime | None = None) -> list[Bar]:
        """Recent bars on this fetcher's feed. On the free plan SIP withholds the last 15 minutes, so
        the fetcher is built with feed=iex (settings.alpaca.data_feed); after an upgrade set it to sip."""
        now = now or datetime.now(timezone.utc)
        return self.fetch(symbols, now - timedelta(minutes=minutes), now, use_cache=False)


class DailyBars:
    """Daily SIP bars, cached under feed tag ``sip-day``. Used to build point-in-time universes."""

    FEED_TAG = "sip-day"

    def __init__(self, client: StockHistoricalDataClient, db: Database | None):
        self.client = client
        self.db = db
        self.calls = 0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=8), reraise=True)
    def _fetch(self, symbols: list[str], start: datetime, end: datetime) -> list[Bar]:
        self.calls += 1
        req = StockBarsRequest(
            symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start, end=end, feed=DataFeed.SIP, limit=None
        )
        resp = self.client.get_stock_bars(req)
        data = resp.data if hasattr(resp, "data") else resp
        out: list[Bar] = []
        for sym, lst in data.items():
            out.extend(_to_bar(sym, b) for b in lst)
        return out

    def fetch(self, symbols: Iterable[str], start: date, end: date, batch: int = 200) -> list[Bar]:
        """Daily bars for [start, end] inclusive. Symbols with any cached bar in the range are not re-fetched."""
        symbols = sorted(set(symbols))
        s_utc = datetime.combine(start, datetime.min.time(), timezone.utc)
        e_utc = datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
        result: list[Bar] = []
        todo: list[str] = []
        for sym in symbols:
            cached = self.db.bars.range(sym, s_utc, e_utc, self.FEED_TAG) if self.db is not None else []
            if cached:
                result.extend(cached)
            else:
                todo.append(sym)
        for i in range(0, len(todo), batch):
            chunk = todo[i : i + batch]
            try:
                got = self._fetch(chunk, s_utc, e_utc - timedelta(seconds=1))
            except Exception as e:  # noqa: BLE001
                logger.warning("daily bars fetch failed for {} symbols: {}", len(chunk), e)
                continue
            if self.db is not None and got:
                self.db.bars.upsert_many(got, feed=self.FEED_TAG)
            result.extend(got)
            logger.debug("daily bars: {} symbols -> {} bars ({} calls so far)", len(chunk), len(got), self.calls)
        result.sort(key=lambda b: (b.symbol, b.ts))
        return result
