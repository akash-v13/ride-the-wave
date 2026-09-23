# Validation, model selection and calibration (Ch. 1, 2, 4 §4, 6 §4)

Printed page numbers.

## Walk-forward protocol (pp. 191, 213–214)

1. Order all data by time. Define a fixed window of W days: train (first part), verification (next),
   test (last). The book's Fig. 6.4 calls these in-sample, verification, test.
2. Fit on train. Tune hyperparameters (λ, tree depth, decision threshold, calibration map) on
   verification only.
3. Score the test slice once. Store predictions.
4. Slide the window forward by the test length. Repeat. Concatenate all test predictions; every
   reported metric comes from that concatenation.
5. A telescoping (growing) train window is allowed but "can lead to difficulty in interpreting the
   confidence of the parameters, due to the loss of control of the sample size" (p. 213). Prefer fixed.

For Ride The Wave (our numbers, the book's structure): 75 trading days → e.g. train 25 / verify 5 /
test 10, step 10, giving four folds. Split on days. Labels use only same-day bars, so day-level
splits do not leak; rows within a day are still dependent (overlapping label windows), so treat the
effective sample size as the number of symbol-days, not rows, when judging significance.

Never: shuffle rows, fit scalers on anything but the train slice (companion notebooks: "re-scale
using the training set statistics"), or pick a threshold by looking at test P/L.

## Objective and metrics

- Fit by cross-entropy / log-likelihood: E(θ) = −Σ [Gᵢ ln g₁(xᵢ) + (1−Gᵢ) ln(1−g₁(xᵢ))] (Ex. 1.4,
  p. 43; Eq. 4.37, p. 141). Not accuracy, not P/L (P/L is the *evaluation*, not the fitting target).
- Rank by AUC (p. 213). Accuracy misleads under imbalance: a constant classifier scores the base rate.
- Confusion-matrix χ² against independence (Eq. 6.49, p. 212): χ² = Σᵢⱼ (mᵢⱼ − mᵢ·m·ⱼ/m)² /
  (mᵢ·m·ⱼ/m), 1 d.o.f., reject white noise above 6.635.
- Two forecasters: Diebold-Mariano on the loss differential, HAC variance (p. 220).
- Precision, recall, F1 as usual (pp. 212–213); "careful consideration must be given as to whether
  there is equal tolerance for type 1 and type 2 errors" (p. 211). For us a bad entry (type I) costs
  money; a missed entry (type II) costs an opportunity.
- Then the numbers that matter: run the gated strategy through the replay engine and report profit
  factor, hit rate, average P/L per trade, max drawdown, information ratio, per fold.

## Bias–variance and regularisation

MSE = variance + bias² (p. 55). "Regularization is arguably the most important aspect of why machine
learning methods have been so successful in finance" (p. 21). L2 = Gaussian prior, L1 = Laplace prior
(p. 21). "Increasing the level of L1 regularization increases the in-sample bias but reduces the
out-of-sample bias" (p. 178). Dropout ≈ ridge with a g-prior; its rate is a hyperparameter for CV
(p. 148). "For small samples, one cannot guarantee that ERM will also minimize the expected risk"
(p. 122): with 8k rows, lean on priors and shrinkage.

## Model selection by evidence (pp. 63–70)

- Rashomon effect: several models with fit within 1% and disjoint variables (pp. 63–64). Sweeping
  gates and picking by in-sample profit factor is exactly this.
- Evidence p(x|M) = ∫ p(x|θ,M) p(θ|M) dθ; Bayes factor B₁₂ = p(x|M₁)/p(x|M₂) (Eqs. 2.16–2.20).
- Worked example (pp. 67–68): 115 heads in 200. Fair-coin evidence C(200,115)/2²⁰⁰ ≈ 0.005956;
  uniform-θ evidence 1/201 ≈ 0.004975; B = 1.2, |ln B| = 0.18: "no evidence", although the two-sided
  frequentist test rejects at p ≈ 4%.
- Occam: complex models "can generate many possible data sets, but they are unlikely to generate any
  particular dataset at random" (p. 69).
- Bayesian model averaging p(y*|y) = Σᵢ p(y*|y,Mᵢ) p(Mᵢ|y) (Eq. 2.28, p. 70) when no model dominates.

Apply to us: reference = three-gate rule. For a candidate classifier, compute the Bayes factor of
"gated win rate = reference win rate" on the aggregated test slices before claiming improvement.
`scripts/evalkit.py bayes` does the binomial version.

## Calibration and sizing

- Logistic output is the posterior only under conditional independence of features given the label
  (p. 71). Calibrate: bin verification-slice predictions into deciles, compare mean prediction with
  observed frequency; fit an isotonic or Platt map if the reliability curve bends.
- Variance of a binary prediction is g(1−g), maximal at 0.5 (p. 10): probabilities near 0.5 carry no
  information; do not size on them.
- Mean–variance fraction u* = E[φ|S]/(2λ Var[φ|S]) (Eq. 1.17, p. 28), from reward u φ − λ u² Var[φ].
  With a calibrated p and payoff asymmetry (win w, loss l): E = p w − (1−p) l, Var ≈ p(1−p)(w+l)².
  Cap at the slot limit.
- Running posterior: Beta(α+wins, β+losses); mean (α+wins)/(α+β+n); with a uniform prior and 116
  trades the s.d. of the win rate is ≈ √(p(1−p)/116) ≈ 0.046 at p = 0.5 (pp. 58–60). Use it live as
  a kill switch: if the posterior probability that win rate < break-even exceeds X, stop trading.

## Label noise

Ex. 1.4 (p. 43): weight each term of the cross-entropy by πᵢ, the probability that label i is
correct, which "renders the model robust to incorrectly labeled data". Our labels depend on
simulated fills; treat borderline P/L (within slippage of zero) as low-confidence labels.

## Non-stationarity (pp. 20, 34–40)

The mortgage model that fit 2001 "almost perfectly" missed 2006 by more than half because the
generating process changed and no series captured it. Remedies the book allows: features that are
themselves predictable or hedgeable (p. 37), stationarity tests before modelling (p. 40), retraining
on a schedule, drift checks between folds. Remedies it does not allow: trusting a single-period fit.
