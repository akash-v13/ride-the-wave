# Dixon, Halperin & Bilokon, *Machine Learning in Finance* (Springer 2020) — Ch. 7 Probabilistic Sequence Modeling, Ch. 8 Advanced Neural Networks

Notes for the Ride The Wave skill. Page numbers are the book's printed pages (221–276). Anything marked **[RTW judgement]** is our inference, not the book's claim.

## 1. What these chapters are about

Ch. 7 introduces state-space models: an unobservable latent process X_t "drives another, observable process" Y_t (p. 221). It covers discrete-state hidden Markov models, the Viterbi most-likely-path algorithm, the Kalman filter as the "continuous latent state analogue" of an HMM (p. 227), particle filters (sequential importance resampling), a stochastic-volatility-with-leverage-and-jumps application, and calibration of such filters by maximum likelihood or MCMC. Ch. 8 reinterprets RNNs as non-linear AR(p) models, GRUs/LSTMs as neural exponential smoothers with gates, 1-D CNNs as AR(p) on kernel-smoothed inputs, and linear autoencoders as PCA, with two small financial notebooks (Coinbase minute prices, ZN-futures tick data). Both chapters are mostly theory: no HMM is ever fitted to real data, and neither notebook reports a numeric out-of-sample result or a linear baseline.

## 2. Key claims with page refs

### HMMs and regime detection
- Model: hidden discrete state s_t is Markov; y_t depends only on s_t. p(s, y) = p(s_1) p(y_1|s_1) prod_{t=2..T} p(s_t|s_{t-1}) p(y_t|s_t) (Eq. 7.1, p. 223).
- Stated motivation is regimes: HMMs "provide intuition for understanding hidden variables and switching"; GRU/LSTM gating "is an implicit modeling step and cannot be controlled explicitly as may be needed for regime switching in finance" (p. 222).
- Example 7.1 "Bull or Bear Market?" (pp. 223–224): two hidden states (Bear = 0, Bull = 1), binary observation (market down = −1, up = +1), emissions P(y=−1|Bear) = 0.8, P(y=+1|Bull) = 0.8, transition A = [[0.9, 0.1], [0.1, 0.9]], P(s_1=0) = P(s_1=1) = 1/2. The matrices are **hand-specified, not fitted**; the example only computes the probability of the hidden path {1,0,0} given observations {−1,1,1}: 0.00036 (p. 224).
- Fitting: forward F_t(s) = P(s_t=s, y_{1:t}), backward B_t(s) = p(y_{t+1:T}|s_t=s), P(s_t=s, y) = F_t(s) B_t(s) (Eqs. 7.4–7.6, p. 224). "The forward–backward algorithm, also known as the Baum–Welch algorithm, is an unsupervised learning algorithm for fitting HMMs which belongs to the class of EM algorithms" (p. 224). **The M-step re-estimation formulas are not printed anywhere.**
- "If these matrices are known, there is no reason to use the Baum–Welch algorithm. If they are unknown, then the Baum–Welch algorithm must be used" (p. 226).
- Per-step argmax "may not lead to the best path in HMMs" (p. 226); Viterbi gives the path.
- Number of states: never chosen from data; both examples are K = 2 toys (bull/bear p. 223; fair/loaded coin p. 225).

### Kalman and particle filters
- Kalman = linear Gaussian state-space model s_t = A s_{t-1} + eps_t, y_t = C s_t + xi_t (Eqs. 7.9–7.10, p. 227). The predict/update recursions are **not given**; Exercises 7.1–7.2 (p. 235) only ask for ARMA(p,q) and Ornstein–Uhlenbeck in state-space form.
- Particle filter (SIR, pp. 228–229): for non-Gaussian, e.g. "bimodal" state distributions (p. 227).
- Application: stochastic volatility with leverage and jumps (p. 230). y_t = log-return, x_t = latent log-variance: y_t = eps_t e^{x_t/2} + J_t zeta_t, x_{t+1} = mu(1−phi) + phi x_t + sigma_v eta_t (Eqs. 7.13–7.14), corr(eps, eta) = rho < 0 (leverage), Bernoulli jumps. Parameters are fitted by maximising the particle-filter log-likelihood (Eq. 7.16, p. 232) with BFGS, or by MCMC/Gibbs on daily mean-adjusted log-returns (pp. 233–234).

### RNN / LSTM / CNN for financial time series
- "Sequence learning, then, is just a composition of a non-linear map and a vectorization of the lagged input variables. If the data is i.i.d., then no sequence is needed (i.e., T = 1), and we recover a feedforward neural network" (p. 240).
- Motivation for special architectures is "parsimony of parameters and therefore less propensity to overfit and reduced training time" (p. 239).
- Unactivated one-unit RNN = AR(p) with geometrically decaying coefficients phi_i = phi_x phi_z^{i−1} (Example 8.1, p. 243); a linear RNN with infinite lags "corresponds to an exponential smoother, z_t = alpha x_t + (1 − alpha) z_{t−1}" (p. 243).
- Design rules (p. 242): sequence length = "the largest significant lag in an estimated 'partial autocorrelation' function"; hidden units by bias–variance, "generally under a hundred units"; "each feature must be a time series and therefore exhibit autocorrelation."
- Stability needs |sigma| <= 1 (tanh) so "past random disturbances decay in the model" (pp. 245–246); a linear RNN is non-stationary (p. 246).
- GRU = dynamic exponential smoothing of the hidden state plus a reset gate (Eqs. 8.45–8.48, p. 253); "The price to pay for this flexibility is the additional complexity of the model" (p. 253). LSTM input gate "appears superfluous and difficult to reason with using time series analysis" (p. 254). GRU/LSTM need no covariance stationarity (pp. 274–275).
- Worked example 1, Bitcoin (p. 256): minute snapshots of Coinbase USD mid-price over 2018, predict the next minute's mid-price. ADF cannot reject a unit root -> "plain RNNs are not suited to non-stationary time series modeling" -> use GRU/LSTM. Result is a plot only (Fig. 8.3).
- Worked example 2, limit order book (pp. 256–257): tick-by-tick ZN futures top-of-book, 1,033,492 observations, labelled up-tick/same/down-tick, but the shown experiment regresses the next VWAP "smart price" on lagged smart prices. ADF on first 200k obs: statistic −3.9706, stationary; Ljung–Box picks the lag count. "Because the data is stationary, we observe little advantage in using a GRU over a plain RNN" (p. 257). No numeric result and no linear baseline.
- 1-D CNN = AR(p) on a kernel-filtered series; "there is no look-ahead bias because we do not filter the last k values"; "These weights are fixed over time and hence the CNN is only suited to prediction from stationary time series" (p. 259). Notebook is a toy integer sequence (p. 265).
- Linear autoencoder reproduces PCA on a yield-curve example (p. 269); not relevant here.

## 3. Procedures worth implementing

### 3a. Minimal two-state HMM regime detector
The book supplies the model, the state-probability identity and the decoder, but not the EM update formulas; use `hmmlearn` (not mentioned by the book) for step 3.

1. Observation series. Book's toy: direction of the market move, y_t in {−1, +1} (p. 223). For us: SPY 1-minute log-returns in the 09:31–11:30 window, or daily SPY returns (the book says nothing about horizon).
2. Model: K = 2 hidden states (the only K the book uses), initial pi, 2x2 transition A, emission B. Book emissions are discrete (p. 225); a per-state Gaussian is the continuous analogue.
3. Fit pi, A, B by Baum–Welch (forward–backward EM) because they are unknown (pp. 224, 226).
4. Per-bar regime probability: P(s_t = s | y) proportional to F_t(s) B_t(s) (Eq. 7.5, p. 224). For a live/causal feature use only the forward quantity F_t(s) (filtering, p. 226); smoothing uses future bars and would leak in backtests.
5. Most likely path, for labelling backtest days (p. 226):
   V_{1,k} = P(y_1|s_1=k) pi_k; V_{t,k} = max_i P(y_t|s_t=k) A_{ik} V_{t−1,i}; store xi(k,t) = argmax_i; s_T = argmax_k V_{T,k}; s_{t−1} = xi(s_t, t).
6. Feature: filtered P(bull state | bars to date) at the candidate bar, as a classifier input alongside the existing "SPY up on the day" gate.

### 3b. Time-series diagnostics before any sequence model (Exercises 8.6–8.7, pp. 273–274; summary p. 272)
(a) ADF test for stationarity; (b) PACF, take the largest lag significant at 99% as sequence length — "you will not be able to draw conclusions if your data is not stationary" (p. 273); (c) MSE in- and out-of-sample as hidden units vary; (d) L1 regularisation; (e) plain RNN vs GRU; (f) Ljung–Box on residuals: "A well-specified model should exhibit white noise error both in and out-of-sample" (p. 274).

### 3c. Volatility as a latent persistent state (p. 230)
Log-variance x_t follows AR(1) with persistence phi. Full particle-filter estimation is heavy; the exponential smoother the book identifies (p. 243) gives the cheap version: EWMA of squared minute returns. **[RTW judgement]**

## 4. Pitfalls and warnings
- Argmax-per-step state estimates "may not lead to the best path" (p. 226).
- Plain RNNs unsuited to non-stationary series (p. 256); CNN weights "fixed over time", stationary series only (p. 259).
- PACF lag selection is invalid on non-stationary data (p. 273); RNN features must themselves be autocorrelated series (p. 242).
- Particle-filter likelihood is discontinuous in theta because resampling draws from "a discontinuous empirical distribution function" (p. 233), which breaks gradient optimisers.
- Gibbs samplers are "a highly nontrivial piece of software" (p. 234).
- GRNN (heteroscedastic RNN) "is not yet proven in practice" (p. 248); on stationary data extra gates buy "little advantage" (p. 257).

## 5. Applicability to Ride The Wave **[RTW judgement throughout]**
- **HMM regime gate.** The book endorses HMMs for "regime switching in finance" (p. 222) but never validates one on data. A 2-state Gaussian HMM on SPY minute returns will separate on variance (minute-return means are tiny versus their standard deviation), so it is a volatility-regime detector, not bull/bear; the toy works only because its emissions are directional with 0.8 purity. Worth a cheap experiment as a classifier input using the filtered (causal) probability, not a hard fourth gate. A daily HMM on 75 days is too little data (six-plus parameters from 75 points).
- **Sequence models: not warranted.** The book's examples use ~0.5M–1M rows; our 8,370 candidate rows are a tabular snapshot with sequence content already summarised into features. By p. 240, treating rows as i.i.d. collapses the model to a feedforward net; a gradient-boosted tree or logistic regression is the appropriate "T = 1" model. The parsimony argument (p. 239) cuts against LSTMs at our size, and p. 257 shows that even with a million rows the gated model added nothing on stationary data.
- **Argues against us.** The streak-3 entry assumes positive autocorrelation of 1-minute returns at lags 1–3. The book's own protocol (PACF at 99%, Ljung–Box; pp. 242, 273) applied to our stocks' minute returns is a direct test. If no lag is significant, the streak has no autoregressive basis and any edge comes from the filters, not the streak. Run it on the 446k-row dataset.
- **Noise estimate.** The SV model (p. 230) says variance is a persistent latent AR(1); our 20-bar range is a crude proxy. EWMA of squared minute returns (p. 243) is the one-line upgrade; particle-filter SV is overkill.

## 6. What to skip and why
- Particle filter / SVLJ / MCMC calibration (pp. 227–234): daily-frequency volatility modelling; heavy machinery for a nuance we do not trade.
- CNN sections (pp. 257–265): image-oriented; the 1-D case is AR(p) on smoothed inputs, which our features already approximate.
- Autoencoders / PCA (pp. 266–271): yield-curve and factor-model uses; no role in an entry classifier.
- GRNN, alpha-RNN, LSTM internals (pp. 248–255): theory with no empirical support in the book.
- Kalman filter: the book gives only the model form, no recursions; nothing to implement from here.
