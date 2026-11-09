# Statistical arbitrage, stage 1: do stocks' own moves reverse over 1 to 5 days? (2017-2026)

**Run 2 November 2026.** The owner's go-ahead for the staged stat-arb plan
(docs/roadmap-advanced-strategies.md, item 3). Code: `src/ridethewave/daily/residuals.py`,
`scripts/research_statarb_stage1.py`. Results: `data/research/statarb/`.

## 1. Why a diagnostic before an engine

Ken French's century of data (docs/research/2026-11-02-momentum-and-reversal-century.md) shows the
textbook base of stat arb is gone: since 2000, buying last month's losers and shorting its winners
earned a Sharpe of 0.12 (large caps 0.02). The version the literature says still works is shorter and
cleaner: take out each stock's market and sector moves, and bet that what is left (the *residual*)
partly reverses over a few days. Building that as a strategy (s-scores, neutral books, borrow) is
weeks of work. This stage measures, in days, whether there is anything for it to trade.

## 2. What was fixed before running

**Universe.** Each month, the 300 company stocks (no funds) with the highest trailing 20-day dollar
volume and a price of at least $5. Ranked from prior data only, from the survivorship-free panel:
every US stock Alpaca has listed, delisted ones included. 3 January 2017 to 22 September 2026.

**Residuals** (`residuals.py`):

    r_i = a + b_m * r_SPY + b_s * (r_sector - r_SPY) + e_i

- **Sector:** the sector ETF (XLK, XLF, XLV, XLY, XLP, XLE, XLI, XLB, XLRE, XLU, XLC) whose moves beyond
  SPY correlated best with the stock's over the previous 252 sessions, re-chosen monthly.
- **Betas:** from the 60 sessions ending the day before.

**Signal.** The sum of a stock's residuals over the last *k* sessions, up to today's close, for
*k* = 1, 3, 5.

**Outcome.** The residual of the next *h* sessions, from tomorrow's **open** to the close *h*
sessions later, for *h* = 1, 3, 5. It uses the same betas, applied to SPY's and the sector ETF's
open-to-close moves.
- Starting at the next open removes the bid-ask bounce that made Ken French's daily files look
  spectacular.
- It also matches when our daily slots could actually trade.

**Measures, for each of the 9 (k, h) cells:**
- **Rank correlation (IC):** each day, the rank correlation between minus the signal and the outcome
  across the universe, then averaged over days.
- **Quintile spread:** the average outcome of the fifth with the most negative signal (bought)
  minus the fifth with the most positive (sold). That is the return of $1 long and $1 short, both
  hedged.
- **t-statistics:** from the daily series, with Newey-West correction for the h−1 days of overlap.
- **Halves:** 2017-2021 and 2022-2026-09.
- **Volatility regimes:** days with VIX ≥ 20 and days below.
- **Break-even cost:** spread ÷ 4. A round trip buys and sells both legs, so it is $4 traded per $1
  long and $1 short. This is the most a trade can cost one-way before the edge is gone.
- **Control, not counted:** the same on raw returns minus the universe average, to show whether
  removing market and sector matters.

**Kill test, set in advance and given to the owner.** Stat arb at a daily horizon stops here unless
at least one cell shows **both**:
- a quintile spread with t ≥ 2 in **both** halves;
- a break-even cost of at least **5 basis points** one-way.

There are 9 cells, so one cell clearing t 2 overall is weak evidence by itself. Requiring both
halves keeps the chance of a false pass small.

A cell that passes only on VIX ≥ 20 days is reported as a lead. Such a strategy would sit out most
of the time, and its evidence would need its own test.

## 3. Results

- **Universe:** 1,020 different stocks were in the monthly top 300 at some point, 296 on an average
  day, over 2,438 test days.
- **Sector assignment on the last day:** XLK 188, XLF 140, XLP 112, XLV 99, XLY 81, XLI 81, XLB 80,
  XLC 75, XLE 68, XLRE 52, XLU 44.

**All days.** Spread in basis points per round trip of h days, t-statistics in brackets.

| Signal k / hold h | Spread | 2017-2021 | 2022-2026 | Rank IC | Break-even | Unhedged control |
|---|---|---|---|---|---|---|
| k1 h1 | +0.6 (0.3) | +5.3 (2.1) | −4.4 (−1.7) | +0.005 | 0.2 bp | +5.2 (1.9) |
| k3 h1 | −0.5 (−0.3) | +2.8 (1.1) | −4.0 (−1.5) | +0.000 | −0.1 bp | +2.5 (0.9) |
| k5 h1 | +1.8 (1.0) | +3.2 (1.2) | +0.4 (0.2) | +0.002 | 0.5 bp | +3.4 (1.2) |
| k1 h3 | +2.9 (0.9) | +7.6 (1.6) | −2.0 (−0.4) | +0.006 | 0.7 bp | +11.7 (2.3) |
| k3 h3 | +6.7 (1.5) | +6.4 (1.0) | +6.9 (1.1) | +0.008 | 1.7 bp | +17.4 (2.6) |
| k5 h3 | +9.8 (2.0) | +6.8 (1.0) | +13.1 (2.0) | +0.010 | 2.5 bp | +16.6 (2.3) |
| k1 h5 | +10.1 (2.1) | +10.5 (1.5) | +9.6 (1.5) | +0.008 | 2.5 bp | +22.4 (3.3) |
| k3 h5 | +15.3 (2.2) | +13.5 (1.3) | +17.3 (1.9) | +0.010 | 3.8 bp | +26.6 (2.6) |
| **k5 h5** | **+17.3 (2.2)** | +15.7 (1.3) | +19.0 (1.9) | +0.011 | **4.3 bp** | +21.1 (1.9) |

**Kill test: FAIL.**
- No cell reaches t 2 in both halves.
- The best break-even is 4.3 bp, below the 5 bp we pay.

**Split by market volatility** (779 days with VIX ≥ 20, about a third):

| Cell | VIX ≥ 20 | Of which 2017-2021 (384 days) | Of which 2022-2026 (395 days) | Break-even on VIX ≥ 20 days | VIX < 20 |
|---|---|---|---|---|---|
| k3 h5 | +35.3 (2.0) | +43.9 (1.4) | +26.9 (1.6) | 8.8 bp | +5.9 (1.0) |
| k5 h3 | +28.0 (2.3) | +32.6 (1.6) | +23.6 (1.8) | 7.0 bp | +1.3 (0.3) |
| **k5 h5** | **+50.9 (2.6)** | +58.0 (1.7) | **+44.0 (2.4)** | **12.7 bp** | +1.5 (0.2) |

Average spread by year, k5 h5:

| 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 to Sep |
|---|---|---|---|---|---|---|---|---|---|
| −8.6 bp | +28.6 | −4.2 | +80.3 | −18.0 | +15.6 | +27.3 | +12.1 | +34.8 | −0.5 |

## 4. Reading

1. **Always-on daily stat arb fails.**
   - Residual reversal exists in the expected direction and grows with the holding period. Over 5
     days it is about 17 bp per round trip.
   - That is too little and too weak to trade at our costs. The kill test does what it was set up
     to do, and no engine is built for the always-on version.
2. **In volatile markets the effect is real-looking and about three times larger.**
   - With VIX at 20 or above, buying the fifth of stocks that fell most against their market and
     sector over the last week, and shorting the fifth that rose most, earned 51 bp per 5-day round
     trip (t 2.6).
   - It is positive in both halves (t 1.7 and 2.4), and it could absorb about 13 bp a trade.
   - On calm days it is zero. This fits Nagel (2012): short-term reversal is pay for supplying
     liquidity, and that pay rises when markets are stressed and liquidity providers pull back.
3. **Why it is a lead, not a pass.**
   - It is the best of 18 looks (9 cells × 2 regimes), and it was not in the kill test.
   - The volatile days cluster: 218 of the 779 are in 2020 (+98 bp on average there) and 228 in 2022
     (+25 bp). Without 2020 the volatile-day spread is +32.5 bp over 561 days, still positive but a
     third smaller. By year: 2018 +52, 2019 −16, 2020 +98, 2021 −21, 2022 +25, 2023 +42, 2024 −5,
     2025 +148 (63 days, the tariff sell-off), 2026 +19.
   - A strategy built on it would be idle two-thirds of the time.
   - The neighbouring cells all point the same way, which argues against a single lucky cell.
4. **The unhedged control is not stat arb.** Raw reversal often shows larger spreads (+22 bp, t 3.3,
   for k1 h5), but it is not market-neutral. The stocks that fell most in a sell-off are the ones
   that move most with the market, so that spread is partly a bet on the market bouncing back.

## 5. Verdict and next step

- **Always-on daily stat arb is stopped,** per the kill test fixed in advance.
- **A volatility-gated residual reversal goes to its own pre-registered strategy test.**
  - **The rule:** the exact k5 h5 setup.
  - **Trading:** only when VIX ≥ 20 at the close. Dollar-neutral quintiles, held 5 sessions, 5 bp
    costs plus a borrow charge on the shorts.
  - **To pass:** it must be profitable after costs in both halves.
  - **If it passes:** it becomes a shadow slot that sits in cash while VIX is below 20, so live
    observation becomes the out-of-sample test.
  - **Honest expectation:** a sleeve that trades about a third of the year and earns its keep in
    stressed markets.
