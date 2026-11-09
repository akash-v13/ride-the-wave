# src/ridethewave/options

The options engine (feature 22), ported from the owner's TraderPro project and wired to Alpaca's
options API on Algo Trader Plus (OPRA quotes, greeks, implied volatility; paper account at options
level 3).

- `structures.py`: the 57 Chapter-2 structures of *151 Trading Strategies* as declarative leg templates.
- `greeks.py`: Black-Scholes price, greeks and implied volatility (stdlib only).
- `chain.py`: chain snapshots and quotes from Alpaca; OCC symbol parsing.
- `resolver.py`: a template against a chain snapshot -> concrete legs, entry net, payoff bounds.
- `lifecycle.py`: pure rules: sizing, valuation, shadow fill prices, exits (DTE, profit target, stop).
- `slot.py`: an options slot: one template on one underlying, at most one structure open, decided daily;
  shadow fills against live quotes or live multi-leg orders on the paper account.
- `backtest.py`: past chains rebuilt from Alpaca's daily option bars (2024 on), replayed through `slot.py`.
- `history_sim.py`: the bull put spread slot's rules on the S&P 500 from 1990, each leg priced from VIX
  through a skew curve fitted on the real 2024-26 chains (docs/research/2026-11-02-put-spread-long-history.md).
