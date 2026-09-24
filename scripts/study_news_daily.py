"""News as a daily feature: does Jev's structured reading of headlines tell us anything at horizons of days?

Pre-registered in docs/progress.md (2026-09-23 handoff). Universe: the survivorship-free monthly top 100
by dollar volume (data/daily_panel). Subcommands, each resumable:

    universe   write the monthly universes 2019-01..2026-09 to data/research/news_daily/universes.json
    fetch      Alpaca news for every symbol ever in the universe, by year, into headlines_<year>.parquet
    pairs      headline-symbol pairs to score: symbol in that month's universe, item tags <= 8 symbols
    score      Jev (questions 2026-09-24.1) on the pairs, resumable, with a spend cap
    features   daily per-symbol features (counts, sentiment, events, earnings calendar)
    test       the four pre-registered tests, printed as a report

    uv run --group jev python scripts/study_news_daily.py fetch
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from loguru import logger

OUT = Path("data/research/news_daily")
START, END = date(2019, 1, 1), date(2026, 9, 22)


def universes() -> dict[str, list[str]]:
    return json.loads((OUT / "universes.json").read_text())


# ------------------------------------------------------------------ universe
def cmd_universe(args) -> int:
    from ridethewave.daily.panel_store import load_long, monthly_universes

    long = load_long(5.0, 2e6)
    u = monthly_universes(long, args.rank_hi)
    u = {m: v[args.rank_lo - 1 :] for m, v in u.items()}  # a band of the dollar-volume ranking
    u = {m: v for m, v in u.items() if START.strftime("%Y-%m") <= m <= END.strftime("%Y-%m")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "universes.json").write_text(json.dumps(u))
    names = sorted({s for v in u.values() for s in v})
    logger.info("{} months, {} distinct names", len(u), len(names))
    return 0


# ------------------------------------------------------------------ fetch
def cmd_fetch(args) -> int:
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    from dotenv import load_dotenv

    load_dotenv(".env")
    client = NewsClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
    u = universes()
    for year in range(START.year, END.year + 1):
        path = OUT / f"headlines_{year}.parquet"
        if path.exists() and not args.force:
            continue
        names = sorted({s for m, v in u.items() if m.startswith(str(year)) for s in v})
        seen: dict[str, dict] = {}
        t0 = time.time()
        for i in range(0, len(names), args.batch):
            chunk = names[i : i + args.batch]
            try:
                resp = client.get_news(
                    NewsRequest(
                        symbols=",".join(chunk),
                        start=datetime(year, 1, 1, tzinfo=timezone.utc),
                        end=min(
                            datetime(year + 1, 1, 1, tzinfo=timezone.utc),
                            datetime.combine(END + timedelta(days=1), datetime.min.time(), timezone.utc),
                        ),
                        limit=None,
                        include_content=False,
                        exclude_contentless=False,
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("{} {}: {}", year, chunk[:3], e)
                continue
            items = resp.data["news"] if isinstance(resp.data, dict) else resp.data
            for n in items:
                seen[str(n.id)] = {
                    "id": str(n.id),
                    "created_at": n.created_at,
                    "headline": n.headline,
                    "summary": (n.summary or "")[:600],
                    "source": n.source,
                    "symbols": list(n.symbols),
                }
            logger.info(
                "{}: {}/{} names, {} unique items, {:.0f}s",
                year,
                min(i + args.batch, len(names)),
                len(names),
                len(seen),
                time.time() - t0,
            )
        df = pd.DataFrame(list(seen.values()))
        if len(df):
            df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
            df["n_symbols"] = df["symbols"].apply(len)
        df.to_parquet(path, index=False)
        logger.info("{}: saved {} items", year, len(df))
    return 0


# ------------------------------------------------------------------ pairs
def cmd_pairs(args) -> int:
    u = {m: set(v) for m, v in universes().items()}
    rows = []
    for f in sorted(OUT.glob("headlines_*.parquet")):
        df = pd.read_parquet(f)
        if not len(df):
            continue
        df = df[df["n_symbols"] <= args.max_symbols]
        if args.keywords:
            pat = "|".join(k.strip().lower() for k in args.keywords.split(",") if k.strip())
            text = (df["headline"].fillna("") + " " + df["summary"].fillna("")).str.lower()
            df = df[text.str.contains(pat, regex=True)]
        for r in df.itertuples():
            m = r.created_at.strftime("%Y-%m")
            for s in r.symbols:
                if s in u.get(m, ()):
                    rows.append((f"{r.id}:{s}", r.id, s, r.created_at))
    pairs = pd.DataFrame(rows, columns=["key", "id", "symbol", "created_at"]).drop_duplicates("key")
    pairs.to_parquet(OUT / "pairs.parquet", index=False)
    est = len(pairs) * 1510 / 1e6 * 0.042
    by_year = pairs.groupby(pairs["created_at"].dt.year).size().to_dict()
    logger.info("{:,} pairs ({} per year); estimated Jev cost ${:.2f}", len(pairs), by_year, est)
    return 0


# ------------------------------------------------------------------ score
def cmd_score(args) -> int:
    from dotenv import load_dotenv

    from ridethewave.signals.jev_client import HeadlineJob, score_headlines

    load_dotenv(".env")
    pairs = pd.read_parquet(OUT / "pairs.parquet")
    heads = pd.concat(
        [pd.read_parquet(f) for f in sorted(OUT.glob("headlines_*.parquet"))], ignore_index=True
    ).set_index("id")
    path = OUT / "scores.parquet"
    done = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    done_keys = set(done["key"]) if len(done) else set()
    todo = pairs[~pairs["key"].isin(done_keys)]
    if args.limit:
        todo = todo.head(args.limit)
    spent = done["input_tokens"].fillna(0).sum() / 1e6 * 0.042 if len(done) else 0.0
    logger.info(
        "{:,} pairs; {:,} done (${:.2f}); scoring {:,} now; cap ${:.0f}",
        len(pairs),
        len(done_keys),
        spent,
        len(todo),
        args.cap,
    )
    t0 = time.time()
    for i in range(0, len(todo), args.batch):
        if spent >= args.cap:
            logger.warning("spend cap ${:.0f} reached; stopping (resumable)", args.cap)
            break
        chunk = todo.iloc[i : i + args.batch]
        jobs = []
        for r in chunk.itertuples():
            h = heads.loc[r.id]
            jobs.append(
                HeadlineJob(r.key, r.symbol, h["headline"], h["summary"] or None, h["source"], list(h["symbols"]))
            )
        new = pd.DataFrame(score_headlines(jobs, concurrency=args.concurrency, mock=args.mock))
        done = pd.concat([done, new], ignore_index=True) if len(done) else new
        done.to_parquet(path, index=False)
        spent = done["input_tokens"].fillna(0).sum() / 1e6 * 0.042
        rate = (i + len(chunk)) / max(time.time() - t0, 1)
        logger.info(
            "{:,}/{:,} scored, {} errors in batch, ${:.2f} spent, {:.0f} pairs/s, ETA {:.0f} min",
            i + len(chunk),
            len(todo),
            int(new["error"].notna().sum()),
            spent,
            rate,
            (len(todo) - i - len(chunk)) / rate / 60,
        )
    return 0


# ------------------------------------------------------------------ features
ET_TZ = "America/New_York"


def _trading_days() -> pd.DatetimeIndex:
    from ridethewave.daily.panel_store import PANEL

    df = pd.read_parquet(sorted(PANEL.glob("bars_*.parquet"))[0], columns=["day"])
    days = pd.DatetimeIndex(sorted(pd.to_datetime(df["day"]).unique()))
    return days[(days >= pd.Timestamp(START) - pd.Timedelta(days=200)) & (days <= pd.Timestamp(END))]


def cmd_features(args) -> int:
    """One row per (symbol, trading day) with news on or before it. News after 16:00 ET belongs to the next
    trading day: everything in a row was public before that day's close, and trades happen at the next open."""
    sc = pd.read_parquet(OUT / "scores.parquet")
    sc = sc[sc["error"].isna() & sc["event"].notna()]
    pairs = pd.read_parquet(OUT / "pairs.parquet").set_index("key")
    sc = sc.join(pairs[["created_at"]], on="key")
    et = sc["created_at"].dt.tz_convert(ET_TZ)
    days = _trading_days()
    local_day = pd.to_datetime(et.dt.date)
    after_close = (et.dt.hour >= 16).to_numpy()
    idx = days.searchsorted(local_day.to_numpy(), side="left")
    idx = idx + ((days[idx.clip(max=len(days) - 1)] == local_day.to_numpy()) & after_close)
    sc = sc[idx < len(days)].copy()
    sc["day"] = days[idx[idx < len(days)]]
    rel = (sc["p_relevant"] > 0.5) & (sc["p_stale"] < 0.5)
    sc["rel"] = rel.astype(int)
    tone = sc["p_up"] - sc["p_down"]
    weight = (sc["materiality"] + 0.5) * (sc["p_durable"] + 0.2)
    sc["sent_w"] = (tone * weight).where(rel, 0.0)
    sc["mat_rel"] = sc["materiality"].where(rel, 0.0)
    bad = rel & (
        (sc["p_toxic"] > 0.5)
        | ((sc["kind"] == "legal_regulatory") & (sc["p_down"] > sc["p_up"]))
        | (sc["direction"] == "down")
    )
    sc["neg_legal"] = bad.astype(int)
    earn = sc["event"].isin(["earnings_release", "guidance_change"]) & rel
    sc["earn_up"] = (earn & (sc["p_up"] > sc["p_down"]) & (sc["p_up"] > 0.5)).astype(int)
    sc["earn_down"] = (earn & (sc["p_down"] > sc["p_up"]) & (sc["p_down"] > 0.5)).astype(int)
    sc["earn_release"] = ((sc["event"] == "earnings_release") & rel).astype(int)
    sc["earn_date_notice"] = ((sc["event"] == "earnings_date") & (sc["p_relevant"] > 0.5)).astype(int)
    daily = sc.groupby(["symbol", "day"]).agg(
        n_all=("key", "size"),
        n_rel=("rel", "sum"),
        sent_w=("sent_w", "sum"),
        mat_rel=("mat_rel", "sum"),
        neg_legal=("neg_legal", "sum"),
        earn_up=("earn_up", "sum"),
        earn_down=("earn_down", "sum"),
        earn_release=("earn_release", "sum"),
        earn_date_notice=("earn_date_notice", "sum"),
    )
    # dense grid per symbol so rolling windows count days without news as zeros
    frames = []
    for sym, g in daily.groupby(level="symbol"):
        g = g.droplevel("symbol").reindex(days, fill_value=0)
        f = pd.DataFrame(index=days)
        f["n_rel"] = g["n_rel"]
        f["n5"] = g["n_rel"].rolling(5, min_periods=1).sum()
        base = g["n_rel"].rolling(120, min_periods=40).mean().shift(5) * 5
        f["abn_news"] = (
            (f["n5"] + 1).div(base + 1).apply(lambda x: float("nan") if pd.isna(x) else __import__("math").log(x))
        )
        f["sent"] = g["sent_w"].ewm(halflife=2).mean() * 5  # about a 5-day memory
        f["mat5"] = g["mat_rel"].rolling(5, min_periods=1).sum()
        f["mat21"] = g["mat_rel"].rolling(21, min_periods=1).sum()
        f["neg_legal3"] = g["neg_legal"].rolling(3, min_periods=1).sum()
        f["earn_up1"] = g["earn_up"]
        f["earn_down1"] = g["earn_down"]
        f["earn_release"] = g["earn_release"]
        f["earn_date_notice"] = g["earn_date_notice"]
        f["symbol"] = sym
        frames.append(f.reset_index(names="day"))
    feats = pd.concat(frames, ignore_index=True)
    feats = feats[feats["day"] >= pd.Timestamp(START)]
    feats.to_parquet(OUT / "features.parquet", index=False)
    cal = (
        sc[sc["earn_release"] == 1].groupby("symbol")["day"].apply(lambda d: sorted({x.date().isoformat() for x in d}))
    )
    (OUT / "earnings_calendar.json").write_text(json.dumps(cal.to_dict()))
    per_sym_year = cal.apply(len).mean() / ((END - START).days / 365.25)
    logger.info(
        "features: {:,} symbol-days, {} symbols; earnings calendar: {} symbols, {:.1f} releases per symbol-year",
        len(feats),
        feats["symbol"].nunique(),
        len(cal),
        per_sym_year,
    )
    return 0


# ------------------------------------------------------------------ tests
def _panel():
    from ridethewave.daily.panel_store import load_long

    long = load_long(5.0, 2e6)
    names = sorted({s for v in universes().values() for s in v})
    long = long[long["symbol"].isin(names)]
    close = long.pivot(index="day", columns="symbol", values="close").sort_index()
    open_ = long.pivot(index="day", columns="symbol", values="open").sort_index()
    return long, close, open_


def _in_universe(frame: pd.DataFrame) -> pd.Series:
    u = {m: set(v) for m, v in universes().items()}
    return pd.Series(
        [s in u.get(d.strftime("%Y-%m"), ()) for s, d in zip(frame["symbol"], frame["day"], strict=True)],
        index=frame.index,
    )


def _fmt_t(x: float) -> str:
    return f"{x:+.2f}"


def cmd_test(args) -> int:
    import numpy as np

    feats = pd.read_parquet(OUT / "features.parquet")
    long, close, open_ = _panel()
    rets = close.pct_change()
    # forward windows start at the next open (the first price a decision on day d can trade at)
    nxt_open = open_.shift(-1)
    fwd = {}
    for h in (1, 5, 20):
        fwd[h] = close.shift(-h) / nxt_open - 1
    rv_past = rets.rolling(20).std()
    rv_fut = rets[::-1].rolling(5).std()[::-1].shift(-1)  # std of returns d+1..d+5
    stack = lambda df, name: df.stack().rename(name)  # noqa: E731
    table = pd.concat([stack(rv_past, "rv20"), stack(rv_fut, "rv5f")] + [stack(fwd[h], f"f{h}") for h in fwd], axis=1)
    table.index.names = ["day", "symbol"]
    table = table.reset_index()
    df = table.merge(feats, on=["day", "symbol"], how="left").fillna(
        {c: 0 for c in feats.columns if c not in ("day", "symbol", "abn_news")}
    )
    df = df[(df["day"] >= pd.Timestamp(START)) & (df["day"] <= pd.Timestamp(END))]
    df = df[_in_universe(df)]
    for h in (1, 5, 20):  # excess over the equal-weight universe on the same window
        df[f"x{h}"] = df[f"f{h}"] - df.groupby("day")[f"f{h}"].transform("mean")
    half = pd.Timestamp("2022-11-10")
    lines = [
        "# News as a daily feature: the four pre-registered tests",
        "",
        f"{len(df):,} symbol-days in the universe, {df['day'].min().date()} to {df['day'].max().date()}; {int((df['n_rel'] > 0).sum()):,} with relevant news that day.",  # noqa: E501
        "",
    ]

    # --- test 1: abnormal news volume and future volatility
    t1 = df.dropna(subset=["rv20", "rv5f", "abn_news"]).copy()
    t1 = t1[(t1["rv20"] > 0) & (t1["rv5f"] > 0)]
    t1["y"] = np.log(t1["rv5f"])
    t1["x0"] = np.log(t1["rv20"])
    for c in ("y", "x0", "abn_news"):
        t1[c + "_d"] = t1[c] - t1.groupby("day")[c].transform("mean")  # cross-sectional: which names move more

    def r2(cols, d):
        X = np.column_stack([d[c + "_d"] for c in cols] + [np.ones(len(d))])
        beta, *_ = np.linalg.lstsq(X, d["y_d"], rcond=None)
        res = d["y_d"] - X @ beta
        return 1 - res.var() / d["y_d"].var(), beta

    lines += [
        "## 1. Does abnormal news volume predict next-week volatility beyond past volatility?",
        "",
        "| Sample | R² past vol only | R² with news volume | Relative gain | News coefficient |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, d in (("all", t1), ("first half", t1[t1["day"] < half]), ("second half", t1[t1["day"] >= half])):
        a, _ = r2(["x0"], d)
        b, beta = r2(["x0", "abn_news"], d)
        lines.append(f"| {name} | {a:.3f} | {b:.3f} | {(b - a) / a * 100:+.1f}% | {beta[1]:+.3f} |")
    lines += ["", "Kill criterion: relative gain under 10%.", ""]

    # --- test 2: sentiment quintiles and forward excess return
    lines += ["## 2. Does impact-weighted sentiment predict excess return over the universe?", ""]
    t2 = df[df["sent"].abs() > 1e-9].copy()
    t2["q"] = t2.groupby("day")["sent"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 5, labels=False) + 1 if len(x) >= 10 else np.nan
    )
    t2 = t2.dropna(subset=["q"])
    lines += [
        f"{len(t2):,} symbol-days with non-zero sentiment on days with at least 10 such names.",
        "",
        "| Horizon | Q1 (most negative) bp | Q3 bp | Q5 (most positive) bp | Q5 − Q1 bp | t | 1st half | 2nd half |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for h in (1, 5, 20):
        g = t2.dropna(subset=[f"x{h}"])
        qm = g.groupby("q")[f"x{h}"].mean() * 1e4
        spread = g[g["q"] == 5].groupby("day")[f"x{h}"].mean() - g[g["q"] == 1].groupby("day")[f"x{h}"].mean()
        spread = spread.dropna()
        s_non = spread.iloc[::h]  # non-overlapping windows for the t-statistic
        t = s_non.mean() / s_non.std() * np.sqrt(len(s_non)) if len(s_non) > 2 else float("nan")
        h1 = spread[spread.index < half].mean() * 1e4
        h2 = spread[spread.index >= half].mean() * 1e4
        lines.append(
            f"| {h} d | {qm.get(1, float('nan')):+.1f} | {qm.get(3, float('nan')):+.1f} | {qm.get(5, float('nan')):+.1f} | {spread.mean() * 1e4:+.1f} | {t:+.2f} | {h1:+.1f} | {h2:+.1f} |"  # noqa: E501
        )
    lines += ["", "Kill criterion: no Q5 − Q1 spread with t ≥ 2 and the same sign in both halves.", ""]

    # --- event pockets (descriptive, same machinery)
    lines += [
        "## 2b. Event pockets: mean excess return after the event (bp), with t",
        "",
        "| Event on day d | n | +1 d | +5 d | +20 d | t (+20 d) | 1st half +20 d | 2nd half +20 d |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, mask in (
        ("earnings or guidance, up", df["earn_up1"] > 0),
        ("earnings or guidance, down", df["earn_down1"] > 0),
        ("negative or legal (last 3 d)", df["neg_legal3"] > 0),
        (
            "abnormal news volume (top decile, names with news)",
            (df["n5"] > 0) & (df["abn_news"] >= df.loc[df["n5"] > 0, "abn_news"].quantile(0.9)),
        ),
    ):
        g = df[mask]
        x20 = g["x20"].dropna()
        # cluster by day: one mean per day, then a t over days
        by_day = x20.groupby(g.loc[x20.index, "day"]).mean()
        t = by_day.mean() / by_day.std() * np.sqrt(len(by_day) / 20) if len(by_day) > 2 else float("nan")
        h1 = g[g["day"] < half]["x20"].mean() * 1e4
        h2 = g[g["day"] >= half]["x20"].mean() * 1e4
        lines.append(
            f"| {name} | {len(g):,} | {g['x1'].mean() * 1e4:+.1f} | {g['x5'].mean() * 1e4:+.1f} | {g['x20'].mean() * 1e4:+.1f} | {t:+.2f} | {h1:+.1f} | {h2:+.1f} |"  # noqa: E501
        )
    lines += ["", "The +20 d t-statistic divides by √20 for overlapping windows (a conservative correction).", ""]

    # --- tests 3 and 4: through the daily engine
    lines += _engine_tests(feats, long)
    report = "\n".join(lines)
    (OUT / "report.md").write_text(report)
    print(report)
    return 0


def _engine_tests(feats: pd.DataFrame, long: pd.DataFrame) -> list[str]:
    from ridethewave.config import load_settings
    from ridethewave.daily import build_daily, run_daily
    from ridethewave.daily.data import Panel, load_panel
    from ridethewave.daily.strategies import DailyStrategy, Window
    from ridethewave.storage import Database

    u = universes()
    names = sorted({s for v in u.values() for s in v})
    sub = long[long["symbol"].isin(names)]
    wide = {
        c: sub.pivot(index="day", columns="symbol", values=c).sort_index()
        for c in ("open", "high", "low", "close", "volume")
    }
    db = Database(load_settings().storage.resolved_db_path())
    spy = load_panel(db, ["SPY"], date(2018, 1, 1), END)
    for c in wide:
        wide[c] = wide[c].join(getattr(spy, c)[["SPY"]], how="left")
    panel = Panel(**wide)
    f = feats.set_index(["day", "symbol"])
    neg = {d: set(g.index.get_level_values("symbol")) for d, g in f[f["neg_legal3"] > 0].groupby(level="day")}
    earn = {d: set(g.index.get_level_values("symbol")) for d, g in f[f["earn_up1"] > 0].groupby(level="day")}
    mat21 = f["mat21"]

    def ufn(day):
        return u.get(day.strftime("%Y-%m"), [])

    class Wrapped(DailyStrategy):
        def __init__(self, inner, mode):
            super().__init__({})
            self.inner, self.mode, self.name = inner, mode, f"{inner.name}+{mode}"

        def targets(self, w: Window):
            t = self.inner.targets(w) or {}
            if self.mode == "exclude_negative":
                bad = neg.get(w.today, set())
                t = {s: v for s, v in t.items() if s not in bad}
            elif self.mode == "tilt_earnings_up":
                good = earn.get(w.today, set())
                t = {s: v * (2.0 if s in good else 1.0) for s, v in t.items()}
            tot = sum(abs(v) for v in t.values())
            return {s: v / tot for s, v in t.items()} if tot > 0 else {}

    class EarningsDrift(DailyStrategy):
        """The universe equal-weight, with names that had an 'earnings or guidance up' event in the last 20 trading
        days held at 5x the base weight. Fully invested, so the excess over the universe is the event's."""

        name = "earnings_drift"

        def __init__(self):
            super().__init__({})
            self.held: dict[str, int] = {}

        def targets(self, w: Window):
            for s in list(self.held):
                self.held[s] += 1
                if self.held[s] >= 20:
                    self.held.pop(s)
            for s in earn.get(w.today, set()):
                if s in w.symbols:
                    self.held[s] = 0
            names_ = [s for s in w.symbols if s in w.close.columns]
            raw = {s: (5.0 if s in self.held else 1.0) for s in names_}
            tot = sum(raw.values())
            return {s: v / tot for s, v in raw.items()} if tot else {}

    class NewsUniverse(DailyStrategy):
        """Equal weight in the half of the universe with the most material news over the last month (or the least)."""

        def __init__(self, most: bool):
            super().__init__({})
            self.most, self.name = most, "news_top_half" if most else "news_bottom_half"

        def targets(self, w: Window):
            if w.today not in mat21.index.get_level_values("day"):
                return {}
            m = mat21.xs(w.today, level="day").reindex(w.symbols).fillna(0)
            ranked = m.sort_values(ascending=not self.most).index.tolist()
            pick = ranked[: len(ranked) // 2]
            return {s: 1.0 / len(pick) for s in pick} if pick else {}

    runs = [
        ("momentum (baseline)", build_daily("price_momentum")),
        ("momentum, exclude fresh negative/legal", Wrapped(build_daily("price_momentum"), "exclude_negative")),
        ("momentum, tilt earnings-up 2x", Wrapped(build_daily("price_momentum"), "tilt_earnings_up")),
        ("universe with earnings-up names 5x for 20 d", EarningsDrift()),
        ("most-newsworthy half of the universe", NewsUniverse(True)),
        ("least-newsworthy half of the universe", NewsUniverse(False)),
    ]
    out = [
        "## 3 and 4. Through the daily engine (2019 to 2026, next-open fills, 5 bp a side)",
        "",
        "| Portfolio | CAGR | Sharpe | Max DD | IR vs universe (t) | Excess vs universe by half |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for label, strat in runs:
        res = run_daily(strat, panel, START, END, universe_fn=ufn, capital=100_000)
        m = res.metrics
        out.append(
            f"| {label} | {m['cagr']:+.1%} | {m['sharpe']:.2f} | {m['max_dd']:+.1%} | "
            f"{m['ir_vs_equal_weight']:+.2f} ({m['ir_t_vs_equal_weight']:+.1f}) | "
            f"{m['h1_excess_cagr_vs_equal_weight']:+.1%} / {m['h2_excess_cagr_vs_equal_weight']:+.1%} |"
        )
        logger.info("{}: CAGR {:+.1%} IR vs EW {:+.2f}", label, m["cagr"], m["ir_vs_equal_weight"])
    ew = run_daily(NewsUniverse(True), panel, START, END, universe_fn=ufn).metrics
    out += [
        "",
        f"Equal-weight universe over the same period: CAGR {ew['equal_weight_cagr']:+.1%}, Sharpe {ew['equal_weight_sharpe']:.2f}.",  # noqa: E501
        "Kill criteria: test 3 needs an IR improvement of at least 0.2 over the momentum baseline; test 4 needs the",
        "most-newsworthy half to beat the universe with the same sign in both halves.",
    ]
    db.close()
    return out


# ------------------------------------------------------------------ post-earnings drift
def cmd_pead(args) -> int:
    """Post-earnings-announcement drift: after a Jev-identified earnings release, does the stock keep moving
    in the direction of its announcement-day reaction? Excess over the universe band, from the next open."""
    import numpy as np

    sc = pd.read_parquet(OUT / "scores.parquet")
    sc = sc[sc["error"].isna() & (sc["event"] == "earnings_release") & (sc["p_relevant"] > 0.5) & (sc["p_stale"] < 0.5)]
    pairs = pd.read_parquet(OUT / "pairs.parquet").set_index("key")
    sc = sc.join(pairs[["created_at"]], on="key")
    days = _trading_days()
    et = sc["created_at"].dt.tz_convert(ET_TZ)
    local = pd.to_datetime(et.dt.date)
    after = (et.dt.hour >= 16).to_numpy()
    idx = days.searchsorted(local.to_numpy(), side="left")
    idx = idx + ((days[idx.clip(max=len(days) - 1)] == local.to_numpy()) & after)
    sc = sc[idx < len(days)].copy()
    sc["day"] = days[idx[idx < len(days)]]  # the reaction day: the first session that can trade on the release
    ev = (
        sc.sort_values("day")
        .groupby(["symbol", "day"])
        .agg(p_down=("p_down", "mean"), p_up=("p_up", "mean"))
        .reset_index()
    )
    ev["gap"] = ev.groupby("symbol")["day"].diff().dt.days
    ev = ev[(ev["gap"].isna()) | (ev["gap"] > 10)]  # one event per report
    long, close, open_ = _panel()
    nxt = open_.shift(-1)
    r0 = close.pct_change()  # the reaction-day return
    fwd = {h: (close.shift(-h) / nxt - 1) for h in (1, 5, 20, 40)}
    tab = pd.concat([r0.stack().rename("r0")] + [fwd[h].stack().rename(f"f{h}") for h in fwd], axis=1)
    tab.index.names = ["day", "symbol"]
    tab = tab.reset_index()
    tab = tab[_in_universe(tab)]
    for h in fwd:
        tab[f"x{h}"] = tab[f"f{h}"] - tab.groupby("day")[f"f{h}"].transform("mean")
    df = ev.merge(tab, on=["day", "symbol"], how="inner").dropna(subset=["r0", "x20"])
    half = df["day"].quantile(0.5)
    lines = [
        "# Post-earnings-announcement drift, from Jev-identified releases",
        "",
        f"{len(df):,} earnings events on {df['symbol'].nunique()} symbols, {df['day'].min().date()} to {df['day'].max().date()} "  # noqa: E501
        f"(universe ranks {args.rank_lo} to {args.rank_hi} by dollar volume, point-in-time). Excess return over the universe "  # noqa: E501
        "from the next open; t uses day clusters and divides by the square root of the horizon in days.",
        "",
        "| Reaction-day return | n | +1 d bp | +5 d bp | +20 d bp | +40 d bp | t (+20 d) | halves +20 d | share negative +20 d |",  # noqa: E501
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    edges = [(-1, -0.08), (-0.08, -0.04), (-0.04, -0.01), (-0.01, 0.01), (0.01, 0.04), (0.04, 0.08), (0.08, 9)]

    def row(name, g):
        if len(g) < 25:
            return None
        by_day = g.groupby("day")["x20"].mean()
        t = by_day.mean() / by_day.std() * np.sqrt(len(by_day) / 20) if len(by_day) > 2 else float("nan")
        h1, h2 = g[g["day"] < half]["x20"].mean() * 1e4, g[g["day"] >= half]["x20"].mean() * 1e4
        return (
            f"| {name} | {len(g):,} | {g['x1'].mean() * 1e4:+.0f} | {g['x5'].mean() * 1e4:+.0f} | {g['x20'].mean() * 1e4:+.0f} | "  # noqa: E501
            f"{g['x40'].mean() * 1e4:+.0f} | {t:+.1f} | {h1:+.0f} / {h2:+.0f} | {(g['x20'] < 0).mean() * 100:.0f}% |"
        )

    for lo, hi in edges:
        r = row(
            f"{lo * 100:+.0f}% to {hi * 100:+.0f}%" if hi < 9 else f"> {lo * 100:+.0f}%",
            df[(df["r0"] > lo) & (df["r0"] <= hi)],
        )
        if r:
            lines.append(r)
    lines += [
        "",
        "By Jev's reading of the release (independent of the price reaction):",
        "",
        "| Jev direction | n | +5 d bp | +20 d bp | +40 d bp | t (+20 d) | halves +20 d |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, g in (
        ("down (p_down > 0.6)", df[df["p_down"] > 0.6]),
        ("up (p_up > 0.6)", df[df["p_up"] > 0.6]),
        ("down and reaction < -4%", df[(df["p_down"] > 0.6) & (df["r0"] < -0.04)]),
        ("up and reaction > +4%", df[(df["p_up"] > 0.6) & (df["r0"] > 0.04)]),
    ):
        r = row(name, g)
        if r:
            lines.append("| " + " | ".join(r.split(" | ")[i] for i in (0, 1, 3, 4, 5, 6, 7)) + " |")
    report = "\n".join(lines)
    (OUT / "pead_report.md").write_text(report)
    df.to_parquet(OUT / "pead_events.parquet", index=False)
    print(report)
    return 0


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("universe")
    p.add_argument("--rank-lo", type=int, default=1)
    p.add_argument("--rank-hi", type=int, default=100)
    p = sub.add_parser("fetch")
    p.add_argument("--batch", type=int, default=25)
    p.add_argument("--force", action="store_true")  # noqa: E702
    p = sub.add_parser("pairs")
    p.add_argument("--max-symbols", type=int, default=8)
    p.add_argument("--keywords", default=None, help="only headlines/summaries containing one of these (comma-separated)")  # noqa: E501
    p = sub.add_parser("score")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--batch", type=int, default=2000)
    p.add_argument("--concurrency", type=int, default=32)
    p.add_argument("--cap", type=float, default=60.0, help="stop when estimated spend reaches this many dollars")
    p.add_argument("--mock", action="store_true")
    sub.add_parser("features")
    sub.add_parser("test")
    p = sub.add_parser("pead")
    p.add_argument("--rank-lo", type=int, default=1)
    p.add_argument("--rank-hi", type=int, default=100)
    ap.add_argument("--out", default=str(OUT), help="working directory for this study")
    args = ap.parse_args()
    OUT = Path(args.out)
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    return {
        "universe": cmd_universe,
        "fetch": cmd_fetch,
        "pairs": cmd_pairs,
        "score": cmd_score,
        "features": cmd_features,
        "test": cmd_test,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
