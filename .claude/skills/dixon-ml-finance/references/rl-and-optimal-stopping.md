# Reinforcement learning, batch dynamic programming and exits (Ch. 9–10)

## When RL is the right frame (pp. 280–284)

RL differs from supervised learning by a feedback loop (actions change the state) and by
exploration. "If rewards obtained at different steps are independent of each other ... the agent
should simply pick the action that maximizes its local reward" (p. 284); with no feedback loop the
problem "becomes equivalent to a sequence of independent one-step episodes", a contextual bandit
(pp. 282–283). Batch (offline) RL has no exploration: it "is essentially a problem of inference of
best possible actions given batch data of a recorded sequence of states, actions, and rewards"
(p. 282), and off-policy methods dominate real applications (p. 315).

For Ride The Wave: entries are near-independent bets → bandit over strategy variants (Thompson
sampling across `config/profiles/`). The hold/sell sequence inside a trade → finite-horizon MDP,
state = (unrealised gain, drawdown from peak, minutes held), which is what the trailing rule already
conditions on. Our orders do not move the price, so logged paths are valid counterfactuals for
"sell now" at every minute.

## Data requirements and the deep-RL warning

DP needs a known model and few states (three or four discretised dimensions, pp. 300, 304). Fitted Q
with K basis functions needs a multiple of K observations per time step (p. 327). Monte Carlo needs
full trajectories; TD(0) is "very volatile" (p. 312). "The practice of using Deep Q-learning on
finance problems is problematic" (p. 336). "Low signal-to-noise ratios and potentially very high
dimensionality are ... two marked differences" from games (p. 348). The book's own QLBS example used
50,000 simulated paths, 12 B-splines in one dimension, ridge 10⁻³ (pp. 373–374). We have 8,370 real
episodes: tiny basis, ridge, expect a "sufficiently good" (p. 307) improvement, mostly fewer stop-outs.

## Reward template

R = return − λ·Var[next value | state] (pp. 285, 289, 363, 384); bounded (p. 301); quadratic
penalties are symmetric (p. 406). Reward shaping r̃ = r + γ f(s′) − f(s) leaves the optimal policy
unchanged (Ex. 9.5, p. 339), so paying P/L changes each minute or a lump sum at exit gives the same
policy with γ = 1.

## Exit rule as optimal stopping: Longstaff-Schwartz on logged paths (pp. 353–355, 379)

1. Paths: every candidate entry in the feature dataset, minute by minute until the horizon (60
   minutes or the flatten time). Because the decision does not affect the path, "such simulation of
   forward paths should only be performed once, and then re-used" (p. 353).
2. Control: {continue, stop}. Immediate payoff hₜ = unrealised gain net of slippage; at the stop
   price hₜ is the stop loss.
3. Continuation value Cₜ(x) = E[max(hₜ₊₁, Cₜ₊₁) | xₜ] (Eq. 10.6), expanded on a small basis
   Cₜ(x) = Σ aₙ(t) φₙ(x) (Eq. 10.8) and fitted by least squares across paths alive at t (Eq. 10.7).
4. Backward from t = T−1 to 0. Rule: sell when hₜ > Cₜ(xₜ) (p. 379).
5. Risk-adjust by subtracting λ·Var[next-minute value] from the continuation (the book's template),
   which replaces the hand-coded minimum-gain floor with a principled one.
6. Fit on training folds, evaluate in the replay engine on test folds. Overestimation bias: never
   take the inner max from the same data used to fit (pp. 328–329, 372).

Cross-check with tabular finite-horizon value iteration on ~50–100 cells of (gain × drawdown × time)
with empirical transitions, like the 15-state market-making example (pp. 300, 322).

## Fitted Q Iteration template (pp. 327–328, 370–372)

Tuples (s, a, r, s′); basis ψₖ(s, a). For t = T−1 … 0: regress y = r + γ maxₐ′ Qₜ₊₁(s′, a′) on
ψ(s, a); Wₜ = Sₜ⁻¹ Mₜ with S = Σ ψψᵀ, M = Σ ψy, plus a small ridge. The inner max comes from the
previous step's fitted Q, never from the empirical max in the same data.

## Signals worth including (p. 383)

A signal belongs in the state only if it "(i) correlates with equity returns, (ii) is predictable
itself, (iii) its characteristic times τ are larger than the time step." A 3-bar streak on 1-minute
bars fails (iii) on a 1-minute decision step; SPY session return and trade-count ratio plausibly pass.

## Skip

QLBS hedge-ratio derivations, G-learning / entropy-regularised LQR for multi-asset allocation with
impact, Merton consumption and retirement planning, softmax/mellowmax operators, deep RL.
