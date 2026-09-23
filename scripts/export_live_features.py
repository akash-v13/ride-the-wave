"""Flatten live-recorded feature rows into the same parquet layout as build_features.py.

    uv run python scripts/export_live_features.py            -> data/features/live-iex.parquet
    uv run python scripts/export_live_features.py --day 2026-09-22

Rows without labels (the bot died before the close) are exported with label columns as null.
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from ridethewave.config import load_settings
from ridethewave.storage import Database


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default="iex")
    ap.add_argument("--day", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    settings = load_settings()
    db = Database(settings.storage.resolved_db_path(), read_only=True)
    rows = db.features.rows(args.feed, args.day)
    if not rows:
        print("no live feature rows")
        return 0
    recs = []
    for r in rows:
        d = {"day": r["day"], "candidate": bool(r["candidate"]), **json.loads(r["features_json"])}
        if r["labels_json"]:
            d.update(json.loads(r["labels_json"]))
        recs.append(d)
    df = pd.DataFrame(recs)
    out = args.out or str(settings.storage.resolved_db_path().parent / "features" / f"live-{args.feed}.parquet")
    df.to_parquet(out, index=False)
    labelled = df["strat_pnl_pct"].notna().sum() if "strat_pnl_pct" in df else 0
    print(
        f"wrote {len(df):,} rows ({int(df['candidate'].sum()):,} candidates, {labelled:,} labelled, "
        f"{df['day'].nunique()} days) to {out}"
    )
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
