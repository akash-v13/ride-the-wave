# Feature 26: shadow slots for shortlist signals A, C and D

**Added 10 November 2026, trading from 11 November.** The owner asked to watch all three in shadow
after their tests (docs/research/2026-11-10-signals-a-c-d.md). **None of them passed.** These slots
are for observation: they risk nothing, they use simulated money, and their results are evidence
about the signals, not a reason to trade them.

| Slot | Signal | Test verdict | Simulated capital | Trades at |
|---|---|---|---|---|
| `mom_night` | C. Momentum held overnight | Missed its 4 bp bar by 0.24 bp | $500,000 | 15:50 (buy), 09:35 next day (sell) |
| `sa_sector` | A. Sector-stress reversal | Rejected: −28.6 bp per cohort | $500,000 | 09:35 |
| `tom_spy` | D. Turn of the month | Rejected: gone since 2006 | $10,000 | 15:50 |

## `mom_night`: momentum held overnight only

**What it does each day.**
1. **15:50 New York time.** Rank the 254 liquid stocks on their return from 252 to 21 sessions ago,
   using closes up to yesterday. Buy the top 30% (about 75 names) in equal amounts.
2. **09:35 the next morning.** Sell everything at each stock's opening auction price.

**How the fills are booked.** The rule that was tested buys at the close and sells at the open.
- **The purchase** is first booked at the price standing at 15:50, because the close is not known
  yet. The next morning it is **re-booked at the official close**, plus 1 bp. The log says how far
  the two were apart on average.
- **The sale** is at the opening auction price, less 1 bp. If Alpaca has no auction print for a
  stock, the day's first trade is used.
- So each night's result is close to open, as in the test. The 15:50 price never reaches the
  result.

**If the bot misses a morning,** the positions are sold at the next open it sees, and their purchase
price is left as it was booked.

**How to judge it.** The test's number was the winners' overnight return *beyond the universe's*
(+3.76 bp a night). The slot's own profit also includes the whole market's overnight move, so it
must be compared with the universe's overnight return on the same nights, not read alone.

**Known gaps.**
- **Dividends.** The slot does not credit a dividend when it holds a stock over its ex-date. That
  understates its return by about half a basis point a night on average. The universe comparison
  has the same gap, so the difference between them is fair.
- **The cost is an allowance.** 1 bp a trade is assumed. A paper account cannot show what a real
  closing or opening auction order would get.
- **It is concentrated.** On 10 November the winners were mostly chip, memory and AI infrastructure
  stocks. The book will move with that group overnight.

**Settings.** `flatten_time: "09:35"` is what makes a slot overnight-only. It is a general setting:
any daily slot with it sells everything at the opening auction each morning.

## `sa_sector`: reversal inside stressed sectors, calm markets

The same machinery as `sa_volrev` with the opposite gate. On a session after VIX closed **below** 20:
- find the sectors whose five-session move beyond SPY is in the top tenth of their own last year;
- inside each, buy the fifth of its stocks whose own move fell most and short the fifth that rose
  most (a sector needs at least 10 ranked stocks; a cohort needs at least 4 names a side);
- hedge with SPY and the sector ETFs, hold five sessions, fill at the opening auction plus 1 bp.

The two slots never form a cohort on the same day: `sa_volrev` trades after a VIX close of 20 or
more, `sa_sector` after a close below 20.

**What to expect.** In the test this lost money in nine years out of ten. If it keeps losing, that
supports the opposite reading (after sector news, moves continue), which is candidate G.

## `tom_spy`: turn of the month

Holds SPY over the last trading day of each month and the first three of the next; cash otherwise.
- Decided at 15:50 for the next session, from Alpaca's trading calendar.
- Filled at the 15:50 price plus 1 bp, a stand-in for the close.
- Without the calendar it keeps whatever it holds.
- First purchase due: Friday 27 November 2026, for Monday the 30th. **That Friday is a half day** (the
  market closes at 13:00), and a 15:50 decision does not run on a half day. Early closes are not
  handled yet for any slot; this has to be fixed before then.

## Where the code is

- Strategies: `overnight_momentum`, `statarb_sector_stress`, `turn_of_month` in
  `src/ridethewave/daily/strategies.py`; the conditions in `daily/signals.py`; the sector cohorts in
  `daily/statarb.py` (`sector_cohort_targets`).
- The morning sale: `DailySlot.sell_at_open` and `BotRunner._sell_portfolio_at_open`.
- Settings: `config/settings.yaml`, under `portfolios:`.
- Tests: `tests/test_daily_slot.py`, `tests/test_signals.py`.

## How to check

- Log lines each day: `[mom_night] ... winners of ... ranked`, `purchases re-booked at the ... close`,
  `sold ... positions at the open`; `[sa_sector] cohort from ...`; `[tom_spy] next session ... is ...`.
- Fill records: `portfolio_fills`, where `basis` is `close` (a re-booked purchase), `auction` or
  `open` (a morning sale), `last` (the 15:50 stand-in, superseded for `mom_night`).
- `uv run python scripts/run_bot.py --dry-run --no-wait` shows what each slot would do now and saves
  nothing.
