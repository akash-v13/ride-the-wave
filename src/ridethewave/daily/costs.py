"""Trading-cost measurements for the daily books, pure (no I/O).

The stat-arb backtest charges 5 bp per stock trade and enters at the open; the shadow slot fills at
about 09:35 (docs/research/2026-11-09-statarb-costs.md). Two things decide whether that is fair:
- **The spread.** A market order pays half the quoted spread. ``half_spread_bp`` measures it from
  quote history, weighting each quote by how long it stood.
- **The wait.** Between the open and 09:35 the picks may already have moved. ``open_to_later``
  reads both prices from minute bars, and ``long_short_gap`` turns them into the part of the
  long-minus-short spread that the wait gives up or gains.
- **The auction.** An order sent for the open pays no spread; it is filled at the opening auction
  price, which ``auction_price`` reads from the day's opening prints
  (docs/research/2026-11-09-statarb-auction-fills.md).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def half_spread_bp(ts_ns: np.ndarray, bid: np.ndarray, ask: np.ndarray, end_ns: int) -> float | None:
    """Time-weighted quoted half-spread over a window, in basis points of the mid.

    ``ts_ns`` are quote times in nanoseconds, oldest first. Each quote stands until the next one, the
    last until ``end_ns``. Quotes with no bid, or with the ask at or below the bid (locked or crossed
    markets, bad prints), count for nothing. None when no valid quote stood for any time."""
    if len(ts_ns) == 0:
        return None
    stood = np.diff(np.append(ts_ns, end_ns)).astype(float)
    ok = (bid > 0) & (ask > bid) & (stood > 0)
    if not ok.any():
        return None
    half = (ask[ok] - bid[ok]) / (ask[ok] + bid[ok]) * 1e4  # (ask - bid) / 2, over the mid (ask + bid) / 2
    return float(np.average(half, weights=stood[ok]))


def auction_price(prints: list[dict] | None) -> float | None:
    """A stock's opening auction price from one day's opening prints (Alpaca's auction history: each
    print has a price ``p`` and a size ``s``). The largest print is the cross on the stock's listing
    exchange, which is where an order sent for the open is filled; the smaller ones are other venues'
    own openings. None when there was no opening print."""
    best = max((x for x in prints or [] if x.get("p") and x.get("s")), key=lambda x: x["s"], default=None)
    return float(best["p"]) if best else None


def auction_day(rows: list[dict] | None, day: str) -> dict | None:
    """The row for ``day`` (``YYYY-MM-DD``) among the daily rows Alpaca's auction history returns for
    one symbol.

    A request for one day can return two rows. NYSE- and ARCA-listed symbols carry a late closing print
    stamped 20:00 New York time, which in winter is 01:00 UTC on the next date, so the day before comes
    back first, with no opening prints. Reading the first row therefore lost every NYSE and ARCA opening
    print from Tuesday to Friday between November and March (found on the first live session,
    2026-11-10). Rows are matched on their own date (``d``) instead."""
    return next((r for r in rows or [] if r.get("d") == day), None)


def open_to_later(bars: pd.DataFrame, later_minute: int = 5) -> float | None:
    """A stock's move from its opening trade to ``later_minute`` minutes after 09:30, from one session's
    minute bars (columns ``minute`` = whole minutes since 09:30, ``open``, ``close``, ``vwap``).

    - **Open:** the open of the first bar before ``later_minute``. A stock that opens late is priced
      from its own first trade, as the daily bar's open is.
    - **Later price:** the volume-weighted price of the ``later_minute`` bar, the closest thing to a
      fill somewhere in that minute. If nothing traded in that minute, the last close before it.
    None when the stock had not traded before ``later_minute``."""
    early = bars[bars["minute"] < later_minute].sort_values("minute")
    if early.empty:
        return None
    first = float(early["open"].iloc[0])
    at = bars[bars["minute"] == later_minute]
    later = float(at["vwap"].iloc[0]) if len(at) and at["vwap"].iloc[0] > 0 else float(early["close"].iloc[-1])
    return later / first - 1 if first > 0 else None


def long_short_gap(
    move: pd.Series, longs: list[str], shorts: list[str], b_m: pd.Series, b_s: pd.Series, sectors: pd.Series
) -> tuple[float | None, int]:
    """The longs' average hedged move minus the shorts', and how many names had a price.

    ``move`` holds each symbol's move over the same stretch, SPY and the sector ETFs included. A
    stock's hedged move is its own minus ``b_m`` times SPY's and ``b_s`` times its sector's move
    beyond SPY, the same hedge the backtest applies to the five-day return."""
    spy = move.get("SPY")
    if spy is None or pd.isna(spy):
        return None, 0

    def side(names: list[str]) -> list[float]:
        out = []
        for s in names:
            own, etf = move.get(s), sectors.get(s)
            sec = move.get(etf) if isinstance(etf, str) else None
            bm, bs = b_m.get(s), b_s.get(s)
            if any(x is None or pd.isna(x) for x in (own, sec, bm, bs)):
                continue
            out.append(own - bm * spy - bs * (sec - spy))
        return out

    lo, sh = side(longs), side(shorts)
    if not lo or not sh:
        return None, len(lo) + len(sh)
    return float(np.mean(lo) - np.mean(sh)), len(lo) + len(sh)
