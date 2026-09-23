"""Kill switches. Pure decisions over numbers the runner already has; the runner acts on them."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ridethewave.config import RiskSettings
from ridethewave.models import Trade


@dataclass(frozen=True, slots=True)
class RiskDecision:
    halt_entries: bool
    flatten: bool
    reason: str | None


def beta_prob_below(threshold: float, alpha: float, beta: float, n: int = 20_000) -> float:
    """P(theta < threshold) for theta ~ Beta(alpha, beta), by a deterministic grid (no numpy needed)."""
    # regularised incomplete beta via a fine trapezoid on the pdf; accurate to ~1e-4 for our sizes
    lo, hi = 1e-9, 1 - 1e-9
    xs = [lo + (hi - lo) * i / n for i in range(n + 1)]
    lg = math.lgamma(alpha + beta) - math.lgamma(alpha) - math.lgamma(beta)

    def pdf(x: float) -> float:
        return math.exp(lg + (alpha - 1) * math.log(x) + (beta - 1) * math.log(1 - x))

    total = 0.0
    below = 0.0
    prev = pdf(xs[0])
    for i in range(1, len(xs)):
        cur = pdf(xs[i])
        area = (prev + cur) * (xs[i] - xs[i - 1]) / 2
        total += area
        if xs[i] <= threshold:
            below += area
        prev = cur
    return below / total if total > 0 else 0.0


class RiskMonitor:
    def __init__(self, cfg: RiskSettings, allocation: float):
        self.cfg = cfg
        self.allocation = allocation
        self.halted_reason: str | None = None

    def check_pnl(self, realized_today: float, unrealized: float) -> RiskDecision:
        if self.allocation <= 0:
            return RiskDecision(False, False, None)
        if self.cfg.max_daily_loss_pct > 0 and realized_today <= -self.allocation * self.cfg.max_daily_loss_pct / 100:
            return self._halt(
                f"daily loss {realized_today:+.2f} breached {self.cfg.max_daily_loss_pct}% of allocation", True
            )
        total = realized_today + unrealized
        if self.cfg.max_open_loss_pct > 0 and total <= -self.allocation * self.cfg.max_open_loss_pct / 100:
            return self._halt(f"open loss {total:+.2f} breached {self.cfg.max_open_loss_pct}% of allocation", True)
        return RiskDecision(self.halted_reason is not None, False, self.halted_reason)

    def check_winrate(self, recent: list[Trade]) -> RiskDecision:
        """Posterior of the live win rate over the last N trades vs the break-even rate."""
        if not self.cfg.winrate_floor_enabled or len(recent) < self.cfg.winrate_min_trades:
            return RiskDecision(self.halted_reason is not None, False, self.halted_reason)
        trades = recent[-self.cfg.winrate_lookback_trades :]
        wins = [t.pnl for t in trades if t.pnl > 0]
        losses = [-t.pnl for t in trades if t.pnl <= 0]
        if self.cfg.winrate_breakeven is not None:
            be = self.cfg.winrate_breakeven
        elif wins and losses:
            aw, al = sum(wins) / len(wins), sum(losses) / len(losses)
            be = al / (aw + al)
        else:
            return RiskDecision(self.halted_reason is not None, False, self.halted_reason)
        p_below = beta_prob_below(be, 1 + len(wins), 1 + len(losses))
        if p_below >= self.cfg.winrate_halt_probability:
            return self._halt(
                f"win rate posterior: P(rate < break-even {be:.2f}) = {p_below:.2f} over last {len(trades)} trades",
                False,
            )
        return RiskDecision(self.halted_reason is not None, False, self.halted_reason)

    def _halt(self, reason: str, flatten: bool) -> RiskDecision:
        if self.halted_reason is None:
            self.halted_reason = reason
        return RiskDecision(True, flatten, self.halted_reason)
