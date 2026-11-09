# Momentum with a volatility-scaled overlay, on our own data (2017-2026)

**Run 2 November 2026.** Follows docs/research/2026-11-02-momentum-and-reversal-century.md. Over
1927-2026, long-only winners scaled by the volatility of their return beyond the market (series M4)
beat the market with an information ratio of 0.83, and 0.38 since 2000. This page asks whether the
same overlay on `pm_actives`' rule holds up on the stocks we actually trade. Code:
`scripts/research_momentum_overlay.py`. Results: `data/research/momentum_overlay/`.

## 1. What was fixed before running

**The book.** `pm_actives`' rule exactly:
- 12-1 month price momentum (231-session formation, 21 skipped);
- the top 30% of the universe, equal-weighted, rebalanced daily on the close, filled at the next
  open, 5 bp per trade.

The universe is September's survivorship-free test: each month the 100 company stocks with the
highest trailing dollar volume, price at least $5. 3 January 2017 to 22 September 2026, $100,000.

**The overlay.** The book's daily return beyond SPY, *a* = r_book − r_SPY, is the bet on momentum.
- Each day the bet is sized by L = 10% ÷ (its realised volatility over the previous 126 sessions,
  annualised), at most 2, set the day before.
- Holding: L in the momentum book, and 1 − L in SPY. When L is above 1, that means shorting SPY.
- Return: r_SPY + L × a, minus 5 bp on the extra trading. Moving L by ΔL trades ΔL of the book and
  ΔL of SPY, so 2 × |ΔL| × 5 bp.

The 10% target sets the size of the bet, not its quality. The information ratio is nearly unchanged
by it.

**Two configurations:** the plain book, and the overlay. Nothing else is run.

**Measures:**
- Information ratio against SPY (annualised mean of *a* ÷ its volatility), with its t-statistic.
- Both halves: 2017-2021 and 2022-2026.
- CAGR, Sharpe, max drawdown, and the worst drawdown of the active return.
- The episodes: the Covid crash, the November 2020 vaccine rotation (a classic momentum crash),
  2022, and the April 2025 tariff drop.

**What passes:** the overlay's information ratio is at least 0.3, positive in both halves, **and**
its active drawdown is smaller than the plain book's.

**Note on power.** Ten years cannot prove an information ratio near the century's: at 0.4, the
t-statistic would be about 1.2. This test checks that our data agrees with the century, not that it
proves it.

## 2. Results

The overlay needs 126 sessions of history, so both books are compared from 6 July 2017 to 22
September 2026.

| | CAGR | Sharpe | Max drawdown | IR vs SPY (t) | 2017-2021 / 2022-2026 | Worst stretch vs SPY | Tracking error |
|---|---|---|---|---|---|---|---|
| Plain book (`pm_actives`' rule) | +23.9% | 0.82 | −36.6% | 0.48 (1.4) | 0.34 / 0.58 | −37.6% | 23.1% |
| **With the overlay** | +19.4% | 0.87 | −34.1% | 0.43 (1.3) | 0.39 / 0.46 | **−19.6%** | 10.9% |
| SPY | +15.2% | 0.86 | −33.8% | | | | |

The overlay's exposure to the momentum bet averaged 0.70, between 0.19 and 1.37. It shorted SPY only
when the exposure was above 1.

| Episode | Plain book | Overlay | SPY |
|---|---|---|---|
| Covid crash (19 Feb to 23 Mar 2020) | −31.8% | −32.7% | −33.5% |
| Vaccine rotation (6 to 13 Nov 2020) | −4.6% | −0.6% | +2.3% |
| 2022 bear market (to 12 Oct) | −26.5% | −23.9% | −24.1% |
| Tariff drop (19 Feb to 8 Apr 2025) | −30.8% | −24.3% | −18.6% |

| Year | 2017 (from Jul) | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 to Sep |
|---|---|---|---|---|---|---|---|---|---|---|
| Plain book | +10.9% | −1.7% | +30.5% | +59.0% | +12.2% | −20.0% | +23.7% | +35.9% | +20.3% | +74.5% |
| Overlay | +10.7% | −2.4% | +30.1% | +40.7% | +22.5% | −17.4% | +22.8% | +31.9% | +21.0% | +29.7% |
| SPY | +11.1% | −5.0% | +31.1% | +18.5% | +28.6% | −18.2% | +26.2% | +24.9% | +17.7% | +14.3% |

## 3. Reading and verdict

**It passes the test fixed in advance:**
- information ratio 0.43, at least 0.3;
- positive in both halves;
- the worst stretch against SPY halved, −19.6% against −37.6%.

**What the overlay does on our data is control risk, not add return.**
- The information ratio is about the same (0.43 against 0.48). The century's doubling did not
  repeat over these nine years.
- What changed is the shape:
  - the worst run of losses against SPY halved;
  - the two halves became even (0.39 / 0.46 instead of 0.34 / 0.58);
  - the momentum crash of November 2020 shrank from −4.6% to −0.6%;
  - the total Sharpe rose slightly, 0.82 to 0.87.
- The price is upside. When momentum ran hot in 2020 and 2026, its volatility rose and the overlay
  cut the bet: 2026 +29.7% instead of +74.5%.

**Neither version proves an edge over nine years** (t 1.3 to 1.4). The century study is where the
evidence lives. This test shows our data agrees with it and that the overlay behaves as designed.

**Next:** a shadow slot running the overlay beside `pm_actives`, so both are observed on the same days.

## 4. Correction, 9 November 2026

The price panel lacked delisted stocks. Repaired and re-run unchanged: information ratio 0.44 for the plain book and 0.39 for the overlay (0.48 and 0.43 above), halves 0.33 / 0.44, worst stretch against SPY −21.6% against −39.9% plain. It still passes. docs/research/2026-11-09-panel-survivorship-gap.md, section 5.
