# Strategy: Wave Rider v1

This is the plain-English specification of the trading rules. It turns the six steps in [outline.md](../outline.md) into precise, testable rules with named parameters. Every parameter lives in `config/settings.yaml`.

## Honest framing first

No strategy guarantees regular positive gains. This one chases short-term momentum, which works in trending markets and loses in choppy ones. Two things in our setup make results look better than they would be with real money: paper trading fills are optimistic, and the free data feed (IEX) shows only a slice of real trading. Treat paper profits as an upper bound. The backtester exists so you can see how often the rules would have lost.

## Definitions

- **Bar:** one minute of trading for one stock: open, high, low, close, volume.
- **Green bar:** a bar whose close is higher than the previous bar's close.
- **Streak:** the count of consecutive green bars ending at the latest bar.
- **Entry price:** the average price actually paid, from the fill.
- **Peak:** the highest trade price seen since entry.
- **Slot:** one of `max_positions` positions the bot may hold at once.

## Step 1: Watch a universe

At start the bot builds a list of symbols (default: top 100 most active by volume, filtered to price between `min_price` and `max_price`, tradable, on a major exchange). It polls prices for all of them every `poll_interval_seconds` and maintains minute bars.

## Step 2: Enter on a green streak

Buy a stock when **all** of these are true at the close of a minute bar:

1. `streak >= green_streak_minutes` (default 3 consecutive rising closes).
2. Total rise over the streak `>= min_streak_gain_pct` (default 1.0%). This filters out three one-cent ticks.
3. Volume over the streak is at least `min_streak_volume` shares (default 10,000) so the move is real on IEX.
4. A slot is free and there is no open position or pending order in this symbol.
5. Time is inside the entry window: after `entry_start` (default 9:31 ET) and before `entry_end` (default 11:30 ET; the sweep showed afternoon entries lose about three times as fast).
6. The symbol was not bought and sold earlier today (`max_entries_per_symbol_per_day`, default 1).
7. The entry filters pass (defaults: SPY up at least 0.1% on the day, the stock up at most 0.6% on the day, and the streak's trade count at most 0.7x the minutes before it). See [features/11-entry-filters.md](features/11-entry-filters.md).

Order: limit buy at ask × (1 + `entry_limit_buffer_pct`, default 0.1%), quantity = floor(slot_dollars / limit price), time in force `day`. If not filled within `entry_fill_timeout_seconds` (default 30), cancel and forget it.

Slot dollars = today's allocation × `position_size_pct` (default 10%). With $10,000 allocated and 10%, each buy is about $1,000.

## Step 3 and 4: Ride the wave

Once filled, the bot tracks the peak price. It also places a server-side safety stop at entry × (1 − `hard_stop_pct`) so the position is protected even if the bot dies.

The position is reviewed every tick (every poll, not just every minute).

## Step 5: Exit rules

Checked in this order; the first that matches wins.

1. **Wave exit (the main rule).** Let `trigger = peak × (1 − trail_pct)` (default trail 1.5%). Let `floor = entry × (1 + min_gain_pct)` (default 0.5%). Sell at market when `last_price <= trigger` **and** `trigger >= floor`. In words: the price has fallen 1.5% from its best, and selling now still locks in at least 0.5% over what we paid. With these defaults the wave exit only arms once the peak is about 2.03% above entry (1.005 ÷ 0.985); before that, only the stop, timeout or close can end the trade.
2. **Hard stop.** Sell when `last_price <= entry × (1 − hard_stop_pct)` (default 1%). The brief does not say what to do when a stock never rises after purchase; without this rule a position could sit at a loss all day. Owner can raise, lower or disable it.
3. **Timeout.** Sell when held longer than `max_hold_minutes` (default 60) and the position is in profit; if it is at a loss, keep holding until the hard stop or close (configurable via `timeout_exit_only_if_profitable`).
4. **Close of day.** If `flatten_at_close` is true (default), sell everything at 15:55 ET.

Between the floor and the trigger there is a grey zone: the price has pulled back from the peak but selling would not yet clear the minimum gain. The bot holds through it. This is intentional and is the "marginal gain" requirement from the brief.

Worked example (defaults): buy at $100.00. Price runs to $103.00 (peak). Trigger = $101.46, floor = $100.50. Trigger is above floor, so the moment the price prints $101.46 or lower, sell. Gain locked ≈ 1.46%. If instead the price only reached $101.50, trigger = $99.98, which is below the floor, so no wave exit. The bot waits: either the price climbs further (trigger rises above floor), or the hard stop at $99.00 fires, or the 60-minute timeout (only if in profit), or the close.

## Parameter history

| Date | Set | Where | Result |
|---|---|---|---|
| 2026-09-17 | v1-original (owner's brief) | `config/profiles/v1-original.yaml` | PF 0.76, -$1,714 over Jun-Sep 2026 |
| 2026-09-17 | sweep best, no filters | `config/profiles/v2-sweep-2026-09-17.yaml` | PF 0.91, -$615 over the same period |
| 2026-09-17 | sweep best + 3 entry filters, current defaults | `config/settings.example.yaml` | PF 1.25, +$168 (116 trades); PF 1.17 on IEX |

Run any profile with `--settings config/profiles/<name>.yaml` on `run_backtest.py`, `sweep.py` or `run_bot.py`.

## Step 6: Consolidate and reinvest

After the close the ledger records for the day: realized profit from closed trades, unrealized profit on anything still held, trade count, wins, losses, largest win, largest loss.

Tomorrow's allocation = `base_allocation` + `reinvest_gains_pct` × cumulative realized gains (default 50%). Losses reduce cumulative gains; the allocation never drops below `base_allocation × min_allocation_ratio` (default 0.5) so one bad day cannot switch the bot off.

## Parameter table

| Parameter | Default | Meaning |
|---|---|---|
| `universe.source` | `most_actives` | `most_actives`, `movers`, or `static` |
| `universe.top` | 100 | Universe size when using a screener |
| `universe.min_price` / `max_price` | 5 / 500 | Price band in dollars |
| `scan.poll_interval_seconds` | 15 | How often prices are fetched |
| `entry.green_streak_minutes` | 3 (was 5) | Consecutive rising minute closes required |
| `entry.min_streak_gain_pct` | 1.0 (was 0.5) | Minimum total rise over the streak |
| `entry.min_streak_volume` | 10000 | Minimum shares traded over the streak (IEX) |
| `entry.max_positions` | 5 | Slots |
| `entry.position_size_pct` | 10 | Percent of allocation per slot |
| `entry.entry_limit_buffer_pct` | 0.1 | Limit price above ask |
| `entry.entry_fill_timeout_seconds` | 30 | Cancel unfilled entries after this |
| `entry.entry_start` / `entry_end` | 09:31 / 11:30 ET (was 09:40 / 15:00) | Entry window; afternoon entries lost ~3x faster in the sweep |
| `entry.max_entries_per_symbol_per_day` | 1 | Re-entry limit |
| `exit.trail_pct` | 1.5 (was 0.5) | Pullback from peak that triggers a sell |
| `exit.min_gain_pct` | 0.5 (was 0.3) | Floor: never wave-exit below this gain |
| `exit.hard_stop_pct` | 1.0 | Safety stop below entry |
| `exit.max_hold_minutes` | 60 (was 120) | Timeout |
| `exit.timeout_exit_only_if_profitable` | true | See exit rule 3 |
| `exit.flatten_at_close` | true | Sell all at 15:55 ET |
| `capital.base_allocation` | 10000 | Dollars the strategy may use per day, before reinvestment |
| `capital.reinvest_gains_pct` | 50 | Share of cumulative realized gains added to allocation |
| `capital.min_allocation_ratio` | 0.5 | Floor on allocation as a fraction of base |

## Things to test in the backtester before trusting any of this

- Streak length 3 vs 5 vs 8.
- Trail 0.3% vs 0.5% vs 1.0% against gain floor 0.2% vs 0.5%.
- Entry window start 9:35 vs 9:40 vs 10:00.
- With and without the hard stop.
- Whether IEX-only minute bars produce enough streaks at all on the chosen universe.
