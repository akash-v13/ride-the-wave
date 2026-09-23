# execution

Turning signals into orders and tracking what we hold.

- `broker.py`: `Broker` interface (submit, cancel, get_orders, get_positions, close_position). Implemented by `AlpacaBroker` here and `SimBroker` in `backtest/`.
- `order_manager.py`: builds order requests from signals (limit entry with OTO safety stop, market exit), enforces per-symbol and per-day limits, cancels stale entries, polls for fills.
- `position_book.py`: in-memory record of open positions with entry price, quantity, peak, entry time and the safety-stop order id. Reconciles with Alpaca on startup.
- `shadow_broker.py`: `ShadowBroker`, the backtest `SimBroker` fed by live ticks, for strategies in incubation (mode `shadow`): same order manager, no real orders.
