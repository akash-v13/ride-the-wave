"""Options backtester: past chains rebuilt from daily option bars, replayed through the live OptionsSlot.

The chain on day d holds every contract on a monthly expiry that traded that day, priced from its daily
close with a synthetic spread (half-spread = max($0.01, spread_pct/2 x price)); implied volatility is
solved from the close. Open legs are marked from their latest close (up to 5 sessions stale); on and
after expiry a leg is worth its intrinsic value. The slot itself (sizing, fills paying spread_fraction of
the half-spread, exits, cash) is the production code in ridethewave.options.slot, run with no database.

Limitations, stated so results are read correctly: closes are last trades, not quotes; only monthly
expiries; no early assignment; no dividends on stock legs; history from February 2024.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from ridethewave.config import OptionsSpec
from ridethewave.options.chain import ChainSnapshot, OptionContract, parse_occ
from ridethewave.options.greeks import implied_vol
from ridethewave.options.slot import OptionsSlot

HISTORY = Path("data/options_history")


class HistoricalChains:
    def __init__(
        self, underlying: str, bars: pd.DataFrame, spot: pd.Series, spread_pct: float = 0.03, rate: float = 0.045
    ):
        """``bars``: symbol, day, close, volume for every contract; ``spot``: raw underlying closes by day."""
        self.underlying = underlying
        self.spot = spot.sort_index()
        self.spread_pct = spread_pct
        self.rate = rate
        b = bars.copy()
        b["day"] = pd.to_datetime(b["day"])
        meta = {s: parse_occ(s) for s in b["symbol"].unique()}
        b["expiry"] = b["symbol"].map(lambda s: meta[s][1])
        b["right"] = b["symbol"].map(lambda s: meta[s][2])
        b["strike"] = b["symbol"].map(lambda s: meta[s][3])
        self.by_day = {d: g for d, g in b.groupby("day")}
        self.close = b.pivot_table(index="day", columns="symbol", values="close").sort_index()
        self.meta = meta

    @classmethod
    def load(cls, underlying: str, directory: Path = HISTORY, **kw) -> HistoricalChains:
        files = sorted(
            p for p in directory.glob(f"{underlying}_*.parquet") if not p.name.endswith("_underlying.parquet")
        )
        bars = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
        spot = pd.read_parquet(directory / f"{underlying}_underlying.parquet")["close"]
        return cls(underlying, bars, spot, **kw)

    def half_spread(self, price: float) -> float:
        return max(0.01, self.spread_pct / 2 * price)

    def snapshot(self, day: date, dte_min: int, dte_max: int, band: float = 0.15) -> ChainSnapshot:
        ts = pd.Timestamp(day)
        spot = float(self.spot.loc[ts])
        g = self.by_day.get(ts)
        contracts: list[OptionContract] = []
        if g is not None:
            dte = (pd.to_datetime(g["expiry"]) - ts).dt.days
            keep = g[
                (dte >= dte_min) & (dte <= dte_max) & (g["strike"].sub(spot).abs() <= band * spot) & (g["close"] > 0)
            ]
            for r in keep.itertuples():
                hs = self.half_spread(r.close)
                t = max((r.expiry - day).days, 1) / 365.0
                iv = implied_vol(r.close, spot, r.strike, t, r.right == "C", self.rate)
                contracts.append(
                    OptionContract(
                        r.symbol,
                        self.underlying,
                        r.expiry,
                        r.right,
                        r.strike,
                        max(r.close - hs, 0.01),
                        r.close + hs,
                        None,
                        iv,
                    )
                )
        return ChainSnapshot(self.underlying, spot, datetime.combine(day, datetime.min.time(), timezone.utc), contracts)

    def quotes(self, symbols: list[str], day: date) -> dict[str, tuple[float, float]]:
        """Bid/ask per contract on ``day``: from its close (ffill up to 5 sessions), intrinsic at or after expiry."""
        ts = pd.Timestamp(day)
        spot = float(self.spot.loc[ts])
        out: dict[str, tuple[float, float]] = {}
        hist = self.close.loc[:ts].tail(6)
        for s in symbols:
            _, expiry, right, strike = self.meta.get(s) or parse_occ(s)
            if day >= expiry:
                intr = max(spot - strike, 0.0) if right == "C" else max(strike - spot, 0.0)
                out[s] = (intr, intr) if intr > 0 else (0.0, 0.0)
                continue
            if s in hist.columns:
                col = hist[s].dropna()
                if len(col):
                    px = float(col.iloc[-1])
                    hs = self.half_spread(px)
                    out[s] = (max(px - hs, 0.005), px + hs)
        return out


@dataclass
class OptionsBacktestResult:
    spec: OptionsSpec
    equity: pd.Series
    trades: list
    notes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _realized_vol(spot: pd.Series, ts: pd.Timestamp, days: int = 20) -> float | None:
    s = spot.loc[:ts].tail(days + 1)
    if len(s) < days + 1:
        return None
    r = (s / s.shift(1)).dropna().map(math.log)
    return float(r.std() * math.sqrt(252))


def run_options_backtest(
    spec: OptionsSpec, chains: HistoricalChains, start: date, end: date, capital: float = 100_000.0
) -> OptionsBacktestResult:
    slot = OptionsSlot(spec, None, "backtest", capital)
    days = [d for d in chains.spot.index if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
    equity = []
    notes: list[str] = []
    for ts in days:
        day = ts.date()
        spot = float(chains.spot.loc[ts])
        occ = sorted({sym for st in slot.open for sym in st.option_symbols})
        quotes = chains.quotes(occ, day)
        stock = {chains.underlying: spot}
        rv = _realized_vol(chains.spot, ts) if spec.entry_gate == "vrp" else None
        now = datetime.combine(day, datetime.min.time(), timezone.utc).replace(hour=19, minute=40)
        # stale-quote guard: legs with no quote keep the last mark inside the slot
        slot.decide(day, now, spot, quotes, stock, lambda lo, hi, _d=day: chains.snapshot(_d, lo, hi), realized_vol=rv)
        if slot.last_note and not slot.last_note.startswith("no entry: vrp gate closed"):
            notes.append(f"{day} {slot.last_note[:160]}")
        equity.append((ts, slot.equity()))
    eq = pd.Series([e for _, e in equity], index=pd.DatetimeIndex([d for d, _ in equity]))
    res = OptionsBacktestResult(spec, eq, list(slot.trades_today), notes)
    res.metrics = _metrics(res, chains)
    return res


def _metrics(res: OptionsBacktestResult, chains: HistoricalChains) -> dict:
    eq = res.equity
    rets = eq.pct_change().dropna()
    years = len(eq) / 252
    m = {
        "days": len(eq),
        "total_return": float(eq.iloc[-1] / eq.iloc[0] - 1),
        "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else -1.0,
        "vol": float(rets.std() * math.sqrt(252)) if len(rets) > 1 else 0.0,
        "sharpe": float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0,
        "max_dd": float((eq / eq.cummax() - 1).min()),
        "worst_day": float(rets.min()) if len(rets) else 0.0,
    }
    pnl = [t.pnl for t in res.trades]
    wins, losses = [p for p in pnl if p > 0], [p for p in pnl if p < 0]
    m["trades"] = len(pnl)
    m["win_rate"] = len(wins) / len(pnl) if pnl else 0.0
    m["profit_factor"] = sum(wins) / -sum(losses) if losses else (math.inf if wins else 0.0)
    m["avg_win"] = sum(wins) / len(wins) if wins else 0.0
    m["avg_loss"] = sum(losses) / len(losses) if losses else 0.0
    m["exits"] = pd.Series([t.exit_reason for t in res.trades]).value_counts().to_dict() if res.trades else {}
    spot = chains.spot.loc[eq.index]
    m["underlying_return"] = float(spot.iloc[-1] / spot.iloc[0] - 1)
    ur = spot.pct_change().dropna()
    m["underlying_sharpe"] = float(ur.mean() / ur.std() * math.sqrt(252))
    m["underlying_max_dd"] = float((spot / spot.cummax() - 1).min())
    m["corr_to_underlying"] = float(rets.corr(ur.reindex(rets.index))) if len(rets) > 2 else 0.0
    half = eq.index[len(eq) // 2]
    for name, part in (("h1", eq[eq.index < half]), ("h2", eq[eq.index >= half])):
        m[f"{name}_return"] = float(part.iloc[-1] / part.iloc[0] - 1) if len(part) > 1 else 0.0
    return m
