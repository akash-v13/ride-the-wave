"""Download the free outside histories (Ken French, Cboe, FRED) into data/external/<source>/.

Each file is fetched whole and replaces the previous copy only once complete. Re-run any time to
refresh; the sources update daily (Cboe, FRED) or monthly (Ken French).

    uv run python scripts/download_external.py               # everything
    uv run python scripts/download_external.py --only vix,spx
    uv run python scripts/download_external.py --list
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from ridethewave.data.external import DATASETS, download, load


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated dataset names")
    ap.add_argument("--list", action="store_true", help="list the datasets and exit")
    args = ap.parse_args()
    if args.list:
        for d in DATASETS.values():
            print(f"{d.name:12} {d.source:7} {d.description}")
        return 0
    names = [n.strip() for n in args.only.split(",")] if args.only else list(DATASETS)
    unknown = [n for n in names if n not in DATASETS]
    if unknown:
        logger.error("unknown dataset(s) {}; known: {}", unknown, sorted(DATASETS))
        return 2
    failed = 0
    for name in names:
        try:
            path = download(name)
            data = load(name)
            first, last = data.index[0].date(), data.index[-1].date()
            logger.info("{}: {} rows, {} to {} -> {}", name, len(data), first, last, path)
        except Exception as e:  # noqa: BLE001 - report every source, then fail at the end
            failed += 1
            logger.error("{}: {}", name, e)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
