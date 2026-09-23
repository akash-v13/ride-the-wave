#!/usr/bin/env python
"""Evaluation helpers from Dixon, Halperin & Bilokon (2020), for Ride The Wave.

Library use:
    from evalkit import (day_folds, calibration_table, confusion_chi2, beta_posterior,
                         bayes_factor_binomial, diebold_mariano)

CLI:
    uv run python .claude/skills/dixon-ml-finance/scripts/evalkit.py folds --parquet data/features/features-*.parquet
    uv run python .claude/skills/dixon-ml-finance/scripts/evalkit.py posterior --wins 41 --losses 75
    uv run python .claude/skills/dixon-ml-finance/scripts/evalkit.py bayes --wins 41 --n 116 --p0 0.35
    uv run python .claude/skills/dixon-ml-finance/scripts/evalkit.py chi2 --tp 30 --fp 40 --fn 20 --tn 60
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence

import numpy as np


# ---------- walk-forward folds by day (Ch. 6 §4.2, pp. 213-214) ----------
def day_folds(days: Sequence, train: int = 25, verify: int = 5, test: int = 10, step: int | None = None):
    """Fixed-window walk-forward over an ordered list of trading days.

    Returns a list of (train_days, verify_days, test_days). Nothing in verify/test precedes train.
    """
    days = list(days)
    step = step or test
    folds = []
    start = 0
    while start + train + verify + test <= len(days):
        tr = days[start : start + train]
        ve = days[start + train : start + train + verify]
        te = days[start + train + verify : start + train + verify + test]
        folds.append((tr, ve, te))
        start += step
    return folds


# ---------- calibration (pp. 71, 149) ----------
def calibration_table(p: np.ndarray, y: np.ndarray, bins: int = 10):
    """Reliability table: per probability decile, mean predicted vs observed frequency and count."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    rows = []
    for i in range(bins):
        m = (p > edges[i]) & (p <= edges[i + 1])
        if m.sum() == 0:
            continue
        rows.append({"bin": i + 1, "n": int(m.sum()), "mean_pred": float(p[m].mean()), "observed": float(y[m].mean())})
    return rows


# ---------- confusion-matrix chi-squared vs white noise (Eq. 6.49, p. 212) ----------
def confusion_chi2(tp: int, fp: int, fn: int, tn: int) -> tuple[float, bool]:
    m = np.array([[tp, fn], [fp, tn]], float)
    tot = m.sum()
    row = m.sum(axis=1, keepdims=True)
    col = m.sum(axis=0, keepdims=True)
    exp = row @ col / tot
    stat = float(((m - exp) ** 2 / exp).sum())
    return stat, stat > 6.635  # 1 d.o.f., 99%


# ---------- Beta-Bernoulli posterior of a win rate (pp. 58-62) ----------
def beta_posterior(wins: int, losses: int, alpha: float = 1.0, beta: float = 1.0):
    a, b = alpha + wins, beta + losses
    mean = a / (a + b)
    var = a * b / ((a + b) ** 2 * (a + b + 1))
    return {"alpha": a, "beta": b, "mean": mean, "sd": math.sqrt(var), "n": wins + losses}


def prob_below(threshold: float, alpha: float, beta: float, samples: int = 200_000, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    return float((rng.beta(alpha, beta, samples) < threshold).mean())


# ---------- Bayes factor: fixed p0 vs uniform theta (Example 2.4, pp. 67-68) ----------
def bayes_factor_binomial(wins: int, n: int, p0: float) -> dict:
    """B = evidence(win rate = p0) / evidence(win rate ~ Uniform). |ln B| < 1 is 'no evidence'."""
    log_c = math.lgamma(n + 1) - math.lgamma(wins + 1) - math.lgamma(n - wins + 1)
    log_ev_p0 = log_c + wins * math.log(p0) + (n - wins) * math.log(1 - p0)
    log_ev_uniform = -math.log(n + 1)  # integral of C(n,k) p^k (1-p)^(n-k) dp = 1/(n+1)
    ln_b = log_ev_p0 - log_ev_uniform
    if abs(ln_b) < 1:
        verdict = "no evidence either way"
    elif ln_b > 0:
        verdict = "favours the fixed rate p0 (no real difference)"
    else:
        verdict = "favours a different win rate"
    return {"ln_B": ln_b, "B": math.exp(ln_b), "verdict": verdict}


# ---------- Diebold-Mariano on two loss series (p. 220) ----------
def diebold_mariano(loss_a: np.ndarray, loss_b: np.ndarray, h: int = 1) -> dict:
    """Test equal predictive accuracy: d = loss_a - loss_b, HAC variance with h-1 lags. Negative DM favours a."""
    d = np.asarray(loss_a, float) - np.asarray(loss_b, float)
    T = len(d)
    mean = d.mean()
    dc = d - mean
    gamma0 = float((dc * dc).mean())
    var = gamma0
    for k in range(1, h):
        gk = float((dc[k:] * dc[:-k]).mean())
        var += 2 * gk
    var = max(var, 1e-12)
    dm = mean / math.sqrt(var / T)
    from math import erf, sqrt

    p = 2 * (1 - 0.5 * (1 + erf(abs(dm) / sqrt(2))))
    return {"DM": dm, "p_value": p, "mean_diff": mean, "T": T}


def pnl_bootstrap(pnl: np.ndarray, n_boot: int = 10_000, seed: int = 0) -> dict:
    """Bootstrap CIs for mean P/L per trade and profit factor. PF is the claim that hit-rate tests miss."""
    pnl = np.asarray(pnl, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(pnl), size=(n_boot, len(pnl)))
    samples = pnl[idx]
    means = samples.mean(axis=1)
    gains = np.where(samples > 0, samples, 0).sum(axis=1)
    losses = -np.where(samples <= 0, samples, 0).sum(axis=1)
    pfs = np.where(losses > 0, gains / np.maximum(losses, 1e-12), np.inf)
    return {
        "n": int(len(pnl)),
        "mean": float(pnl.mean()),
        "mean_ci95": (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))),
        "p_mean_below_zero": float((means <= 0).mean()),
        "pf": profit_factor(pnl),
        "pf_ci95": (float(np.quantile(pfs, 0.025)), float(np.quantile(pfs, 0.975))),
        "p_pf_below_one": float((pfs <= 1.0).mean()),
    }


def pf_difference_bootstrap(pnl_a: np.ndarray, pnl_b: np.ndarray, n_boot: int = 10_000, seed: int = 0) -> dict:
    """Is PF(a) > PF(b)? Independent resamples of each trade list; reports the CI of the difference."""
    a = np.asarray(pnl_a, float)
    b = np.asarray(pnl_b, float)
    rng = np.random.default_rng(seed)

    def pfs(x):
        idx = rng.integers(0, len(x), size=(n_boot, len(x)))
        smp = x[idx]
        g = np.where(smp > 0, smp, 0).sum(axis=1)
        l = -np.where(smp <= 0, smp, 0).sum(axis=1)
        return g / np.maximum(l, 1e-12)

    d = pfs(a) - pfs(b)
    return {
        "pf_a": profit_factor(a),
        "pf_b": profit_factor(b),
        "diff_ci95": (float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))),
        "p_a_not_better": float((d <= 0).mean()),
    }


def breakeven_win_rate(avg_win: float, avg_loss: float) -> float:
    """Win rate at which expected P/L is zero given the average winner and (positive) average loser."""
    return avg_loss / (avg_win + avg_loss)


def profit_factor(pnl: np.ndarray) -> float | None:
    pnl = np.asarray(pnl, float)
    g = pnl[pnl > 0].sum()
    l = -pnl[pnl <= 0].sum()
    return float(g / l) if l > 0 else None


# ---------- CLI ----------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("folds")
    f.add_argument("--parquet", required=True)
    f.add_argument("--train", type=int, default=25)
    f.add_argument("--verify", type=int, default=5)
    f.add_argument("--test", type=int, default=10)
    f.add_argument("--step", type=int, default=None)
    p = sub.add_parser("posterior")
    p.add_argument("--wins", type=int, required=True)
    p.add_argument("--losses", type=int, required=True)
    p.add_argument("--breakeven", type=float, default=None, help="win rate below which the strategy loses")
    b = sub.add_parser("bayes")
    b.add_argument("--wins", type=int, required=True)
    b.add_argument("--n", type=int, required=True)
    b.add_argument("--p0", type=float, required=True, help="reference win rate")
    c = sub.add_parser("chi2")
    for k in ("tp", "fp", "fn", "tn"):
        c.add_argument(f"--{k}", type=int, required=True)
    bs = sub.add_parser("bootstrap", help="CIs for mean P/L and profit factor from a per-trade file")
    bs.add_argument("--file", required=True, help="csv or parquet with a pnl column")
    bs.add_argument("--col", default="pnl")
    bs.add_argument("--where", default=None, help='pandas query to select the trades, e.g. "combo == 3"')
    bs.add_argument("--vs", default=None, help="pandas query for a comparison set; reports PF difference")
    a = ap.parse_args()

    if a.cmd == "folds":
        import pandas as pd

        df = pd.read_parquet(a.parquet, columns=["day", "candidate"])
        days = sorted(df["day"].unique())
        folds = day_folds(days, a.train, a.verify, a.test, a.step)
        print(f"{len(days)} days -> {len(folds)} folds (train {a.train} / verify {a.verify} / test {a.test})")
        cand = df[df["candidate"]]
        for i, (tr, ve, te) in enumerate(folds, 1):
            n = lambda ds: int(cand["day"].isin(ds).sum())  # noqa: E731
            print(
                f"fold {i}: train {tr[0]}..{tr[-1]} ({n(tr)} cand) | verify {ve[0]}..{ve[-1]} ({n(ve)}) | "
                f"test {te[0]}..{te[-1]} ({n(te)})"
            )
    elif a.cmd == "posterior":
        r = beta_posterior(a.wins, a.losses)
        print(
            f"win rate posterior Beta({r['alpha']:.0f},{r['beta']:.0f}): "
            f"mean {r['mean']:.3f} sd {r['sd']:.3f} n={r['n']}"
        )
        if a.breakeven is not None:
            print(f"P(win rate < {a.breakeven}) = {prob_below(a.breakeven, r['alpha'], r['beta']):.3f}")
    elif a.cmd == "bayes":
        r = bayes_factor_binomial(a.wins, a.n, a.p0)
        print(f"ln B = {r['ln_B']:+.3f} (B = {r['B']:.2f}): {r['verdict']}")
    elif a.cmd == "chi2":
        stat, sig = confusion_chi2(a.tp, a.fp, a.fn, a.tn)
        print(f"chi2 = {stat:.2f}; {'beats' if sig else 'does not beat'} white noise at 99% (critical 6.635)")
    elif a.cmd == "bootstrap":
        import pandas as pd

        df = pd.read_parquet(a.file) if a.file.endswith(".parquet") else pd.read_csv(a.file)
        sel = df.query(a.where) if a.where else df
        r = pnl_bootstrap(sel[a.col].to_numpy())
        wins = sel[a.col][sel[a.col] > 0]
        losses = -sel[a.col][sel[a.col] <= 0]
        print(
            f"n={r['n']} mean P/L {r['mean']:+.3f} CI95 [{r['mean_ci95'][0]:+.3f}, {r['mean_ci95'][1]:+.3f}] "
            f"P(mean<=0)={r['p_mean_below_zero']:.3f}"
        )
        pf = "inf" if r["pf"] is None else f"{r['pf']:.2f}"
        print(f"PF {pf} CI95 [{r['pf_ci95'][0]:.2f}, {r['pf_ci95'][1]:.2f}] P(PF<=1)={r['p_pf_below_one']:.3f}")
        if len(wins) and len(losses):
            print(
                f"break-even win rate {breakeven_win_rate(wins.mean(), losses.mean()):.3f} "
                f"(avg win {wins.mean():+.3f}, avg loss {-losses.mean():+.3f})"
            )
        if a.vs:
            other = df.query(a.vs)
            d = pf_difference_bootstrap(sel[a.col].to_numpy(), other[a.col].to_numpy())
            print(
                f"vs: PF {d['pf_a']:.2f} against {d['pf_b']:.2f}; diff CI95 [{d['diff_ci95'][0]:+.2f}, "
                f"{d['diff_ci95'][1]:+.2f}]; P(not better)={d['p_a_not_better']:.3f}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
