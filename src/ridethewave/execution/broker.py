"""Broker interface plus the Alpaca implementation.

The interface is intentionally tiny: the bot only ever places limit buys (optionally with a
protective stop leg), market sells, cancels, and reads back orders/positions/account/clock.
``SimBroker`` in the backtest package implements the same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, LimitOrderRequest, MarketOrderRequest, StopLossRequest
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

FILLED = "filled"
TERMINAL = {"filled", "canceled", "expired", "rejected", "done_for_day", "replaced", "stopped", "suspended"}


@dataclass(slots=True)
class OrderResult:
    id: str
    client_order_id: str
    symbol: str
    side: str
    type: str
    status: str
    qty: float
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    legs: list[OrderResult] = field(default_factory=list)

    @property
    def is_filled(self) -> bool:
        return self.status == FILLED

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL


@dataclass(slots=True)
class BrokerPosition:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float | None


@dataclass(slots=True)
class AccountInfo:
    equity: float
    cash: float
    buying_power: float


@dataclass(slots=True)
class ClockInfo:
    now: datetime
    is_open: bool
    next_open: datetime
    next_close: datetime


class Broker(ABC):
    @abstractmethod
    def submit_limit_buy(
        self, symbol: str, qty: float, limit_price: float, client_order_id: str, stop_loss_price: float | None = None
    ) -> OrderResult: ...

    @abstractmethod
    def submit_market_sell(self, symbol: str, qty: float, client_order_id: str) -> OrderResult: ...

    @abstractmethod
    def cancel(self, order_id: str) -> None: ...

    @abstractmethod
    def get_order(self, order_id: str) -> OrderResult: ...

    @abstractmethod
    def open_orders(self) -> list[OrderResult]: ...

    @abstractmethod
    def positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    def account(self) -> AccountInfo: ...

    @abstractmethod
    def clock(self) -> ClockInfo: ...

    @abstractmethod
    def close_position(self, symbol: str) -> OrderResult | None: ...


def _f(x) -> float | None:
    return None if x is None else float(x)


def _to_result(o) -> OrderResult:
    return OrderResult(
        id=str(o.id),
        client_order_id=o.client_order_id or "",
        symbol=o.symbol or "",
        side=str(getattr(o.side, "value", o.side)),
        type=str(getattr(o.type, "value", o.type)),
        status=str(getattr(o.status, "value", o.status)),
        qty=_f(o.qty) or 0.0,
        filled_qty=_f(o.filled_qty) or 0.0,
        filled_avg_price=_f(o.filled_avg_price),
        limit_price=_f(o.limit_price),
        stop_price=_f(o.stop_price),
        submitted_at=o.submitted_at,
        filled_at=o.filled_at,
        legs=[_to_result(l) for l in (o.legs or [])],
    )


class AlpacaBroker(Broker):
    def __init__(self, client: TradingClient):
        self.client = client
        self.calls = 0

    def _retry(self, fn, *a, **kw):
        @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=4), reraise=True)
        def go():
            self.calls += 1
            return fn(*a, **kw)

        return go()

    def submit_limit_buy(self, symbol, qty, limit_price, client_order_id, stop_loss_price=None):
        kwargs = dict(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(limit_price, 2),
            client_order_id=client_order_id,
        )
        if stop_loss_price is not None:
            kwargs["order_class"] = OrderClass.OTO
            kwargs["stop_loss"] = StopLossRequest(stop_price=round(stop_loss_price, 2))
        o = self._retry(self.client.submit_order, LimitOrderRequest(**kwargs))
        logger.info("BUY submitted {} x{} @ {} stop={} id={}", symbol, qty, limit_price, stop_loss_price, o.id)
        return _to_result(o)

    def submit_market_sell(self, symbol, qty, client_order_id):
        o = self._retry(
            self.client.submit_order,
            MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                client_order_id=client_order_id,
            ),
        )
        logger.info("SELL submitted {} x{} market id={}", symbol, qty, o.id)
        return _to_result(o)

    def cancel(self, order_id):
        try:
            self._retry(self.client.cancel_order_by_id, order_id)
        except Exception as e:  # noqa: BLE001  (already filled/cancelled is fine)
            logger.debug("cancel {} ignored: {}", order_id, e)

    def get_order(self, order_id):
        return _to_result(self._retry(self.client.get_order_by_id, order_id))

    def open_orders(self):
        orders = self._retry(self.client.get_orders, GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True))
        return [_to_result(o) for o in orders]

    def positions(self):
        return [
            BrokerPosition(p.symbol, float(p.qty), float(p.avg_entry_price), _f(p.current_price))
            for p in self._retry(self.client.get_all_positions)
        ]

    def account(self):
        a = self._retry(self.client.get_account)
        return AccountInfo(float(a.equity), float(a.cash), float(a.buying_power))

    def clock(self):
        c = self._retry(self.client.get_clock)
        return ClockInfo(
            c.timestamp.astimezone(timezone.utc),
            c.is_open,
            c.next_open.astimezone(timezone.utc),
            c.next_close.astimezone(timezone.utc),
        )

    def close_position(self, symbol):
        try:
            o = self._retry(self.client.close_position, symbol)
            return _to_result(o)
        except Exception as e:  # noqa: BLE001
            logger.warning("close_position {} failed: {}", symbol, e)
            return None

    # ---------- option structures (feature 22) ----------
    def submit_structure(self, legs: list[dict], qty: int) -> str:
        """Place a resolved structure on the paper account. ``legs``: [{symbol, instrument, side, ratio}].
        Stock legs go first as separate market orders (Alpaca's multi-leg order is options only, at most
        four legs, no naked short legs at level 3); the option legs go as one MLEG market order. Returns
        the last broker order id. Verified request shape 2026-09-23, docs/api/options.md."""
        from alpaca.trading.requests import OptionLegRequest

        stock_legs = [x for x in legs if x["instrument"] == "stock"]
        option_legs = [x for x in legs if x["instrument"] != "stock"]
        last_id = ""
        for leg in stock_legs:
            o = self._retry(
                self.client.submit_order,
                MarketOrderRequest(
                    symbol=leg["symbol"],
                    qty=leg["ratio"] * qty,
                    side=OrderSide.BUY if leg["side"] == "buy" else OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                ),
            )
            last_id = str(o.id)
            logger.info("structure stock leg {} {} x{} id={}", leg["side"], leg["symbol"], leg["ratio"] * qty, o.id)
        if len(option_legs) == 1:
            leg = option_legs[0]
            o = self._retry(
                self.client.submit_order,
                MarketOrderRequest(
                    symbol=leg["symbol"],
                    qty=leg["ratio"] * qty,
                    side=OrderSide.BUY if leg["side"] == "buy" else OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                ),
            )
            last_id = str(o.id)
        elif option_legs:
            o = self._retry(
                self.client.submit_order,
                MarketOrderRequest(
                    qty=qty,
                    order_class=OrderClass.MLEG,
                    time_in_force=TimeInForce.DAY,
                    legs=[
                        OptionLegRequest(
                            symbol=leg["symbol"],
                            ratio_qty=leg["ratio"],
                            side=OrderSide.BUY if leg["side"] == "buy" else OrderSide.SELL,
                        )
                        for leg in option_legs
                    ],
                ),
            )
            last_id = str(o.id)
            logger.info("MLEG order {}: {} option legs x{}", o.id, len(option_legs), qty)
        return last_id
