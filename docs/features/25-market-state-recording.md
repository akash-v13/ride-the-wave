# 25. Daily recordings: fill quotes, borrow flags and option quotes

**Built 9 November 2026.** Three records the system now keeps every trading day. None of them
changes a trade. Each stores something that cannot be looked up later.

## Why

The 9 November assessment (docs/roadmap-advanced-strategies.md, top section) found that the
stat-arb evidence rests on assumptions nobody had checked, and that some of the data needed to
check them is not kept by Alpaca:
- **What a trade costs.** The shadow books charge themselves a flat 5 bp. The real cost is half the
  quoted spread at that moment, which was never stored.
- **Whether a stock could be shorted.** Alpaca says so for today only. The backtest assumed every
  short was available.
- **What options implied.** Alpaca's option history starts in February 2024 and holds prices only,
  with no implied volatility.

Recording these daily costs almost nothing. A year from now the files are a dataset no cheap vendor
sells.

## 1. The quote beside every simulated fill

**What it does.** When a daily portfolio slot (`portfolios:` in the settings) fills a trade, it
stores the bid and ask from the same price snapshot. The fill itself is unchanged: last trade plus
or minus `slippage_bps`.

**Where.** Table `portfolio_fills` in the database, one row per fill:

| Column | Meaning |
|---|---|
| `strategy`, `day`, `ts` | The slot, the session decided, and the decision time (UTC) |
| `symbol`, `qty` | The stock and the signed number of shares (+ bought, − sold) |
| `price` | The simulated fill |
| `last` | The last trade the fill was priced from |
| `bid`, `ask` | The quote at that moment; empty when the snapshot had none |
| `target` | The target weight that caused the fill |

After each decision the log also says what the fills would have paid. The numbers below only show
the format:

    [sa_volrev] quoted half-spread at the fills: mean 3.1 bp, median 2.0 bp (110 of 112 quoted; the book charges itself 5.0 bp)

**Example query:** the average half-spread a slot's fills faced, by day.

```sql
SELECT day, COUNT(*) AS fills,
       ROUND(AVG((ask - bid) / (ask + bid) * 10000), 1) AS half_spread_bp
FROM portfolio_fills
WHERE strategy = 'sa_volrev' AND bid > 0 AND ask > bid
GROUP BY day;
```

**If storing fails** (a full disk, a locked file), the slot logs a warning and the decision stands.

## 2. Borrow flags

**What it does.** Once a day, saves Alpaca's whole list of active US stocks and funds (about
14,400 rows) with each one's `shortable` and `easy_to_borrow` flags.

**Where.** `data/recordings/assets/<day>.parquet`. Columns: `day`, `symbol`, `exchange`,
`tradable`, `marginable`, `shortable`, `easy_to_borrow`, `fractionable`.

**Why the whole list.** Tomorrow's research universe is not known today, and the file is about
100 KB.

**First day's finding (9 November):** of the 254 stat-arb names, one (ONDS) cannot be shorted, and
two (KVUE, WBD) are no longer listed at all.

## 3. Option quotes

**What it does.** For each stock in the stat-arb universe, plus SPY, QQQ, IWM and the 11 sector
ETFs, saves every option contract that is:
- in one of the next two monthly expiries (third Fridays) at least 7 days away. These two sit
  either side of about 30 days, so a constant 30-day measure can be interpolated;
- within 20% of the current stock price.

**Where.** `data/recordings/options/<day>.parquet`, about 28,000 rows and 1.2 MB a day.

| Column | Meaning |
|---|---|
| `day`, `ts`, `market_open` | The session, when it was recorded, and whether the market was open then |
| `underlying`, `spot` | The stock and its price when the chain was read |
| `symbol`, `expiry`, `right`, `strike` | The contract |
| `bid`, `ask`, `bid_size`, `ask_size`, `quote_ts` | The latest quote and its time |
| `last`, `last_ts` | The latest trade and its time |
| `iv`, `delta`, `gamma`, `theta`, `vega`, `rho` | Implied volatility and greeks as the feed gives them |

**Stored raw.** Nothing is computed or filled in. A contract with no quote or no implied volatility
is kept with those fields empty. Skew, the call-put spread, or 30-day implied volatility can all be
built later, but only for days that were recorded.

**Details that matter:**
- **Stock price.** In the session, the last trade. After the close, today's closing price, because
  option quotes stop at 16:00 and a later after-hours trade would misstate each strike's distance
  from the money.
- **Stock prices are re-read every 40 names,** so a chain is never priced against a stock price
  more than a few seconds old.
- **Delisted names are skipped.** A delisted stock still answers with its last trade and dead
  option quotes, so only names tradable today are recorded. The skipped names are logged.
- **Holiday expiries.** When the third Friday is a market holiday, the monthly expires on the
  Thursday; an empty answer for the Friday is asked again for the Thursday.

## When it runs

- **Fill quotes:** inside the bot, at each slot's decision.
- **Borrow flags and option quotes:** `scripts/record_market_state.py`, run by the operator tick
  at **15:45 ET** on trading days, so the quotes are live. It takes about 20 seconds and is a
  separate process, so the bot is not slowed near the close.
  - **Late or half-day runs** (up to four hours late, as for every operator task) record the
    closing quotes and mark the file `market_open = false`.
  - **A day already recorded is never replaced,** unless the script is run with `--force`.
  - **Holidays:** nothing is recorded.

## If something goes wrong

The script sends a phone alert and exits with an error when:
- the asset list has fewer than 5,000 rows;
- fewer than 80% of the names come back with implied volatility;
- either request fails outright.

The latest run's counts are in the database under the key `recording` (table `bot_state`).

## Files

- `src/ridethewave/data/recordings.py`: expiry choice, row building, file writing.
- `scripts/record_market_state.py`: the daily run.
- `src/ridethewave/operator/dispatch.py`: the 15:45 ET task `record-market`.
- `src/ridethewave/portfolio/daily_slot.py` (`_record_fills`), `src/ridethewave/storage/schema.sql`
  (`portfolio_fills`), `src/ridethewave/storage/repos.py` (`FillRepo`).
- Tests: `tests/test_recordings.py`, two cases in `tests/test_daily_slot.py`, one in
  `tests/test_dispatch.py`.

## Limits

- **`easy_to_borrow` is a yes or no,** not a borrowing fee. It shows which shorts were available,
  not what they cost.
- **One snapshot a day.** Borrow status and implied volatility both move during the day.
- **BRK.B's options come back without implied volatility.** The prices are stored, so it can be
  computed.
- **Options are recorded for about 266 names only.** A wider universe later starts its history on
  the day it is added.
- **Size:** about 300 MB a year at this universe.
