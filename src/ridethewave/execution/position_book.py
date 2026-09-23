"""The bot's own memory of what it holds and what is in flight."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from ridethewave.execution.broker import BrokerPosition
from ridethewave.models import PendingEntry, Position, Trade


@dataclass(slots=True)
class PendingExit:
    symbol: str
    order_id: str
    submitted_at: datetime
    reason: str


@dataclass
class PositionBook:
    positions: dict[str, Position] = field(default_factory=dict)
    pending_entries: dict[str, PendingEntry] = field(default_factory=dict)
    pending_exits: dict[str, PendingExit] = field(default_factory=dict)
    entries_today: dict[str, int] = field(default_factory=dict)

    def open_slots(self, max_positions: int) -> int:
        return max(0, max_positions - len(self.positions) - len(self.pending_entries))

    def has(self, symbol: str) -> bool:
        return symbol in self.positions

    def open(self, pos: Position) -> None:
        self.positions[pos.symbol] = pos
        self.pending_entries.pop(pos.symbol, None)
        self.entries_today[pos.symbol] = self.entries_today.get(pos.symbol, 0) + 1
        logger.info("OPEN {} x{} @ {:.2f}", pos.symbol, pos.qty, pos.entry_price)

    def close(
        self,
        symbol: str,
        exit_price: float,
        exit_time: datetime,
        reason: str,
        mode: str,
        run_id: str,
        exit_order_id: str | None = None,
    ) -> Trade:
        pos = self.positions.pop(symbol)
        self.pending_exits.pop(symbol, None)
        t = Trade(
            symbol=symbol,
            qty=pos.qty,
            entry_price=pos.entry_price,
            entry_time=pos.entry_time,
            exit_price=exit_price,
            exit_time=exit_time,
            exit_reason=reason,
            peak_price=pos.peak_price,
            mode=mode,
            run_id=run_id,
            entry_order_id=pos.entry_order_id,
            exit_order_id=exit_order_id,
            strategy=pos.strategy,
        )
        logger.info(
            "CLOSE {} x{} @ {:.2f} pnl={:+.2f} ({:+.2f}%) [{}]", symbol, t.qty, exit_price, t.pnl, t.pnl_pct, reason
        )
        return t

    def reconcile(self, broker_positions: list[BrokerPosition], now: datetime, strategy: str = "wave_rider") -> None:
        """Make our book agree with the broker (startup or after a crash).

        Positions the broker has but we do not: adopt them, peak = max(entry, current).
        Positions we have but the broker does not: drop them (they were closed while we were away).
        """
        seen = set()
        for bp in broker_positions:
            seen.add(bp.symbol)
            if bp.symbol in self.positions:
                p = self.positions[bp.symbol]
                p.qty = bp.qty
                if bp.current_price:
                    p.update_price(bp.current_price)
            else:
                cur = bp.current_price or bp.avg_entry_price
                self.positions[bp.symbol] = Position(
                    symbol=bp.symbol,
                    qty=bp.qty,
                    entry_price=bp.avg_entry_price,
                    entry_time=now,
                    peak_price=max(bp.avg_entry_price, cur),
                    last_price=cur,
                    strategy=strategy,
                )
                logger.warning("adopted position from broker: {} x{} @ {}", bp.symbol, bp.qty, bp.avg_entry_price)
        for sym in list(self.positions):
            if sym not in seen:
                logger.warning("position {} no longer at broker; dropping from book", sym)
                self.positions.pop(sym)
                self.pending_exits.pop(sym, None)

    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())
