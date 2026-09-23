"""Does Jev's reading of a headline predict the stock's forward return? Gate 1 for the news filter.

    uv run python scripts/study_news_jev.py fetch   --start 2026-06-01 --end 2026-09-16
    uv run python scripts/study_news_jev.py score   [--limit N] [--mock]      # resumable; skips scored keys
    uv run python scripts/study_news_jev.py analyze --start 2026-06-01 --end 2026-09-16

Files under data/research/news/: headlines.parquet, scores.parquet, labelled.parquet.
Symbols = every symbol with cached SIP bars in the range (the point-in-time universes), plus SPY.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from loguru import logger

from ridethewave.config import load_settings

ET = ZoneInfo("America/New_York")
OUT = Path("data/research/news")


def universe_symbols(db_path: Path, start: date, end: date) -> list[str]:
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT DISTINCT symbol FROM bars WHERE feed='sip' AND ts>=? AND ts<? ",
        (str(start), str(end + timedelta(days=1))),
    ).fetchall()
    con.close()
    return sorted({r[0] for r in rows} - {"SPY"})


# ------------------------------------------------------------------ fetch
def cmd_fetch(args) -> int:
    import os

    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    from dotenv import load_dotenv

    load_dotenv(".env")
    settings = load_settings()
    syms = universe_symbols(settings.storage.resolved_db_path(), args.start, args.end)
    logger.info("fetching news for {} symbols, {}..{}", len(syms), args.start, args.end)
    client = NewsClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
    seen: dict[str, dict] = {}
    t0 = time.time()
    for i, sym in enumerate(syms, 1):
        try:
            resp = client.get_news(
                NewsRequest(
                    symbols=sym,
                    start=datetime.combine(args.start, datetime.min.time(), timezone.utc),
                    end=datetime.combine(args.end + timedelta(days=1), datetime.min.time(), timezone.utc),
                    limit=5000,
                    exclude_contentless=False,
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("{}: {}", sym, e)
            continue
        items = resp.data["news"] if isinstance(resp.data, dict) else resp.data
        for n in items:
            seen[str(n.id)] = {
                "id": str(n.id),
                "created_at": n.created_at,
                "headline": n.headline,
                "summary": n.summary or "",
                "source": n.source,
                "symbols": list(n.symbols),
            }
        if i % 10 == 0:
            logger.info("{}/{} symbols, {} unique items, {:.0f}s", i, len(syms), len(seen), time.time() - t0)
    df = pd.DataFrame(list(seen.values()))
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["n_symbols"] = df["symbols"].apply(len)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "headlines.parquet", index=False)
    logger.info(
        "saved {} headlines ({} with >8 symbols) to {}",
        len(df),
        int((df.n_symbols > 8).sum()),
        OUT / "headlines.parquet",
    )
    return 0


# ------------------------------------------------------------------ score
def cmd_score(args) -> int:
    from dotenv import load_dotenv

    from ridethewave.signals.jev_client import HeadlineJob, score_headlines

    load_dotenv(".env")
    settings = load_settings()
    heads = pd.read_parquet(OUT / "headlines.parquet")
    syms = set(universe_symbols(settings.storage.resolved_db_path(), args.start, args.end))
    jobs = []
    for r in heads.itertuples():
        for s in r.symbols:
            if s in syms:
                jobs.append(
                    HeadlineJob(
                        key=f"{r.id}:{s}",
                        symbol=s,
                        headline=r.headline,
                        summary=r.summary or None,
                        source=r.source,
                        symbols=list(r.symbols),
                    )
                )
    path = OUT / "scores.parquet"
    done = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    done_keys = set(done["key"]) if len(done) else set()
    todo = [j for j in jobs if j.key not in done_keys]
    if args.limit:
        todo = todo[: args.limit]
    logger.info(
        "{} headline-symbol pairs; {} already scored; scoring {} now (mock={})",
        len(jobs),
        len(done_keys),
        len(todo),
        args.mock,
    )
    t0 = time.time()
    batch = 400
    for i in range(0, len(todo), batch):
        rows = score_headlines(todo[i : i + batch], concurrency=args.concurrency, mock=args.mock)
        new = pd.DataFrame(rows)
        done = pd.concat([done, new], ignore_index=True) if len(done) else new
        done.to_parquet(path, index=False)
        ok = int(new["error"].isna().sum())
        logger.info(
            "batch {}: {} ok, {} errors, {:,} tokens so far, {:.0f}s",
            i // batch + 1,
            ok,
            len(new) - ok,
            int(done["input_tokens"].fillna(0).sum()),
            time.time() - t0,
        )
    logger.info(
        "scored total {} rows, {} errors, {:,} input tokens (≈ ${:.2f})",
        len(done),
        int(done["error"].notna().sum()),
        int(done["input_tokens"].fillna(0).sum()),
        done["input_tokens"].fillna(0).sum() / 1e6 * 0.042,
    )
    return 0


# ------------------------------------------------------------------ label + analyze
def load_bars(db_path: Path, start: date, end: date) -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT symbol, ts, open, close FROM bars WHERE feed='sip' AND ts>=? AND ts<? ORDER BY symbol, ts",
        con,
        params=[str(start), str(end + timedelta(days=1))],
    )
    con.close()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    et = df["ts"].dt.tz_convert(ET)
    df["day"] = et.dt.date
    t = et.dt.hour * 60 + et.dt.minute
    df = df[(t >= 9 * 60 + 30) & (t < 16 * 60)]
    return {s: g.reset_index(drop=True) for s, g in df.groupby("symbol")}


def label_one(bars: pd.DataFrame, t: pd.Timestamp) -> dict | None:
    """Entry = first bar at/after t in the same session, else the next session's first bar."""
    ts = bars["ts"].dt.tz_convert("UTC").dt.as_unit("ns").astype("int64").to_numpy()
    i = int(np.searchsorted(ts, int(t.tz_convert("UTC").as_unit("ns").value)))
    if i >= len(bars):
        return None
    et = t.tz_convert(ET)
    same_session = et.weekday() < 5 and (9 * 60 + 30) <= et.hour * 60 + et.minute < 16 * 60
    entry_day = bars["day"].iloc[i]
    if not same_session and bars["ts"].iloc[i].tz_convert(ET).date() == et.date() and et.hour >= 16:
        # after the close: skip to next day's first bar
        nxt = bars.index[bars["day"] > entry_day]
        if len(nxt) == 0:
            return None
        i = int(nxt[0])
        entry_day = bars["day"].iloc[i]
    day_rows = bars[bars["day"] == entry_day]
    if day_rows.empty:
        return None
    entry = float(bars["open"].iloc[i])
    prev_day = bars[bars["day"] < entry_day]
    prev_close = float(prev_day["close"].iloc[-1]) if len(prev_day) else np.nan
    day_close = float(day_rows["close"].iloc[-1])
    nxt_rows = bars[bars["day"] > entry_day]
    next_close = (
        float(nxt_rows[nxt_rows["day"] == nxt_rows["day"].iloc[0]]["close"].iloc[-1]) if len(nxt_rows) else np.nan
    )

    def fwd(minutes: int) -> float:
        j = i + minutes
        j = min(j, int(day_rows.index[-1]))
        return float(bars["close"].iloc[j]) / entry - 1

    return {
        "entry_ts": bars["ts"].iloc[i],
        "same_session": same_session,
        "entry": entry,
        "pre_move_pct": (entry / prev_close - 1) * 100 if prev_close == prev_close else np.nan,
        "fwd30_bp": fwd(30) * 1e4,
        "fwd60_bp": fwd(60) * 1e4,
        "fwd180_bp": fwd(180) * 1e4,
        "fwd_close_bp": (day_close / entry - 1) * 1e4,
        "fwd_next_close_bp": (next_close / entry - 1) * 1e4 if next_close == next_close else np.nan,
    }


def cmd_analyze(args) -> int:
    settings = load_settings()
    heads = pd.read_parquet(OUT / "headlines.parquet").set_index("id")
    scores = pd.read_parquet(OUT / "scores.parquet")
    scores = scores[scores["error"].isna()].copy()
    scores["id"] = scores["key"].str.split(":").str[0]
    scores = scores.join(heads[["created_at", "headline", "source", "n_symbols"]], on="id")
    bars = load_bars(settings.storage.resolved_db_path(), args.start, args.end)
    rows = []
    for r in scores.itertuples():
        b = bars.get(r.symbol)
        if b is None:
            continue
        lab = label_one(b, pd.Timestamp(r.created_at))
        if lab:
            rows.append({**r._asdict(), **lab})
    df = pd.DataFrame(rows).drop(columns=["Index"], errors="ignore")
    df.to_parquet(OUT / "labelled.parquet", index=False)
    print(
        f"labelled {len(df):,} headline-symbol pairs ({df['id'].nunique():,} headlines, "
        f"{df['symbol'].nunique()} symbols, "
        f"{df['same_session'].mean():.0%} published in session hours)"
    )
    pd.set_option("display.width", 220)
    horizons = ["fwd30_bp", "fwd60_bp", "fwd180_bp", "fwd_close_bp", "fwd_next_close_bp"]

    def table(g: pd.DataFrame, by: str) -> pd.DataFrame:
        out = (
            g.groupby(by)
            .agg(
                n=("key", "size"),
                **{h: (h, "mean") for h in horizons},
                hit180=("fwd180_bp", lambda s: (s > 0).mean()),
                pre_move=("pre_move_pct", "mean"),
            )
            .round(2)
        )
        return out

    print("\n[1] unconditional (all pairs):", {h: round(float(df[h].mean()), 2) for h in horizons})
    fresh = df[(df.p_stale < 0.5) & (df.n_symbols <= 8)]
    print(f"\n[2] fresh items only (p_stale < 0.5, ≤ 8 symbols): n={len(fresh):,} of {len(df):,}")
    print("    by direction (confidence ≥ 0.6):")
    print(table(fresh[fresh.direction_conf >= 0.6], "direction").to_string())
    fresh = fresh.assign(mat=pd.cut(fresh.materiality, [-0.01, 0.5, 1.5, 2.01], labels=["routine", "notable", "major"]))
    print("\n    by materiality level:")
    print(table(fresh, "mat").to_string())
    print("\n    up × materiality:")
    print(table(fresh[fresh.direction == "up"], "mat").to_string())
    print("\n    down × materiality:")
    print(table(fresh[fresh.direction == "down"], "mat").to_string())
    print("\n[3] by kind (fresh, any direction):")
    print(table(fresh, "kind").to_string())
    sig = df[(df.p_positive > 0.7) & (df.p_stale < 0.3) & (df.materiality >= 1.5) & (df.n_symbols <= 8)]
    neg = df[
        (df.direction == "down")
        & (df.direction_conf >= 0.6)
        & (df.p_stale < 0.3)
        & (df.materiality >= 1.5)
        & (df.n_symbols <= 8)
    ]
    for name, g in (("fresh material positive", sig), ("fresh material negative", neg)):
        if len(g):
            se = g["fwd180_bp"].std() / np.sqrt(len(g))
            print(
                f"\n[4] {name}: n={len(g)}, fwd180 {g.fwd180_bp.mean():+.1f} ± {2 * se:.1f} bp, "
                f"close {g.fwd_close_bp.mean():+.1f}, "
                f"next close {g.fwd_next_close_bp.mean():+.1f}, hit180 {(g.fwd180_bp > 0).mean():.1%}, "
                f"pre-move {g.pre_move_pct.mean():+.2f}%"
            )
    mid = df["created_at"].quantile(0.5)
    for lab, g in (("first half", sig[sig.created_at <= mid]), ("second half", sig[sig.created_at > mid])):
        if len(g):
            print(
                f"    positive, {lab}: n={len(g)}, fwd180 {g.fwd180_bp.mean():+.1f}, close {g.fwd_close_bp.mean():+.1f}"
            )
    print("\n[5] does the score add to our entries? candidates with a fresh headline in the prior 6 hours:")
    feat = Path("data/features/features-2026-06-01-2026-09-16-sip.parquet")
    if feat.exists():
        cand = pd.read_parquet(feat)
        cand = cand[cand.candidate].copy()
        cand["ts"] = pd.to_datetime(cand["ts"], utc=True)
        s2 = df[["symbol", "created_at", "p_positive", "direction", "materiality", "p_stale"]].sort_values("created_at")
        merged = pd.merge_asof(
            cand.sort_values("ts"),
            s2.rename(columns={"created_at": "news_ts"}),
            left_on="ts",
            right_on="news_ts",
            by="symbol",
            direction="backward",
            tolerance=pd.Timedelta(hours=6),
        )
        merged["bucket"] = np.select(
            [
                merged.news_ts.isna(),
                (merged.p_stale < 0.5) & (merged.direction == "up"),
                (merged.p_stale < 0.5) & (merged.direction == "down"),
            ],
            ["no fresh news", "fresh up", "fresh down"],
            "other news",
        )
        t = (
            merged.groupby("bucket")
            .agg(
                n=("symbol", "size"),
                win=("strat_pnl_pct", lambda s: (s > 0).mean()),
                pnl=("strat_pnl_pct", "mean"),
                pf=("strat_pnl_pct", lambda s: s[s > 0].sum() / -s[s <= 0].sum() if (s <= 0).any() else np.inf),
            )
            .round(3)
        )
        print(t.to_string())
    print(f"\nsaved {OUT / 'labelled.parquet'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "score", "analyze"):
        p = sub.add_parser(name)
        p.add_argument("--start", type=date.fromisoformat, default=date(2026, 6, 1))
        p.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 16))
        if name == "score":
            p.add_argument("--limit", type=int, default=None)
            p.add_argument("--concurrency", type=int, default=16)
            p.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    return {"fetch": cmd_fetch, "score": cmd_score, "analyze": cmd_analyze}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
