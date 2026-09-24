"""Cross-sectional open-to-close strategies, long-only. After Kakushadze & Serur (2018), *151 Trading
Strategies*: 3.9 mean-reversion (single cluster), 3.20 alpha combos and Appendix A, whose backtest
code trades two "alphas" established at the open and liquidated at the close: delay-0 mean-reversion
on the overnight return and delay-1 momentum on the previous day's open-to-close return.

Once per session, on the first completed bar at or after ``entry_time``, every stock in the universe
with a 09:30 bar and yesterday's daily bar gets a score (log returns, demeaned across the universe so
the market move cancels; the book demeans within industry clusters, which we do not have):

    overnight_reversal   score = -(r_on - mean r_on)      r_on = ln(open_today / close_yesterday)
    prev_day_momentum    score =  (r_pd - mean r_pd)      r_pd = ln(close_yesterday / open_yesterday)
    intraday_reversal    score = -(r_id - mean r_id)      r_id = ln(price_now / open_today)
    combo                score = overnight_reversal + prev_day_momentum (both in return units)

The ``top_n`` highest scores are bought with equal dollars (or dollars proportional to 1/volatility),
each with a hard stop ``stop_pct`` below entry and an optional target, and sold at ``exit_time``.
The book's version is dollar-neutral (it also shorts the bottom of the ranking); that half needs
short selling, which the execution layer does not have yet, so this is the long leg only.

Pure: no network, no database. Daily context arrives through ``on_session_start``.
"""

from __future__ import annotations

import math
from datetime import datetime, time
from statistics import fmean, median, pstdev
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from ridethewave.models import Bar, Position, Signal, SignalType, Tick
from ridethewave.strategy.base import Strategy, StrategyContext

ET = ZoneInfo("America/New_York")

SignalKind = Literal["overnight_reversal", "prev_day_momentum", "intraday_reversal", "combo"]


class XsParams(BaseModel):
    signal: SignalKind = "overnight_reversal"
    entry_time: str = "09:35"  # decide on the first completed bar at/after this time (ET)
    exit_time: str = "15:55"
    top_n: int = Field(5, ge=1)  # also capped by entry.max_positions (open slots)
    min_score_pct: float = Field(0.5, ge=0)  # demeaned move must be at least this, in percent; 0 = off
    max_gap_pct: float = Field(8.0, ge=0)  # skip |overnight move| above this (earnings/news); 0 = off
    stop_pct: float = Field(3.0, ge=0)  # hard stop below entry (client-side and server-side); 0 = none
    target_pct: float = Field(0.0, ge=0)  # take-profit above entry; 0 = off
    weight_by: Literal["equal", "inv_vol"] = "equal"
    min_price: float = 5.0
    min_universe: int = Field(10, ge=2)  # need at least this many scored names to rank at all
    vol_lookback: int = Field(20, ge=5)  # sessions of daily returns for the volatility weights
    demean: bool = True
    invert: bool = False  # trade the opposite side of the ranking (e.g. overnight continuation instead of reversal)
    stocks_only: bool = True  # drop ETFs, leveraged products and crypto trusts from the ranking

    model_config = {"extra": "forbid"}


def _t(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


class CrossSectionalDaytrade(Strategy):
    name = "xs_daytrade"
    flatten_at_close = True

    def __init__(self, params: dict | None = None):
        self.p = XsParams.model_validate(params or {})
        self.name = f"xs_{self.p.signal}" + ("_inv" if self.p.invert else "")
        self.uses_protective_stop = self.p.stop_pct > 0
        self.stocks_only = self.p.stocks_only
        self._entry = _t(self.p.entry_time)
        self._exit = _t(self.p.exit_time)
        # yesterday's context, per symbol
        self.prev_close: dict[str, float] = {}
        self.prev_open: dict[str, float] = {}
        self.vol: dict[str, float] = {}
        # today's state
        self.today_open: dict[str, float] = {}
        self.last: dict[str, float] = {}
        self.stops: dict[str, float] = {}
        self.targets: dict[str, float] = {}
        self.last_scores: dict[str, float] = {}
        self.decided = False
        self._day: str | None = None

    # ---------- daily context ----------
    def on_session_start(self, day: str, daily: dict[str, list[Bar]]) -> None:
        self._reset_day(day)
        self.prev_close.clear()
        self.prev_open.clear()
        self.vol.clear()
        for sym, bars in daily.items():
            if not bars:
                continue
            last = bars[-1]
            if last.close <= 0 or last.open <= 0:
                continue
            self.prev_close[sym] = last.close
            self.prev_open[sym] = last.open
            closes = [b.close for b in bars[-(self.p.vol_lookback + 1) :]]
            rets = [
                math.log(closes[i] / closes[i - 1])
                for i in range(1, len(closes))
                if closes[i - 1] > 0 and closes[i] > 0
            ]
            if len(rets) >= 5:
                self.vol[sym] = pstdev(rets)

    def _reset_day(self, day: str) -> None:
        self._day = day
        self.today_open.clear()
        self.last.clear()
        self.stops.clear()
        self.targets.clear()
        self.last_scores.clear()
        self.decided = False

    # ---------- bars ----------
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Signal]:
        et = bar.ts.astimezone(ET)
        day = et.strftime("%Y-%m-%d")
        if self._day != day:  # a session nobody announced (no daily context): intraday signals still work
            self._reset_day(day)
        sym = bar.symbol
        pos = ctx.position(sym)
        if pos is not None:
            return self._check_exit(pos, bar.close, bar.ts)
        mins = et.hour * 60 + et.minute - (9 * 60 + 30)
        if mins < 0:
            return []
        if sym not in self.today_open and mins <= 2 and bar.open > 0:
            self.today_open[sym] = bar.open
        self.last[sym] = bar.close
        if self.decided or et.time() < self._entry:
            return []
        return self._decide(bar.ts, ctx)

    def on_tick(self, tick: Tick, ctx: StrategyContext) -> list[Signal]:
        pos = ctx.position(tick.symbol)
        if pos is None:
            return []
        return self._check_exit(pos, tick.price, tick.ts)

    # ---------- the ranking ----------
    def scores(self) -> list[tuple[str, float, float]]:
        """(symbol, score, overnight return) for every name that can be scored right now."""
        cand: list[tuple[str, float, float, float]] = []
        for sym, op in self.today_open.items():
            pc = self.prev_close.get(sym)
            po = self.prev_open.get(sym)
            px = self.last.get(sym)
            if not px or px < self.p.min_price or op <= 0:
                continue
            if self.p.signal == "intraday_reversal":
                r_on = math.log(op / pc) if pc else 0.0
            else:
                if not pc:
                    continue
                r_on = math.log(op / pc)
            if self.p.max_gap_pct and abs(r_on) > self.p.max_gap_pct / 100:
                continue
            r_pd = math.log(pc / po) if pc and po else 0.0
            r_id = math.log(px / op)
            cand.append((sym, r_on, r_pd, r_id))
        if len(cand) < self.p.min_universe:
            return []

        def demean(vals: list[float]) -> list[float]:
            m = fmean(vals) if self.p.demean else 0.0
            return [v - m for v in vals]

        on = demean([c[1] for c in cand])
        pd_ = demean([c[2] for c in cand])
        idr = demean([c[3] for c in cand])
        if self.p.signal == "overnight_reversal":
            score = [-x for x in on]
        elif self.p.signal == "prev_day_momentum":
            score = pd_
        elif self.p.signal == "intraday_reversal":
            score = [-x for x in idr]
        else:
            score = [-a + b for a, b in zip(on, pd_, strict=True)]
        if self.p.invert:
            score = [-x for x in score]
        return [(c[0], s, c[1]) for c, s in zip(cand, score, strict=True)]

    def _decide(self, ts: datetime, ctx: StrategyContext) -> list[Signal]:
        self.decided = True
        rows = self.scores()
        self.last_scores = {sym: sc for sym, sc, _ in rows}
        n = min(self.p.top_n, ctx.open_slots)
        if n <= 0 or not rows:
            return []
        rows.sort(key=lambda r: r[1], reverse=True)
        threshold = self.p.min_score_pct / 100
        out: list[Signal] = []
        for rank, (sym, score, gap) in enumerate(rows, start=1):
            if len(out) >= n or score < threshold:
                break
            if sym in ctx.positions or sym in ctx.pending_entries:
                continue
            px = self.last[sym]
            if self.p.stop_pct > 0:
                self.stops[sym] = round(px * (1 - self.p.stop_pct / 100), 4)
            if self.p.target_pct > 0:
                self.targets[sym] = round(px * (1 + self.p.target_pct / 100), 4)
            out.append(
                Signal(
                    SignalType.BUY,
                    sym,
                    ts,
                    f"xs_{self.p.signal} | score={score * 100:+.2f}% gap={gap * 100:+.2f}% rank={rank}/{len(rows)}",
                    px,
                    noise_pct=None,
                )
            )
        return out

    # ---------- exits ----------
    def _check_exit(self, pos: Position, price: float, ts: datetime) -> list[Signal]:
        if pos.exit_pending:
            return []
        pos.update_price(price)
        stop = self.stops.get(pos.symbol)
        if stop is not None and price <= stop:
            return [Signal(SignalType.SELL, pos.symbol, ts, f"xs_stop | stop={stop:.2f}", price, pos.qty)]
        target = self.targets.get(pos.symbol)
        if target is not None and price >= target:
            return [Signal(SignalType.SELL, pos.symbol, ts, f"xs_target | target={target:.2f}", price, pos.qty)]
        if ts.astimezone(ET).time() >= self._exit:
            return [Signal(SignalType.SELL, pos.symbol, ts, "xs_close | timed exit", price, pos.qty)]
        return []

    def exit_trigger(self, pos: Position) -> float | None:
        return self.stops.get(pos.symbol)

    # ---------- sizing hook (order manager) ----------
    def qty_for(self, symbol: str, price: float, allocation: float, slot_dollars: float) -> int | None:
        """Equal dollars by default; with ``weight_by: inv_vol`` scale the slot by median σ / σ_i (0.5x to 2x)."""
        if self.p.weight_by != "inv_vol" or price <= 0:
            return None
        v = self.vol.get(symbol)
        vols = [x for x in self.vol.values() if x > 0]
        if not v or v <= 0 or len(vols) < 2:
            return None
        scale = min(2.0, max(0.5, median(vols) / v))
        return max(0, int(slot_dollars * scale / price))
