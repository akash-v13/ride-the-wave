"""The bull put spread slot (`bps_spy`) replayed over 1990-2026 on the S&P 500, priced from VIX.

Calibrates the skew curve on the real 2024-26 SPY chains (data/options_history, from
scripts/download_option_history.py), checks the model against the real-chain backtest over the same
months, then runs the five pre-registered configurations and writes
data/research/put_spread_history/{report.md, summary.csv, trades_base.csv} and the base daily returns
to data/research/put_spread_history.parquet. Method and verdict:
docs/research/2026-11-02-put-spread-long-history.md.

    uv run python scripts/download_external.py --only spx,vix,dtb3,put,bxm,cndr,pput,ff_factors   # once
    uv run python scripts/backtest_put_spread_history.py
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger

from ridethewave.config import OptionsSpec
from ridethewave.data.external import load, tbill_daily_return, us_market_total_return
from ridethewave.options.backtest import HISTORY, HistoricalChains, run_options_backtest
from ridethewave.options.chain import parse_occ
from ridethewave.options.history_sim import (
    CONTRACT_MULT,
    SimConfig,
    deflated_sharpe,
    episode_stats,
    fit_skew,
    pick_expiry,
    put_implied_vol,
    put_price,
    realised_vol,
    simulate,
    standardised_moneyness,
    summarize,
    trade_stats,
)

OUT = Path("data/research/put_spread_history")
RETURNS = Path("data/research/put_spread_history.parquet")
CAL_START, CAL_END = date(2024, 2, 1), date(2026, 9, 18)  # the real-chain backtest's window
SIM_START = date(1990, 1, 2)
HALF = "2008-01-01"
DIV = SimConfig().div_yield

# S&P 500 peak to trough for each stress episode (closing prices), plus the 2025 tariff drop that the
# real-chain backtest saw, as a check on the model.
EPISODES = [
    ("1990 Gulf War", "1990-07-17", "1990-10-11"),
    ("1998 LTCM / Russia", "1998-07-20", "1998-10-08"),
    ("2000-02 bear market", "2000-03-27", "2002-10-09"),
    ("2007-09 financial crisis", "2007-10-10", "2009-03-09"),
    ("Aug 2011 US downgrade", "2011-07-25", "2011-10-03"),
    ("Aug 2015 yuan devaluation", "2015-08-17", "2015-09-29"),
    ("Feb 2018 volatility spike", "2018-01-29", "2018-02-08"),
    ("Q4 2018 sell-off", "2018-09-21", "2018-12-24"),
    ("Mar 2020 Covid crash", "2020-02-20", "2020-03-23"),
    ("2022 bear market", "2022-01-04", "2022-10-12"),
    ("Apr 2025 tariff drop", "2025-02-20", "2025-04-08"),
]


def _pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:+.{digits}f}%"


# ---------------------------------------------------------------- calibration
def put_observations(vix: pd.Series, rate: pd.Series) -> pd.DataFrame:
    """Every SPY put close in the 2024-26 cache, 20-50 days out, strike 85-102% of the price, with its
    implied vol (same dividend convention as the simulation) and its ratio to that day's VIX."""
    files = sorted(p for p in HISTORY.glob("SPY_*.parquet") if not p.name.endswith("_underlying.parquet"))
    bars = pd.concat([pd.read_parquet(p, columns=["symbol", "day", "close", "volume"]) for p in files])
    spot = pd.read_parquet(HISTORY / "SPY_underlying.parquet")["close"]
    spot.index = pd.to_datetime(spot.index).normalize()
    bars = bars[bars["symbol"].str[-9] == "P"].copy()
    meta = {s: parse_occ(s) for s in bars["symbol"].unique()}
    bars["day"] = pd.to_datetime(bars["day"])
    bars["expiry"] = pd.to_datetime(bars["symbol"].map(lambda s: meta[s][1]))
    bars["strike"] = bars["symbol"].map(lambda s: meta[s][3])
    bars["spot"] = bars["day"].map(spot)
    bars["vix"] = bars["day"].map(vix) / 100.0
    bars["rate"] = bars["day"].map(rate.reindex(rate.index.union(bars["day"].unique())).ffill())
    bars["dte"] = (bars["expiry"] - bars["day"]).dt.days
    bars["k"] = bars["strike"] / bars["spot"]
    keep = bars[
        bars["dte"].between(20, 50)
        & bars["k"].between(0.85, 1.02)
        & (bars["close"] >= 0.05)
        & (bars["volume"] > 0)
        & bars["spot"].notna()
        & bars["vix"].notna()
        & (bars["day"] >= pd.Timestamp(CAL_START))
        & (bars["day"] <= pd.Timestamp(CAL_END))
    ].copy()
    t = keep["dte"] / 365.0
    keep["iv"] = [
        put_implied_vol(c, s, k, tt, r, DIV)
        for c, s, k, tt, r in zip(keep["close"], keep["spot"], keep["strike"], t, keep["rate"], strict=True)
    ]
    keep = keep.dropna(subset=["iv"])
    keep = keep[(keep["iv"] > 0.02) & (keep["iv"] < 2.0)]
    keep["z"] = [
        standardised_moneyness(k, s, v, d / 365.0)
        for k, s, v, d in zip(keep["strike"], keep["spot"], keep["vix"], keep["dte"], strict=True)
    ]
    keep["ratio"] = keep["iv"] / keep["vix"]
    return keep


def gate_ratios(chains: HistoricalChains, vix: pd.Series) -> pd.Series:
    """The slot's ATM implied vol (snapshot 20-50 days, mean of the six nearest contracts) over VIX."""
    out = {}
    for ts in chains.spot.index:
        if not (pd.Timestamp(CAL_START) <= ts <= pd.Timestamp(CAL_END)) or ts not in vix.index:
            continue
        iv = chains.snapshot(ts.date(), 20, 50).atm_iv()
        if iv:
            out[ts] = iv / (float(vix.loc[ts]) / 100.0)
    return pd.Series(out).sort_index()


def credit_check(obs: pd.DataFrame, skew) -> pd.DataFrame:
    """Each day: the real 95%/90% spread credit at the expiry nearest 35 days vs the model's, same strikes."""
    rows = []
    for day, g in obs.groupby("day"):
        exps = sorted({e.date() for e in g["expiry"]})
        e = pick_expiry(day.date(), exps, 35, 15)
        if e is None:
            continue
        ge = g[g["expiry"] == pd.Timestamp(e)]
        s = float(ge["spot"].iloc[0])
        sh = ge.iloc[(ge["strike"] - s * 0.95).abs().argsort()[:1]]
        lo = ge.iloc[(ge["strike"] - s * 0.90).abs().argsort()[:1]]
        if (
            sh.empty
            or lo.empty
            or abs(float(sh["k"].iloc[0]) - 0.95) > 0.01
            or abs(float(lo["k"].iloc[0]) - 0.90) > 0.01
        ):
            continue
        v, r, t = float(ge["vix"].iloc[0]), float(ge["rate"].iloc[0]), (e - day.date()).days / 365.0
        ks, kl = float(sh["strike"].iloc[0]), float(lo["strike"].iloc[0])
        real = float(sh["close"].iloc[0]) - float(lo["close"].iloc[0])
        model = put_price(s, ks, t, skew.iv(v, s, ks, t), r, DIV) - put_price(s, kl, t, skew.iv(v, s, kl, t), r, DIV)
        if real > 0:
            rows.append({"day": day, "real": real, "model": model, "short_real": float(sh["close"].iloc[0])})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- benchmarks
def market_series(spx: pd.Series) -> pd.Series:
    """US market total return: Ken French (CRSP value-weighted, dividends included) while it lasts,
    then the S&P 500's price return plus the assumed dividend yield."""
    ff = us_market_total_return()
    px = spx.pct_change().dropna() + DIV / 252
    tail = px[px.index > ff.index[-1]]
    return pd.concat([ff, tail]).sort_index()


def top_drawdowns(equity: pd.Series, n: int = 5) -> list[dict]:
    out, peak_v, peak_d, trough_v, trough_d = [], equity.iloc[0], equity.index[0], equity.iloc[0], equity.index[0]
    for d, v in equity.items():
        if v >= peak_v:
            if trough_v < peak_v:
                out.append({"peak": peak_d, "trough": trough_d, "recovered": d, "depth": trough_v / peak_v - 1})
            peak_v, peak_d, trough_v, trough_d = v, d, v, d
        elif v < trough_v:
            trough_v, trough_d = v, d
    if trough_v < peak_v:
        out.append({"peak": peak_d, "trough": trough_d, "recovered": None, "depth": trough_v / peak_v - 1})
    return sorted(out, key=lambda x: x["depth"])[:n]


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-real", action="store_true", help="skip the real-chain backtest re-run (slow)")
    args = ap.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    OUT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    spx = load("spx")["close"]
    vix = load("vix")["close"]
    rate = load("dtb3") / 100.0
    tbill = tbill_daily_return()
    market = market_series(spx)
    market_level = (1 + market).cumprod()

    # 1. calibration on the real chains
    obs = put_observations(vix, rate)
    chains = HistoricalChains.load("SPY", spread_pct=0.03)
    gates = gate_ratios(chains, vix)
    skew = fit_skew(obs["z"].to_numpy(), obs["ratio"].to_numpy(), float(gates.median()))
    obs["model_iv"] = [
        skew.iv(v, s, k, d / 365.0)
        for v, s, k, d in zip(obs["vix"], obs["spot"], obs["strike"], obs["dte"], strict=True)
    ]
    err = (obs["model_iv"] - obs["iv"]) * 100
    say("## Calibration (real SPY puts, Feb 2024 to Sep 2026)")
    say("")
    say(
        f"- {len(obs):,} put closes on {obs['day'].nunique()} days. "
        f"Fitted IV/VIX = {skew.c0:.3f} {skew.c1:+.3f}·z {skew.c2:+.3f}·z²"
    )
    say(
        f"- Slot's ATM IV / VIX: median {gates.median():.3f} "
        f"(25-75%: {gates.quantile(0.25):.3f} to {gates.quantile(0.75):.3f}) on {len(gates)} days"
    )
    say(f"- IV error, all strikes: RMSE {math.sqrt((err**2).mean()):.2f} vol points, bias {err.mean():+.2f}")
    for lo, hi, name in ((0.94, 0.96, "~5% out"), (0.89, 0.91, "~10% out"), (0.99, 1.01, "at the money")):
        b = err[obs["k"].between(lo, hi)]
        say(f"- {name}: RMSE {math.sqrt((b**2).mean()):.2f} vol points, bias {b.mean():+.2f}, n {len(b):,}")
    cc = credit_check(obs, skew)
    rel = (cc["model"] - cc["real"]) / cc["real"]
    say(
        f"- Entry credit of the 95/90 spread, model vs real close, {len(cc)} days: median error {rel.median():+.1%}, "
        f"mean absolute {rel.abs().mean():.1%}, correlation {cc['model'].corr(cc['real']):.2f}"
    )
    say("")

    # 2. the model over the real-chain window, against the real-chain backtest
    base_cfg = SimConfig()
    check_cfg = replace(base_cfg, capital=100_000.0, cash_interest=False)
    syn = simulate(spx, vix, rate, skew, check_cfg, CAL_START, CAL_END)
    syn_r = syn.equity.pct_change().dropna()
    say("## Check: model vs real chains, same rules, Feb 2024 to Sep 2026 (no interest, raw Sharpe)")
    say("")
    say("| | Return | Sharpe | Max DD | Trades | Win |")
    say("| --- | --- | --- | --- | --- | --- |")
    st = trade_stats(syn.trades)
    say(
        f"| model (S&P 500 + VIX) | {_pct(syn.equity.iloc[-1] / syn.equity.iloc[0] - 1)} | "
        f"{syn_r.mean() / syn_r.std() * math.sqrt(252):.2f} | {_pct((syn.equity / syn.equity.cummax() - 1).min())} | "
        f"{st['trades']} | {st['win_rate']:.0%} |"
    )
    if not args.skip_real:
        spec = OptionsSpec(
            id="bt",
            template="bull_put_spread",
            underlying="SPY",
            strike_step_pct=0.025,
            entry_gate="vrp",
            spread_fraction=1.0,
            risk_fraction=0.2,
            profit_target_pct=1.0,
            stop_mult=10.0,
            close_dte=1,
        )
        real = run_options_backtest(spec, chains, CAL_START, CAL_END)
        m = real.metrics
        say(
            f"| real chains (SPY) | {_pct(m['total_return'])} | {m['sharpe']:.2f} | {_pct(m['max_dd'])} | "
            f"{m['trades']} | {m['win_rate']:.0%} |"
        )
        real_open = sorted({t.entry_time.date() for t in real.trades})
        syn_open = sorted({t.opened for t in syn.trades})
        common = len(set(real_open) & set(syn_open))
        say("")
        say(f"- Entry days in common: {common} of {len(real_open)} real and {len(syn_open)} modelled.")
    say("")

    # 3. the five configurations, 1990-2026
    configs = {
        "base": (base_cfg, skew),
        "skew x0.75": (base_cfg, skew.scaled(0.75)),
        "skew x1.25": (base_cfg, skew.scaled(1.25)),
        "gate off": (replace(base_cfg, gate="none"), skew),
        "costs x3": (replace(base_cfg, spread_pct=0.09), skew),
    }
    # not a trial: the base rule sized so the short put's strike value equals equity (one times notional,
    # like Cboe's fully collateralised PutWrite), i.e. a max loss of about 5% of equity per spread
    extras = {"base at 1x notional (risk 5%)": (replace(base_cfg, risk_fraction=0.05), skew)}
    results = {}
    for name, (cfg, sk) in {**configs, **extras}.items():
        results[name] = simulate(spx, vix, rate, sk, cfg, SIM_START)
    end = results["base"].equity.index[-1].date()
    mkt = market_level.loc[str(SIM_START) : str(end)]
    mkt_stats = summarize(mkt, tbill)
    say(f"## Results, {SIM_START} to {end}")
    say("")
    say(
        "| Configuration | CAGR | Excess CAGR | Vol | Sharpe (excess) | Sortino | Max DD | DD peak → trough "
        "| Worst month | Months up | Trades | Win | PF | In market |"
    )
    say("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    rows = []
    for name, res in results.items():
        s = summarize(res.equity, res.rf, market)
        t = trade_stats(res.trades)
        frac = res.days_in_market / len(res.equity)
        rows.append({"config": name, **s, **{k: v for k, v in t.items() if k != "exits"}, "in_market": frac})
        say(
            f"| {name} | {_pct(s['cagr'])} | {_pct(s['excess_cagr'])} | {s['vol']:.1%} | {s['sharpe']:.2f} | "
            f"{s['sortino']:.2f} | {_pct(s['max_dd'])} | {s['dd_peak']} → {s['dd_trough']} | "
            f"{_pct(s['worst_month'])} ({s['worst_month_at']}) | {s['months_positive']:.0%} | {t['trades']} | "
            f"{t['win_rate']:.0%} | {t['profit_factor']:.2f} | {frac:.0%} |"
        )
    say(
        f"| US market (total return) | {_pct(mkt_stats['cagr'])} | {_pct(mkt_stats['excess_cagr'])} | "
        f"{mkt_stats['vol']:.1%} | "
        f"{mkt_stats['sharpe']:.2f} | {mkt_stats['sortino']:.2f} | {_pct(mkt_stats['max_dd'])} | "
        f"{mkt_stats['dd_peak']} → {mkt_stats['dd_trough']} | "
        f"{_pct(mkt_stats['worst_month'])} ({mkt_stats['worst_month_at']}) | "
        f"{mkt_stats['months_positive']:.0%} | | | | |"
    )
    pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)
    base = results["base"]
    bs = summarize(base.equity, base.rf, market)
    say("")
    rv = realised_vol(spx, 20).reindex(base.equity.index)
    gate_open = ((vix.reindex(base.equity.index) / 100.0) * skew.atm_gate - rv >= base_cfg.vrp_threshold).mean()
    ror = pd.Series([t.pnl / (t.max_loss * CONTRACT_MULT * t.qty) for t in base.trades])
    held = sum((t.closed - t.opened).days for t in base.trades) / 365.25
    risk_years = sum(t.max_loss * CONTRACT_MULT * t.qty * (t.closed - t.opened).days / 365.25 for t in base.trades)
    say(
        f"- Base: correlation with the US market {bs['corr_daily']:.2f} daily, {bs['corr_monthly']:.2f} monthly; "
        f"beta {bs['beta_daily']:.2f}. Exits: {trade_stats(base.trades)['exits']}. "
        f"Gate open on {gate_open:.0%} of days."
    )
    say(
        f"- Return on risk capital (P&L / max loss posted), per trade: mean {ror.mean():+.1%}, "
        f"median {ror.median():+.1%}, "
        f"worst {ror.min():+.1%}, 5th percentile {ror.quantile(0.05):+.1%}; over {held:.1f} years in a position, "
        f"{sum(t.pnl for t in base.trades) / risk_years:+.1%} a year on the capital at risk."
    )
    say("")

    # halves
    say("### Halves (base)")
    say("")
    say("| Period | CAGR | Excess CAGR | Sharpe | Max DD | Market CAGR | Market max DD |")
    say("| --- | --- | --- | --- | --- | --- | --- |")
    halves = {}
    for label, lo, hi in (("1990-2007", str(SIM_START), "2007-12-31"), ("2008-2026", HALF, str(end))):
        e = base.equity.loc[lo:hi]
        s = summarize(e, base.rf.loc[lo:hi])
        mk = summarize(market_level.loc[lo:hi], tbill)
        halves[label] = s
        say(
            f"| {label} | {_pct(s['cagr'])} | {_pct(s['excess_cagr'])} | {s['sharpe']:.2f} | {_pct(s['max_dd'])} | "
            f"{_pct(mk['cagr'])} | {_pct(mk['max_dd'])} |"
        )
    say("")

    # episodes
    say("### Stress episodes (S&P peak to trough)")
    say("")
    say("| Episode | Window | Market | Market DD | Base | Base DD inside | Gate off | Skew x1.25 |")
    say("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, lo, hi in EPISODES:
        b = episode_stats(base.equity, market_level, lo, hi)
        g = episode_stats(results["gate off"].equity, market_level, lo, hi)
        k = episode_stats(results["skew x1.25"].equity, market_level, lo, hi)
        if not b:
            continue
        say(
            f"| {name} | {lo} to {hi} | {_pct(b['market'])} | {_pct(b['market_dd'])} | {_pct(b['strategy'])} | "
            f"{_pct(b['strategy_dd'])} | {_pct(g.get('strategy'))} | {_pct(k.get('strategy'))} |"
        )
    say("")
    say("### The base configuration's five deepest drawdowns")
    say("")
    say("| Peak | Trough | Recovered | Depth |")
    say("| --- | --- | --- | --- |")
    for dd in top_drawdowns(base.equity):
        rec = dd["recovered"].date() if dd["recovered"] is not None else "not yet"
        say(f"| {dd['peak'].date()} | {dd['trough'].date()} | {rec} | {_pct(dd['depth'])} |")
    say("")
    worst = sorted(base.trades, key=lambda t: t.pnl)[:8]
    say("Worst trades (base): " + "; ".join(f"{t.opened} → {t.closed} {t.reason} ${t.pnl:,.0f}" for t in worst))
    say("")

    # 4. Cboe benchmarks over common periods
    say("### Against Cboe's option-strategy indexes (total return, Sharpe on excess over T-bills)")
    say("")
    say("| Series | Period | CAGR | Vol | Sharpe | Max DD | Base over the same period: CAGR / Sharpe / Max DD |")
    say("| --- | --- | --- | --- | --- | --- | --- |")
    for nm, label in (
        ("put", "PutWrite (ATM put, fully collateralised)"),
        ("cndr", "Iron Condor"),
        ("pput", "5% Put Protection"),
        ("bxm", "BuyWrite"),
    ):
        lvl = load(nm)["close"]
        lvl = lvl[lvl.index >= pd.Timestamp(SIM_START)]
        if nm == "put":
            lvl = lvl[lvl.index >= "2007-01-01"]  # daily only from 2007 in Cboe's file
        lo, hi = max(lvl.index[0], base.equity.index[0]), min(lvl.index[-1], base.equity.index[-1])
        s = summarize(lvl.loc[lo:hi], tbill)
        b = summarize(base.equity.loc[lo:hi], base.rf.loc[lo:hi])
        say(
            f"| {label} | {lo.date()} to {hi.date()} | {_pct(s['cagr'])} | {s['vol']:.1%} | {s['sharpe']:.2f} | "
            f"{_pct(s['max_dd'])} | {_pct(b['cagr'])} / {b['sharpe']:.2f} / {_pct(b['max_dd'])} |"
        )
    say("")

    # 5. pass/fail and the deflated Sharpe
    trial = {n: results[n] for n in configs}
    trial_sr = []
    for res in trial.values():
        r = res.equity.pct_change().dropna()
        ex = r - res.rf.reindex(r.index).fillna(0.0)
        trial_sr.append(float(ex.mean() / ex.std()))
    r = base.equity.pct_change().dropna()
    ex = r - base.rf.reindex(r.index).fillna(0.0)
    dsr = deflated_sharpe(ex, trial_sr, len(trial))
    sk75 = summarize(trial["skew x0.75"].equity, trial["skew x0.75"].rf)
    sk125 = summarize(trial["skew x1.25"].equity, trial["skew x1.25"].rf)
    crit = [
        ("1. positive excess return in both halves", all(h["excess_cagr"] > 0 for h in halves.values())),
        (
            "2. excess Sharpe >= 0.3 in base and both skew variants",
            min(bs["sharpe"], sk75["sharpe"], sk125["sharpe"]) >= 0.3,
        ),
        ("3. max DD no worse than half the market's", bs["max_dd"] >= mkt_stats["max_dd"] / 2),
        ("4. deflated Sharpe probability >= 0.90 (5 trials)", dsr["dsr"] >= 0.90),
    ]
    say("### Pre-registered criteria")
    say("")
    for label, ok in crit:
        say(f"- {label}: **{'pass' if ok else 'fail'}**")
    say(
        f"- Deflated Sharpe: annual Sharpe {dsr['sharpe_annual']:.2f}, luck threshold {dsr['sr0_annual']:.2f}, "
        f"skew {dsr['skew']:.1f}, kurtosis {dsr['kurtosis']:.0f}, probability vs zero {dsr['psr_vs_zero']:.3f}, "
        f"deflated {dsr['dsr']:.3f}; market max DD {_pct(mkt_stats['max_dd'])}"
    )
    (OUT / "report.md").write_text("\n".join(lines) + "\n")

    out = pd.DataFrame({"ret": r, "excess": ex})
    out.index.name = "date"
    out.to_parquet(RETURNS)
    pd.DataFrame([t.__dict__ for t in base.trades]).to_csv(OUT / "trades_base.csv", index=False)
    print(f"\nwrote {OUT / 'report.md'}, {RETURNS}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
