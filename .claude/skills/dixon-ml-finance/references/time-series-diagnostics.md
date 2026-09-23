# Time-series diagnostics and when sequence models are warranted (Ch. 6, Ch. 8)

## The protocol (pp. 205–208, 242, 272–274; companion notebooks ARIMA-HFT, RNNs-HFT)

1. **Stationarity**: Augmented Dickey-Fuller, null = unit root. "Attempting to fit a time series
   model to non-stationary data will result in dubious interpretations of the estimated partial
   autocorrelation function and poor predictions" (p. 205). Difference if needed; no guarantee one
   difference suffices (p. 206). Returns are stationary; prices are not.
2. **Autocorrelation**: ACF and PACF with bands ±1.96/√T (95%, Eq. 6.44, p. 207) or ±2.58/√T (99%,
   notebooks). PACF cut-off → AR order p; ACF cut-off → MA order q; or AIC = ln σ̂² + 2k/T (Eq. 6.45).
   Lag-2 PACF: τ̃₂ = (τ₂ − τ₁²)/(1 − τ₁²) (Eq. 6.17, p. 198).
3. **Whiteness of residuals**: Ljung-Box Q(m) = T(T+2) Σₗ ρ̂ₗ²/(T−l) ~ χ²(m−p) (Eq. 6.46, p. 208).
   "A well-specified model should exhibit white noise error both in and out-of-sample" (p. 274).
   ARCH test = Ljung-Box on squared residuals (p. 220).
4. **Then** the strategy's own question: conditional forward return after the trigger, by horizon,
   against the unconditional mean, with a standard error. `scripts/diagnose_returns.py` does 1–4.

## Autoregression basics

AR(p): yₜ = μ + Σ φᵢ yₜ₋ᵢ + εₜ (Eq. 6.2, p. 194). AR(1) stable iff |φ| < 1; impulse response φʲ
(p. 195). Stationary iff all characteristic roots lie outside the unit circle (pp. 196–197).
Conditional MLE = OLS (p. 200). Heteroscedastic errors: two-step fit, but "the sample variance of the
residuals is only appropriate when the sample size is sufficient" (pp. 200–201).

## Volatility

GARCH(1,1) variance forecasts mean-revert at rate (α₁+β₁); half-life ln(0.5)/ln(α₁+β₁) (p. 203).
Exponential smoothing ỹₜ₊₁ = α yₜ + (1−α) ỹₜ, half-life −ln(2α)/ln(1−α) (Eqs. 6.36, 6.38, p. 204).
A linear RNN with infinite lags is an exponential smoother (p. 243). For our per-stock noise
estimate, an EWMA of squared minute returns is the cheap upgrade from the 20-bar mean range; the
stochastic-volatility model treats log-variance as a persistent AR(1) (p. 230).

## When a sequence model is justified (pp. 239–242, 257)

- "Each feature must be a time series and therefore exhibit autocorrelation" (p. 242).
- Sequence length = largest significant PACF lag (p. 242); hidden units "generally under a hundred".
- "If the data is i.i.d., then no sequence is needed (i.e., T = 1), and we recover a feedforward
  neural network" (p. 240). Our rows are tabular snapshots whose sequence content is already in the
  features; T = 1 applies.
- Even with a million stationary tick observations, "we observe little advantage in using a GRU over
  a plain RNN" (p. 257); plain RNNs are unsuited to non-stationary series (p. 256); 1-D CNN weights
  are fixed over time, so stationary series only (p. 259).
- The book's examples use 0.5–1M rows and report plots, not out-of-sample numbers or linear baselines.

## Forecast evaluation for a continuous target

MSE or MAE over the horizon (p. 210); "linear regressions predicting the difference between a future
and current price, taking as inputs various moving averages, are often used in preference to
parametric models, such as GARCH" (p. 218). The horizon must allow "economic realization of the
trading signals" (p. 217). Match model frequency to data frequency: build on native bars and forecast
k steps ahead (pp. 191–192).

## What the 2026-09-17 diagnostic found (docs/research/2026-09-17-streak-autocorrelation.md)

Pooled ACF of 1-minute returns at lags 1–3: −0.0009, 0.0017, 0.0061 against a band of ±0.0021.
Median per-symbol lag-1: −0.004 (bid-ask bounce). After a 3-bar streak with ≥1% gain in the entry
window: +5.9 bp at 10 minutes, −10.7 ± 9.2 bp at 60 minutes. Consequence: no sequence model, no
trigger tuning; test slower bars (5, 15 min), pullback entries, and the filter/exit combination.
