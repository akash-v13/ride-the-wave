---
name: dixon-ml-finance
description: >
  Rules for building, validating and using statistical / machine-learning models in the Ride The Wave
  trading bot, distilled from Dixon, Halperin & Bilokon, "Machine Learning in Finance: From Theory to
  Practice" (Springer 2020) with printed page references. Load this whenever the work involves a
  classifier or regression on the feature dataset, train/test or cross-validation splits, walk-forward
  or backtest overfitting, calibrated probabilities or confidence for entries, position sizing from a
  model, feature ranking or interpretability, stationarity / autocorrelation / GARCH / HMM regime
  detection, sequence models (RNN, LSTM), reinforcement learning, optimal stopping or a learned exit
  rule, or any claim that a strategy "works" from a backtest. Also load it before adding scikit-learn,
  statsmodels, hmmlearn or a neural-network library to this project.
---

# Machine learning in finance, applied to Ride The Wave

The book's one-line thesis: supervised ML is "an algorithmic form of statistical model estimation in
which the data generation process is treated as an unknown" (p. 16), judged by out-of-sample
prediction, and "a common mistake is to assume that building a predictive model will result in a
profitable trading strategy" (p. 32). Every rule below exists to keep us honest about small, noisy,
non-stationary data. Page numbers are the book's printed pages; the PDF is at
`docs/books/machine-learning-in-finance-*.pdf` (printed page = PDF page − 22).

## 1. Before any model: prove there is structure to learn

Run `scripts/diagnose_returns.py` (or the equivalent for new data) and read the result before writing
a model. The book's protocol (pp. 205–208, 242, 273–274): ADF for stationarity, ACF/PACF against the
white-noise band ±2.58/√T (99%) or ±1.96/√T (95%), Ljung-Box for whiteness, then the conditional
question the strategy actually asks ("what happens after the trigger fires?").

Result recorded 2026-09-17 (`docs/research/2026-09-17-streak-autocorrelation.md`): 1-minute returns
are white noise at lags 1–3; after our 3-bar streak with 1% gain, forward return is +6 bp at 10 min
and **−10.7 ± 9.2 bp at 60 min**. The streak trigger is not the edge; the filters and the asymmetric
exit are. A feature is only worth modelling if it "correlates with returns, is predictable itself, and
its characteristic time is larger than the time step" (p. 383). Details: `references/time-series-diagnostics.md`.

## 2. Labels and features

- **Label = the tradable outcome**: the sign/size of the P/L *our own exit rules* would produce
  (p. 30 "it must be actionable (i.e., tradable)"). Keep MFE/MAE and target-before-stop as
  diagnostics and check they agree with the tradable label (p. 36: mislabelling biases everything).
- Check the base rate. Far from balanced means an "outlier prediction problem ... beyond an
  off-the-shelf classifier" (p. 32); rebalance the threshold ε rather than the model.
- Features as scale-free ratios or within-window z-scores, never raw levels (pp. 31, 205–206).
  Drop collinear pairs (p. 37). Exclude anything that cannot itself be predicted or hedged (p. 37).
- Non-stationarity is the default: "cross-validation would not help here, as we cannot draw testing
  data from the distribution we care about, since that distribution comes from the future" (p. 39).
  Check feature drift between folds; plan periodic refits.

## 3. Model ladder for ~8k noisy rows

1. **Reference model**: the current rule (three gates). "Model selection is always relative rather
   than absolute. We must always pick a reference model" (p. 67).
2. **Regularised logistic regression** (L1/L2): the "zero-hidden-layer network" (pp. 116, 141) and
   the MAP of a Bayesian logistic model (p. 21). Start here.
3. **Shallow trees / boosted stumps**: the book's answer to interactions the linear model misses
   (p. 5); regularise by depth, leaves, learning rate, iterations (Table 4.1, p. 139).
4. **One tanh hidden layer, ≤10 units, L1 + dropout tuned by walk-forward** (p. 178). Expect the
   gain over linear to be "marginal" (p. 179). tanh, not ReLU, so the model stays interpretable (p. 177).
5. **Not**: deep nets ("very data intensive", p. 47), RNN/LSTM unless PACF shows memory the features
   do not carry ("If the data is i.i.d., then no sequence is needed (i.e., T = 1)", p. 240), deep
   Q-learning ("problematic" in finance, p. 336).

If no model clearly beats the reference by evidence, average them (Eq. 2.28, p. 70) or keep the rule.

## 4. Validation: walk-forward by day, three slices, aggregated test

"In prediction models over time series data, no future observations can be used in the training set.
Instead, a sliding window must be used" (p. 213). Fig. 6.4: each window has **train → verification
(tune λ, threshold, calibration) → test**; slide forward; concatenate the test slices and report only
those. Fixed window length keeps sample sizes interpretable (p. 213).

- Split on **days**, never on rows: minutes within a symbol-day are autocorrelated and overlapping
  label windows make rows dependent (look-ahead bias, p. 214). Our labels use same-day bars only, so
  day splits do not leak; row shuffles do.
- Tune nothing on the test slice. The 2026-09-17 half/half split had no verification slice, so the
  gate thresholds are in-sample; re-tune per fold (`references/validation-and-model-selection.md`).
- Score with log-loss for fitting (p. 13), AUC for ranking ("robust to class imbalance", p. 213),
  never accuracy. Test the confusion matrix against white noise with the χ² of Eq. 6.49 (critical
  6.635, p. 212). Compare two models with Diebold-Mariano, not a t-test on means (p. 220).
- The decision threshold is a business choice: "0.5 is intuitive but arbitrary" and bad entries and
  missed entries have unequal costs (pp. 211–212). Choose it on the verification slice.
- **Evaluate on the strategy**: profit factor, hit rate, average win and loss, **max drawdown against
  net P/L**, trades per day and information ratio of the gated system in the replay engine, because
  prediction ≠ profit (p. 34). `scripts/sweep.py --save-trades` records per-trade P/L for this.
- A profit-factor claim is about payoff size as much as hit rate. Bootstrap the per-trade P/L
  (`evalkit.py bootstrap`) for a CI on mean P/L and PF, and on the PF *difference* against the
  reference; the binomial Bayes factor only tests the hit rate.

Helpers: `scripts/evalkit.py` (day folds, calibration table, χ², posterior win rate, Bayes factor,
P/L and PF bootstrap, break-even win rate, Diebold-Mariano).

## 5. Probabilities, confidence and sizing

- Deterministic rules are "hard-wired ... rule-based technical analysis" (p. 11); an overconfident
  model loses **unboundedly** when bet on, a 50/50 model's loss is bounded (Ex. 1.2, p. 42). The
  classifier must emit calibrated probabilities, and "the probability vector obtained from the network
  is often erroneously interpreted as model confidence" (p. 149).
- Logistic outputs are true posteriors only if features are conditionally independent given the
  label (p. 71). Ours are not: **calibrate on the verification slice** and report a reliability table.
- Output variance is g(1−g), maximal at 0.5 (p. 10): a probability of 0.55 carries almost nothing.
  Gate well above 0.5 and size by the mean–variance rule u* = E[return]/(2λ·Var[return]) (Eq. 1.17,
  p. 28), capped by the slot limit.
- Keep a running **Beta–Bernoulli posterior** of the live win rate: prior Beta(α, β) → posterior
  Beta(α + wins, β + losses) (p. 60). Two integers, exact, and a calibrated kill switch.
- Claims of edge need evidence, not p-values: 115 heads in 200 rejects fairness at p ≈ 4% but the
  Bayes factor is 1.2, "no evidence" (Ex. 2.4, p. 68). PF 1.25 on 116 trades is in this territory.
  Compute the Bayes factor against the reference before saying a change "works". The reference
  rate is the win rate *without* the change (for a filter: the unfiltered candidates; for a
  parameter change: the previous profile), and the break-even rate is avg_loss/(avg_win+avg_loss).
  Report both the posterior probability of being below break-even and the PF bootstrap.

## 6. Explaining the model

Rank features by **sensitivities** (Jacobian of the output on standardised inputs) and pairs by
**interaction effects** (Hessian), with bootstrap confidence intervals (Ch. 5, pp. 168–178). For
logistic regression the sensitivities are the coefficients. Use tanh so derivatives exist ("We do not
recommend using ReLU", p. 177). Run the control first: fit simulated linear data and confirm the model
recovers the OLS coefficients (p. 168). `references/interpretability.md`.

## 7. Regimes and volatility

A 2-state Gaussian HMM on SPY minute returns is a cheap regime feature, but it separates on
*variance*, not direction; use only the **filtered** (causal) state probability, never the smoothed
one, or the backtest leaks (pp. 224–226). A daily HMM on 75 days is too little data. Volatility is a
persistent latent AR(1) (p. 230); the one-line upgrade to our 20-bar range is an EWMA of squared
minute returns (p. 243). `references/regimes-and-state-space.md`.

## 8. Reinforcement learning: exits yes, end-to-end no

RL collapses to independent one-step decisions when actions do not change the environment (p. 284);
our entries are near-independent bets, so strategy selection is a contextual bandit (Thompson
sampling over `config/profiles/`, pp. 282–283), not an MDP. The **intra-trade hold/sell sequence** is
an MDP, specifically American-style optimal stopping, and our trades do not move prices, so the
logged paths in the feature dataset are the "forward paths" of Longstaff-Schwartz (pp. 353–355, 379):
regress continuation value on (unrealised gain, drawdown from peak, minutes held), backward in
hold-time, sell when immediate payoff exceeds continuation. Batch DP on logged data, no simulator, no
exploration (p. 282). Expect fewer stop-outs, not more upside (low signal-to-noise, p. 348). Never
fit the action and Q on the same data (p. 372). `references/rl-and-optimal-stopping.md`.

## 9. Working order for phase 13

`references/ride-the-wave-plan.md` turns all of the above into the concrete sequence: diagnostics
(done) → slower-bar diagnostics → walk-forward folds → logistic reference vs trees → calibration →
strategy-level evaluation in the engine → Bayes factor vs the three gates → exit-rule DP study.
Record every experiment in `docs/research/` with the fold table and the reliability table.

## Raw material

`references/notes/` holds the chapter-by-chapter notes with page references (chapters 1–2, 4–6, 7–8,
9–10). Chapters 3 (Gaussian processes for derivatives), 11 (inverse RL) and 12 (frontiers) were not
distilled; nothing in them applies to an intraday equity bot today.
