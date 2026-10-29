# 04 · Universe (which stocks to watch)

**What it does.** Each morning the bot builds the list of symbols it will scan.

1. Gets candidates: the top N most-active stocks by volume from Alpaca's screener (default N=100), or the top gainers, or a fixed list from settings.
2. Keeps only those that Alpaca marks tradable and that trade on NYSE, NASDAQ or ARCA (drops OTC and penny listings).
3. Keeps only those whose latest price is between `min_price` and `max_price` (default $5 to $500).

On 2026-09-17 this turned 100 most-actives into 65 symbols. The most-active list is dominated by sub-$5 names, so the price filter matters.

**Why most-actives.** On the free IEX-only feed, quiet stocks print very few trades, so their minute bars are patchy and streaks are noise. Active stocks have real IEX volume.

**Refresh.** Rebuilt every `refresh_minutes` (default 30). Held positions are always polled even if they drop out of the universe. A symbol that joins the list mid-session gets its recent minute bars straight away (warm-up), so it has history just like a symbol that was there at the open.

**Where the asset list comes from.** Step 2 needs Alpaca's list of every US stock: about 14,400 rows with the exchange, the tradable flag and the company name. The bot asks Alpaca for that list as raw JSON and reads each row itself (`data/assets.py`). It does not use alpaca-py's `get_all_assets`. That function checks every row's exchange against a fixed list, and one unknown code makes the whole list fail. On 20 October 2026 Alpaca started listing ten stocks on the new Texas Stock Exchange (code `TXSE`). alpaca-py 0.44.0, the newest release, rejected the code, and every universe build failed for six sessions. Now an unknown exchange code is kept as text. The exchange filter drops it like any exchange it was not told to allow. A row that cannot be read is skipped and counted.

**When the build fails.** A build can still fail, for example on a dropped connection after the Mac wakes from sleep. In that case:

1. Every Alpaca call retries a connection that fails or drops (see `docs/features/14-operator.md`, "Network failures").
2. At start-up the bot tries the build three times, waiting 15 and then 45 seconds between attempts.
3. If the universe is still empty, the bot tries again every 2 minutes, not every 30.
4. When a late build succeeds, the new symbols get their warm-up bars and every strategy gets its daily context, as at a normal start. The daily-context step only runs when the universe was empty, because it resets per-day state such as the opening-range breakout's ranges.
5. A failed build keeps the previous list. An empty universe during market hours raises an alert.

Before 28 October 2026, a failed start-up build left the session empty until the 30-minute refresh. In October the refresh kept failing too, and the operator still reported the system as healthy.

**Settings.** `universe.source`, `universe.top`, `universe.static_symbols`, `universe.min_price`, `universe.max_price`, `universe.exchanges`, `universe.refresh_minutes`.

**Code:** `src/ridethewave/data/universe.py`, `src/ridethewave/data/assets.py`, and `BotRunner._rebuild_universe` and `_refresh_universe` in `src/ridethewave/runner.py`.
