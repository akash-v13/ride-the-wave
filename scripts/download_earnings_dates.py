"""Earnings report dates for the research universe, from the SEC's 8-K item 2.02 filings (2026-11-10).

Why and what the dates mean: src/ridethewave/data/edgar.py. Two steps, each safe to run again:
1. ``ciks``: each symbol's SEC company number. Listed symbols come from Massive's ticker list (a few
   requests, 13 seconds apart on the free plan); delisted ones from the list saved on 9 November.
2. ``download``: for every stock that was ever in the monthly top 300, read its filings from EDGAR
   (about five requests a second, well under the SEC's limit of ten) and keep the acceptance time of
   each 8-K with item 2.02. Saved to data/reference/earnings_8k.parquet (symbol, cik, accepted).

Needs SEC_CONTACT in .env (the SEC asks automated readers to identify themselves) and, for step 1,
MASSIVE_API_KEY.

    uv run python scripts/download_earnings_dates.py ciks
    uv run python scripts/download_earnings_dates.py download
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from loguru import logger

from ridethewave.config import load_secrets
from ridethewave.daily.panel_store import load_long, monthly_universes
from ridethewave.data.delistings import massive_delisted
from ridethewave.data.edgar import earnings_filings, fetch_submissions

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
CIKS, OUT = REF / "ticker_cik.parquet", REF / "earnings_8k.parquet"
SINCE = "2016-06-01"
PAUSE = 0.2


def ciks() -> int:
    key = load_secrets().massive_api_key
    if not key:
        raise SystemExit("MASSIVE_API_KEY is not set in .env")
    listed = massive_delisted(key, active=True)[["ticker", "cik"]].assign(delisted=None)
    gone = pd.read_parquet(REF / "delisted_massive.parquet")[["ticker", "cik", "delisted"]]
    both = pd.concat([listed, gone], ignore_index=True).dropna(subset=["cik"])
    both["delisted"] = both["delisted"].astype(str).replace({"None": "", "NaT": "", "nan": ""})
    both.to_parquet(CIKS, index=False)
    logger.info("{} listed and {} delisted tickers with a company number", listed["cik"].notna().sum(),
                gone["cik"].notna().sum())  # fmt: skip
    return 0


def cik_of(symbol: str, table: pd.DataFrame, delisted_on: str | None) -> str | None:
    """A listed symbol's number; for a delisted one, the row of that ticker whose delisting date is
    nearest the one our panel records (a ticker can be reused by a later company)."""
    rows = table[table["ticker"] == symbol]
    if rows.empty:
        return None
    if not delisted_on:
        live = rows[rows["delisted"] == ""]
        return str((live if len(live) else rows).iloc[-1]["cik"])
    dated = rows[rows["delisted"] != ""]
    if dated.empty:
        return str(rows.iloc[-1]["cik"])
    gap = (pd.to_datetime(dated["delisted"]) - pd.Timestamp(delisted_on)).abs()
    return str(dated.loc[gap.idxmin(), "cik"])


def download() -> int:
    contact = load_secrets().sec_contact
    if not contact:
        raise SystemExit("SEC_CONTACT is not set in .env")
    table = pd.read_parquet(CIKS)
    universes = monthly_universes(load_long(5.0, 2e6), 300)
    symbols = sorted({s for names in universes.values() for s in names})
    gone = pd.read_parquet(ROOT / "data" / "daily_panel" / "assets_delisted.parquet").set_index("symbol")["delisted"]
    rows, no_cik, no_file = [], [], []
    for n, sym in enumerate(symbols, 1):
        cik = cik_of(sym, table, gone.get(sym))
        if cik is None:
            no_cik.append(sym)
            continue
        body = fetch_submissions(f"CIK{int(cik):010d}.json", contact)
        time.sleep(PAUSE)
        if body is None:
            no_file.append(sym)
            continue
        times = earnings_filings(body["filings"]["recent"])
        for older in body["filings"].get("files", []):
            if older.get("filingTo", "") >= SINCE:  # an older file that still reaches into our years
                extra = fetch_submissions(older["name"], contact)
                time.sleep(PAUSE)
                times += earnings_filings(extra or {})
        rows += [{"symbol": sym, "cik": cik, "accepted": t} for t in times]
        if n % 100 == 0:
            logger.info("{} of {} symbols, {} filings so far", n, len(symbols), len(rows))
    df = pd.DataFrame(rows).drop_duplicates()
    df = df[df["accepted"] >= pd.Timestamp(SINCE, tz="UTC")].sort_values(["symbol", "accepted"])
    df.to_parquet(OUT, index=False)
    logger.info("{} filings for {} of {} symbols; no company number for {} ({}); no filings file for {} ({})",
                len(df), df["symbol"].nunique(), len(symbols), len(no_cik), ", ".join(no_cik[:15]), len(no_file),
                ", ".join(no_file[:15]))  # fmt: skip
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["ciks", "download"])
    args = ap.parse_args()
    return ciks() if args.step == "ciks" else download()


if __name__ == "__main__":
    sys.exit(main())
