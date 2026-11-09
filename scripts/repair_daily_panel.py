"""Add the delisted stocks the daily price panel is missing (2026-11-09).

Why: docs/research/2026-11-09-panel-survivorship-gap.md. The panel was built from Alpaca's asset list,
which drops a stock when it is delisted, so it lacked most stocks delisted since late 2022 and all of
those delisted in 2016-17.

Steps, each safe to run again:
1. ``list``: download Massive's list of delisted stocks once (about 5 requests a minute on the free plan)
   into data/reference/delisted_massive.parquet.
2. ``download``: for each company stock on NYSE, NASDAQ or ARCA delisted inside the panel's dates and not
   in the panel, ask Alpaca for its adjusted daily bars as that symbol stood shortly before it left.
   Tickers that are only an old name of a company the panel already holds are dropped. The rest are
   written beside the panel as ``bars_delisted_NNNN.parquet``, which ``load_long`` reads with the others.
3. ``report``: what was added, by the year each stock's prices end.

Every price comes from Alpaca. Massive supplies only the symbols and dates.

    uv run python scripts/repair_daily_panel.py list
    uv run python scripts/repair_daily_panel.py download
    uv run python scripts/repair_daily_panel.py report
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger

from ridethewave.clients import with_retries, with_timeouts
from ridethewave.config import load_secrets, load_settings
from ridethewave.data.delistings import massive_delisted, renamed

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "daily_panel"
LISTING = ROOT / "data" / "reference" / "delisted_massive.parquet"
START, END = date(2016, 1, 1), date(2026, 9, 22)  # the panel's own dates
BEFORE_LEAVING = 10  # days before the last trading date at which the symbol is looked up
MIN_BARS = 20
CHUNK = 100
WORKERS = 8

_local = threading.local()


def client() -> StockHistoricalDataClient:
    if not hasattr(_local, "client"):
        s = load_secrets()
        c = StockHistoricalDataClient(s.alpaca_api_key, s.alpaca_secret_key, raw_data=True)
        _local.client = with_retries(with_timeouts(c))
    return _local.client


def panel_bars(pattern: str = "bars_[0-9]*.parquet") -> pd.DataFrame:
    frames = [pd.read_parquet(f, columns=["symbol", "day", "volume"]) for f in sorted(PANEL.glob(pattern))]
    out = pd.concat(frames, ignore_index=True)
    out["day"] = pd.to_datetime(out["day"])
    return out


def candidates(listing: pd.DataFrame, have: set[str]) -> pd.DataFrame:
    """Company stocks on the panel's exchanges, delisted inside its dates, that it does not hold.
    A ticker can be delisted more than once (reused by a later company): each use is its own row."""
    allowed = {e.upper() for e in load_settings().universe.exchanges}
    dated = listing["delisted"].notna()
    inside = listing["delisted"].map(lambda d: d is not None and pd.notna(d) and START <= d <= END)
    c = listing[(inside | ~dated) & listing["exchange"].isin(allowed)]  # undated rows are tried by year
    c = c[c["ticker"].str.isalpha() & ~c["ticker"].isin(have)]
    return c.sort_values(["ticker", "delisted"]).reset_index(drop=True)


def fetch(ticker: str, left: date | None) -> pd.DataFrame:
    """Adjusted daily bars for ``ticker`` as it stood shortly before ``left``, up to a week after it.

    Massive gives no last trading date for about 200 tickers (US Steel among them). Those are looked up
    as the symbol stood in the middle of each year, latest first, and the first answer whose prices stop
    before the panel ends is kept: a stock still trading at the end was not delisted."""
    if left is None or pd.isna(left):
        for year in range(END.year, START.year - 1, -1):
            got = _bars(ticker, date(year, 6, 30).isoformat(), END)
            if len(got) and got["day"].max() < END - timedelta(days=20):
                return got
        return pd.DataFrame()
    return _bars(ticker, (left - timedelta(days=BEFORE_LEAVING)).isoformat(), min(left + timedelta(days=7), END))


def _bars(ticker: str, asof: str, end: date) -> pd.DataFrame:
    req = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Day,
        start=datetime.combine(START, datetime.min.time(), timezone.utc),
        end=datetime.combine(end, datetime.max.time(), timezone.utc),
        feed=DataFeed.SIP,
        adjustment=Adjustment.ALL,
        asof=asof,
        limit=None,
    )
    try:
        raw = client().get_stock_bars(req)
    except Exception as e:  # noqa: BLE001
        logger.debug("{} (as of {}): {}", ticker, asof, str(e)[:120])
        return pd.DataFrame()
    rows = [r for lst in raw.values() for r in lst]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(
        {
            "symbol": ticker,
            "day": pd.to_datetime([r["t"] for r in rows], utc=True).date,
            "open": [float(r["o"]) for r in rows],
            "high": [float(r["h"]) for r in rows],
            "low": [float(r["l"]) for r in rows],
            "close": [float(r["c"]) for r in rows],
            "volume": [int(r["v"]) for r in rows],
        }
    )
    return df[df["day"] <= END]


def download() -> int:
    listing = pd.read_parquet(LISTING)
    panel = panel_bars()
    cand = candidates(listing, set(panel["symbol"]))
    # one company per ticker here: a ticker delisted twice inside the dates keeps its last use
    cand = cand.drop_duplicates("ticker", keep="last")
    logger.info("{} delisted tickers to ask Alpaca for", len(cand))
    with ThreadPoolExecutor(WORKERS) as pool:
        frames = list(pool.map(lambda t: fetch(*t), zip(cand["ticker"], cand["delisted"], strict=True)))
    got = [f for f in frames if len(f) >= MIN_BARS]
    bars = pd.concat(got, ignore_index=True)
    logger.info("Alpaca served {} of them ({} bars)", len(got), len(bars))
    # Drop old names: of companies the panel already holds under their new symbol (FB is META), and of
    # companies that changed name and were delisted later (YHOO became AABA, which left in 2019). Alpaca
    # files each company's whole history under its last symbol, so the old name's final days match it.
    dated = bars.assign(day=pd.to_datetime(bars["day"]))[["symbol", "day", "volume"]]
    tails = dated.sort_values("day").groupby("symbol").tail(10)
    same = renamed(tails, pd.concat([panel, dated], ignore_index=True))
    bars = bars[~bars["symbol"].isin(same)]
    kept = sorted(bars["symbol"].unique())
    for old in PANEL.glob("bars_delisted_*.parquet"):
        old.unlink()
    for i in range(0, len(kept), CHUNK):
        part = bars[bars["symbol"].isin(kept[i : i + CHUNK])]
        part.to_parquet(PANEL / f"bars_delisted_{i // CHUNK:04d}.parquet", index=False)
    info = cand.set_index("ticker").loc[kept].reset_index()
    added = pd.DataFrame(
        {
            "symbol": info["ticker"],
            "name": info["name"],
            "exchange": info["exchange"],
            "status": "delisted",
            "fund": False,
            "delisted": [str(d) if d is not None and pd.notna(d) else "" for d in info["delisted"]],
        }
    )
    added.to_parquet(PANEL / "assets_delisted.parquet", index=False)
    summary = {
        "asked": int(len(cand)),
        "served": int(len(got)),
        "old_names_of_panel_companies": int(len(same)),
        "added": int(len(kept)),
        "bars": int(len(bars)),
        "renames_sample": dict(list(sorted(same.items()))[:15]),
    }
    (PANEL / "repair_report.json").write_text(json.dumps(summary, indent=1))
    logger.info("added {}", summary)
    return 0


def report() -> int:
    old, new = panel_bars(), panel_bars("bars_delisted_*.parquet")
    for label, frame in (("panel before", old), ("added", new)):
        last = frame.groupby("symbol")["day"].max()
        ended = last[last < pd.Timestamp(END) - pd.Timedelta(days=20)]
        by_year = ended.dt.year.value_counts().sort_index().to_dict()
        logger.info("{}: {} symbols; prices end by year: {}", label, last.size, by_year)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["list", "download", "report"])
    args = ap.parse_args()
    if args.step == "list":
        key = load_secrets().massive_api_key
        if not key:
            raise SystemExit("MASSIVE_API_KEY is not set in .env")
        LISTING.parent.mkdir(parents=True, exist_ok=True)
        frame = massive_delisted(key)
        frame.to_parquet(LISTING, index=False)
        logger.info("{} delisted tickers saved to {}", len(frame), LISTING)
        return 0
    return download() if args.step == "download" else report()


if __name__ == "__main__":
    sys.exit(main())
