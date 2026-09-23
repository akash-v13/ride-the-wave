"""How much money each trade gets."""

from __future__ import annotations

import math

from ridethewave.config import CapitalSettings, EntrySettings


class CapitalAllocator:
    def __init__(self, capital: CapitalSettings, entry: EntrySettings, allocation: float | None = None):
        self.capital = capital
        self.entry = entry
        self.allocation = allocation if allocation is not None else capital.base_allocation

    def slot_dollars(self) -> float:
        return self.allocation * self.entry.position_size_pct / 100.0

    def qty_for(self, price: float) -> int:
        if price <= 0:
            return 0
        return int(math.floor(self.slot_dollars() / price))
