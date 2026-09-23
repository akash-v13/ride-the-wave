# Vision: an autonomous simulated quant trader

**Owner's end goal (2026-09-21):** a paper-trading quant system that runs on this machine with
little manual involvement (about five check-ins a day), not chasing low latency, but drawing on
many strategies from books, papers and news that an individual trader would never hold in their
head at once, with AI doing the research, orchestration and reporting.

## What is realistic here, and what is not

| Realistic on this machine and data | Not realistic, and not needed |
|---|---|
| Strategies with holding periods from minutes to weeks | Sub-second execution, market making, latency arbitrage |
| Dozens of strategies researched, tested and incubated in parallel | Hundreds of live strategies with real capital behind each |
| Fully scheduled daily operation with alerts and plain-English reports | Zero supervision: someone must approve what trades and how much |
| Free IEX real-time data for liquid names; full SIP history for research | Reliable intraday fills on thin names without the paid SIP feed |
| Paper account with 4x margin and shorting for realistic long-short tests | Paper fills as a proxy for real slippage; treat every result as an upper bound |

The binding constraint is not compute. It is edge size per bet and data quality. A $99/month SIP
upgrade is the single biggest feasibility lever for intraday strategies; it is the owner's call.

## Where AI genuinely adds, and where it does not

Adds:
1. **Research throughput.** Turning books and papers into testable rules (skills), then running
   them through one strict validation protocol, many per night, and writing up what survived.
2. **Judgment on text.** News, filings and sentiment as features, via Jev or an LLM, which code
   alone cannot do.
3. **Operations.** Scheduling, monitoring, anomaly triage, and reports written for a five-minute
   check-in rather than a log file.
4. **Meta-allocation.** Deciding how much each live strategy gets, as a bandit over strategies
   with a risk budget, updated from live results.

Does not add: edge from noise. More strategies means more chances to fool ourselves; the
multiple-testing problem grows with breadth of search. The counterweight is procedural: the Dixon
protocol for every candidate, paper incubation before allocation, and evidence thresholds that
scale with how many things were tried.

## Architecture: strategy factory, allocator, operator

```
        BOOKS / PAPERS / NEWS                 MARKET DATA (Alpaca)
               │                                     │
     ┌─────────▼─────────┐               ┌───────────▼───────────┐
     │  Research pipeline│               │  Data layer            │
     │  skill → rules →  │◄──────────────│  cache, features,      │
     │  backtest under   │               │  news, universe        │
     │  protocol → note  │               └───────────┬───────────┘
     └─────────┬─────────┘                           │
               │ candidates that pass                │ bars, features
     ┌─────────▼─────────┐               ┌───────────▼───────────┐
     │  Incubation       │               │  Strategy plugins      │
     │  shadow mode on   │──────────────►│  signal / portfolio /  │
     │  paper, no capital│               │  market-timing types   │
     └─────────┬─────────┘               └───────────┬───────────┘
               │ promoted                            │ signals, target weights
     ┌─────────▼───────────────────────────────────▼───────────┐
     │  Allocator: risk budget, vol targeting, drawdown limits, │
     │  bandit over live strategies                              │
     └─────────────────────────────┬───────────────────────────┘
                                   │ orders
     ┌─────────────────────────────▼───────────────────────────┐
     │  Execution: broker, position book, reconciliation, stops │
     └─────────────────────────────┬───────────────────────────┘
                                   │
     ┌─────────────────────────────▼───────────────────────────┐
     │  Operator: scheduler, watchdog, kill switches, check-in  │
     │  reports (5/day), alerts, nightly research jobs          │
     └──────────────────────────────────────────────────────────┘
```

What exists today: the data layer, one signal-type strategy, execution, a replay engine, the
feature dataset, the validation skill, and a dashboard. What is missing is everything in the
operator and allocator boxes, the portfolio strategy type, and the incubation stage.

## The five check-ins

| Time (ET) | What the owner sees | Decisions |
|---|---|---|
| ~09:00 | Pre-market brief: data health, universe, which strategies are armed, risk budget, news flags | Pause a strategy, change risk |
| ~11:30 | Morning report: positions, P/L, anything abnormal | Nothing unless alerted |
| ~14:00 | Midday report | Same |
| ~16:15 | Close report: ledger, per-strategy P/L, drawdown, fills vs expected slippage | Same |
| ~21:00 | Research digest: nightly jobs finished, candidates that passed, what to approve for incubation or promotion | Approve, reject, ask for more |

Alerts outside check-ins only for: stale heartbeat, API failures, drawdown or daily-loss breach,
reconciliation mismatch.

## Sequence

- **A. Operator first.** Scheduled start and stop, watchdog restart, kill switches (daily loss,
  posterior win-rate floor), the five reports as plain-English pages, alerts. This makes the
  five-check-in day real for whatever strategies exist.
- **B. Multi-strategy core.** Strategy registry with three types (signal, market-timing,
  portfolio), shadow mode, per-strategy books and ledgers, allocator with a risk budget.
- **C. Strategy pipeline.** SPY intraday momentum, opening-range breakout, pairs, cross-sectional
  momentum and reversal, each through the protocol and into incubation. See
  [roadmap-advanced-strategies.md](roadmap-advanced-strategies.md).
- **D. Nightly research automation.** Data refresh, feature rebuild, diagnostics and sweeps for
  queued ideas, digest for the evening check-in.
- **E. Knowledge intake.** Tsay and Rao skills, Jev for news, more books as they arrive.

## Honest expectations

Paper results overstate live results; the free feed understates volume and fill quality; and a
system that tries many strategies will find false positives. The goal of the build is therefore a
robust, self-running research-and-trading loop in which the owner's check-ins are decisions, not
operations, and in which every promotion of a strategy is backed by evidence the protocol produced.
