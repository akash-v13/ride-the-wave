# 23. Trend-following sleeve and outside histories

**Built 2 November 2026.** Shadow only. Part of the strategy re-think: a portfolio of independent
sleeves instead of one intraday edge (brainstorm 2026-10-29, progress log 2026-11-02).

## What it does

### The trend sleeve (`trend_following`, shadow slot `tf_etfs`)

Once every five sessions, at 15:50 ET, the slot looks at 21 ETFs in four asset classes:
- **Stocks:** SPY, IWM, EFA, EEM, EWJ, VNQ.
- **Bonds:** IEF, TLT, TIP, LQD, HYG, EMB.
- **Commodities:** GLD, SLV, DBC, USO, DBA, UNG.
- **Currencies:** UUP, FXE, FXY.

For each fund it asks one question: has it been going up or down over the last 1, 3 and 12 months?

- All three up: fully long. All three down: fully short. Mixed: a third of a position either way.
- Each asset class gets the same share of risk, and each fund inside a class the same share.
- A fund's position is divided by its own volatility, so a calm bond fund and a wild gas fund carry
  the same risk.
- The whole book is then sized so its expected volatility is 10% a year, using how the funds have
  moved together over the last six months.
- Each position is capped at half the book, and total long plus short exposure at 2× (the overnight
  margin limit).

Between rebalances it holds and marks its positions to market. It runs on $50,000 of simulated money,
enough that whole-share rounding stays small.

**Why it exists.** The rule is meant as insurance, not as a source of return. Over 2017-2026 it
earned the T-bill rate. But it tends to be short stocks and long safe assets by the time a sell-off
has run for a few weeks: +26% in 2022, +5% in the Covid crash, and positive in every long bear
market since 1929. The put-spread sleeve loses in exactly those months.
docs/research/2026-11-02-trend-following.md has the evidence and the cases where it fails: fast
V-shaped drops such as April 2025, and the year after a big trend year, such as 2023.

### Outside histories (`ridethewave.data.external`)

Alpaca's data starts in 2016. These three public sources go further back, for research only. The
bot never trades on them.

| Name | Source | What | From |
|---|---|---|---|
| `ff_factors`, `ff_momentum` | Ken French data library | US stock market, size, value and momentum factor returns, daily | 1926 |
| `ff_st_reversal`, `ff_st_reversal_monthly`, `ff_mom_deciles`, `ff_rev_deciles`, `ff_rev_deciles_monthly`, `ff_49_industries` | Ken French data library | Short-term reversal factor, ten portfolios sorted on 12-2 month and on last month's return, 49 industries. **The daily files re-sort every day**; read each file's preamble before use | 1926 |
| `spx`, `vix` | Cboe | S&P 500 index level; VIX | 1975; 1990 |
| `put`, `bxm`, `cndr`, `pput` | Cboe | PutWrite, BuyWrite, iron condor and 5% put-protection benchmark indexes | 2007 (PUT daily); 2002; 1986; 1986 |
| `dgs10`, `dtb3` | FRED | 10-year Treasury yield; 3-month T-bill rate | 1962; 1954 |

The module includes helpers for the series the studies need:
- `us_market_total_return()`: the whole US stock market, dividends included.
- `treasury_10y_total_return()`: a 10-year Treasury rebuilt from the yield, as a par bond.
- `tbill_daily_return()`: cash.

## How to run

```bash
uv run python scripts/download_external.py                 # all outside datasets (--list, --only vix,spx)
uv run python scripts/download_daily.py --start 2015-06-01 --end 2026-11-02 --universe trend_etfs_21
uv run python scripts/research_trend.py                    # the study: ETFs 2017-26 and the century test
uv run python scripts/research_sleeves.py                  # sleeves combined at a 10% volatility target
uv run python scripts/run_daily_backtest.py --strategy trend_following --universe trend_etfs_21 \
    --start 2017-01-03 --end 2026-10-30 --rebalance-days 5 --max-gross 2   # one run through the engine
```

Re-run `download_external.py` to refresh. Cboe and FRED update daily; Ken French monthly, about a
month behind.

## Settings

```yaml
portfolios:
  - id: tf_etfs
    kind: trend_following
    universe: trend_etfs_21
    rebalance_days: 5        # trade every 5 sessions, hold and mark in between
    max_gross: 2.0
    weight: 5.0              # capital = base_allocation x weight
    params: {}               # defaults: lookbacks [21, 63, 252], vol_com 60, cov_days 126, target_vol 0.10,
                             # max_weight 0.5, allow_short true, classes = the four classes above
```

`rebalance_days` used to be accepted and ignored. Since this feature, every daily slot honours it.
The slot remembers the date of its last rebalance across restarts.

## Files

- `src/ridethewave/daily/strategies.py`: `TREND_CLASSES`, `TrendParams`, `trend_weights` (the pure
  rule) and `TimeSeriesMomentum`.
- `src/ridethewave/daily/universe.py`: `trend_etfs_21`.
- `src/ridethewave/data/external.py`: dataset registry, download, parsers, derived series.
- `src/ridethewave/portfolio/daily_slot.py`: `rebalance_days`.
- `scripts/download_external.py`, `scripts/research_trend.py`, `scripts/research_sleeves.py`.
- Tests: `tests/test_trend_following.py`, two new cases in `tests/test_daily_slot.py`.
- Data: `data/external/<source>/`, results in `data/research/trend/` and `data/research/sleeves/`.

## Limits

- **Shadow only.** Fills are simulated at the 15:50 price plus 5 basis points. The slot sends
  nothing to Alpaca.
- **No borrow fees or margin interest** are charged on shorts or on leverage above 1×, and no
  interest is paid on cash. The research page shows results both without interest and with T-bill
  interest on the net cash balance. A live version would need the account's actual rates modelled.
- **Signs of total return, not return over cash.** Simpler, and needs no rate data live. When
  T-bills pay 5%, a bond fund earning 3% still counts as "rising".
- **Whole shares.**
