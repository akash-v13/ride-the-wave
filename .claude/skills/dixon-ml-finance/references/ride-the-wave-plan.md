# Phase 13 plan: classifier and exit study, by the book

Status 2026-09-17. Dataset: `data/features/features-2026-06-01-2026-09-16-sip.parquet`, 446,233
prospect rows, 8,370 candidates, 75 days, 81 symbols.

## Step 0: diagnostics (done)

`scripts/diagnose_returns.py`: minute returns are white noise at lags 1–3; the streak trigger has no
predictive content beyond ~10 minutes and reverses by 60. See
`docs/research/2026-09-17-streak-autocorrelation.md`.

## Step 1: slower bars and alternative triggers (cheap, do first)

Rerun the diagnostic on 5- and 15-minute bars (aggregate from the cache). If a streak on slower bars
shows positive, growing conditional forward returns, the whole strategy should move to that bar size.
Also measure the pullback entry: forward return after a ≥1% surge followed by a retrace of 30–50% of
it within N minutes, conditioned on SPY up.

## Step 2: folds

`scripts/evalkit.py folds --parquet <file> --train 25 --verify 5 --test 10 --step 10`. Four folds.
Fit scalers and everything else on train; tune on verify; predict test; concatenate.

## Step 3: models

1. Reference: three gates as they stand (thresholds re-tuned per fold on verify).
2. L1-regularised logistic regression on standardised features, λ by verify log-loss.
3. Gradient-boosted stumps (depth 1–2, few hundred trees, learning rate ≤0.05), tuned on verify.
4. Optional: one tanh layer ≤10 units with L1 and dropout.

Label: sign of `strat_pnl_pct` net of slippage; rows with |P/L| below slippage weighted down as
low-confidence labels (Ex. 1.4). Report base rate per fold.

## Step 4: probabilities

Reliability table on verify (deciles); isotonic map if bent. Choose the gating threshold on verify by
strategy P/L, expecting well above 0.5. Report AUC, log-loss, χ² of the confusion matrix, and the
reliability table on the concatenated test slices.

## Step 5: strategy-level evaluation

Wire the calibrated model as an `entry.filters` alternative (a `model_gate` with a probability
threshold) and run the replay engine on the test days of each fold. Compare with the reference on the
same days: PF, hit rate, trades, drawdown, information ratio. Diebold-Mariano on per-day P/L series.

## Step 6: evidence

Bayes factor for "model-gated win rate = reference win rate" on the concatenated test trades
(`scripts/evalkit.py bayes`). Posterior of the win rate with its s.d. If |ln B| < 1, say "no
evidence" and keep the rule; consider model averaging only if the model is at least as good.

## Step 7: exits

Longstaff-Schwartz continuation regression on the candidate paths (state: gain, drawdown from peak,
minutes held; basis: low-order polynomials; ridge), fitted on train days, evaluated as an exit rule in
the engine on test days. Success = fewer stop-outs at equal or better P/L.

## Step 8: sizing and monitoring

Mean-variance fraction from the calibrated probability (Eq. 1.17), capped. Live Beta-Bernoulli
posterior of the win rate with a kill switch. Refit schedule: monthly, plus drift checks on feature
distributions between the last fold and live data.

Every step writes a dated page in `docs/research/` with the fold table, reliability table and the
engine results on test days only.
