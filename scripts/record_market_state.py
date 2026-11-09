"""Record today's borrow flags and option quotes (feature 25). Run by the operator tick at 15:45 ET.

Alpaca keeps no history of which stocks could be shorted, and its option history has no implied
volatility. This writes one file a day of each under data/recordings/ so later research has them:
- ``assets/<day>.parquet``: every active US stock and fund, with its shortable and easy-to-borrow flags;
- ``options/<day>.parquet``: quotes, implied volatility and greeks within 20% of the money for the next
  two monthly expiries of the stat-arb universe, SPY, QQQ, IWM and the sector ETFs.

A day already recorded is left alone unless ``--force`` is given. If little came back, the owner
gets a phone alert and the script exits 1.

    uv run python scripts/record_market_state.py
    uv run python scripts/record_market_state.py --force     # replace today's files
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.trading.requests import GetCalendarRequest
from loguru import logger

from ridethewave.clients import make_clients
from ridethewave.config import load_secrets, load_settings
from ridethewave.daily.universe import SECTOR_ETFS_11, resolve
from ridethewave.data.assets import fetch_assets
from ridethewave.data.market_data import SnapshotPoller
from ridethewave.data.recordings import asset_frame, option_frame, write_day
from ridethewave.operator.notify import notify, ntfy_topic
from ridethewave.storage import Database

ET = ZoneInfo("America/New_York")
UNIVERSE = "file:config/universes/liquid_stocks_254.txt"
FUNDS = ["SPY", "QQQ", "IWM", *SECTOR_ETFS_11]
BATCH = 40  # underlyings per spot poll, so a chain is never priced against a spot more than seconds old
MIN_ASSETS = 5000  # the list has about 14,000 rows; far fewer means a broken answer
MIN_COVERAGE = 0.8  # share of underlyings that must come back with implied volatility


def spots(poller: SnapshotPoller, symbols: list[str], market_open: bool, today: str) -> dict[str, float]:
    """In the session, the last trade. After the close, today's closing price: option quotes stop at
    16:00, and a later after-hours trade would misstate how far each strike is from the money."""
    out = {}
    for sym, snap in poller.poll(symbols).items():
        bar = snap.daily_bar
        closed_today = bar is not None and bar.ts.astimezone(ET).strftime("%Y-%m-%d") == today
        price = snap.tick.price if market_open or not closed_today else bar.close
        if price and price > 0:
            out[sym] = float(price)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="replace today's files if they exist")
    ap.add_argument("--universe", default=UNIVERSE, help="stocks whose options are recorded")
    args = ap.parse_args()
    settings = load_settings()
    clients = make_clients(load_secrets(), settings)
    today = datetime.now(ET).date()
    day = today.isoformat()
    if not clients.trading.get_calendar(GetCalendarRequest(start=today, end=today)):
        logger.info("no session on {}; nothing recorded", day)
        return 0
    market_open = bool(clients.trading.get_clock().is_open)
    problems: list[str] = []
    tradable: set[str] | None = None  # today's tradable symbols, once the asset list has been read
    state: dict = {"day": day, "at": datetime.now(ET).isoformat(timespec="seconds"), "market_open": market_open}

    # 1. borrow flags: the whole asset list, since tomorrow's universe is not known today
    try:
        assets = asset_frame(fetch_assets(clients.trading), day)
        state["assets"] = {"rows": len(assets), "shortable": int(assets["shortable"].sum()),
                           "easy_to_borrow": int(assets["easy_to_borrow"].sum())}  # fmt: skip
        if len(assets) < MIN_ASSETS:
            problems.append(f"asset list has only {len(assets)} rows")
        else:
            tradable = set(assets.loc[assets["tradable"], "symbol"])
            if write_day(assets, "assets", day, force=args.force) is None:
                logger.info("assets for {} already recorded; left alone", day)
    except Exception as e:  # noqa: BLE001
        problems.append(f"asset list failed: {type(e).__name__}")
        logger.warning("asset recording failed: {}: {}", type(e).__name__, e)

    # 2. option quotes
    try:
        names = sorted(set(resolve(args.universe)) | set(FUNDS))
        # A delisted stock still answers with its last trade and its dead option quotes (KVUE and WBD
        # did on 2026-11-09), so only names tradable today are recorded.
        gone = [n for n in names if tradable is not None and n not in tradable]
        if gone:
            logger.warning("not tradable today, options not recorded: {}", ", ".join(gone))
            names = [n for n in names if n not in gone]
        poller = SnapshotPoller(clients.data, settings.alpaca.data_feed)
        frames, total = [], {"asked": len(names), "priced": 0, "with_contracts": 0, "with_iv": 0, "failed": 0}
        for i in range(0, len(names), BATCH):
            priced = spots(poller, names[i : i + BATCH], market_open, day)
            frame, stats = option_frame(clients.options, priced, today, market_open)
            frames.append(frame)
            total["priced"] += len(priced)
            for k in ("with_contracts", "with_iv", "failed"):
                total[k] += stats[k]
            total["expiries"] = stats["expiries"]
        options = pd.concat([f for f in frames if len(f)], ignore_index=True) if any(len(f) for f in frames) else None
        total["contracts"] = 0 if options is None else len(options)
        total["not_tradable"] = gone
        state["options"] = total
        if total["with_iv"] < MIN_COVERAGE * total["asked"]:
            problems.append(f"options: implied volatility for only {total['with_iv']} of {total['asked']} names")
        elif write_day(options, "options", day, force=args.force) is None:
            logger.info("options for {} already recorded; left alone", day)
    except Exception as e:  # noqa: BLE001
        problems.append(f"option quotes failed: {type(e).__name__}")
        logger.warning("option recording failed: {}: {}", type(e).__name__, e)

    state["problems"] = problems
    db = Database(settings.storage.resolved_db_path())
    db.state.set("recording", state)
    db.close()
    if problems:
        text = f"Market recording for {day} is incomplete: " + "; ".join(problems)
        logger.warning(text)
        notify(
            "Ride The Wave", text, settings.operator.notify, topic=ntfy_topic(), server=settings.operator.ntfy_server
        )
        return 1
    logger.info("recorded {}: {} | {}", day, state.get("assets"), state.get("options"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
