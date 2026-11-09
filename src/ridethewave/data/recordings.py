"""Daily recordings of market state that cannot be bought back later (2026-11-09).

Two things the research will want, for which Alpaca keeps no history:
- **Borrow flags.** The asset list says, each day, which stocks can be shorted and which are easy to
  borrow. The stat-arb backtest assumed every short was available at 0.5% a year; nothing recorded
  whether that was true.
- **Option quotes.** Bid, ask, implied volatility and greeks around the money for the next two
  monthly expiries of each stock in the stat-arb universe. Alpaca's option history starts in
  February 2024 and carries prices only, no implied volatility.

One parquet file per day and kind under ``data/recordings/``. Values are stored as Alpaca sent them.
Any measure (30-day implied volatility, skew, the call-put spread) can be built later, but only for
days that were recorded. Feature page: docs/features/25-market-state-recording.md.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from alpaca.data.enums import OptionsFeed
from alpaca.data.requests import OptionChainRequest
from loguru import logger

from ridethewave.data.assets import AssetInfo
from ridethewave.options.chain import parse_occ

ROOT = Path(__file__).resolve().parents[3] / "data" / "recordings"
MIN_DTE = 7  # skip an expiry closer than this: its quotes say more about pinning than about volatility
N_EXPIRIES = 2  # the two monthlies either side of about 30 days, enough to interpolate a constant maturity
STRIKE_BAND = 0.20  # strikes within 20% of the spot: covers the usual skew measures without the far wings


def third_friday(year: int, month: int) -> date:
    """The standard monthly option expiry."""
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def monthly_expiries(today: date, n: int = N_EXPIRIES, min_dte: int = MIN_DTE) -> list[date]:
    """The next ``n`` monthly expiries at least ``min_dte`` days away."""
    out: list[date] = []
    year, month = today.year, today.month
    while len(out) < n:
        friday = third_friday(year, month)
        if (friday - today).days >= min_dte:
            out.append(friday)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def write_day(frame: pd.DataFrame, kind: str, day: str, root: Path = ROOT, force: bool = False) -> Path | None:
    """Write ``frame`` to ``<root>/<kind>/<day>.parquet``. Returns None, writing nothing, when the day is
    already recorded and ``force`` is off: a late re-run must not replace quotes taken in the session
    with stale ones. Written to a temporary file first, so a reader never sees half a file."""
    path = root / kind / f"{day}.parquet"
    if path.exists() and not force:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    frame.to_parquet(tmp, index=False, compression="zstd")
    tmp.replace(path)
    return path


# ---------------------------------------------------------------- borrow flags
def asset_frame(assets: list[AssetInfo], day: str) -> pd.DataFrame:
    """One row per active US stock or fund: can it be shorted today, and is it easy to borrow."""
    cols = ("symbol", "exchange", "tradable", "marginable", "shortable", "easy_to_borrow", "fractionable")
    frame = pd.DataFrame([{c: getattr(a, c) for c in cols} for a in assets], columns=list(cols))
    frame.insert(0, "day", day)
    return frame.sort_values("symbol", ignore_index=True)


# ---------------------------------------------------------------- option quotes
def _num(x) -> float | None:
    return float(x) if x is not None else None


def _when(x) -> datetime | None:
    return x.astimezone(timezone.utc) if x is not None else None


def contract_rows(underlying: str, spot: float, raw: dict) -> list[dict]:
    """One row per contract in a chain response. Fields the feed left out stay empty: an option
    with no quote or no implied volatility is recorded as such, not dropped or filled in."""
    rows = []
    for symbol, snap in raw.items():
        try:
            _, expiry, right, strike = parse_occ(symbol)
        except ValueError:
            continue
        quote, trade = getattr(snap, "latest_quote", None), getattr(snap, "latest_trade", None)
        greeks = getattr(snap, "greeks", None)
        rows.append(
            {
                "underlying": underlying,
                "spot": spot,
                "symbol": symbol,
                "expiry": expiry.isoformat(),
                "right": right,
                "strike": strike,
                "bid": _num(getattr(quote, "bid_price", None)),
                "ask": _num(getattr(quote, "ask_price", None)),
                "bid_size": _num(getattr(quote, "bid_size", None)),
                "ask_size": _num(getattr(quote, "ask_size", None)),
                "quote_ts": _when(getattr(quote, "timestamp", None)),
                "last": _num(getattr(trade, "price", None)),
                "last_ts": _when(getattr(trade, "timestamp", None)),
                "iv": _num(getattr(snap, "implied_volatility", None)),
                **{g: _num(getattr(greeks, g, None)) for g in ("delta", "gamma", "theta", "vega", "rho")},
            }
        )
    return rows


def fetch_chain(client, underlying: str, spot: float, expiry: date, feed: str = "opra") -> dict:
    """The chain for one expiry within ``STRIKE_BAND`` of the spot. When the third Friday is a market
    holiday (Good Friday in some years) the monthly expires on the Thursday, so an empty answer is
    asked again for the day before."""
    for day in (expiry, expiry - timedelta(days=1)):
        raw = client.get_option_chain(
            OptionChainRequest(
                underlying_symbol=underlying,
                feed=OptionsFeed(feed),
                expiration_date=day,
                strike_price_gte=round(spot * (1 - STRIKE_BAND), 2),
                strike_price_lte=round(spot * (1 + STRIKE_BAND), 2),
            )
        )
        if raw:
            return raw
    return {}


def option_frame(
    client, spots: dict[str, float], today: date, market_open: bool, feed: str = "opra"
) -> tuple[pd.DataFrame, dict]:
    """Chains for every underlying in ``spots``, and a count of what came back.

    One underlying failing is logged and counted; the others are still recorded."""
    expiries = monthly_expiries(today)
    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    stats = {"asked": len(spots), "with_contracts": 0, "with_iv": 0, "failed": 0}
    for underlying, spot in sorted(spots.items()):
        try:
            got = [
                r
                for e in expiries
                for r in contract_rows(underlying, spot, fetch_chain(client, underlying, spot, e, feed))
            ]
        except Exception as e:  # noqa: BLE001
            stats["failed"] += 1
            logger.warning("options recording: {} failed: {}: {}", underlying, type(e).__name__, e)
            continue
        stats["with_contracts"] += bool(got)
        stats["with_iv"] += any(r["iv"] for r in got)
        rows.extend(got)
    frame = pd.DataFrame(rows)
    if len(frame):
        frame.insert(0, "day", today.isoformat())
        frame.insert(1, "ts", now)
        frame.insert(2, "market_open", market_open)
    stats["contracts"] = len(frame)
    stats["expiries"] = [e.isoformat() for e in expiries]
    return frame, stats
