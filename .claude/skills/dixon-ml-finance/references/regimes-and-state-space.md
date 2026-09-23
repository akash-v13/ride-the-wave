# Regime detection and state-space models (Ch. 7)

## Hidden Markov models (pp. 221–226)

Latent discrete state sₜ is Markov; observation yₜ depends only on sₜ:
p(s, y) = p(s₁) p(y₁|s₁) ∏ p(sₜ|sₜ₋₁) p(yₜ|sₜ) (Eq. 7.1, p. 223). Motivation is explicit regime
switching, which gated RNNs do implicitly and "cannot be controlled explicitly as may be needed for
regime switching in finance" (p. 222).

The book's bull/bear example (pp. 223–224) hand-specifies emissions 0.8/0.2 and transitions
0.9/0.1 and never fits them. Forward Fₜ(s) = P(sₜ=s, y₁:ₜ), backward Bₜ(s) = p(yₜ₊₁:ₜ|sₜ=s),
P(sₜ=s | y) ∝ Fₜ(s)Bₜ(s) (Eqs. 7.4–7.6). Baum-Welch (EM) fits unknown matrices (p. 224); the update
formulas are not printed. Viterbi gives the most likely path; per-step argmax "may not lead to the
best path" (p. 226).

## Minimal regime detector for Ride The Wave

1. Series: SPY 1-minute log returns (or 5-minute, after the slower-bar diagnostic).
2. K = 2 states, Gaussian emissions (the continuous analogue of the book's ±1 observations).
3. Fit with `hmmlearn` (not in the book) on the training slice of each walk-forward fold only.
4. Feature = **filtered** P(state | bars up to now), i.e. the forward quantity. The smoothed
   posterior uses future bars and would leak into a backtest.
5. Expect the two states to differ mainly in **variance**: minute-return means are tiny relative to
   their standard deviation, so this is a volatility-regime detector, not bull/bear. That is still
   useful: the filter analysis showed our edge depends on the market state.
6. A daily-return HMM on 75 days has too few observations for six-plus parameters. Do not.
7. Use as a classifier input first; promote to a gate only if the walk-forward evidence says so.

## Kalman and particle filters (pp. 227–234)

Kalman = linear Gaussian state space sₜ = A sₜ₋₁ + ε, yₜ = C sₜ + ξ (Eqs. 7.9–7.10); recursions not
given. Particle filters handle non-Gaussian states; their likelihood is discontinuous in θ because of
resampling, which "breaks" gradient optimisers (p. 233). The stochastic-volatility application
(log-variance as AR(1) with leverage and jumps, pp. 230–232) is daily-frequency machinery; the cheap
version for us is an EWMA of squared minute returns as the noise estimate.
