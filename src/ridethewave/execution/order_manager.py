"""Turns strategy signals into broker orders and tracks them to completion."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from loguru import logger

from ridethewave.config import EntrySettings, ExitSettings
from ridethewave.execution.broker import Broker, OrderResult
from ridethewave.execution.position_book import PendingExit, PositionBook
from ridethewave.models import PendingEntry, Position, Signal, SignalType, Trade
from ridethewave.portfolio.allocator import CapitalAllocator
from ridethewave.storage import Database


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
        self._seq = 0
        self.trades: list[Trade] = []

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
        pos = self.book.positions.get(sig.symbol)
        if pos is None or pos.exit_pending:
            return
        pos.exit_pending = True
        if pos.stop_order_id:
            self.broker.cancel(pos.stop_order_id)
            pos.stop_order_id = None
        cid = self._next_client_id(sig.symbol, "sell", now)
        res = self.broker.submit_market_sell(sig.symbol, pos.qty, cid)
        self.book.pending_exits[sig.symbol] = PendingExit(sig.symbol, res.id, now, sig.reason)
        self._record(res, reason=sig.reason)

    # ---------- polling ----------
    def poll(self, now: datetime) -> list[Trade]:
        """Check in-flight orders. Returns any trades completed on this poll."""
        completed: list[Trade] = []
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
                    completed.append(t)
                    self.trades.append(t)
                    if self.db is not None:
                        t.strategy = self.strategy
                        self.db.trades.insert(t)
                        self.db.positions.delete(sym, self.strategy)
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
