# Dixon, Halperin & Bilokon, *Machine Learning in Finance* — notes on Ch. 4–6

Page numbers are the **printed** numbers in the running headers (printed = PDF page − 22; the file's `printed ~m` markers are one too high).

## 1. What these chapters are about

Ch. 4 (pp. 111–166) is feedforward-network theory for **i.i.d. data**: geometry of hidden units, VC dimension and empirical risk, why depth helps, how MLPs relate to other learners, the train/validate/test procedure, SGD, back-propagation, dropout, Bayesian networks. The authors say up front that this setting "is not suitable for times series data" (p. 111). Ch. 5 (pp. 167–190) is a white-box interpretability method: rank features by *sensitivities* (Jacobian of output w.r.t. inputs) and rank pairs by *interaction effects* (Hessian), with variance bounds, applied to cross-sectional factor models. Ch. 6 (pp. 191–220) is an econometrics primer: AR/MA/ARMA, stationarity and unit roots, PACF, MLE, heteroscedasticity, GARCH, exponential smoothing, the Box–Jenkins loop, forecast and binary-event evaluation, walk-forward cross-validation, PCA.

## 2. Key claims and principles

**Train / validation / test (Ch. 4 §4, pp. 140–141).** Two phases: training, then "assess how well the deep learner has been trained for out-of-sample prediction." The second is often split into 2.a "estimate the out-of-sample accuracy of all approaches (a.k.a. validation)" and 2.b "compare the models and select the best performing approach based on the validation data (a.k.a. verification)". Objective: minimise f(W,b) + λφ(W,b); λ "we tune using the out-of-sample predictive mean squared error"; the penalty "introduces a bias–variance tradeoff" (p. 141). A "not explicitly stated" assumption is homoscedastic errors, relaxable "by weighting the observations differently" (pp. 140–141). This section is generic; the financial split rule is in Ch. 6.

**Walk-forward cross-validation (Ch. 6 §4.2, pp. 213–214).** "In prediction models over time series data, no future observations can be used in the training set. Instead, a sliding window must be used to train and predict out-of-sample over multiple repetitions." Fig. 6.4 ("walk forward optimization") splits each window into an in-sample period, a *verification* period for tuning hyperparameters, and a *test* period; test periods are aggregated. A telescoping window "has the advantage of including more observations in the training set but can lead to difficulty in interpreting the confidence of the parameters, due to the loss of control of the sample size" (p. 213). Ordinary CV "must be modified for use on time series data" (p. 191).

**Regularisation, dropout, early stopping.** "The main tools for variable or predictor selection are regularization and dropout" (pp. 112, 140). Dropout rate θ is "a further hyperparameter (like λ) which can be tuned via cross-validation" and the objective "is closely related to ridge regression with a g-prior" (p. 148). "Increasing the level of L1 regularization increases the in-sample bias but reduces the out-of-sample bias" (p. 178). Early stopping appears only as Exercise 4.11: Keras EarlyStopping with |L(k+1) − L(k)| ≤ δ (p. 156). "for small samples, one cannot guarantee that ERM will also minimize the expected risk" (p. 122).

**MLPs vs. logistic regression and trees.** "A feedforward classifier with no hidden layers is a logistic regression model—it partitions the input space with a plane" (p. 116; also p. 141). With linear activations the network "is just linear regression, regardless of the number of layers" (p. 114); activation introduces interaction terms X_i X_j (Eq. 4.5, p. 114). One hidden layer "is essentially a projection pursuit regression"; "Boosted decision stumps ... can even be expressed as a single-layer MLP"; but "Caution must be exercised in over-stretching these conceptual similarities" (p. 139). Table 4.1 (p. 139) lists each learner's regularisers: trees (depth, leaves, minimal leaf size), random forest (trees, variables per tree, bootstrap size), boosting (learning rate, iterations). "decision trees with t − 1 nodes correspond to t-sawtooths" (p. 130).

**Interpretability (Ch. 5).** "Model sensitivities are the change of the fitted model output w.r.t. input" and match regression coefficients, ∂_{X_i} Ŷ = β_i (pp. 168–169). Requires Lipschitz continuity: tanh qualifies, "ReLU(x) := max(·, 0) is not continuously differentiable and one cannot use the approach" (p. 169). Sensitivities "are independent of the error", so heteroscedasticity is irrelevant here (p. 169). Rank inputs by sensitivity (Figs. 5.1–5.2) and pairs by off-diagonal Hessian (Fig. 5.3, p. 173). Garson's method "does not provide the direction"; Olden's "does not account for non-linearity introduced into the activation" (p. 186); PDPs ignore interactions (pp. 185–186). For ReLU shallow nets V[J_ij] = μ_ij(n−1)/n, so more units "reduces interpretability of the sensitivities" (Remark 5.1, p. 173); inputs "should be rescaled so that each μ_ij ... is a small positive value" (Remark 5.2, p. 174). With tanh, sensitivity std falls monotonically with width: 0.109 at 2 units, 0.026 at 200 (Tables 5.2–5.3, p. 176), CIs "estimated under a non-parametric distribution". Verdict: "We do not recommend using ReLU activation because it does not permit identification of the interaction terms and has provably non-convergent sensitivity variances" (p. 177). Control experiment: fit to simulated linear data and check the NN recovers OLS coefficients (p. 168; Table 5.1, p. 175).

**Factor modelling (Ch. 5 §6, pp. 177–183).** BARRA r_t = B_t f_t + ε_t (Eq. 5.17); non-linear r_t = F_t(B_t) + ε_t via an MLP; "stationarity of the factor realizations is not required" because it predicts next period only (p. 177). Inputs "are standardized to enable model interpretability"; L1 + tanh; width and λ by three-fold CV (p. 178). NN edge on the toy set is "marginal because the dataset is too simplistic" (p. 179); on Russell 3000 with ~50 factors it gives "positive and higher information ratios than OLS", with random portfolios "for control" (p. 180).

**Autoregression and stationarity (Ch. 6 §2–3).** AR(p): y_t = μ + Σ φ_i y_{t−i} + ε_t (Eq. 6.2, p. 194). AR(1) stable iff |φ| < 1, impulse response φ^j (p. 195). Stationary and ergodic iff all roots of the characteristic polynomial lie outside the unit circle; random walk has root z = 1; roots are companion-matrix eigenvalues (pp. 196–197). ADF unit-root test (null = non-stationary): "Attempting to fit a time series model to non-stationary data will result in dubious interpretations of the estimated partial autocorrelation function and poor predictions" (p. 205). Remedy is differencing, with "no guarantee that first order differencing yields a stationary difference process" (p. 206). PACF cut-off gives p, ACF cut-off gives q (p. 207), or AIC. Residuals must be white noise (Ljung–Box, p. 208). "Maximizing the conditional likelihood is equivalent to ordinary least squares estimation" (p. 200). Heteroscedastic AR (ε_t ~ N(0, σ²_{n,t})) is fitted in two steps but "the use of the sample variance of the residuals is only appropriate when the sample size is sufficient" (pp. 200–201). GARCH variance forecasts mean-revert at rate (α1+β1) (p. 203).

**Forecast evaluation (Ch. 6 §4).** Continuous: "MSE or the MAE" over the horizon (p. 210). Binary: model the log-odds; the 0.5 threshold is "intuitive but arbitrary" (p. 212); "careful consideration must be given as to whether there is equal tolerance for type 1 and type 2 errors" (p. 211); chi-squared test of the confusion matrix against white noise (p. 212); ROC/AUC is "robust to class imbalance", accuracy is not (p. 213). Mariano–Diebold compares two time-series models; ARCH test = Ljung–Box on squared residuals (Table 6.3, p. 220). "linear regressions predicting the difference between a future and current price, taking as inputs various moving averages, are often used in preference to parametric models, such as GARCH" (p. 218). Horizon must allow "economic realization of the trading signals" (p. 217).

## 3. Formulas and procedures worth implementing

- **Binary cross-entropy** (Eq. 4.37, p. 141): L = −G ln Ĝ − (1−G) ln(1−Ĝ), Ĝ = sigmoid output.
- **Sensitivities, one tanh layer** (Eqs. 5.4–5.5, p. 169): ∂_{X_j} Ŷ = Σ_i w^(2)_{·,i} (1 − σ²(I^(1)_i)) w^(1)_{ij}; matrix form ∂_X Ŷ = W^(2) D(I^(1)) W^(1), D_ii = σ′(I_i), off-diagonal 0. L layers (Eq. 5.7, p. 170): ∂_X Ŷ = W^(L) D(I^(L−1)) W^(L−1) … D(I^(1)) W^(1). Bounds (Eq. 5.6): min(W^(2)W^(1), 0) ≤ ∂_X Ŷ ≤ max(W^(2)W^(1), 0).
- **Interactions** (Eq. 5.9, p. 170): ∂²_{X_i X_j} Ŷ = W^(2) diag(W^(1)_i) D″(I^(1)) W^(1)_j; activation "at least twice differentiable".
- **Ranking recipe** (pp. 170–178): standardise inputs; tanh net with L1 chosen by CV; Jacobian per observation; rank inputs by its distribution; rank pairs by Hessian; refit with resampling for CIs.
- **PACF 95% band** (Eq. 6.44, p. 207): ±1.96/√T. **Lag-2 PACF** (Eq. 6.17, p. 198): τ̃_2 = (τ_2 − τ_1²)/(1 − τ_1²).
- **AIC** (Eq. 6.45, p. 207): ln(σ̂²) + 2k/T, k = p + q + 1.
- **Ljung–Box** (Eq. 6.46, p. 208): Q(m) = T(T+2) Σ_{l=1}^m ρ̂_l²/(T−l) ~ χ²(m−p) for AR(p).
- **Confusion-matrix chi-squared** (Eq. 6.49, p. 212): χ² = Σ_{ij} (m_ij − m_{i·}m_{·j}/m)² / (m_{i·}m_{·j}/m), 1 d.o.f., critical value 6.635.
- **TPR = TP/(TP+FN), FPR = FP/(FP+TN), precision = TP/(TP+FP), F1 = 2·prec·rec/(prec+rec)** (pp. 212–213).
- **Exponential smoothing** (Eqs. 6.36, 6.38, p. 204): ỹ_{t+1} = α y_t + (1−α) ỹ_t; half-life k = −ln(2α)/ln(1−α). **GARCH half-life** (p. 203): K = ln(0.5)/ln(α1+β1).
- **Walk-forward** (pp. 213–214): slide a fixed window; train → tune on verification slice → score on test slice; concatenate test slices.

## 4. Pitfalls and warnings

- The VC bound "only holds for i.i.d. data and little is known in the case when the data is auto-correlated" (p. 123).
- "the probability vector obtained from the network is often erroneously interpreted as model confidence" (p. 149); dropout samples are draws from the predictive posterior (p. 151).
- Back-prop "is not guaranteed to convergence to a unique minimum" (p. 158); fits "will vary slightly with each optimization" (p. 175); learning rates "are usually found empirically" (p. 143).
- "potential instabilities whereby small changes in hyperparameters lead to substantial differences in model performance" (p. 205); prefer parsimony.
- In-sample fitting gives "no strong guarantee of avoiding over-fitting as the performance of the model is not assessed out-of-sample" (p. 209).
- Look-ahead bias "occurs when one or more observations in the training set are from the future" (p. 214).
- Accuracy misleads under class imbalance: a constant classifier is x% accurate on x% positives (p. 213).
- ReLU breaks sensitivity/interaction analysis (pp. 169, 173, 177).
- Match model frequency to data frequency: build on the native bars and forecast k steps ahead (pp. 191–192).

## 5. Applicability to Ride The Wave

**Validation.** Our first-half/second-half split is a single fold of Fig. 6.4 with no verification slice, so any threshold or λ chosen on the second half is in-sample. Replace it with rolling walk-forward over **days** (e.g. ~25 days train, 5 verification, 10 test, stepped forward; our numbers, the book's structure), fixed window length (p. 213), and report the aggregated test metric. Never shuffle rows: minutes within a symbol-day are autocorrelated, so row-level K-fold is the look-ahead bias of p. 214. Because labels look 60 bars ahead, drop the last 60 bars of each training window (our extension of the same principle).

**Model choice for ~8k rows.** The book's own small-data recipe is a shallow tanh network with L1, width and λ by CV (p. 178), and it repeatedly finds the NN's edge over linear models "marginal" on simple data (p. 179). So: baseline = zero-hidden-layer network, i.e. logistic regression (pp. 116, 141); challenger = one tanh layer of ≤10 units with L1 and dropout tuned by walk-forward. Boosted stumps are a legitimate second challenger (p. 139), regularised per Table 4.1. Score with AUC, not accuracy (p. 213); choose the gating threshold on the verification slice, treating 0.5 as arbitrary (p. 212) and weighting type I errors (bad entries) more than type II (missed entries) (p. 211). Test the confusion matrix against white noise (Eq. 6.49) and compare classifier vs. the three gates with Mariano–Diebold (p. 220), not a plain t-test.

**Explaining decisions.** Use tanh so Jacobian and Hessian exist (pp. 169, 177); standardise features (p. 178); rank features by the sensitivity distribution over candidates and rank pairs (e.g. relative volume × SPY return) by Hessian entries, with bootstrap CIs (p. 176). Run the linear-data control first (p. 168). For logistic regression the sensitivities are the coefficients.

**Calibration and sizing.** Raw sigmoid output is not confidence (p. 149). Calibrate on the verification slice before using probabilities for sizing; with a NN, use dropout sampling for an uncertainty band (p. 151).

**Sequence models: not yet.** Ch. 6 is the "performance baseline" (p. 191) and our features already summarise the recent sequence. Before any RNN, run the classical checks on minute returns: ADF (p. 205) and PACF against ±1.96/√T (p. 207). If the PACF is flat past lag 1–3, a sequence model has nothing to learn that the streak features do not already carry.

**Against current practice.** (1) Gate thresholds tuned on all 75 days are in-sample; re-tune per fold. (2) PF 1.25 on 116 trades carries no significance test; add Eq. 6.49 and Mariano–Diebold. (3) Session return and relative volume are regime-dependent levels; the book's remedy is differencing/standardising (pp. 205–206), so keep features as within-window z-scores or ratios. (4) P/L variance scales with volatility; weight observations (p. 141) or vol-scale the label, mirroring the two-step heteroscedastic fit (pp. 200–201).

## 6. What to skip and why

- Ch. 4 §2.3–2.7 (dimensionality heuristics, universal approximation, VC theorems, splines, sawtooth depth lemmas, pp. 117–132): i.i.d. theory with no design guidance beyond "one hidden layer suffices in principle".
- Ch. 4 §3 convexity and no-arbitrage constraints (pp. 132–138): option pricing.
- Ch. 4 §5.1–5.2 back-prop derivations, Adam/RMSprop/AdaGrad, ADMM (pp. 143–148): library internals.
- Ch. 4 §6 Bayesian NNs, ELBO, reparameterisation (pp. 149–152): keep only the dropout-uncertainty remark.
- Ch. 5 §5.1 Chernoff bounds and the variance proof (pp. 174, 186–187): weak bounds; the conclusion (avoid ReLU) is what matters.
- Ch. 5 Table 5.4 Bloomberg factors (pp. 181–182): monthly fundamentals.
- Ch. 6 §2.6 exact vs. conditional MLE, §2.8 MA algebra, §2.9 GARCH forecasting, §5 PCA (pp. 199–204, 213–217): revisit GARCH only if we vol-scale labels, PCA only if features grow past ~30.
