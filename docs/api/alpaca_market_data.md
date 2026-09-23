# Alpaca Market Data API

Verified against docs.alpaca.markets on 2026-09-17. SDK: alpaca-py 0.44.0.

## Plan limits (Basic, free)

| Limit | Basic | Algo Trader Plus ($99/mo) |
|---|---|---|
| Real-time feed | IEX exchange only | All US exchanges (SIP) |
| Historical data | Latest 15 minutes withheld (SIP) | No restriction |
| Websocket symbols | 30 | Unlimited |
| Websocket connections | 1 | more |
| REST rate limit | 200 / min | 10,000 / min |

**This account is on Algo Trader Plus as of 2026-09-21.** `data_feed` in settings is `sip`; every request goes to the consolidated tape. The IEX notes below remain for reference and for anyone running the code on a Basic account.

Base URL: `https://data.alpaca.markets`. Same auth headers as trading.

## GET /v2/stocks/snapshots  (the bot's main call)

What for: latest trade, quote, current minute bar and daily bar for many symbols in one call. Called every poll interval with up to 200 symbols.

```python
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockSnapshotRequest
from alpaca.data.enums import DataFeed
data = StockHistoricalDataClient(api_key, secret_key)
snaps = data.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=["AAPL", "TSLA"], feed=DataFeed.IEX))
```

Params: `symbols` (comma-separated), `feed` (`iex`, `sip`, `delayed_sip`), `currency`.

Sample response:

```json
{
  "AAPL": {
    "latestTrade": { "t": "2022-08-17T10:18:24.114694956Z", "i": 1011, "p": 172.61, "s": 160, "x": "Q", "c": ["@", "T"], "z": "C" },
    "latestQuote": { "t": "2022-08-17T10:18:27.052763263Z", "bp": 172.6, "bs": 2, "bx": "Q", "ap": 172.7, "as": 5, "ax": "Q", "c": ["R"], "z": "C" },
    "minuteBar":   { "t": "2022-08-17T10:16:00Z", "o": 172.69, "h": 172.69, "l": 172.69, "c": 172.69, "v": 106, "n": 3, "vw": 172.688113 },
    "dailyBar":    { "t": "2022-08-16T04:00:00Z", "o": 172.62, "h": 173.71, "l": 171.6618, "c": 173.03, "v": 56457696, "n": 515139, "vw": 172.743391 },
    "prevDailyBar":{ "t": "2022-08-15T04:00:00Z", "o": 171.5, "h": 173.39, "l": 171.345, "c": 173.19, "v": 54091719, "n": 501626, "vw": 172.625371 }
  }
}
```

Field key: `t` time, `o/h/l/c` open/high/low/close, `v` volume, `n` trade count, `vw` volume-weighted average price, `p` trade price, `s` trade size, `bp/ap` bid/ask price, `bs/as` bid/ask size, `x` exchange code.

## GET /v2/stocks/bars  (backtests and warm-up)

What for: historical minute bars for backtesting and to seed the streak detector at startup with the last hour.

```python
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
bars = data.get_stock_bars(StockBarsRequest(
    symbol_or_symbols=["AAPL"], timeframe=TimeFrame.Minute,
    start="2026-09-10", end="2026-09-11", feed=DataFeed.IEX, limit=10000,
))
df = bars.df
```

Params: `symbols`, `timeframe` (`1Min`..`59Min`, `1Hour`.., `1Day`, `1Week`, `1Month`), `start`, `end`, `limit` (≤10,000), `feed`, `adjustment` (`raw`, `split`, `dividend`, `all`), `sort`, `page_token`.

Sample response:

```json
{
  "bars": {
    "AAPL": [
      { "t": "2022-01-03T09:00:00Z", "o": 178.26, "h": 178.26, "l": 178.21, "c": 178.21, "v": 1118, "n": 65, "vw": 178.235733 }
    ]
  },
  "next_page_token": "QUFQTHxNfDIwMjItMDEtMDNUMDk6MDA6MDAuMDAwMDAwMDAwWg=="
}
```

Keep calling with `page_token` until it is null. The SDK does this for you. Bar timestamps are UTC; 09:30 ET is 13:30Z in September.

Backtest note: for data older than 15 minutes the free plan allows `feed=sip`, which is the full consolidated tape. Backtests should be run with **both** feeds. SIP shows what the market did; IEX shows what the live bot would have seen.

## How far back history goes (measured 2026-09-17)

| Feed | Minute bars | Daily bars | Hours covered | Recency |
|---|---|---|---|---|
| SIP | from January 2016 | from January 2016 | extended hours included (about 700 to 950 bars/day) | everything older than 15 minutes on the free plan |
| IEX | from about 2021 | | regular hours only (about 390 bars/day) | real time |

Download speed: 50 symbols for one full day in about 1.6 s; one symbol, one month (18k bars) in 0.3 s.

**Pagination trap.** `limit` on the bars request is a hard cap on the total returned, not a page size.
Pass `limit=None` and the SDK follows `next_page_token` for you. With `limit=10000` a 50-symbol day
(about 30k bars) is silently truncated.

## GET /v1beta1/screener/stocks/most-actives  (universe)

```python
from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.requests import MostActivesRequest
screener = ScreenerClient(api_key, secret_key)
actives = screener.get_most_actives(MostActivesRequest(top=100, by="volume"))
```

Params: `by` (`volume` or `trades`), `top` (1–100). Uses SIP data even on the free plan.

Sample response:

```json
{
  "most_actives": [
    { "symbol": "AAPL", "volume": 122709184, "trade_count": 639626 }
  ],
  "last_updated": "2026-05-27T17:58:03.000Z"
}
```

## GET /v1beta1/screener/stocks/movers  (alternative universe)

```python
from alpaca.data.requests import MarketMoversRequest
movers = screener.get_market_movers(MarketMoversRequest(top=50))
```

Params: `market_type` path (`stocks`), `top` (≤50). Resets at market open; before that it shows the previous day.

Sample response:

```json
{
  "gainers": [ { "symbol": "AGRI", "percent_change": 145.56, "change": 2.46, "price": 4.15 } ],
  "losers":  [ { "symbol": "TIG",  "percent_change": -51.21, "change": -3.61, "price": 3.435 } ],
  "market_type": "stocks",
  "last_updated": "2022-03-10T17:53:30.088309839Z"
}
```

Caution: movers are dominated by tiny, volatile names. If used, the price and volume filters are essential.

## Websocket: wss://stream.data.alpaca.markets/v2/iex  (v2 feature)

Channels: `trades`, `quotes`, `bars` (minute), `updatedBars`, `dailyBars`, `statuses`. Free plan: 1 connection, 30 symbols.

```python
from alpaca.data.live import StockDataStream
stream = StockDataStream(api_key, secret_key, feed=DataFeed.IEX)
async def on_bar(bar): ...
stream.subscribe_bars(on_bar, "AAPL", "TSLA")
stream.run()
```

Sample bar message:

```json
{ "T": "b", "S": "SPY", "o": 388.985, "h": 389.13, "l": 388.975, "c": 389.12, "v": 49378, "n": 461, "vw": 389.062639, "t": "2021-02-22T19:15:00Z" }
```

Exceeding the symbol limit returns error 405; a second connection returns 406.
