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
