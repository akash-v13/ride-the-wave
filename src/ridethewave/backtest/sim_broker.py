"""A pretend broker for backtests. Implements the same interface as AlpacaBroker.

Fill model (deliberately a little pessimistic, since paper trading is optimistic):
- A limit buy submitted after bar T fills on the next bar for that symbol if that bar's low
  reaches the limit. Fill price = min(limit, next open) plus slippage.
- A market sell fills at the next bar's open minus slippage.
- A protective stop (child of a filled buy) fills when a bar's low touches it, at
  min(stop, bar open) minus slippage, i.e. a gap down fills at the open, not the stop.
- Nothing fills inside the bar the decision was made on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ridethewave.execution.broker import AccountInfo, Broker, BrokerPosition, ClockInfo, OrderResult
from ridethewave.models import Bar


@dataclass(slots=True)
class _SimPos:
    qty: float
    avg_price: float
    last: float


@dataclass
class SimBroker(Broker):
    cash: float
    slippage_pct: float = 0.05
    now: datetime = field(default_factory=lambda: datetime.min)
    orders: dict[str, OrderResult] = field(default_factory=dict)
    positions_: dict[str, _SimPos] = field(default_factory=dict)
    _n: int = 0
    fills: int = 0

    # ----- interface -----
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
        o = self.orders.get(order_id)
        if o and not o.is_terminal:
            o.status = "canceled"

    def get_order(self, order_id):
        return self.orders[order_id]

    def open_orders(self):
        return [o for o in self.orders.values() if o.status in ("accepted", "new")]

    def positions(self):
        return [BrokerPosition(s, p.qty, p.avg_price, p.last) for s, p in self.positions_.items() if p.qty > 0]

    def account(self):
        eq = self.equity()
        return AccountInfo(eq, self.cash, self.cash)

    def clock(self):
        return ClockInfo(self.now, True, self.now, self.now)

    def close_position(self, symbol):
        p = self.positions_.get(symbol)
        if not p or p.qty <= 0:
            return None
        return self.submit_market_sell(symbol, p.qty, f"close-{symbol}")

    # ----- simulation -----
    def equity(self) -> float:
        return self.cash + sum(p.qty * p.last for p in self.positions_.values())

    def process_bar(self, bar: Bar) -> None:
        """Fill any working orders for this symbol against this bar, then mark to market."""
        self.now = bar.ts
        slip = self.slippage_pct / 100.0
        for o in list(self.orders.values()):
            if o.symbol != bar.symbol:
                continue
            if o.status == "accepted" and o.type == "limit" and o.side == "buy":
                if bar.low <= o.limit_price:
                    px = min(o.limit_price, bar.open) * (1 + slip)
                    self._fill(o, px, bar.ts)
                    self._open(o.symbol, o.qty, px)
                    for leg in o.legs:
                        leg.status = "accepted"
            elif o.status == "accepted" and o.type == "market" and o.side == "sell":
                px = bar.open * (1 - slip)
                self._fill(o, px, bar.ts)
                self._close(o.symbol, o.qty, px)
            elif o.status == "accepted" and o.type == "stop" and o.side == "sell":
                if bar.low <= o.stop_price and self.positions_.get(o.symbol, _SimPos(0, 0, 0)).qty > 0:
                    px = min(o.stop_price, bar.open) * (1 - slip)
                    self._fill(o, px, bar.ts)
                    self._close(o.symbol, o.qty, px)
        p = self.positions_.get(bar.symbol)
        if p:
            p.last = bar.close

    def force_close_all(self, last_prices: dict[str, float], ts: datetime) -> None:
        """End of a backtest day: liquidate at the last known close. If the order manager already has a
        working market sell for the symbol, fill THAT order (so its trade is recorded with its reason)
        instead of creating a second one."""
        for sym, p in list(self.positions_.items()):
            if p.qty <= 0 or sym not in last_prices:
                continue
            px = last_prices[sym] * (1 - self.slippage_pct / 100.0)
            working = next(
                (
                    o
                    for o in self.orders.values()
                    if o.symbol == sym and o.side == "sell" and o.type == "market" and o.status == "accepted"
                ),
                None,
            )
            o = working or self.submit_market_sell(sym, p.qty, f"eod-{sym}")
            self._fill(o, px, ts)
            self._close(sym, p.qty, px)

    # ----- internals -----
    def _new(self, symbol, side, type, qty, limit=None, stop=None, cid="") -> OrderResult:
        self._n += 1
        o = OrderResult(
            id=f"sim{self._n}",
            client_order_id=cid,
            symbol=symbol,
            side=side,
            type=type,
            status="accepted",
            qty=qty,
            limit_price=limit,
            stop_price=stop,
            submitted_at=self.now,
        )
        self.orders[o.id] = o
        return o

    def _fill(self, o: OrderResult, px: float, ts: datetime) -> None:
        o.status = "filled"
        o.filled_qty = o.qty
        o.filled_avg_price = round(px, 4)
        o.filled_at = ts
        self.fills += 1

    def _open(self, symbol: str, qty: float, px: float) -> None:
        self.cash -= qty * px
        p = self.positions_.get(symbol)
        if p and p.qty > 0:
            total = p.qty + qty
            p.avg_price = (p.avg_price * p.qty + px * qty) / total
            p.qty = total
        else:
            self.positions_[symbol] = _SimPos(qty, px, px)

    def _close(self, symbol: str, qty: float, px: float) -> None:
        p = self.positions_.get(symbol)
        if not p:
            return
        q = min(qty, p.qty)
        self.cash += q * px
        p.qty -= q
        if p.qty <= 0:
            self.positions_.pop(symbol, None)
        # any other working sell orders for this symbol are now moot
        for o in self.orders.values():
            if o.symbol == symbol and o.side == "sell" and o.status in ("accepted", "held"):
                o.status = "canceled"
