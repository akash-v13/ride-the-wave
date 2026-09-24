# Alpaca options API (verified 2026-09-23)

What we checked against the live paper account and the data API, with `alpaca-py` 0.44, and what
the code relies on. Re-verify against https://docs.alpaca.markets when in doubt.

## Account

`TradingClient.get_account()` on the paper account:

| Field | Value on 2026-09-23 |
| --- | --- |
| `options_approved_level` | 3 (the maximum: multi-leg spreads allowed) |
| `options_trading_level` | 3 |
| `options_buying_power` | 100,000 |

Level 3 accepts multi-leg orders of up to four legs with no naked short leg. 17 of the 57 book
structures have a naked short leg and are therefore shadow-only in our config (`OptionsSpec`
refuses `mode: live` for them).

## Contracts

`TradingClient.get_option_contracts(GetOptionContractsRequest(underlying_symbols=["SPY"],
expiration_date_gte=..., expiration_date_lte=..., type=ContractType.PUT, limit=5))` returns
`OptionContractsResponse` with `option_contracts` (each: `symbol` OCC, `expiration_date`,
`strike_price`, `tradable`, `open_interest`) and `next_page_token`. Sample:

```
('SPY261016P00300000', '2026-10-16', 300.0, True, '5205')
('SPY261016P00305000', '2026-10-16', 305.0, True, '2490')
```

## Market data (Algo Trader Plus)

`OptionHistoricalDataClient.get_option_chain(OptionChainRequest(underlying_symbol="SPY",
feed=OptionsFeed.OPRA, expiration_date_gte, expiration_date_lte, strike_price_gte, strike_price_lte,
type=...))` returns `{occ_symbol: OptionsSnapshot}` with `latest_quote` (bid/ask price and size),
`latest_trade`, `implied_volatility` and `greeks` (delta, gamma, theta, vega, rho). Both feeds work
on this plan; OPRA is the real-time consolidated feed and is what the bot uses. Sample, 47 SPY puts
between 700 and 720 for 16 October 2026:

```
opra:       SPY261016P00708000  bid 0.95  ask 0.96  iv 0.211   delta -0.0543
indicative: SPY261016P00710000  bid 0.98  ask 1.03  iv 0.2076  delta -0.0576
```

`get_option_latest_quote(OptionLatestQuoteRequest(symbol_or_symbols=[...], feed=OptionsFeed.OPRA))`
returns quotes for a list of contracts in one call (used to value open structures).

## Orders

Multi-leg: `MarketOrderRequest(qty=n, order_class=OrderClass.MLEG, time_in_force=TimeInForce.DAY,
legs=[OptionLegRequest(symbol=occ, ratio_qty=r, side=OrderSide.BUY|SELL), ...])` with no `symbol`
on the parent request. Stock legs (covered calls, collars) are separate equity market orders placed
first. The code path is `AlpacaBroker.submit_structure` in `src/ridethewave/execution/broker.py`;
it has not yet been exercised with a real order (all options slots run in shadow). Options orders
are only accepted during regular hours; a DAY order placed after the close is queued for the open.

## OCC symbols

`ROOT + YYMMDD + C|P + strike*1000` as 8 digits, e.g. `SPY261016P00708000` = SPY put, 16 October
2026, strike 708. Parsed by `ridethewave.options.chain.parse_occ`.
