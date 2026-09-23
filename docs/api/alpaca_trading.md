# Alpaca Trading API (paper)

Verified against docs.alpaca.markets on 2026-09-17. SDK: alpaca-py 0.44.0.

## Basics

| Item | Value |
|---|---|
| Paper base URL | `https://paper-api.alpaca.markets` |
| Live base URL (never used by this bot) | `https://api.alpaca.markets` |
| Auth headers | `APCA-API-KEY-ID`, `APCA-API-SECRET-KEY` |
| Paper account default balance | $100,000, can be reset from the dashboard by creating a new paper account |
| Paper fill simulation | Fills when marketable against NBBO; 10% of the time a random partial fill; no slippage, no market impact, no fees, no dividends |

SDK client:

```python
from alpaca.trading.client import TradingClient
client = TradingClient(api_key, secret_key, paper=True)
```

## GET /v2/account

What the bot uses it for: equity, cash and buying power at start of day and for the dashboard.

```python
acct = client.get_account()
```

Sample response:

```json
{
  "id": "1d9eed04-be39-4e01-9b84-a48ac5bbafcf",
  "status": "ACTIVE",
  "equity": "123346.11",
  "cash": "122086.5",
  "buying_power": "245432.61",
  "last_equity": "122011.09751111286868",
  "multiplier": "2",
  "long_market_value": "1259.61",
  "short_market_value": "0",
  "initial_margin": "629.8",
  "maintenance_margin": "377.88",
  "account_blocked": false,
  "trading_blocked": false,
  "transfers_blocked": false,
  "shorting_enabled": true
}
```

Note: all money fields are strings. Convert with `Decimal`.

## GET /v2/clock

What for: is the market open, and when does it next open/close. Polled once a minute.

```python
clock = client.get_clock()
```

Sample response:

```json
{
  "timestamp": "2026-09-17T14:31:05.123Z",
  "is_open": true,
  "next_open": "2026-09-18T13:30:00Z",
  "next_close": "2026-09-17T20:00:00Z"
}
```

## GET /v2/assets

What for: filter the universe to tradable stocks on major exchanges. Called once at start.

```python
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus
assets = client.get_all_assets(GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY))
```

Query params: `status` (`active`), `asset_class` (`us_equity`), `exchange` (`NYSE`, `NASDAQ`, `ARCA`, ...), `attributes`.

Sample response (one element of the array):

```json
{
  "id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
  "symbol": "AAPL",
  "name": "Apple Inc. Common Stock",
  "class": "us_equity",
  "exchange": "NASDAQ",
  "status": "active",
  "tradable": true,
  "fractionable": true,
  "shortable": true,
  "marginable": true,
  "easy_to_borrow": true,
  "borrow_status": "easy_to_borrow"
}
```

## POST /v2/orders

What for: every buy and sell.

Body fields the bot uses:

| Field | Values | Notes |
|---|---|---|
| `symbol` | e.g. `AAPL` | |
| `qty` | whole shares | We use whole shares; fractional orders cannot use stop or trailing types |
| `side` | `buy` / `sell` | |
| `type` | `market`, `limit`, `stop`, `stop_limit`, `trailing_stop` | |
| `time_in_force` | `day` (bot default), `gtc`, `opg`, `cls`, `ioc`, `fok` | |
| `limit_price` | string | required for `limit` / `stop_limit`; 2 decimals for prices ≥ $1 |
| `stop_price` | string | required for `stop` / `stop_limit` |
| `order_class` | `simple`, `bracket`, `oco`, `oto` | bot uses `oto` for entry + safety stop |
| `stop_loss` | `{"stop_price": "..."}` | with `oto`/`bracket` |
| `client_order_id` | ≤128 chars | bot sets `rtw-<date>-<symbol>-<n>` for idempotency |

SDK example (entry with safety stop):

```python
from alpaca.trading.requests import LimitOrderRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

req = LimitOrderRequest(
    symbol="AAPL", qty=5, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
    limit_price="150.15", order_class=OrderClass.OTO,
    stop_loss=StopLossRequest(stop_price="148.50"),
    client_order_id="rtw-20260917-AAPL-1",
)
order = client.submit_order(req)
```

Sample response:

```json
{
  "id": "7b08df51-c1ac-453c-99f9-323a5f075f0d",
  "client_order_id": "rtw-20260917-AAPL-1",
  "created_at": "2026-09-17T14:31:24.668464435Z",
  "submitted_at": "2026-09-17T14:31:24.577215743Z",
  "filled_at": null,
  "symbol": "AAPL",
  "asset_class": "us_equity",
  "qty": "5",
  "filled_qty": "0",
  "filled_avg_price": null,
  "order_class": "oto",
  "type": "limit",
  "side": "buy",
  "time_in_force": "day",
  "limit_price": "150.15",
  "stop_price": null,
  "status": "accepted",
  "extended_hours": false,
  "legs": [ { "...": "the stop-loss leg, status held until parent fills" } ],
  "trail_percent": null,
  "trail_price": null,
  "hwm": null
}
```

Order status values you will see: `new`, `accepted`, `partially_filled`, `filled`, `canceled`, `expired`, `rejected`, `held` (child legs).

Constraints worth remembering:
- Stop price must be at least $0.01 away from the base price.
- Bracket/OTO/OCO cannot use extended hours.
- Trailing stops only trigger in regular hours.

## GET /v2/orders, GET /v2/orders/{id}, DELETE /v2/orders/{id}

What for: poll fills each tick (v1), cancel unfilled entries after the timeout, cancel the safety stop before a client-side exit.

```python
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
open_orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
client.cancel_order_by_id(order_id)
```

## GET /v2/positions, DELETE /v2/positions/{symbol}

What for: reconcile the position book on startup; flatten at close.

```python
positions = client.get_all_positions()
client.close_position("AAPL")          # market sell of the whole position
client.close_all_positions(cancel_orders=True)
```

Sample response (one element):

```json
{
  "asset_class": "us_equity",
  "symbol": "AAPL",
  "qty": "5",
  "avg_entry_price": "100.0",
  "current_price": "120.0",
  "cost_basis": "500.0",
  "market_value": "600.0",
  "unrealized_pl": "100.0",
  "unrealized_plpc": "0.20",
  "side": "long",
  "exchange": "NASDAQ",
  "lastday_price": "119.0",
  "change_today": "0.0084",
  "unrealized_intraday_pl": "10.0",
  "unrealized_intraday_plpc": "0.0084",
  "qty_available": "4"
}
```

`qty_available` is less than `qty` when some shares are tied up in an open sell order.

## Trade updates websocket (v2)

`wss://paper-api.alpaca.markets/stream`, channel `trade_updates`. Events: `new`, `partial_fill`, `fill`, `canceled`, `expired`, `rejected`. A `fill` event carries `timestamp`, `price`, `qty`, `position_qty` and the full order object.

```python
from alpaca.trading.stream import TradingStream
stream = TradingStream(api_key, secret_key, paper=True)
async def on_update(data): ...
stream.subscribe_trade_updates(on_update)
stream.run()
```

## Rules that matter for a day-trading bot

- **Pattern Day Trader rule is retired.** FINRA replaced it on 2026-06-04 with an intraday margin framework. No 4-trades-in-5-days limit and no $25k threshold. The account must keep intraday margin adequate; a deficit under $1,000 or 5% of equity is disregarded. Paper accounts start with $100k and 2x margin, so this will not bind.
- **Rate limit** for trading endpoints: 200 requests/min on the basic tier. The bot budgets for 20/min.
