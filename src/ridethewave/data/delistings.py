"""Which stocks stopped trading, and when: the record the daily price panel needs to be free of survivors.

Alpaca's asset list drops a stock when it is delisted (docs/research/2026-11-09-panel-survivorship-gap.md),
so the list cannot say which stocks used to exist. Alpaca still serves a delisted stock's prices to anyone
who asks for it by symbol. Two sources supply the symbols:

- **The past, once.** ``massive_delisted`` downloads Massive's list of delisted tickers with their last
  trading dates (back to 2003). It is a one-time backfill saved under ``data/reference/``. Nothing in the bot
  or the studies calls Massive again; every price still comes from Alpaca.
- **From 2026-11-09 on, in-house.** The operator saves Alpaca's whole asset list each day (feature 25).
  ``left_the_list`` compares two days of it: a stock in yesterday's file and not in today's has gone.

``renamed`` keeps a ticker change from being counted twice. Massive lists the old ticker of a renamed company
as delisted, but Alpaca files that company's whole history under its new symbol, which the panel already has.
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import requests
from loguru import logger

MASSIVE = "https://api.massive.com"
COMPANY_TYPES = ("CS", "ADRC")  # common stocks and ADRs; funds, notes, warrants and units are not companies
MIC = {"XNYS": "NYSE", "XNAS": "NASDAQ", "ARCX": "ARCA", "XASE": "AMEX", "BATS": "BATS"}


def massive_delisted(
    api_key: str, types: tuple[str, ...] = COMPANY_TYPES, pause: float = 13.0, active: bool = False
) -> pd.DataFrame:
    """Every delisted US stock ticker Massive knows, one row each: ``ticker``, ``name``, ``type``,
    ``exchange``, ``delisted`` (its last trading date), ``figi``, ``cik``. With ``active`` the listed
    tickers instead (no delisting date), which is where a current symbol's SEC company number comes from.

    The key goes in a header and is never logged. ``pause`` seconds pass between pages, because the free
    plan allows 5 requests a minute; a refusal for going too fast is waited out and asked again."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"
    rows: list[dict] = []
    for kind in types:
        url: str | None = f"{MASSIVE}/v3/reference/tickers"
        params: dict | None = {
            "market": "stocks",
            "active": "true" if active else "false",
            "type": kind,
            "limit": 1000,
            "sort": "ticker",
        }
        pages = 0
        while url:
            r = session.get(url, params=params, timeout=40)
            if r.status_code == 429:
                time.sleep(pause * 2)
                continue
            r.raise_for_status()
            body = r.json()
            rows.extend(body.get("results") or [])
            url, params = body.get("next_url"), None  # the next page's address carries its own cursor
            pages += 1
            if pages % 5 == 0:
                logger.info(
                    "{} {}: {} pages, {} rows so far", "listed" if active else "delisted", kind, pages, len(rows)
                )
            if url:
                time.sleep(pause)
    frame = pd.DataFrame(rows)
    out = pd.DataFrame(
        {
            "ticker": frame["ticker"],
            "name": frame.get("name"),
            "type": frame.get("type"),
            "exchange": frame.get("primary_exchange").map(lambda m: MIC.get(m, m)),
            # listed tickers carry no delisting date
            "delisted": pd.to_datetime(
                frame.reindex(columns=["delisted_utc"])["delisted_utc"], utc=True, errors="coerce"
            ).dt.date,
            "figi": frame.get("composite_figi"),
            "cik": frame.get("cik"),
        }
    )
    return out.dropna(subset=["ticker"]).sort_values(["ticker", "delisted"], ignore_index=True)


def left_the_list(before: pd.DataFrame, after: pd.DataFrame, day: date | str) -> pd.DataFrame:
    """Stocks that were tradable in one day's saved asset list and are absent from the next: our own
    delisting record. ``before`` and ``after`` are two days of ``data/recordings/assets``; ``day`` is the
    date of ``after``, the first day each stock was missing."""
    was = before[before["tradable"]]
    gone = was[~was["symbol"].isin(set(after["symbol"]))]
    return pd.DataFrame({"symbol": gone["symbol"], "exchange": gone["exchange"], "gone_by": str(day)}).reset_index(
        drop=True
    )


def renamed(candidates: pd.DataFrame, panel: pd.DataFrame, need: float = 0.8) -> dict[str, str]:
    """Candidates that are a company the panel already holds under another symbol: {candidate: panel symbol}.

    Both frames have ``symbol``, ``day`` and ``volume``. Two series are the same company when at least
    ``need`` of the candidate's days (five or more of them) show exactly the same volume on the same day
    under one panel symbol. Exact share counts do not repeat by chance across a week."""
    hits = candidates.merge(panel, on=["day", "volume"], suffixes=("", "_panel"))
    hits = hits[hits["symbol"] != hits["symbol_panel"]]
    days = candidates.groupby("symbol")["day"].nunique()
    matched = hits.groupby(["symbol", "symbol_panel"])["day"].nunique()
    out: dict[str, str] = {}
    for (cand, other), n in matched.items():
        if days[cand] >= 5 and n >= need * days[cand]:
            out[cand] = other
    return out
