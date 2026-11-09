# Momentum and short-term reversal over a century (Ken French data, 1927-2026)

**Run 2 November 2026.** Owner's request: start with the Ken French data, and plan statistical
arbitrage. Code: `scripts/research_ken_french.py`. Data: `scripts/download_external.py`
(`ff_factors`, `ff_momentum`, `ff_st_reversal`, `ff_mom_deciles`, `ff_rev_deciles`). Results:
`data/research/ken_french/`.

## 1. Two questions

1. **Momentum.** `pm_actives` (long-only, top 30% by 12-1 month return) is our only stock-ranking
   lead, with an information ratio of 0.51 (t 1.6) over 2017-26. That is not enough evidence. Over a
   century, do recent winners beat the market? Does scaling momentum by its own volatility remove
   its famous crashes (1932, 2009)? See Barroso and Santa-Clara 2015, "Momentum has its moments".
2. **Short-term reversal, the engine of statistical arbitrage.** Stat arb mostly bets that a stock's
   recent move away from its peers will partly reverse. Ken French's short-term reversal factor buys
   last month's losers and shorts last month's winners. It is the longest public record of that bet.
   How much of it is left, and how much can a trade cost before it is gone?

## 2. What was fixed before running

Six return series, every one counted against the result. Nothing else was run.

| Id | Series | Built from |
|---|---|---|
| M1 | Momentum, long-short (UMD) | Ken French's momentum factor: winners minus losers on 12-2 month returns, rebalanced monthly |
| M2 | Long-only winners against the market | Average of the top three momentum deciles (value-weighted), minus the market: the active return of a "top 30%" book like `pm_actives` |
| M3 | M1 scaled by its own volatility | Exposure = 12% / realised volatility of the last 126 sessions, at most 2×, set the day before |
| M4 | M2 scaled by its own volatility | Exposure = 6% / realised volatility of the active return over 126 sessions, at most 2×, set the day before |
| R1 | Short-term reversal, long-short | Ken French's ST_Rev: last month's losers minus winners (small and big stocks equally) |
| R2 | Large-cap reversal | Value-weighted bottom decile minus top decile on last month's return, so big stocks dominate |

**Statistics.**
- Long-short and active series are excess returns. Their Sharpe ratio is mean ÷ standard deviation,
  annualised.
- Periods: the full sample, the two halves (1927-1976 and 1977-2026), 2000-2026 (the era of cheap
  trading and crowded quant funds), and each decade.
- Episodes: momentum's crashes in summer 1932, spring 1933, March to May 2009 and November 2020.

**Trading costs.** Ken French's returns are before costs. For each series, the **break-even cost**
is the one-way cost per dollar traded that would wipe out its average return, assuming both legs are
fully replaced every month. That is $4 traded per $1 long and $1 short. For reversal this is close to
the truth, because a one-month sort reshuffles almost completely. For momentum it is a floor: its
holdings change more slowly, so its real break-even is higher.

What passes:
- **For momentum to count as an alpha:** M2 or M4 needs an information ratio of at least 0.3,
  positive in both halves and in 2000-2026, with t of at least 2.
- **For reversal to be worth building a stat-arb engine on:** R2's break-even cost over 2000-2026
  must be well above what we pay. That is about 5 basis points one-way in liquid large caps, plus
  borrow on the short side.

**One change after the first run.** The first run used Ken French's *daily* reversal files. Their
preamble says they re-sort **every day** on days −20 to −1, so yesterday's close is part of the sort.
A closing price that happened to print at the bid looks like a loser and then "recovers" to the
mid the next day. That is the bid-ask bounce, which nobody can trade. They showed Sharpe ratios of
3.8 and 3.1 and returns of 56% and 90% a year: impossible as a tradable premium. R1 and R2 were
re-run on the **monthly** files, which re-sort once a month on last month's return, the classic
construction. The daily numbers are kept in the results file, labelled not valid. The momentum
files also re-sort daily, but their sort skips the most recent month (days −250 to −21), so they
have no bounce.

## 3. Results

Sharpe ratios of excess returns (no cash subtracted); t-statistics in brackets. "Break-even" is the
one-way cost per dollar traded that would wipe out the average return if both legs turned over fully
every month. It is close to the truth for reversal and a floor for momentum.

| Series | 1927-2026 | 1927-1976 | 1977-2026 | **2000-2026** | 2010-2026 | Max drawdown | Break-even 2000-26 |
|---|---|---|---|---|---|---|---|
| M1 momentum long-short | 0.51 (5.2) | 0.50 | 0.52 | 0.21 (1.1) | 0.28 | −72% (1932 to 1942) | 7.5 bp |
| M2 long-only winners minus market | 0.55 (5.6) | 0.63 | 0.46 | 0.24 (1.2) | 0.17 | −26% | 3.8 bp |
| **M3 momentum, volatility-scaled** | **0.99 (10.1)** | 0.93 | 1.05 | **0.55 (2.8)** | 0.54 (2.2) | −45% | 14.5 bp |
| **M4 winners minus market, volatility-scaled** | **0.83 (8.5)** | 0.92 | 0.74 | **0.38 (2.0)** | 0.24 (1.0) | −22% | 5.1 bp |
| R1 short-term reversal (monthly) | 0.64 (6.4) | **0.98** | 0.27 | **0.12 (0.6)** | **0.01** | −40% (2020 to 2026) | **3.4 bp** |
| R2 large-cap reversal (monthly) | 0.45 (4.5) | 0.84 | 0.07 | **0.02 (0.1)** | −0.02 | −82% (1989 to 2026) | **1.1 bp** |
| *Not valid: the same two on the daily re-sort* | *3.77, 3.05* | | | | | | |

For context, the market itself had a Sharpe of 0.63 (1927-2026) and 0.52 (2000-2026). The top 30%
of winners, held outright, had 0.75 and 0.58.

**Sharpe ratio by decade.**

| | 1930s | 1940s | 1950s | 1960s | 1970s | 1980s | 1990s | 2000s | 2010s | 2020s |
|---|---|---|---|---|---|---|---|---|---|---|
| M3 momentum, volatility-scaled | −0.03 | 0.37 | 1.43 | 1.77 | 1.37 | 1.28 | 1.98 | 0.57 | 0.57 | 0.49 |
| M4 winners minus market, scaled | 0.26 | 0.88 | 1.04 | 1.48 | 1.38 | 0.69 | 1.06 | 0.60 | 0.26 | 0.22 |
| R1 short-term reversal | 1.17 | 1.59 | 1.49 | 1.14 | 1.35 | 0.69 | 0.16 | 0.25 | 0.42 | −0.39 |
| R2 large-cap reversal | 1.40 | 0.78 | 1.23 | 0.64 | 0.74 | 0.53 | −0.27 | 0.08 | 0.28 | −0.23 |

**Momentum's crashes, and what volatility scaling did.**

| Episode | M1 plain | M3 scaled | M2 long-only active | M4 scaled |
|---|---|---|---|---|
| Summer 1932 rebound | −51% | −26% | −18% | −11% |
| Spring 1933 rebound | −4% | −2% | +5% | +3% |
| March to May 2009 rebound | −50% | −18% | −15% | −8% |
| November 2020 rotation (one week) | −13% | −4% | −3% | −2% |

## 4. Reading

1. **Short-term reversal, the base of stat arb, has been traded away.**
   - The monthly version was strong until the 1980s, with Sharpe 1.1 to 1.6 a decade.
   - It fell below 0.3 from the 1990s, and is about zero since 2010.
   - Its large-cap form has earned nothing since 1977.
   - Since 2000 it can absorb about 3 basis points per trade (large caps 1). We pay about 5, plus
     borrow on the shorts.
   - This matches the literature: reversal profits are mostly pay for supplying liquidity (Nagel
     2012). That business went to electronic market makers once spreads collapsed after 2001.
   - Monthly-horizon stat arb on raw returns is closed to us.
2. **Momentum survives, and volatility scaling is the single best thing found so far.**
   - Scaling momentum by its own recent volatility roughly doubled its Sharpe over a century (0.51
     to 0.99). It halved its worst crashes (2009: −50% to −18%) and still had a Sharpe of 0.55
     (t 2.8) since 2000.
   - The long-only version, closest to what `pm_actives` does, passes the pre-set test: information
     ratio 0.83 (t 8.5), positive in both halves, 0.38 (t 2.0) since 2000. The unscaled long-only
     version fails since 2000 (0.24).
   - Both are fading. M4 was 0.26 in the 2010s and 0.22 in the 2020s. Its break-even cost since
     2000 (5 bp at full monthly turnover, more in practice since momentum turns over more slowly) is
     close to what we pay.
3. **What stays unproven.** These are Ken French's portfolios across all US stocks, value-weighted,
   before costs, rebalanced every day. Our book holds about 40 of the most-traded names. Our own
   2017-2026 result after 5 bp costs (information ratio 0.51, t 1.6) is consistent with the
   post-2000 rows here, which is encouraging, but it is not proof.

## 5. Verdict

- **Momentum, scaled by its volatility, is the leading candidate for an actual edge.** It goes next
  to a pre-registered test on our own data: `pm_actives` with the M4 overlay. The book holds the
  winners, sized by the active return's own recent volatility, with SPY as the hedge.
- **Stat arb in its textbook form (monthly reversal on raw returns) is not worth building.** What is
  left to test is the version the literature says still works: reversal of each stock's *residual*,
  its move after removing the market's and its sector's, over 1 to 5 days. It has to be tested on
  our own point-in-time data with next-open fills, because Ken French's daily files cannot separate
  that effect from the bounce. Plan: docs/roadmap-advanced-strategies.md.
