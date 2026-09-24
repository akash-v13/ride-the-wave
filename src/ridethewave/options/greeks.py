"""Black-Scholes pricing, greeks and implied volatility (from TraderPro, stdlib only).

Used for marks when quotes are stale or absent, payoff math,
strike selection fallback when the feed omits greeks. European BS on
American options is imprecise but plenty for selection/marking purposes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SQRT_2PI = math.sqrt(2 * math.pi)


def _norm_pdf(x: float) -> float:
    return math.exp(-x * x / 2) / SQRT_2PI


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    theta: float  # per day
    vega: float  # per 1 vol point (0.01)


def bs_greeks(
    spot: float,
    strike: float,
    t_years: float,
    vol: float,
    is_call: bool,
    rate: float = 0.04,
) -> Greeks:
    """Black-Scholes price + greeks. t_years and vol must be > 0."""
    if t_years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        # at/past expiry: intrinsic value, degenerate greeks
        intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
        delta = (1.0 if spot > strike else 0.0) if is_call else (-1.0 if spot < strike else 0.0)
        return Greeks(price=intrinsic, delta=delta, gamma=0.0, theta=0.0, vega=0.0)

    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate + vol * vol / 2) * t_years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    disc = math.exp(-rate * t_years)

    if is_call:
        price = spot * _norm_cdf(d1) - strike * disc * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        theta_y = -spot * _norm_pdf(d1) * vol / (2 * sqrt_t) - rate * strike * disc * _norm_cdf(d2)
    else:
        price = strike * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
        theta_y = -spot * _norm_pdf(d1) * vol / (2 * sqrt_t) + rate * strike * disc * _norm_cdf(-d2)

    gamma = _norm_pdf(d1) / (spot * vol * sqrt_t)
    vega = spot * _norm_pdf(d1) * sqrt_t / 100  # per 1 vol point
    return Greeks(price=price, delta=delta, gamma=gamma, theta=theta_y / 365, vega=vega)


def implied_vol(
    option_price: float,
    spot: float,
    strike: float,
    t_years: float,
    is_call: bool,
    rate: float = 0.04,
) -> float | None:
    """Bisection IV solve; None if the price is outside no-arbitrage bounds."""
    if t_years <= 0 or option_price <= 0:
        return None
    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    if option_price < intrinsic - 1e-9:
        return None

    lo, hi = 1e-4, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        price = bs_greeks(spot, strike, t_years, mid, is_call, rate).price
        if abs(price - option_price) < 1e-6:
            return mid
        if price < option_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
