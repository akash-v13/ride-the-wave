# docs/research

Write-ups of experiments run with the backtester: what was tested, on which data, the numbers, and what was concluded. One file per experiment, dated. Raw sweep CSVs live in `data/sweeps/` (gitignored).

## Index

- 2026-09-17-time-slice-sweep.md: 62 parameter configurations; none profitable; afternoon entries worst.
- 2026-09-17-feature-analysis.md: feature dataset; three entry filters; first profitable configuration (thin).
- 2026-09-17-streak-autocorrelation.md: 1-minute returns are white noise; the streak trigger is not the edge.
- 2026-09-21-slower-bars.md: 5-minute bars no; 15-minute bars show a small, growing, two-half-robust signal.
- 2026-09-21-spy-intraday-momentum.md: the published first-to-last half-hour effect is absent (slightly reversed) in 2016-2026; strategy rejected.
- 2026-09-21-news-jev-validation.md: Jev scores 21k headline-symbol pairs; positive news has no intraday edge and hurts streak entries; negative/legal news drifts lower; no filter built, keep collecting.
- 2026-09-22-fifteen-minute-and-orb-backtests.md: 15-minute Wave Rider (PF 0.89 / 1.00 with the market gate) and long-only ORB (PF 0.93); both to shadow as observation only.
- 2026-09-23-kakushadze-151-feasibility.md: the 151-strategy catalogue against our Alpaca provisions; the open-to-close alphas (feature 19) have no ranking power in Jun-Sep 2026 and all 37 backtest combinations lose; shadow only; short selling is the unlock.
- 2026-09-23-traderpro-extraction.md: inventory of the owner's TraderPro platform; its 2019-26 results replicated on adjusted data with benchmarks (momentum adds 6-12 points over an equal-weight mega-cap universe, mean reversion adds nothing); ETF/index rules do not beat SPY; point-in-time universe test.
- 2026-09-24-news-daily-jev.md: 357k headline-symbol pairs 2019-2026 scored with Jev ($23); four pre-registered tests (volatility, sentiment, momentum filter, news-ranked universe) all fail in the top-100 universe; negative news reverses slightly; no news feature adopted.
- 2026-09-24-options-backtest.md: first options backtest on rebuilt chains (Feb 2024 to Sep 2026, SPY/QQQ/IWM, 144 configurations); the vrp-gated 5%-out bull put spread matches or beats the index's Sharpe with a third of its drawdown on all three; iron condors lose; about 20 trades each, so a candidate, not a proof.
