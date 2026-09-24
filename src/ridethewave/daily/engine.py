"""Replay daily-bar portfolio strategies: targets on the close, fills at the next open plus slippage.

Long and short. Equity is marked at each close. A position closes (or flips) as a round trip so
profit factor and hit rate can be reported alongside the equity-curve statistics. Every run also
carries the benchmark's buy-and-hold curve and the equal-weight universe curve, so a result is always
read against what doing nothing clever would have earned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from ridethewave.daily.data import Panel
from ridethewave.daily.strategies import DailyStrategy, Window

TRADING_DAYS = 252


@dataclass
class DailyResult:
    strategy: str
    params: dict
    start: date
    end: date
    universe: list[str]
    equity: pd.Series
    benchmark: pd.Series | None
    equal_weight: pd.Series | None
    weights: pd.DataFrame  # target weights by rebalance date
    trades: list[dict]  # closed round trips
    fills: list[dict]
    metrics: dict = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


class _Book:
    def __init__(self, cash: float):
        self.cash = cash
        self.qty: dict[str, float] = {}
        self.avg: dict[str, float] = {}
        self.entry_day: dict[str, pd.Timestamp] = {}
        self.fills: list[dict] = []
        self.trades: list[dict] = []

    def equity(self, prices: pd.Series) -> float:
        return self.cash + sum(q * float(prices.get(s, np.nan)) for s, q in self.qty.items() if q)

    def execute(self, symbol: str, delta: float, price: float, day: pd.Timestamp) -> None:
        if delta == 0 or not price or price <= 0 or math.isnan(price):
            return
        old = self.qty.get(symbol, 0.0)
        new = old + delta
        self.cash -= delta * price
        self.fills.append({"day": day, "symbol": symbol, "qty": delta, "price": price})
        if old != 0 and (new == 0 or (old > 0) != (new > 0)):
            pnl = old * (price - self.avg.get(symbol, price))
            self.trades.append(
                {
                    "symbol": symbol,
                    "side": "long" if old > 0 else "short",
                    "entry_day": self.entry_day.get(symbol, day),
                    "exit_day": day,
                    "qty": old,
                    "entry_price": self.avg.get(symbol, price),
                    "exit_price": price,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round((price / self.avg[symbol] - 1) * (100 if old > 0 else -100), 3)
                    if self.avg.get(symbol)
                    else 0.0,
                    "held_days": int((day - self.entry_day.get(symbol, day)).days),
                }
            )
        if new != 0:
            if old == 0 or (old > 0) != (new > 0):
                self.avg[symbol] = price
                self.entry_day[symbol] = day
            elif abs(new) > abs(old):
                self.avg[symbol] = (self.avg.get(symbol, price) * abs(old) + price * abs(delta)) / abs(new)
            self.qty[symbol] = new
        else:
            self.qty.pop(symbol, None)
            self.avg.pop(symbol, None)
            self.entry_day.pop(symbol, None)


def run_daily(
    strategy: DailyStrategy,
    panel: Panel,
    start: date,
    end: date,
    universe: list[str] | None = None,
    universe_fn=None,
    capital: float = 100_000.0,
    slippage_bps: float = 5.0,
    rebalance_days: int = 1,
    benchmark: str = "SPY",
    max_gross: float = 1.0,
) -> DailyResult:
    """Replay ``strategy`` from ``start`` to ``end``. ``panel`` should begin earlier than ``start`` by at
    least the strategy's warm-up. ``universe_fn(day) -> list[str]`` overrides ``universe`` per day."""
    universe = [s for s in (universe or panel.symbols) if s in panel.close.columns]
    dates = panel.dates
    s_ts, e_ts = pd.Timestamp(start), pd.Timestamp(end)
    active = [d for d in dates if s_ts <= d <= e_ts]
    if len(active) < 3:
        raise ValueError("fewer than three sessions in range")
    slip = slippage_bps / 10_000.0
    book = _Book(capital)
    closes_ffill = panel.close.ffill()
    pending: dict[str, float] | None = None
    equity_pts: list[tuple[pd.Timestamp, float]] = []
    weight_rows: dict[pd.Timestamp, dict[str, float]] = {}
    logs: list[str] = []
    seen_syms: set[str] = set(universe)
    since_rebalance = rebalance_days  # rebalance on the first active day

    for day in active:
        i = dates.get_loc(day)
        # 1. yesterday's targets fill at today's open
        if pending is not None:
            opens = panel.open.loc[day]
            marks = closes_ffill.loc[day]
            eq_open = book.cash + sum(
                q * float(opens.get(s)) if not math.isnan(opens.get(s, np.nan)) else q * float(marks.get(s, np.nan))
                for s, q in book.qty.items()
                if q
            )
            for sym in sorted(set(pending) | set(book.qty)):
                px = float(opens.get(sym, np.nan))
                if math.isnan(px) or px <= 0:
                    continue
                w = pending.get(sym, 0.0)
                target_qty = int(eq_open * w / px)  # truncates toward zero for both signs
                delta = target_qty - book.qty.get(sym, 0.0)
                if delta:
                    book.execute(sym, delta, px * (1 + slip * (1 if delta > 0 else -1)), day)
            pending = None
        # 2. mark at the close
        eq = book.equity(closes_ffill.loc[day])
        equity_pts.append((day, eq))
        # 3. new targets on the close (not on the final day: nothing could fill)
        since_rebalance += 1
        if since_rebalance >= rebalance_days and day != active[-1]:
            since_rebalance = 0
            todays = universe_fn(day.date()) if universe_fn else universe
            todays = [s for s in todays if s in panel.close.columns]
            seen_syms.update(todays)
            w = Window(
                close=panel.close.iloc[: i + 1],
                open=panel.open.iloc[: i + 1],
                high=panel.high.iloc[: i + 1],
                low=panel.low.iloc[: i + 1],
                volume=panel.volume.iloc[: i + 1],
                today=day,
                symbols=todays,
                benchmark=benchmark,
                held={s: q for s, q in book.qty.items() if q},
                log=logs.append,
            )
            try:
                targets = strategy.targets(w) or {}
            except Exception as e:  # noqa: BLE001
                logs.append(f"{day.date()} strategy raised: {e}")
                targets = {}
            gross = sum(abs(v) for v in targets.values())
            if gross > max_gross and gross > 0:
                targets = {s: v * max_gross / gross for s, v in targets.items()}
            weight_rows[day] = targets
            pending = targets

    equity = pd.Series([e for _, e in equity_pts], index=pd.DatetimeIndex([d for d, _ in equity_pts]), name="equity")
    bench = None
    if benchmark in panel.close.columns:
        b = closes_ffill.loc[equity.index, benchmark]
        bench = (b / b.iloc[0] * capital).rename(benchmark)
    ew = None
    cols = [s for s in seen_syms if s in panel.close.columns]
    if cols:
        rets = closes_ffill.loc[equity.index, cols].pct_change().mean(axis=1).fillna(0.0)
        ew = ((1 + rets).cumprod() * capital).rename("equal_weight")
    reb_days = sorted(weight_rows)
    weights = pd.DataFrame([weight_rows[d] for d in reb_days], index=pd.DatetimeIndex(reb_days)).fillna(0.0)
    if weights.empty:
        weights = pd.DataFrame(index=pd.DatetimeIndex(reb_days))
    res = DailyResult(
        strategy=strategy.name,
        params=strategy.params_dict(),
        start=start,
        end=end,
        universe=sorted(seen_syms),
        equity=equity,
        benchmark=bench,
        equal_weight=ew,
        weights=weights,
        trades=book.trades,
        fills=book.fills,
        logs=logs[-200:],
    )
    res.metrics = compute_metrics(res)
    return res


# ---------------------------------------------------------------- metrics
def _curve_stats(eq: pd.Series) -> dict:
    rets = eq.pct_change().dropna()
    years = len(eq) / TRADING_DAYS
    total = float(eq.iloc[-1] / eq.iloc[0] - 1) if len(eq) > 1 and eq.iloc[0] > 0 else 0.0
    cagr = (
        float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1)
        if years > 0 and eq.iloc[0] > 0 and eq.iloc[-1] > 0
        else -1.0
    )
    vol = float(rets.std() * math.sqrt(TRADING_DAYS)) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / rets.std() * math.sqrt(TRADING_DAYS)) if len(rets) > 1 and rets.std() > 0 else 0.0
    dd = float((eq / eq.cummax() - 1).min()) if len(eq) else 0.0
    return {"total_return": total, "cagr": cagr, "vol": vol, "sharpe": sharpe, "max_dd": dd}


def _ir(eq: pd.Series, bench: pd.Series) -> tuple[float, float]:
    ex = (eq.pct_change() - bench.pct_change()).dropna()
    if len(ex) < 3 or ex.std() == 0:
        return 0.0, 0.0
    ir = float(ex.mean() / ex.std() * math.sqrt(TRADING_DAYS))
    t = float(ex.mean() / ex.std() * math.sqrt(len(ex)))
    return ir, t


def compute_metrics(res: DailyResult) -> dict:
    eq = res.equity
    m: dict = {"days": len(eq), "years": round(len(eq) / TRADING_DAYS, 2)}
    m.update(_curve_stats(eq))
    wins = [t for t in res.trades if t["pnl"] > 0]
    losses = [t for t in res.trades if t["pnl"] < 0]
    gp, gl = sum(t["pnl"] for t in wins), -sum(t["pnl"] for t in losses)
    m["trades"] = len(res.trades)
    m["win_rate"] = len(wins) / len(res.trades) if res.trades else 0.0
    m["profit_factor"] = gp / gl if gl > 0 else (math.inf if gp > 0 else 0.0)
    m["avg_trade_pct"] = float(np.mean([t["pnl_pct"] for t in res.trades])) if res.trades else 0.0
    m["avg_held_days"] = float(np.mean([t["held_days"] for t in res.trades])) if res.trades else 0.0
    if len(res.weights):
        gross = res.weights.abs().sum(axis=1)
        m["avg_gross"] = float(gross.mean())
        m["avg_net"] = float(res.weights.sum(axis=1).mean())
        m["turnover"] = float(res.weights.diff().abs().sum(axis=1).mean())  # per rebalance, one-way
    half = eq.index[len(eq) // 2]
    for name, curve in (("benchmark", res.benchmark), ("equal_weight", res.equal_weight)):
        if curve is None:
            continue
        cs = _curve_stats(curve)
        m[f"{name}_total_return"], m[f"{name}_cagr"], m[f"{name}_sharpe"], m[f"{name}_max_dd"] = (
            cs["total_return"],
            cs["cagr"],
            cs["sharpe"],
            cs["max_dd"],
        )
        ir, t = _ir(eq, curve)
        m[f"ir_vs_{name}"], m[f"ir_t_vs_{name}"] = ir, t
        h1 = _curve_stats(eq[eq.index < half]), _curve_stats(curve[curve.index < half])
        h2 = _curve_stats(eq[eq.index >= half]), _curve_stats(curve[curve.index >= half])
        m[f"h1_excess_cagr_vs_{name}"] = h1[0]["cagr"] - h1[1]["cagr"]
        m[f"h2_excess_cagr_vs_{name}"] = h2[0]["cagr"] - h2[1]["cagr"]
    m["h1_cagr"], m["h2_cagr"] = _curve_stats(eq[eq.index < half])["cagr"], _curve_stats(eq[eq.index >= half])["cagr"]
    m["h1_sharpe"], m["h2_sharpe"] = (
        _curve_stats(eq[eq.index < half])["sharpe"],
        _curve_stats(eq[eq.index >= half])["sharpe"],
    )
    return m


def format_report(res: DailyResult, last_trades: int = 10) -> str:
    m = res.metrics

    def pct(x: float) -> str:
        return f"{x * 100:+.1f}%"

    lines = [
        f"=== {res.strategy} {res.params} ===",
        f"{res.start} to {res.end}  {m['days']} sessions ({m['years']} y)  universe {len(res.universe)}",
        f"return {pct(m['total_return'])}  CAGR {pct(m['cagr'])}  vol {pct(m['vol'])}  "
        f"Sharpe {m['sharpe']:.2f}  max DD {pct(m['max_dd'])}",
        f"trades {m['trades']}  win {m['win_rate'] * 100:.0f}%  PF {m['profit_factor']:.2f}  "
        f"avg trade {m['avg_trade_pct']:+.2f}%  held {m['avg_held_days']:.0f} d  gross {m.get('avg_gross', 0):.2f}  "
        f"net {m.get('avg_net', 0):.2f}  turnover {m.get('turnover', 0):.3f}/rebalance",
        f"halves: CAGR {pct(m['h1_cagr'])} / {pct(m['h2_cagr'])}, Sharpe {m['h1_sharpe']:.2f} / {m['h2_sharpe']:.2f}",
    ]
    for name in ("benchmark", "equal_weight"):
        if f"{name}_cagr" not in m:
            continue
        lines.append(
            f"vs {name}: its CAGR {pct(m[f'{name}_cagr'])} Sharpe {m[f'{name}_sharpe']:.2f} "
            f"DD {pct(m[f'{name}_max_dd'])}; IR {m[f'ir_vs_{name}']:+.2f} (t {m[f'ir_t_vs_{name}']:+.2f}); "
            f"excess CAGR by half {pct(m[f'h1_excess_cagr_vs_{name}'])} / {pct(m[f'h2_excess_cagr_vs_{name}'])}"
        )
    if res.trades:
        lines.append("last trades:")
        for t in res.trades[-last_trades:]:
            lines.append(
                f"  {t['symbol']:6s} {t['side']:5s} {str(t['entry_day'].date()):10s} -> "
                f"{str(t['exit_day'].date()):10s} {t['entry_price']:9.2f} -> {t['exit_price']:9.2f}  "
                f"{t['pnl']:+9.2f} ({t['pnl_pct']:+.2f}%)  {t['held_days']} d"
            )
    return "\n".join(lines)
