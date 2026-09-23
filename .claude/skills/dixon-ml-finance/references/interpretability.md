# Explaining a fitted model (Ch. 5)

## Sensitivities and interactions (pp. 168–174)

- Sensitivity = ∂Ŷ/∂Xᵢ, the change of the fitted output for a change in input; for linear regression
  it is the coefficient βᵢ (pp. 168–169). For logistic regression it is the coefficient times
  g(1−g) at the point.
- One tanh hidden layer: ∂ₓŶ = W⁽²⁾ D(I⁽¹⁾) W⁽¹⁾ with D = diag(σ′(I)) (Eqs. 5.4–5.5, p. 169);
  L layers chain the same way (Eq. 5.7, p. 170). Bounds: min(W⁽²⁾W⁽¹⁾, 0) ≤ ∂ₓŶ ≤ max(W⁽²⁾W⁽¹⁾, 0).
- Interaction effect = ∂²Ŷ/∂Xᵢ∂Xⱼ = W⁽²⁾ diag(W⁽¹⁾ᵢ) D″(I⁽¹⁾) W⁽¹⁾ⱼ (Eq. 5.9, p. 170); needs a twice
  differentiable activation.
- Requires Lipschitz continuity: tanh qualifies, ReLU does not (p. 169). With ReLU the sensitivity
  variance grows with width (Remark 5.1, p. 173). "We do not recommend using ReLU activation because
  it does not permit identification of the interaction terms and has provably non-convergent
  sensitivity variances" (p. 177).

## Procedure (pp. 168–178)

1. Standardise inputs (p. 178; Remark 5.2, p. 174).
2. Control experiment: simulate linear data, fit the model, confirm it recovers the OLS coefficients
   (p. 168; Table 5.1, p. 175). If it cannot, the explanation method is not trustworthy on real data.
3. Fit with tanh and L1 chosen by walk-forward (p. 178).
4. Compute the Jacobian per observation; rank inputs by the distribution of sensitivities (median,
   interquartile range), not by a single number.
5. Rank pairs by the off-diagonal Hessian entries (Fig. 5.3, p. 173). For us the obvious pairs are
   SPY-session-return × session-return and trade-count-ratio × relative-volume, which the three
   hand-coded gates approximate.
6. Bootstrap (refit on resampled days) for confidence intervals (p. 176). With tanh the sensitivity
   s.d. falls with width: 0.109 at 2 units, 0.026 at 200 (Tables 5.2–5.3).

## Methods the book rejects (pp. 185–186)

Garson's weight products give no direction; Olden's ignore non-linearity in the activation; partial
dependence plots ignore interactions. Sensitivities and Hessians are the recommended route.

## Factor-model precedent (pp. 177–183)

Non-linear factor model rₜ = Fₜ(Bₜ) + εₜ with an MLP: standardised inputs, L1 + tanh, width and λ by
three-fold CV; on Russell 3000 with ~50 factors it produced "positive and higher information ratios
than OLS", with random portfolios as control (p. 180). On the toy set the edge was "marginal because
the dataset is too simplistic" (p. 179). Our dataset is closer to the toy.
