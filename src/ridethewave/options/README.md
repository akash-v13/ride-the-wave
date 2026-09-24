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
