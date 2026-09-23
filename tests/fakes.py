"""A fake broker for unit tests: fills are controlled by the test."""

from __future__ import annotations

from datetime import datetime, timezone

from ridethewave.execution.broker import AccountInfo, Broker, BrokerPosition, ClockInfo, OrderResult


class FakeBroker(Broker):
    def __init__(self):
        self.orders: dict[str, OrderResult] = {}
        self.cancelled: list[str] = []
        self._n = 0
        self._positions: list[BrokerPosition] = []

    def _new(self, symbol, side, type, qty, limit=None, stop=None, cid="") -> OrderResult:
        self._n += 1
        o = OrderResult(
            id=f"o{self._n}",
            client_order_id=cid,
            symbol=symbol,
            side=side,
            type=type,
            status="accepted",
            qty=qty,
            limit_price=limit,
            stop_price=stop,
            submitted_at=datetime.now(timezone.utc),
        )
        self.orders[o.id] = o
        return o

    def submit_limit_buy(self, symbol, qty, limit_price, client_order_id, stop_loss_price=None):
        o = self._new(symbol, "buy", "limit", qty, limit=limit_price, cid=client_order_id)
        if stop_loss_price is not None:
            leg = self._new(symbol, "sell", "stop", qty, stop=stop_loss_price)
            leg.status = "held"
            o.legs = [leg]
        return o

    def submit_market_sell(self, symbol, qty, client_order_id):
        return self._new(symbol, "sell", "market", qty, cid=client_order_id)

    def cancel(self, order_id):
        self.cancelled.append(order_id)
        o = self.orders.get(order_id)
        if o and not o.is_terminal:
            o.status = "canceled"

    def get_order(self, order_id):
        return self.orders[order_id]

    def open_orders(self):
        return [o for o in self.orders.values() if not o.is_terminal]

    def positions(self):
        return list(self._positions)

    def account(self):
        return AccountInfo(100000, 100000, 200000)

    def clock(self):
        now = datetime.now(timezone.utc)
        return ClockInfo(now, True, now, now)

    def close_position(self, symbol):
        return None

    # test helpers
    def fill(self, order_id: str, price: float, at: datetime | None = None, qty: float | None = None):
        o = self.orders[order_id]
        o.status = "filled"
        o.filled_qty = qty if qty is not None else o.qty
        o.filled_avg_price = price
        o.filled_at = at or datetime.now(timezone.utc)
