# docs/api

Reference notes for every external API the bot calls, with the endpoints we use, why we use them, SDK snippets and sample responses.

- [alpaca_trading.md](alpaca_trading.md): account, clock, assets, orders, positions, trade-updates stream, and the trading rules (PDT retirement) that affect a day-trading bot.
- [alpaca_market_data.md](alpaca_market_data.md): plan limits, snapshots, historical bars, screener, IEX websocket.

Each file records the date it was verified against docs.alpaca.markets. Re-verify when upgrading alpaca-py.
- `options.md`: account options level, contracts, OPRA chain snapshots and greeks, multi-leg orders (verified 2026-09-23).
