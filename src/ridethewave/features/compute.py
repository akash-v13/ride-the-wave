"""Per-bar features from a symbol's session bars. Pure; no I/O.

All ratios use only bars from the current session up to and including the latest bar, so the same
code gives identical answers live (aggregator history) and in replay (cached bars).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from ridethewave.models import Bar
from ridethewave.strategy.indicators import green_streak, streak_gain_pct, streak_volume

LOOKBACK = 20  # bars used for "normal" volume and range
MIN_BARS = 5  # fewer than this and ratios are unreliable -> None


@dataclass(frozen=True, slots=True)
class BarFeatures:
    symbol: str
    ts: datetime
    close: float
    minutes_since_open: int
    bars_in_session: int
    streak: int
    streak_gain_pct: float
    streak_volume: int
    rvol_20: float | None  # this bar's volume / mean volume of the prior 20 bars
    streak_vol_ratio: float | None  # mean volume during the streak / mean volume of the 20 bars before it
    trade_count_ratio: float | None  # same, for trade count
    vwap_dist_pct: float | None  # (close - session VWAP) / VWAP * 100
    session_ret_pct: float | None  # close / session open - 1
    range_pct_20: float | None  # mean (high-low)/close over prior 20 bars, in %
    gain_vs_range: float | None  # streak gain / range_pct_20 (how many "normal minutes" the move is)
    spy_ret_5m_pct: float | None
    spy_ret_session_pct: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b <= 0:
        return None
    return a / b


def compute_features(bars: list[Bar], spy_bars: list[Bar] | None, session_start: datetime) -> BarFeatures | None:
    """Features for the last bar in ``bars``. ``bars`` may include earlier sessions; only bars with
    ``ts >= session_start`` are used. ``spy_bars`` is SPY's history (any length, oldest first)."""
    sess = [b for b in bars if b.ts >= session_start]
    if not sess:
        return None
    cur = sess[-1]
    n = len(sess)
    streak = green_streak(sess)
    gain = streak_gain_pct(sess, streak)
    svol = streak_volume(sess, streak)

    prior = sess[:-1]  # everything before the current bar
    look = prior[-LOOKBACK:]
    base_vol = _mean([b.volume for b in look]) if len(look) >= MIN_BARS else None
    rvol = _ratio(cur.volume, base_vol)

    # streak vs the window immediately before the streak
    k = max(streak, 1)
    streak_bars = sess[-k:]
    before = sess[:-k][-LOOKBACK:]
    if len(before) >= MIN_BARS:
        svr = _ratio(_mean([b.volume for b in streak_bars]), _mean([b.volume for b in before]))
        tcr = _ratio(_mean([b.trade_count for b in streak_bars]), _mean([b.trade_count for b in before]))
    else:
        svr = tcr = None

    tot_vol = sum(b.volume for b in sess)
    vwap = sum((b.vwap or b.close) * b.volume for b in sess) / tot_vol if tot_vol > 0 else None
    vwap_dist = (cur.close / vwap - 1.0) * 100.0 if vwap else None
    sess_open = sess[0].open
    sess_ret = (cur.close / sess_open - 1.0) * 100.0 if sess_open > 0 else None

    rng = _mean([(b.high - b.low) / b.close * 100.0 for b in look if b.close > 0]) if len(look) >= MIN_BARS else None
    gvr = _ratio(gain, rng) if rng else None

    spy5 = spys = None
    if spy_bars:
        spy_sess = [b for b in spy_bars if b.ts >= session_start and b.ts <= cur.ts]
        if spy_sess:
            last = spy_sess[-1]
            if len(spy_sess) > 5 and spy_sess[-6].close > 0:
                spy5 = (last.close / spy_sess[-6].close - 1.0) * 100.0
            if spy_sess[0].open > 0:
                spys = (last.close / spy_sess[0].open - 1.0) * 100.0

    return BarFeatures(
        symbol=cur.symbol,
        ts=cur.ts,
        close=cur.close,
        minutes_since_open=int((cur.ts - session_start).total_seconds() // 60),
        bars_in_session=n,
        streak=streak,
        streak_gain_pct=gain,
        streak_volume=svol,
        rvol_20=rvol,
        streak_vol_ratio=svr,
        trade_count_ratio=tcr,
        vwap_dist_pct=vwap_dist,
        session_ret_pct=sess_ret,
        range_pct_20=rng,
        gain_vs_range=gvr,
        spy_ret_5m_pct=spy5,
        spy_ret_session_pct=spys,
    )
