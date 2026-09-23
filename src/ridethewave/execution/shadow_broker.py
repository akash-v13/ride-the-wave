"""Shadow broker: a simulated broker fed by live ticks, for strategies in incubation.

Uses the backtest SimBroker's fill logic unchanged. Each live tick becomes a one-price bar, so a
market order fills at the next tick (about 15 s later) and a limit buy fills when the next tick
prints at or below the limit. Nothing reaches Alpaca. Positions and P/L are tracked here and written
to the database with mode='shadow'.
"""

from __future__ import annotations

from datetime import datetime

from ridethewave.backtest.sim_broker import SimBroker
from ridethewave.execution.broker import Broker
from ridethewave.models import Bar, Tick


class ShadowBroker(Broker):
    def __init__(self, cash: float, slippage_pct: float = 0.05):
        self.sim = SimBroker(cash=cash, slippage_pct=slippage_pct)
        self.calls = 0

    # feed
    def on_tick(self, tick: Tick) -> None:
        self.sim.process_bar(Bar(tick.symbol, tick.ts, tick.price, tick.price, tick.price, tick.price, 0))

    def on_bar(self, bar: Bar) -> None:
        self.sim.process_bar(bar)

    # Broker interface, delegated
    def submit_limit_buy(self, symbol, qty, limit_price, client_order_id, stop_loss_price=None):
        return self.sim.submit_limit_buy(symbol, qty, limit_price, client_order_id, stop_loss_price)

    def submit_market_sell(self, symbol, qty, client_order_id):
        return self.sim.submit_market_sell(symbol, qty, client_order_id)

    def cancel(self, order_id):
        self.sim.cancel(order_id)

    def get_order(self, order_id):
        return self.sim.get_order(order_id)

    def open_orders(self):
        return self.sim.open_orders()

    def positions(self):
        return self.sim.positions()

    def account(self):
        return self.sim.account()

    def clock(self):
        return self.sim.clock()

    def close_position(self, symbol):
        return self.sim.close_position(symbol)

    def force_close_all(self, last_prices: dict[str, float], ts: datetime) -> None:
        self.sim.force_close_all(last_prices, ts)

    def equity(self) -> float:
        return self.sim.equity()
