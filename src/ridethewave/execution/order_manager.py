"""Turns strategy signals into broker orders and tracks them to completion."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta

from loguru import logger

from ridethewave.config import EntrySettings, ExitSettings
from ridethewave.execution.broker import Broker, OrderResult
from ridethewave.execution.position_book import PendingExit, PositionBook
from ridethewave.models import PendingEntry, Position, Signal, SignalType, Trade
from ridethewave.portfolio.allocator import CapitalAllocator
from ridethewave.storage import Database

# After cancelling a protective stop, Alpaca may answer "pending_cancel" before the order settles as cancelled
# or filled. Wait this many times this long for the final state before deciding whether to sell.
STOP_SETTLE_CHECKS = 4
STOP_SETTLE_WAIT_S = 0.5


class OrderManager:
    def __init__(
        self,
        broker: Broker,
        book: PositionBook,
        allocator: CapitalAllocator,
        db: Database | None,
        entry: EntrySettings,
        exit: ExitSettings,
        run_id: str,
        mode: str,
        ask_lookup: Callable[[str], float | None] | None = None,
        strategy: str = "wave_rider",
        protective_stop: bool = True,
        strategy_obj=None,
        verify_holdings: bool = False,
    ):
        self.broker = broker
        self.book = book
        self.allocator = allocator
        self.db = db
        self.entry = entry
        self.exit = exit
        self.run_id = run_id
        self.mode = mode
        self.ask_lookup = ask_lookup or (lambda s: None)
        self.strategy = strategy
        self.protective_stop = protective_stop
        self.strategy_obj = strategy_obj  # optional: qty_for()/stops for strategy-specific sizing and stops
        # Live slots only: before a market sell, ask the broker how many shares it really holds and never sell more.
        # A sell beyond the holding opens a short. Off for shadow and backtest brokers, which simulate holdings.
        self.verify_holdings = verify_holdings
        self._sleep = time.sleep  # replaced in tests
        self._seq = 0
        self.trades: list[Trade] = []
        self._booked: list[Trade] = []  # trades closed outside poll(), handed out by the next poll()

    # ---------- signals ----------
    def handle(self, signals: list[Signal], now: datetime) -> None:
        for sig in signals:
            try:
                if sig.type == SignalType.BUY:
                    self._buy(sig, now)
                else:
                    self._sell(sig, now)
            except Exception as e:  # noqa: BLE001
                logger.error("signal {} {} failed: {}", sig.type.value, sig.symbol, e)

    def _next_client_id(self, symbol: str, kind: str, now: datetime) -> str:
        self._seq += 1
        return f"rtw-{self.strategy[:12]}-{now:%Y%m%d}-{symbol}-{kind}-{self._seq}"

    def _buy(self, sig: Signal, now: datetime) -> None:
        if self.book.has(sig.symbol) or sig.symbol in self.book.pending_entries:
            return
        if self.book.open_slots(self.entry.max_positions) <= 0:
            return
        ask = self.ask_lookup(sig.symbol) or sig.reference_price
        limit = round(max(ask, sig.reference_price) * (1.0 + self.entry.entry_limit_buffer_pct / 100.0), 2)
        qty = self.allocator.qty_for(limit)
        if self.strategy_obj is not None and hasattr(self.strategy_obj, "qty_for"):
            custom = self.strategy_obj.qty_for(
                sig.symbol, limit, self.allocator.allocation, self.allocator.slot_dollars()
            )
            if custom is not None:
                qty = custom
        if qty <= 0:
            logger.warning(
                "BUY {} skipped: slot ${:.0f} too small for price {:.2f}",
                sig.symbol,
                self.allocator.slot_dollars(),
                limit,
            )
            return
        stop = None
        _, _, stop_pct = self.exit.effective(sig.noise_pct)
        if stop_pct > 0 and self.protective_stop:
            stop = round(limit * (1.0 - stop_pct / 100.0), 2)
        custom_stop = getattr(self.strategy_obj, "stops", {}).get(sig.symbol) if self.strategy_obj is not None else None
        if custom_stop is not None and self.protective_stop:
            stop = round(min(custom_stop, limit * 0.999), 2)
        cid = self._next_client_id(sig.symbol, "buy", now)
        res = self.broker.submit_limit_buy(sig.symbol, qty, limit, cid, stop_loss_price=stop)
        self.book.pending_entries[sig.symbol] = PendingEntry(
            symbol=sig.symbol,
            order_id=res.id,
            client_order_id=cid,
            submitted_at=now,
            limit_price=limit,
            qty=qty,
            noise_pct=sig.noise_pct,
        )
        self._record(res, reason=sig.reason)

    def _sell(self, sig: Signal, now: datetime) -> None:
        """Exit a position: cancel its protective stop, then sell at market.

        On 2026-10-29 the stop sold NUWE six seconds before the bot's own exit fired. The bot ignored the
        "already filled" reply to its cancel and sent a market sell for shares it no longer held; Alpaca refused
        only because NUWE could not be shorted. Two guards now prevent that:
        1. After the cancel, read the stop's final state. If it filled, book the stop's fill and sell nothing;
           if it filled in part, sell only the rest.
        2. Live slots (`verify_holdings`): never sell more than the broker says it holds."""
        pos = self.book.positions.get(sig.symbol)
        if pos is None or pos.exit_pending:
            return
        pos.exit_pending = True
        qty = pos.qty
        if pos.stop_order_id:
            stop = self._settle_stop(pos.stop_order_id)
            if stop is not None and stop.is_filled:
                logger.warning(
                    "{} [{}]: the protective stop already sold it at {}; booking that fill, no market sell",
                    sig.symbol,
                    self.strategy,
                    stop.filled_avg_price,
                )
                self._booked.append(self._book_stop_fill(sig.symbol, stop, now))
                return
            if stop is not None and stop.filled_qty:
                logger.warning(
                    "{}: protective stop filled {} of {}; selling the rest", sig.symbol, stop.filled_qty, qty
                )
                qty = max(0.0, qty - stop.filled_qty)
            pos.stop_order_id = None
        if self.verify_holdings:
            held = self._held(sig.symbol)
            if held is not None and held < qty:
                if held <= 0:
                    logger.error(
                        "{} [{}]: the broker holds none, so a sell would open a short; dropping it from the book "
                        "without a trade record (closed outside the bot)",
                        sig.symbol,
                        self.strategy,
                    )
                    self.book.positions.pop(sig.symbol, None)
                    if self.db is not None:
                        self.db.positions.delete(sig.symbol, self.strategy)
                    return
                logger.warning("{}: the broker holds {} of {}; selling only that", sig.symbol, held, qty)
                qty = held
        if qty <= 0:
            return
        cid = self._next_client_id(sig.symbol, "sell", now)
        res = self.broker.submit_market_sell(sig.symbol, qty, cid)
        self.book.pending_exits[sig.symbol] = PendingExit(sig.symbol, res.id, now, sig.reason)
        self._record(res, reason=sig.reason)

    def _settle_stop(self, stop_id: str) -> OrderResult | None:
        """Cancel the protective stop and return its final state (cancelled, filled or partly filled).
        None when the broker cannot say; the caller then sells as before."""
        self.broker.cancel(stop_id)
        res: OrderResult | None = None
        for i in range(STOP_SETTLE_CHECKS):
            try:
                res = self.broker.get_order(stop_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("could not read stop {} after cancelling: {}", stop_id, e)
                return None
            if res.status != "pending_cancel":
                return res
            if i < STOP_SETTLE_CHECKS - 1:
                self._sleep(STOP_SETTLE_WAIT_S)
        return res

    def _held(self, symbol: str) -> float | None:
        """Shares the broker holds in ``symbol`` (0 when none), or None when it cannot be read."""
        try:
            return sum(bp.qty for bp in self.broker.positions() if bp.symbol == symbol)
        except Exception as e:  # noqa: BLE001
            logger.warning("could not read broker positions before selling {}: {}", symbol, e)
            return None

    def _book_stop_fill(self, sym: str, res: OrderResult, now: datetime) -> Trade:
        """Close the book position at the protective stop's fill and store the trade."""
        self._record(res)
        t = self.book.close(
            sym,
            res.filled_avg_price or 0.0,
            res.filled_at or now,
            "server_stop",
            self.mode,
            self.run_id,
            exit_order_id=res.id,
        )
        self.trades.append(t)
        if self.db is not None:
            t.strategy = self.strategy
            self.db.trades.insert(t)
            self.db.positions.delete(sym, self.strategy)
        return t

    # ---------- polling ----------
    def poll(self, now: datetime) -> list[Trade]:
        """Check in-flight orders. Returns any trades completed on this poll (and any booked since the last one)."""
        completed: list[Trade] = self._booked
        self._booked = []
        for sym, pe in list(self.book.pending_entries.items()):
            res = self.broker.get_order(pe.order_id)
            self._record(res)
            if res.is_filled:
                stop_id = next((l.id for l in res.legs if l.type in ("stop", "stop_limit")), None)
                pos = Position(
                    symbol=sym,
                    qty=res.filled_qty or pe.qty,
                    entry_price=res.filled_avg_price or pe.limit_price,
                    entry_time=res.filled_at or now,
                    peak_price=res.filled_avg_price or pe.limit_price,
                    last_price=res.filled_avg_price or pe.limit_price,
                    entry_order_id=res.id,
                    stop_order_id=stop_id,
                    noise_pct=pe.noise_pct,
                    strategy=self.strategy,
                )
                self.book.open(pos)
            elif res.is_terminal:
                logger.info("entry {} ended as {}", sym, res.status)
                self.book.pending_entries.pop(sym, None)
            elif now - pe.submitted_at > timedelta(seconds=self.entry.entry_fill_timeout_seconds):
                logger.info("entry {} unfilled after timeout; cancelling", sym)
                self.broker.cancel(pe.order_id)
                if res.filled_qty and res.filled_qty > 0:
                    # partial fill: keep what we got
                    pos = Position(
                        symbol=sym,
                        qty=res.filled_qty,
                        entry_price=res.filled_avg_price or pe.limit_price,
                        entry_time=now,
                        peak_price=res.filled_avg_price or pe.limit_price,
                        last_price=res.filled_avg_price or pe.limit_price,
                        entry_order_id=res.id,
                        noise_pct=pe.noise_pct,
                        strategy=self.strategy,
                    )
                    self.book.open(pos)
                else:
                    self.book.pending_entries.pop(sym, None)

        for sym, px in list(self.book.pending_exits.items()):
            res = self.broker.get_order(px.order_id)
            self._record(res)
            if res.is_filled:
                code = px.reason.split(" | ")[0]
                t = self.book.close(
                    sym,
                    res.filled_avg_price or 0.0,
                    res.filled_at or now,
                    code,
                    self.mode,
                    self.run_id,
                    exit_order_id=res.id,
                )
                completed.append(t)
                self.trades.append(t)
                if self.db is not None:
                    t.strategy = self.strategy
                    self.db.trades.insert(t)
                    self.db.positions.delete(sym, self.strategy)
            elif res.is_terminal:
                logger.warning("exit {} ended as {}; will retry", sym, res.status)
                self.book.pending_exits.pop(sym, None)
                pos = self.book.positions.get(sym)
                if pos:
                    pos.exit_pending = False

        # A server-side stop may have fired while we were not looking.
        for sym, pos in list(self.book.positions.items()):
            if pos.stop_order_id and not pos.exit_pending:
                res = self.broker.get_order(pos.stop_order_id)
                if res.is_filled:
                    completed.append(self._book_stop_fill(sym, res, now))
        return completed

    def flatten_all(self, now: datetime, reason: str = "close_flatten") -> None:
        for sym, pos in list(self.book.positions.items()):
            if not pos.exit_pending:
                self._sell(Signal(SignalType.SELL, sym, now, reason, pos.last_price, pos.qty), now)

    def cancel_pending_entries(self) -> None:
        for sym, pe in list(self.book.pending_entries.items()):
            self.broker.cancel(pe.order_id)
            self.book.pending_entries.pop(sym, None)

    def _record(self, res: OrderResult, reason: str | None = None) -> None:
        if self.db is None:
            return
        self.db.orders.upsert(
            id=res.id,
            client_order_id=res.client_order_id,
            run_id=self.run_id,
            mode=self.mode,
            symbol=res.symbol,
            side=res.side,
            type=res.type,
            status=res.status,
            qty=res.qty,
            limit_price=res.limit_price,
            stop_price=res.stop_price,
            filled_qty=res.filled_qty,
            filled_avg_price=res.filled_avg_price,
            submitted_at=res.submitted_at,
            filled_at=res.filled_at,
            reason=reason,
        )
        for leg in res.legs:
            self.db.orders.upsert(
                id=leg.id,
                client_order_id=leg.client_order_id,
                run_id=self.run_id,
                mode=self.mode,
                symbol=leg.symbol,
                side=leg.side,
                type=leg.type,
                status=leg.status,
                qty=leg.qty,
                stop_price=leg.stop_price,
                filled_qty=leg.filled_qty,
                filled_avg_price=leg.filled_avg_price,
                submitted_at=leg.submitted_at,
                filled_at=leg.filled_at,
                parent_id=res.id,
                reason="safety_stop",
            )
