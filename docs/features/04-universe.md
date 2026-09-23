# 04 · Universe (which stocks to watch)

**What it does.** Each morning the bot builds the list of symbols it will scan.

1. Gets candidates: the top N most-active stocks by volume from Alpaca's screener (default N=100), or the top gainers, or a fixed list from settings.
2. Keeps only those that Alpaca marks tradable and that trade on NYSE, NASDAQ or ARCA (drops OTC and penny listings).
3. Keeps only those whose latest price is between `min_price` and `max_price` (default $5 to $500).

On 2026-09-17 this turned 100 most-actives into 65 symbols. The most-active list is dominated by sub-$5 names, so the price filter matters.

**Why most-actives.** On the free IEX-only feed, quiet stocks print very few trades, so their minute bars are patchy and streaks are noise. Active stocks have real IEX volume.

**Refresh.** Rebuilt every `refresh_minutes` (default 30). Held positions are always polled even if they drop out of the universe.

**Settings.** `universe.source`, `universe.top`, `universe.static_symbols`, `universe.min_price`, `universe.max_price`, `universe.exchanges`, `universe.refresh_minutes`.

**Code:** `src/ridethewave/data/universe.py`.
