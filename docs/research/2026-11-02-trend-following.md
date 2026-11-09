# Trend following across asset classes: 2017-2026 on ETFs, and a century on outside data

**Run 2 November 2026.** Question 1 of the strategy re-think (owner, 29 October and 2 November 2026).
Code: `trend_weights` and `TimeSeriesMomentum` in `src/ridethewave/daily/strategies.py`,
`scripts/research_trend.py`. Data: `scripts/download_daily.py --universe trend_etfs_21` (Alpaca) and
`scripts/download_external.py` (Ken French, Cboe, FRED). Results: `data/research/trend/`.

## 1. Why this test

The re-think proposed building a portfolio of three to five independent "sleeves" instead of hunting
for one intraday edge. One sleeve sells insurance: the bull put spreads, which earn a little most
months and lose in crashes. Trend following is the classic partner for it. It has no reason to
earn much in calm years, but it tends to be **short stocks and long bonds by the time a long sell-off
is under way**, so it often makes money in exactly the months when the put spread loses. The
literature (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017, "A Century of Evidence on
Trend-Following Investing") reports this across 1880 to 2016 on futures.

So this page asks two questions. Does trend following earn anything on its own? Does it behave like
insurance when stocks fall? Section 6 then asks the question that matters: does it make the put-spread
sleeve safer?

September's long-only `multi_asset_trend` (TraderPro's port) was judged against SPY and lost to it
(docs/research/2026-09-23-traderpro-extraction.md, section 4). That was the wrong benchmark. A
long-only rule also cannot do the insurance job, because it can only go to cash, never short.

## 2. What was fixed before running

The rule, the markets and the variants below were written into the script before the first run, and
none was changed afterwards. Pass/fail thresholds were *not* set in advance, so the verdict in
section 7 is a judgment on the numbers, stated as such.

**The rule (base configuration).**
1. **Signal.** For each market, the average of the signs of its 1-, 3- and 12-month returns (21, 63
   and 252 sessions). That gives −1, −⅓, +⅓ or +1: fully long when all three are rising, fully short
   when all three are falling.
2. **Risk budget.** Four asset classes (stocks, bonds, commodities, currencies), each an equal share
   of risk, so six bond funds do not outvote three currency funds. Inside a class, equal shares.
3. **Size.** Signal × budget ÷ the market's own volatility (exponentially weighted, centre of mass 60
   sessions). A quiet bond fund and a wild natural-gas fund then carry the same risk.
4. **Whole book.** Scaled to **10% volatility a year** using the last 126 sessions' covariance, so
   markets that move together get less. Each position is capped at 50% of equity, and the gross
   exposure at 2× (the paper account's overnight margin limit).
5. **Trading.** Rebalanced every 5 sessions on the close, filled at the next open, 5 basis points of
   slippage per trade.

**Markets (`trend_etfs_21`).**
- Stocks: SPY, IWM, EFA, EEM, EWJ, VNQ.
- Bonds: IEF, TLT, TIP, LQD, HYG, EMB.
- Commodities: GLD, SLV, DBC, USO, DBA, UNG.
- Currencies: UUP, FXE, FXY.

SHY is left out: at 1 to 2% volatility it is cash, and scaling it to the others' risk would need many
times leverage.

**Variants, and the number of configurations.** Every configuration tried counts against the result
(deflated Sharpe): **five on the ETFs** (the base, long-only, 12-month signal only, no class
budgets, September's `multi_asset_trend`) and **three on the long history**. Nothing else was run.

**Cash interest.** The daily engine pays no interest on cash. A futures account earns T-bill
interest on its collateral, and that is how published trend records are measured. A retail stock
account mostly does not. Both views are shown below: "engine" is roughly what the paper account
would book, "with interest" adds T-bill interest on the net cash balance (1 − net exposure). T-bills
averaged 2.55% a year over 2017-2026.

## 3. Data

- **ETFs.** Alpaca adjusted daily bars, January 2016 to 30 October 2026. The first year is warm-up,
  so the test runs 3 January 2017 to 30 October 2026, 9.8 years.
- **A century of US stocks.** Ken French's daily market return (CRSP value-weighted, dividends
  included), July 1926 to September 2026.
- **10-year Treasury, 1962 on.** Rebuilt from FRED's daily 10-year yield as a par bond: one day of
  coupon, minus duration times the yield change, plus convexity. It ignores roll-down, so it is an
  approximation. Over 2017-2026 it returned 0.4% a year, a period in which yields rose from 2.4% to
  about 4%.
- **Cash.** FRED's 3-month T-bill (ETF part); Ken French's risk-free rate (long history).

## 4. Results on the ETFs, 2017-2026

| Configuration | CAGR, engine | CAGR, with interest | Sharpe over cash, with interest (2017-21 / 2022-26) | Volatility | Max drawdown, with interest | Correlation with SPY, monthly | In SPY's worst 10% of months |
|---|---|---|---|---|---|---|---|
| **Base (pre-registered)** | +1.1% | +2.2% | **0.00** (0.15 / −0.14) | 8.6% | −20.0% (Oct 2022 to Nov 2023) | **−0.16** | **+1.7%** |
| Long-only | +5.2% | +3.5% | 0.15 (0.53 / −0.23) | 8.9% | −19.9% | 0.51 | −1.6% |
| 12-month signal only | +3.4% | +4.2% | 0.26 (0.10 / 0.40) | 7.4% | −14.1% | −0.01 | +0.8% |
| No class budgets | +1.2% | +2.1% | −0.01 (0.25 / −0.23) | 8.8% | −22.4% | −0.16 | +1.8% |
| September's `multi_asset_trend` | +3.7% | +3.8% | 0.20 (0.65 / −0.19) | 7.1% | −14.1% | 0.54 | −1.4% |
| SPY, buy and hold | +14.9% | | 0.73 (0.94 / 0.49) | 17.8% | −33.8% | 1 | −7.5% |

In SPY's worst 10% of months, SPY itself averaged −7.5% a month.

**Year by year (engine basis).**

| Year | Base | Long-only | 12-month only | SPY |
|---|---|---|---|---|
| 2017 | +0.7% | +12.2% | +6.9% | +20.9% |
| 2018 | −4.6% | −4.1% | −9.6% | −5.0% |
| 2019 | +3.6% | +16.7% | +8.2% | +31.1% |
| 2020 | +5.6% | +3.6% | −0.9% | +18.5% |
| 2021 | +2.5% | +5.2% | +0.8% | +28.6% |
| 2022 | **+15.7%** | +0.0% | +18.4% | −18.2% |
| 2023 | **−11.7%** | −4.0% | −6.3% | +26.2% |
| 2024 | +4.1% | +10.8% | +10.3% | +24.9% |
| 2025 | +0.8% | +12.3% | +6.1% | +17.7% |
| 2026 to 30 Oct | −3.1% | +0.8% | +2.1% | +11.7% |

**In the sell-offs (engine basis).**

| Episode | Base | Long-only | 12-month only | SPY |
|---|---|---|---|---|
| Q4 2018 (20 Sep to 24 Dec) | +3.5% | −2.5% | −1.9% | −18.7% |
| Covid (19 Feb to 23 Mar 2020) | +5.1% | −7.5% | −0.0% | −33.5% |
| 2022 (3 Jan to 12 Oct) | **+26.1%** | +3.8% | +28.3% | −24.1% |
| Tariffs (19 Feb to 8 Apr 2025) | −4.8% | −6.0% | −7.1% | −18.6% |

Each asset class added something to the base book (average contribution a year, before costs):
stocks +1.2%, commodities +0.8%, currencies +0.7%, bonds +0.4%.

## 5. Results over a century (outside data)

Same `trend_weights` function, rebalanced every 5 sessions, 5 basis points of cost per unit of
turnover, collateral earning cash. The series have no opening prices, so weights apply from the next
close, not the next open. One known limit: with only one or two markets, the 50% position cap stops
the book from reaching its 10% volatility target. Sharpe ratios are unaffected; returns and drawdowns
are smaller than a full-risk book would show.

| Configuration | Years | CAGR | Volatility | Sharpe over cash | Max drawdown | Correlation with stocks, monthly | In stocks' worst 10% of months |
|---|---|---|---|---|---|---|---|
| Trend on US stocks only, 1927-2026 | 99 | +5.6% | 7.3% | 0.37 | −26.5% (1937 to 1941) | 0.05 | **+1.5%** (stocks −8.9%) |
| US stocks, buy and hold, 1927-2026 | 99 | +9.8% | 17.2% | 0.45 | −84.1% (1929 to 1932) | 1 | −8.9% |
| **Trend on stocks + 10-year Treasury, 1963-2026** | 64 | +6.8% | 6.7% | **0.37** | **−14.5%** (Jun 2022 to May 2023) | 0.21 | **+1.0%** (stocks −7.6%) |
| The same, long-only | 64 | +7.3% | 5.5% | 0.54 | −12.9% | 0.62 | −0.8% |
| 60/40 stocks / 10-year Treasury | 64 | +9.2% | 10.0% | 0.50 | −31.9% (1973 to 1974) | 0.95 | −4.4% |
| US stocks, buy and hold, 1963-2026 | 64 | +11.0% | 16.1% | 0.46 | −54.6% (2007 to 2009) | 1 | −7.6% |

**In the great sell-offs.**

| Episode | Trend, stocks only | Trend, stocks + bonds | Long-only version | 60/40 | US stocks |
|---|---|---|---|---|---|
| 1929-32 crash | **+63%** | | | | −84% |
| 1937-38 | −0% | | | | −50% |
| 1973-74 | **+45%** | **+36%** | +4% | −32% | −48% |
| 1987 crash | +9% | +0% | −4% | −20% | −33% |
| 2000-02 | −2% | +2% | −2% | −22% | −49% |
| 2008-09 | +13% | +12% | +2% | −30% | −54% |
| Q4 2018 | +6% | +1% | −3% | −11% | −20% |
| Covid 2020 | +5% | +1% | −2% | −19% | −34% |
| 2022 | −5% | +6% | −8% | −21% | −25% |
| Tariffs 2025 | +8% | +3% | −0% | −11% | −19% |

**Sharpe ratio by decade, trend on US stocks only:**

| 1920s | 1930s | 1940s | 1950s | 1960s | 1970s | 1980s | 1990s | 2000s | 2010s | 2020s |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.73 | 0.51 | 0.58 | 1.09 | 0.56 | 0.34 | 0.41 | **0.07** | **0.01** | **−0.13** | 0.52 |

## 6. Combined with the put-spread sleeve

`scripts/research_sleeves.py`, results in `data/research/sleeves/results.json`.

**The sleeves, all daily, 3 January 1990 to 30 September 2026 (9,249 sessions):**
- **Put spread.** The `bps_spy` rule priced from S&P 500 and VIX history (the companion study,
  docs/research/2026-11-02-put-spread-long-history.md, which on its own **rejects** it: Sharpe 0.25,
  −52% drawdown).
- **Trend.** The rule above on US stocks and the 10-year Treasury. The 21-ETF book only exists from
  2017.
- **Stocks.** The US market held at constant volatility, a stand-in for the equity and momentum
  sleeves.

**How each portfolio is built.** The sleeves get equal risk (weights 1 / trailing one-year
volatility), and the whole portfolio is scaled to 10% volatility from the last 63 sessions, at most
2×. Only past data is used. Six portfolios were fixed before the run; "trend + stocks" was added
after it, once the put spread had failed, and is labelled as such.

| Portfolio | CAGR | Sharpe over cash | Max drawdown | Worst month | Volatility target that would have kept the drawdown inside −15% |
|---|---|---|---|---|---|
| Put spread alone | +8.0% | 0.52 | −37.7% (2000 to 2002) | −15.1% (Sep 2001) | 3.5% |
| Trend alone | +6.2% | 0.39 | −17.3% (2022 to 2023) | −7.2% | 8.7% |
| Stocks alone, constant volatility | +9.1% | **0.63** | −25.8% (2000 to 2002) | −9.5% | 6.4% |
| Put spread + trend | +7.3% | 0.53 | −33.6% | −10.4% | 5.1% |
| Put spread + stocks | +9.1% | 0.62 | −35.8% | −11.3% | 4.8% |
| Put spread + trend + stocks | +8.7% | 0.62 | −38.7% | −9.2% | 4.0% |
| Trend + stocks (added after the run) | +8.9% | 0.63 | −28.8% | −7.9% | 5.9% |

Monthly correlations: put spread with stocks **0.53**, put spread with trend −0.09, trend with
stocks 0.16. In the put spread's 20 worst months (average −12.0%), trend averaged **+1.1%** and was
up in 12 of them.

**In the sell-offs, at the 10% target:**

| Episode | Put spread | Trend | Stocks | Put spread + trend | All three |
|---|---|---|---|---|---|
| 1998 LTCM | −14% | +2% | −13% | −7% | −10% |
| 2000-02 | −37% | +5% | −25% | −30% | −37% |
| 2008-09 | −30% | +9% | −21% | −14% | −22% |
| Aug 2011 | −16% | +4% | −11% | −12% | −12% |
| Feb 2018 | −14% | −5% | −10% | −11% | −12% |
| Covid 2020 | −15% | −1% | −17% | −9% | −13% |
| 2022 | −4% | +9% | −13% | +4% | −7% |
| Tariffs 2025 | −5% | +5% | −12% | +0% | −5% |

**Reading.**

1. **The put spread is mostly a leveraged bet that stocks stay calm.** Its correlation with stocks is
   0.53. Adding it to constant-volatility stocks leaves the Sharpe unchanged (0.62 against 0.63) and
   deepens the drawdown. It earns its keep only if it is the *only* way to hold equity risk, and it
   is not.
2. **Trend helps the put spread, but not enough.** It halved the 2008-09 loss and turned 2022 and
   2025 positive. It did nothing in 2000-02, where the put spread lost slowly for two and a half
   years: −30% together against −37% alone. The pair still had a −34% drawdown at 10% volatility.
3. **A word of caution on the "put spread alone" line.** At a constant 10% volatility it shows a
   Sharpe of 0.52, against 0.25 for the slot as specified. Most of that improvement comes from
   shrinking the book after volatility jumps. For an options book this assumes spreads can be bought
   back at no cost in the middle of a crash, when option spreads are at their widest. Treat it as an
   upper bound.
4. **Answer to the risk question.**
   - At a 10% volatility target, every portfolio with stocks or the put spread in it had a drawdown
     of 26% to 39% in 2000-02.
   - To have stayed inside a 15% drawdown, these books needed a target of about **4% to 6.5%**
     (trend alone 8.7%).
   - So the two numbers in the risk budget cannot both hold for an equity-heavy book: either run at
     about 6% volatility, or accept a drawdown near 25-30%.

## 7. What this means

1. **Trend following is not an alpha here.**
   - The pre-registered ETF book earned exactly the T-bill rate from 2017 to 2026: Sharpe 0.00 with
     interest, +1.1% a year on the engine.
   - The best variant (the 12-month signal, Sharpe 0.26) is one of five tried. Ten years of data put
     about ±0.3 of noise on any Sharpe ratio, so none of the five can be told apart from zero.
   - Over a century, trend on US stocks earned a Sharpe of 0.37, against 0.45 for simply holding
     stocks, and its edge has faded since the 1990s.
2. **It is insurance, and the insurance is real.**
   - In the stock market's worst tenth of months it made money in both samples: +1.7% a month on the
     ETFs, +1.5% over a century, while stocks lost 7.5% and 8.9%.
   - It was positive in 1929-32, 1973-74, 1987, 2008-09, Q4 2018, Covid and (the ETF book) 2022.
   - Its max drawdown over a century was −26.5% for the stocks-only version, against −84% for holding
     stocks. With bonds added, it was −14.5% over 64 years.
3. **The insurance has two known gaps.**
   - **Sell-offs that reverse within weeks:** the 2025 tariff drop cost the ETF book 4.8%. Trend needs
     a fall to last long enough for the 1-to-12-month signals to turn.
   - **The year after a big trend year:** 2023 cost 11.7% as 2022's positions (short bonds, long the
     dollar) reversed. This produced the base book's −20% drawdown from October 2022 to November 2023.
4. **Only the long-short version insures.** Long-only trend (ours or September's) looks better on
   Sharpe in a rising decade, but it loses money in the sell-offs. It can only step aside, and so it
   does not do the job this sleeve is for.

5. **As a partner for the put spread, it is not enough.** Section 6: it cut the put spread's losses
   in 2008-09, 2022 and 2025, but not in 2000-02, and the pair still drew down 34% at 10%
   volatility. Next to constant-volatility stocks it left the Sharpe unchanged over 1990-2026.

**Verdict:**
- **Not promoted.** It runs as an observation shadow slot, `tf_etfs`: the base configuration exactly,
  rebalanced every 5 sessions, gross exposure up to 2×.
- **It is the only candidate here that holds up in long bear markets.** So it stays the insurance
  candidate for any book that holds stock risk.
- **It is not a fix for the put spread,** which the companion study rejects on its own.
- **What to watch in shadow:** that the live book matches the backtest's positions and costs.
  A few weeks cannot prove a premium.
