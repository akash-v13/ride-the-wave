"""Long-history simulation of the bull put spread slot (`bps_spy`) on the S&P 500, priced from VIX.

Our option prices start in 2024 (Alpaca's option bars), one bull market with one crash. To see the
rule through 1990-2023 each leg is priced with Black-Scholes (``greeks.bs_greeks``) at an implied
volatility read off that day's VIX through a skew curve fitted on the real 2024-26 SPY chains:

    IV(strike) / VIX = c0 + c1·z + c2·z²,   z = ln(strike / spot) / (VIX · √T)

``z`` is how far out of the money the strike is in units of the expected move, so one curve covers
every expiry and every volatility level. The rules are the production slot's (``options.slot``,
``options.lifecycle``; settings ``bps_spy``): enter when flat at the monthly expiry nearest 35 days
(20 to 50), short put 5% and long put 10% below the price, vrp gate, exits on days-to-expiry, profit
target and stop, max loss sized to a fraction of current equity. Costs follow the 2024-26 backtest:
a modelled bid-ask of a fixed share of each option's price, absolute minimums scaled from SPY's
price so they mean the same at any index level.

Pure: series in, results out. ``scripts/backtest_put_spread_history.py`` loads the data and writes
the report (docs/research/2026-11-02-put-spread-long-history.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from statistics import NormalDist

import numpy as np
import pandas as pd

from ridethewave.options.greeks import bs_greeks, implied_vol

CONTRACT_MULT = 100
# SPY's price when the 2024-26 cost assumptions were set. The $0.01 minimum half-spread, the $0.005
# bid floor and the resolver's $0.05 minimum mid are expressed as fractions of it.
SPY_REFERENCE = 700.0


# ---------------------------------------------------------------- the skew curve
@dataclass(frozen=True)
class SkewCurve:
    c0: float
    c1: float
    c2: float
    atm_gate: float  # the slot's "ATM implied vol" (mean of the six contracts nearest the price) / VIX
    floor: float = 0.3
    cap: float = 4.0

    def ratio(self, z: float) -> float:
        return min(self.cap, max(self.floor, self.c0 + self.c1 * z + self.c2 * z * z))

    def iv(self, vix: float, spot: float, strike: float, t_years: float) -> float:
        """Implied vol (decimal) for a strike, from VIX as a decimal (0.18, not 18)."""
        z = math.log(strike / spot) / (vix * math.sqrt(max(t_years, 1 / 365)))
        return vix * self.ratio(z)

    def scaled(self, k: float) -> SkewCurve:
        """Slope and curvature times ``k`` with the at-the-money level unchanged: steeper when k > 1."""
        return replace(self, c1=self.c1 * k, c2=self.c2 * k)


def standardised_moneyness(strike: float, spot: float, vix: float, t_years: float) -> float:
    return math.log(strike / spot) / (vix * math.sqrt(max(t_years, 1 / 365)))


def fit_skew(z: np.ndarray, ratio: np.ndarray, atm_gate: float) -> SkewCurve:
    """Least-squares quadratic of IV/VIX on standardised moneyness."""
    c2, c1, c0 = np.polyfit(np.asarray(z, float), np.asarray(ratio, float), 2)
    return SkewCurve(float(c0), float(c1), float(c2), float(atm_gate))


def put_price(spot: float, strike: float, t_years: float, vol: float, rate: float, div_yield: float) -> float:
    """European put with a continuous dividend yield: Black-Scholes on the dividend-discounted spot."""
    if t_years <= 0:
        return max(strike - spot, 0.0)
    return bs_greeks(spot * math.exp(-div_yield * t_years), strike, t_years, vol, False, rate).price


def put_implied_vol(
    price: float, spot: float, strike: float, t_years: float, rate: float, div_yield: float
) -> float | None:
    """Inverse of ``put_price`` (same dividend convention), for the calibration."""
    return implied_vol(price, spot * math.exp(-div_yield * t_years), strike, t_years, False, rate)


# ---------------------------------------------------------------- configuration and results
@dataclass(frozen=True)
class SimConfig:
    short_otm: float = 0.05  # strike_step_pct 0.025 x OTM(2)
    long_otm: float = 0.10  # x OTM(4)
    dte_target: int = 35
    dte_window: int = 15  # the slot's chain window: 20 to 50 days
    gate: str = "vrp"  # vrp | none
    vrp_threshold: float = 0.03
    rv_days: int = 20
    profit_target_pct: float = 1.0
    stop_mult: float = 10.0
    close_dte: int = 1
    risk_fraction: float = 0.2  # max loss of each spread as a share of current equity
    spread_pct: float = 0.03  # modelled full bid-ask as a share of the option's price
    spread_fraction: float = 1.0  # share of the half-spread paid per leg (the 2024-26 backtest: all of it)
    capital: float = 20_000.0
    div_yield: float = 0.018
    cash_interest: bool = True  # all cash, collateral included, earns the T-bill rate
    min_half_spread_frac: float = 0.01 / SPY_REFERENCE
    bid_floor_frac: float = 0.005 / SPY_REFERENCE
    min_mid_frac: float = 0.05 / SPY_REFERENCE


@dataclass
class SimTrade:
    opened: date
    closed: date
    expiry: date
    k_short: float
    k_long: float
    qty: float
    credit: float  # filled, per share
    max_profit: float  # mid credit, per share
    max_loss: float  # width - mid credit, per share
    exit_value: float  # filled, per share (negative: paid to close)
    pnl: float
    reason: str


@dataclass
class SimResult:
    equity: pd.Series
    rf: pd.Series  # the T-bill return each day on one dollar (0 where cash_interest is off)
    trades: list[SimTrade]
    gate_open_days: int = 0
    days_in_market: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- calendar and helpers
def monthly_expiries(trading_days: pd.DatetimeIndex) -> list[date]:
    """Third Friday of every month in range; the previous trading day when that Friday is a holiday
    (Good Friday), as for SPY and SPX."""
    days = {d.date() for d in trading_days}
    first, last = trading_days[0].date(), trading_days[-1].date() + timedelta(days=60)
    out: list[date] = []
    y, m = first.year, first.month
    while date(y, m, 1) <= last:
        d1 = date(y, m, 1)
        third_friday = d1 + timedelta(days=(4 - d1.weekday()) % 7 + 14)
        d = third_friday
        if d <= trading_days[-1].date():
            while d not in days and d > d1:
                d -= timedelta(days=1)
        out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def pick_expiry(today: date, expiries: list[date], target: int, window: int) -> date | None:
    inside = [e for e in expiries if target - window <= (e - today).days <= target + window]
    return min(inside, key=lambda e: abs((e - today).days - target)) if inside else None


def realised_vol(close: pd.Series, days: int = 20) -> pd.Series:
    """Annualised standard deviation of daily log returns over the last ``days`` (the slot's measure)."""
    return np.log(close / close.shift(1)).rolling(days).std() * math.sqrt(252)


def _quote(price: float, spot: float, cfg: SimConfig) -> tuple[float, float]:
    """Bid/ask around a model price, as the 2024-26 backtest built them from closes."""
    h = max(cfg.min_half_spread_frac * spot, cfg.spread_pct / 2 * price)
    return max(price - h, cfg.bid_floor_frac * spot), price + h


def _fill(q: tuple[float, float], side: str, frac: float) -> float:
    bid, ask = q
    mid, half = (bid + ask) / 2, (ask - bid) / 2
    return mid + frac * half if side == "buy" else mid - frac * half


def _mid(q: tuple[float, float]) -> float:
    return (q[0] + q[1]) / 2


# ---------------------------------------------------------------- the simulation
def simulate(
    spx: pd.Series,
    vix: pd.Series,
    rate: pd.Series,
    skew: SkewCurve,
    cfg: SimConfig = SimConfig(),
    start: date | None = None,
    end: date | None = None,
) -> SimResult:
    """``spx``: index closes; ``vix``: VIX in points (18.5); ``rate``: T-bill rate as a decimal a year."""
    spx = spx.sort_index()
    rv = realised_vol(spx, cfg.rv_days)
    days = spx.index.intersection(vix.index)
    if start:
        days = days[days >= pd.Timestamp(start)]
    if end:
        days = days[days <= pd.Timestamp(end)]
    rate = rate.sort_index().reindex(spx.index.union(rate.index)).ffill().reindex(days).fillna(0.0)
    expiries = monthly_expiries(spx.index)

    cash = cfg.capital
    pos: SimTrade | None = None
    trades: list[SimTrade] = []
    eq_vals, rf_vals = [], []
    gate_open = in_market = 0
    prev_day: date | None = None
    prev_rate = 0.0

    def leg_quotes(p: SimTrade, d: date, s: float, v: float, r: float):
        t = (p.expiry - d).days / 365.0
        qs = []
        for k in (p.k_short, p.k_long):
            if t <= 0:
                intr = max(k - s, 0.0)
                qs.append((intr, intr))
            else:
                qs.append(_quote(put_price(s, k, t, skew.iv(v, s, k, t), r, cfg.div_yield), s, cfg))
        return qs

    for ts in days:
        d = ts.date()
        s, v, r = float(spx.loc[ts]), float(vix.loc[ts]) / 100.0, float(rate.loc[ts])
        rf = 0.0
        if prev_day is not None and cfg.cash_interest:
            rf = prev_rate * (d - prev_day).days / 360.0
            cash += cash * rf
        # 1. exits (days to expiry first, then profit target, then stop; lifecycle.exit_reason)
        if pos is not None:
            q_short, q_long = leg_quotes(pos, d, s, v, r)
            value = -_mid(q_short) + _mid(q_long)
            dte = (pos.expiry - d).days
            pl = pos.credit + value
            reason = None
            if dte <= cfg.close_dte:
                reason = "dte_exit"
            elif pl >= cfg.profit_target_pct * pos.max_profit:
                reason = "profit_target"
            elif pl <= -cfg.stop_mult * pos.max_profit:
                reason = "stop"
            if reason:
                v_exit = -_fill(q_short, "buy", cfg.spread_fraction) + _fill(q_long, "sell", cfg.spread_fraction)
                cash += v_exit * CONTRACT_MULT * pos.qty
                pos.closed, pos.exit_value, pos.reason = d, v_exit, reason
                pos.pnl = (pos.credit + v_exit) * CONTRACT_MULT * pos.qty
                trades.append(pos)
                pos = None
        # 2. entry when flat
        if pos is None:
            ok = True
            if cfg.gate == "vrp":
                rvd = rv.get(ts)
                ok = rvd is not None and not math.isnan(rvd) and v * skew.atm_gate - rvd >= cfg.vrp_threshold
            if ok:
                gate_open += 1
                pos = _open(d, s, v, r, expiries, skew, cfg, cash)
                if pos is not None:
                    cash += pos.credit * CONTRACT_MULT * pos.qty
        # 3. mark at mid
        value = 0.0
        if pos is not None:
            in_market += 1
            q_short, q_long = leg_quotes(pos, d, s, v, r)
            value = (-_mid(q_short) + _mid(q_long)) * CONTRACT_MULT * pos.qty
        eq_vals.append(cash + value)
        rf_vals.append(rf)
        prev_day, prev_rate = d, r

    equity = pd.Series(eq_vals, index=days, name="equity")
    return SimResult(equity, pd.Series(rf_vals, index=days, name="rf"), trades, gate_open, in_market)


def _open(
    d: date, s: float, v: float, r: float, expiries: list[date], skew: SkewCurve, cfg: SimConfig, equity: float
) -> SimTrade | None:
    expiry = pick_expiry(d, expiries, cfg.dte_target, cfg.dte_window)
    if expiry is None or equity <= 0:
        return None
    t = (expiry - d).days / 365.0
    k_short, k_long = s * (1 - cfg.short_otm), s * (1 - cfg.long_otm)

    def price(k: float) -> float:
        return put_price(s, k, t, skew.iv(v, s, k, t), r, cfg.div_yield)

    min_mid = cfg.min_mid_frac * s
    p_short, p_long = price(k_short), price(k_long)
    if p_short < min_mid:
        return None
    if p_long < min_mid:
        # the resolver keeps only contracts worth at least $0.05 and takes the nearest of those, so the
        # long leg moves up to the furthest strike that is still worth the minimum
        lo, hi = k_long, k_short
        for _ in range(40):
            mid_k = (lo + hi) / 2
            lo, hi = (mid_k, hi) if price(mid_k) < min_mid else (lo, mid_k)
        k_long, p_long = hi, price(hi)
        if k_long >= k_short:
            return None
    q_short, q_long = _quote(p_short, s, cfg), _quote(p_long, s, cfg)
    max_profit = _mid(q_short) - _mid(q_long)
    max_loss = (k_short - k_long) - max_profit
    credit = _fill(q_short, "sell", cfg.spread_fraction) - _fill(q_long, "buy", cfg.spread_fraction)
    if credit <= 0 or max_loss <= 0:
        return None
    qty = equity * cfg.risk_fraction / (max_loss * CONTRACT_MULT)
    return SimTrade(d, d, expiry, k_short, k_long, qty, credit, max_profit, max_loss, 0.0, 0.0, "")


# ---------------------------------------------------------------- statistics
def max_drawdown(equity: pd.Series) -> tuple[float, pd.Timestamp | None, pd.Timestamp | None, pd.Timestamp | None]:
    """(depth, peak date, trough date, recovery date or None)."""
    peak = equity.cummax()
    dd = equity / peak - 1
    trough = dd.idxmin()
    depth = float(dd.min())
    if depth >= 0:
        return 0.0, None, None, None
    peak_day = equity.loc[:trough].idxmax()
    after = equity.loc[trough:]
    rec = after[after >= equity.loc[peak_day]]
    return depth, peak_day, trough, (rec.index[0] if len(rec) else None)


def summarize(equity: pd.Series, rf: pd.Series, market: pd.Series | None = None) -> dict:
    """Curve statistics. Sharpe and Sortino on returns in excess of ``rf`` (T-bill return per day)."""
    r = equity.pct_change().dropna()
    ex = r - rf.reindex(r.index).fillna(0.0)
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    depth, peak, trough, rec = max_drawdown(equity)
    monthly = pd.concat([equity.iloc[:1], equity.resample("ME").last()]).pct_change().dropna()
    monthly = monthly[monthly.index > equity.index[0]]
    downside = math.sqrt(float((np.minimum(ex, 0.0) ** 2).mean())) if len(ex) else 0.0
    out = {
        "start": equity.index[0].date(),
        "end": equity.index[-1].date(),
        "cagr": float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) if years > 0 else 0.0,
        "excess_cagr": float(np.exp(np.log1p(ex).sum() / years) - 1) if years > 0 else 0.0,
        "vol": float(r.std() * math.sqrt(252)),
        "sharpe": float(ex.mean() / ex.std() * math.sqrt(252)) if ex.std() > 0 else 0.0,
        "sortino": float(ex.mean() / downside * math.sqrt(252)) if downside > 0 else 0.0,
        "max_dd": depth,
        "dd_peak": peak.date() if peak is not None else None,
        "dd_trough": trough.date() if trough is not None else None,
        "dd_recovered": rec.date() if rec is not None else None,
        "worst_month": float(monthly.min()) if len(monthly) else 0.0,
        "worst_month_at": monthly.idxmin().strftime("%Y-%m") if len(monthly) else "",
        "months_positive": float((monthly > 0).mean()) if len(monthly) else 0.0,
        "worst_day": float(r.min()) if len(r) else 0.0,
    }
    if market is not None:
        m = market.reindex(r.index)
        ok = m.notna()
        out["corr_daily"] = float(r[ok].corr(m[ok]))
        mm = (1 + market).cumprod().resample("ME").last().pct_change()
        both = pd.concat([monthly, mm], axis=1, join="inner").dropna()
        out["corr_monthly"] = float(both.iloc[:, 0].corr(both.iloc[:, 1])) if len(both) > 2 else float("nan")
        out["beta_daily"] = float(r[ok].cov(m[ok]) / m[ok].var()) if m[ok].var() > 0 else float("nan")
    return out


def trade_stats(trades: list[SimTrade]) -> dict:
    pnl = np.array([t.pnl for t in trades])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    return {
        "trades": len(pnl),
        "win_rate": float(len(wins) / len(pnl)) if len(pnl) else 0.0,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else float("inf"),
        "exits": pd.Series([t.reason for t in trades]).value_counts().to_dict() if trades else {},
    }


def episode_stats(equity: pd.Series, market_level: pd.Series, start: str, end: str) -> dict:
    """Return of the strategy and of the market over [start, end], from the last close before start,
    and the strategy's worst drawdown inside the window."""
    e = equity.loc[:end]
    m = market_level.loc[:end]
    e0 = e.loc[: pd.Timestamp(start) - pd.Timedelta(days=1)]
    m0 = m.loc[: pd.Timestamp(start) - pd.Timedelta(days=1)]
    e_in, m_in = e.loc[start:], m.loc[start:]
    if e0.empty or e_in.empty:
        return {}
    path = pd.concat([e0.iloc[-1:], e_in])
    return {
        "strategy": float(e_in.iloc[-1] / e0.iloc[-1] - 1),
        "market": float(m_in.iloc[-1] / m0.iloc[-1] - 1) if len(m0) and len(m_in) else float("nan"),
        "strategy_dd": float((path / path.cummax() - 1).min()),
        "market_dd": float((pd.concat([m0.iloc[-1:], m_in]) / pd.concat([m0.iloc[-1:], m_in]).cummax() - 1).min()),
    }


def deflated_sharpe(excess: pd.Series, trial_sharpes: list[float], n_trials: int) -> dict:
    """Bailey and López de Prado (2014): the probability that the true Sharpe exceeds the best one
    expected by luck from ``n_trials`` tries. Sharpes here are per period (daily), not annualised."""
    x = excess.dropna().to_numpy()
    n = len(x)
    sr = float(x.mean() / x.std(ddof=1))
    skew = float(((x - x.mean()) ** 3).mean() / x.std() ** 3)
    kurt = float(((x - x.mean()) ** 4).mean() / x.std() ** 4)
    var_sr = float(np.var(trial_sharpes, ddof=1)) if len(trial_sharpes) > 1 else 0.0
    nd = NormalDist()
    gamma = 0.5772156649
    if n_trials > 1 and var_sr > 0:
        sr0 = math.sqrt(var_sr) * (
            (1 - gamma) * nd.inv_cdf(1 - 1 / n_trials) + gamma * nd.inv_cdf(1 - 1 / (n_trials * math.e))
        )
    else:
        sr0 = 0.0
    denom = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr * sr, 1e-12))
    psr0 = nd.cdf(sr * math.sqrt(n - 1) / denom)  # against a true Sharpe of zero
    dsr = nd.cdf((sr - sr0) * math.sqrt(n - 1) / denom)
    return {
        "sharpe_daily": sr,
        "sharpe_annual": sr * math.sqrt(252),
        "sr0_annual": sr0 * math.sqrt(252),
        "skew": skew,
        "kurtosis": kurt,
        "psr_vs_zero": psr0,
        "dsr": dsr,
        "n_obs": n,
        "n_trials": n_trials,
    }
