# Strategy intake: how to hand me a strategy

Drop a Markdown file in `docs/strategies/inbox/` named `YYYY-MM-DD-short-name.md` using the
template below, or paste the same headings in chat. Half-filled is fine; "unknown" is an answer. I
implement it against the right engine, run the evidence protocol, and write the verdict back to
`docs/strategies/<name>.md` with the numbers. Nothing gets capital without passing the gates.

## The pipeline every idea goes through

| Stage | What happens | Gate to pass |
| --- | --- | --- |
| 1. Brief | Your file, in the format below | Signal and horizon are stated |
| 2. Implementation | Pure strategy code: intraday (`Strategy`), daily portfolio (`DailyStrategy`) or options slot | Unit tests on a synthetic case |
| 3. Diagnostic | Is there anything to predict? Forward returns by signal quintile, rank correlation, halves | Effect with a t-statistic near 2, same sign in both halves |
| 4. Backtest | Replay with fills at the next bar plus slippage, against the benchmark and the equal-weight universe; point-in-time, survivorship-free universe | Information ratio above the universe > 0.5, positive both halves, profit factor > 1.2 net |
| 5. Shadow | Simulated fills on live prices for 2 to 4 weeks | Live behaviour matches the backtest (fills, frequency, P&L sign) |
| 6. Live paper | A capital share; kill switches apply | 30+ trades with the backtest's expectancy |
| 7. Review | Monthly, on the leaderboard | Keep, resize or retire |

## The template

```markdown
# <Strategy name>

**Source.** Book / paper / article / your own idea (link or citation).
**Asset class and universe.** Stocks (which ones: liquid large caps, sector ETFs, a screen?),
options (underlying), crypto (pairs).
**Horizon.** Intraday (minutes to hours), daily (overnight to weeks), monthly.
**Signal.** In words, then the formula if you have it. What is measured, over what lookback.
**Entry.** When exactly, at what price (market, limit, open, close, extended hours).
**Exit.** Target, stop, time limit, or a rebalance rule.
**Sizing and risk.** Equal weight, volatility-scaled, max positions, max loss per trade or per day.
**Data needed.** Bars (which size), quotes, options chains, news, corporate actions, anything outside Alpaca.
**Why it should work.** Who is on the other side and why they pay: risk premium, behavioural
bias, structural flow, information lag.
**Known failure modes.** Regimes or events where it loses (crashes, earnings, low volatility).
**How to test it.** Period, benchmark, what result would make you drop it.
**Anything you already know.** Prior results, where and on what data; what universe was used.
```

## A filled example

```markdown
# Overnight return effect on liquid stocks

**Source.** Berkman, Koch, Tuttle, Zhang (2012), "Paying attention: overnight returns and the
hidden cost of buying at the open"; our own finding that intraday open-to-close drift was -16 bp
a day in Jun-Sep 2026.
**Asset class and universe.** Stocks; point-in-time top 100 by dollar volume, funds excluded.
**Horizon.** Overnight: buy at the close, sell at the next open.
**Signal.** None or a filter: skip names with earnings the next morning; optionally rank by the
previous overnight return.
**Entry.** Market-on-close proxy: a limit order at 15:58 at the ask; or 15:59 extended-hours.
**Exit.** Limit at the bid at 09:31, or extended-hours at 04:05 for the pre-market drift.
**Sizing and risk.** Equal dollars across 20 names; no leverage; skip a name if its spread exceeds 10 bp.
**Data needed.** Daily bars (close, next open) for the backtest; extended-hours quotes live.
**Why it should work.** Retail attention buys at the open; overnight earns the risk premium
without paying the intraday reversal. It is a documented split of the equity premium.
**Known failure modes.** Gap risk on news; transaction costs on two trades a day; the effect
weakened after 2015 in some studies.
**How to test it.** 2017-2026, survivorship-free universe, versus holding SPY 24 hours;
drop it if the close-to-open excess over SPY's own close-to-open is under 3 bp a day net.
**Anything you already know.** Not tested yet.
```

## What you get back

`docs/strategies/<name>.md`: the brief, what was built (file and registry name), the diagnostic
table, the backtest table with benchmarks and halves, the verdict (run in shadow / rejected /
needs data), and what is in the settings if it runs. The research page index in
`docs/research/README.md` links the details.

## Ideas the API now makes possible (untested)

Overnight return effect (above); post-earnings drift once an earnings calendar exists; dividend
capture via the corporate-actions feed; short-side momentum on easy-to-borrow names; crypto trend
and volatility targeting 24/7; pairs with a cointegration gate on the survivorship-free universe;
covered-call overwriting on a held daily portfolio; volatility-risk-premium condors gated on the
options backtester once it exists.
