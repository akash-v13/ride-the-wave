"""Free outside histories that reach back before Alpaca's 2016 start (owner approved 2026-11-02).

Alpaca's bars begin in 2016, one decade that mostly rewarded holding US stocks. A strategy that only
earns in calm markets, or one meant to earn in crises, cannot be judged on that decade alone. These
three public sources reach back to 1926, 1962 and 1986:

- **Ken French data library** (Dartmouth): daily US market, size, value and momentum factor returns
  from July 1926, in percent. ``Mkt-RF + RF`` is the return of the whole US stock market including
  dividends.
- **Cboe index histories**: the S&P 500 (daily from 1975), VIX (from 1990) and Cboe's
  option-strategy benchmarks, the published, rule-based records of the volatility risk premium:
  the iron condor and 5% protective-put indexes (daily from 1986), BuyWrite (covered call, from
  2002) and PutWrite (sells a one-month at-the-money S&P put each month, fully collateralised in
  T-bills; daily from 2007, only a handful of points before that in Cboe's file).
- **FRED** (St. Louis Fed): the 10-year Treasury yield (daily from 1962) and the 3-month T-bill rate
  (from 1954), in percent a year.

``scripts/download_external.py`` saves the raw files under ``data/external/<source>/``; the loaders
here parse them. Nothing here touches the network except ``download``.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

EXTERNAL_DIR = Path(__file__).resolve().parents[3] / "data" / "external"

_FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
_CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/"
_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="


@dataclass(frozen=True)
class Dataset:
    name: str
    source: str  # french | cboe | fred
    url: str
    filename: str
    description: str


DATASETS: dict[str, Dataset] = {
    d.name: d
    for d in (
        Dataset(
            "ff_factors",
            "french",
            _FRENCH + "F-F_Research_Data_Factors_daily_CSV.zip",
            "F-F_Research_Data_Factors_daily_CSV.zip",
            "Fama-French 3 factors, daily, from 1926: Mkt-RF, SMB, HML, RF (decimal returns)",
        ),
        Dataset(
            "ff_momentum",
            "french",
            _FRENCH + "F-F_Momentum_Factor_daily_CSV.zip",
            "F-F_Momentum_Factor_daily_CSV.zip",
            "Momentum factor (winners minus losers, 12-2 months), daily, from 1926 (decimal returns)",
        ),
        Dataset(
            "ff_st_reversal",
            "french",
            _FRENCH + "F-F_ST_Reversal_Factor_daily_CSV.zip",
            "F-F_ST_Reversal_Factor_daily_CSV.zip",
            "Short-term reversal factor (last month's losers minus winners), daily, from 1926 (decimal returns)",
        ),
        Dataset(
            "ff_st_reversal_monthly",
            "french",
            _FRENCH + "F-F_ST_Reversal_Factor_CSV.zip",
            "F-F_ST_Reversal_Factor_CSV.zip",
            "Short-term reversal factor re-sorted monthly on last month's return, monthly, from 1926. The daily"
            " file re-sorts every day on days -20 to -1, so it includes yesterday's bid-ask bounce",
        ),
        Dataset(
            "ff_rev_deciles_monthly",
            "french",
            _FRENCH + "10_Portfolios_Prior_1_0_CSV.zip",
            "10_Portfolios_Prior_1_0_CSV.zip",
            "Ten value-weighted portfolios re-sorted monthly on last month's return, monthly, from 1926",
        ),
        Dataset(
            "ff_mom_deciles",
            "french",
            _FRENCH + "10_Portfolios_Prior_12_2_Daily_CSV.zip",
            "10_Portfolios_Prior_12_2_Daily_CSV.zip",
            "Ten value-weighted portfolios sorted on 12-2 month return (Lo PRIOR ... Hi PRIOR), daily, from 1926",
        ),
        Dataset(
            "ff_rev_deciles",
            "french",
            _FRENCH + "10_Portfolios_Prior_1_0_Daily_CSV.zip",
            "10_Portfolios_Prior_1_0_Daily_CSV.zip",
            "Ten value-weighted portfolios sorted on last month's return, daily, from 1926",
        ),
        Dataset(
            "ff_49_industries",
            "french",
            _FRENCH + "49_Industry_Portfolios_daily_CSV.zip",
            "49_Industry_Portfolios_daily_CSV.zip",
            "49 value-weighted industry portfolios, daily, from 1926 (missing = NaN)",
        ),
        Dataset("spx", "cboe", _CBOE + "SPX_History.csv", "SPX_History.csv", "S&P 500 index level (price only)"),
        Dataset("vix", "cboe", _CBOE + "VIX_History.csv", "VIX_History.csv", "VIX: 30-day S&P implied volatility"),
        Dataset("put", "cboe", _CBOE + "PUT_History.csv", "PUT_History.csv", "Cboe S&P 500 PutWrite index"),
        Dataset("bxm", "cboe", _CBOE + "BXM_History.csv", "BXM_History.csv", "Cboe S&P 500 BuyWrite index"),
        Dataset("cndr", "cboe", _CBOE + "CNDR_History.csv", "CNDR_History.csv", "Cboe S&P 500 Iron Condor index"),
        Dataset("pput", "cboe", _CBOE + "PPUT_History.csv", "PPUT_History.csv", "Cboe S&P 500 5% Put Protection index"),
        Dataset("dgs10", "fred", _FRED + "DGS10", "DGS10.csv", "10-year Treasury constant-maturity yield, % a year"),
        Dataset("dtb3", "fred", _FRED + "DTB3", "DTB3.csv", "3-month Treasury bill rate (discount basis), % a year"),
    )
}


def path_of(name: str, root: Path | None = None) -> Path:
    d = DATASETS[name]
    return (root or EXTERNAL_DIR) / d.source / d.filename


def download(name: str, root: Path | None = None, timeout: float = 60.0) -> Path:
    """Fetch one dataset's raw file and save it, replacing the old copy only once the new one is complete."""
    d = DATASETS[name]
    target = path_of(name, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(d.url, headers={"User-Agent": "ridethewave-research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URLs above
        body = r.read()
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(body)
    tmp.replace(target)
    return target


# ---------------------------------------------------------------- parsers
def parse_french(raw: bytes) -> pd.DataFrame:
    """Ken French CSV inside a zip: a text preamble, then ``YYYYMMDD,v1,...`` (daily) or ``YYYYMM,v1,...``
    (monthly, indexed at month end) rows in percent, then a copyright line or a further block. Returns
    the first block (value-weighted, in the portfolio files) as decimal returns; -99.99 and -999 mark
    missing values and become NaN.

    Read the file's preamble before using a series: Ken French's *daily* files re-sort their portfolios
    every day, the monthly files once a month."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        member = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        text = z.read(member).decode("latin-1")
    header: list[str] | None = None
    width = 0  # 8 for daily dates, 6 for monthly, set by the first data row
    rows: list[list[str]] = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.split(",")]
        if header is None:
            if len(cells) > 1 and cells[0] == "" and all(cells[1:]):
                header = cells[1:]
            continue
        if len(cells) == len(header) + 1 and cells[0].isdigit() and len(cells[0]) == (width or len(cells[0])):
            if not width and len(cells[0]) not in (6, 8):
                continue
            width = len(cells[0])
            rows.append(cells)
        elif rows:
            break  # the daily block ended (copyright line or an annual block)
    if header is None or not rows:
        raise ValueError("no daily or monthly table found in the Ken French file")
    if width == 8:
        idx = pd.to_datetime([r[0] for r in rows], format="%Y%m%d")
    else:
        idx = pd.to_datetime([r[0] for r in rows], format="%Y%m") + pd.offsets.MonthEnd(0)
    vals = np.array([[float(x) for x in r[1:]] for r in rows])
    vals[(vals <= -99.99 + 1e-9) & (vals >= -999.0 - 1e-9)] = np.nan
    return pd.DataFrame(vals / 100.0, index=idx, columns=header).sort_index()


def parse_cboe(raw: bytes, name: str) -> pd.DataFrame:
    """Cboe history CSV: a DATE column plus either OPEN/HIGH/LOW/CLOSE or one column named after the
    index. Returns lower-case columns with at least ``close``."""
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "date" not in df.columns:
        raise ValueError(f"{name}: no DATE column in {list(df.columns)}")
    df.index = pd.to_datetime(df.pop("date"), format="mixed")
    if "close" not in df.columns:
        value_cols = [c for c in df.columns]
        if len(value_cols) != 1:
            raise ValueError(f"{name}: expected CLOSE or one value column, got {value_cols}")
        df = df.rename(columns={value_cols[0]: "close"})
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df[df["close"] > 0]
    return df[~df.index.duplicated(keep="last")].sort_index()


def parse_fred(raw: bytes, name: str) -> pd.Series:
    """FRED graph CSV: a date column and one value column; missing days are '.' or blank."""
    df = pd.read_csv(io.BytesIO(raw))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    s.name = name
    return s.dropna().sort_index()


def load(name: str, root: Path | None = None) -> pd.DataFrame | pd.Series:
    """Parse a downloaded dataset. Raises FileNotFoundError with the command to run if it is missing."""
    d = DATASETS[name]
    p = path_of(name, root)
    if not p.exists():
        raise FileNotFoundError(f"{p} missing: run `uv run python scripts/download_external.py --only {name}`")
    raw = p.read_bytes()
    if d.source == "french":
        return parse_french(raw)
    if d.source == "cboe":
        return parse_cboe(raw, name)
    return parse_fred(raw, name)


def us_market_total_return(root: Path | None = None) -> pd.Series:
    """Daily total return of the US stock market (CRSP value-weighted, dividends included), from 1926."""
    ff = load("ff_factors", root)
    return (ff["Mkt-RF"] + ff["RF"]).rename("market")


def treasury_10y_total_return(root: Path | None = None) -> pd.Series:
    """Approximate daily total return of a constant-maturity 10-year Treasury from FRED's yield.

    A par bond priced off the yield curve: return = carry (yesterday's yield / 252) minus modified
    duration times the yield change, plus half the convexity times the change squared. Duration and
    convexity are those of a 10-year par bond at yesterday's yield. It ignores roll-down, so it is an
    approximation; the research page compares it with IEF over the years both exist.
    """
    y = load("dgs10", root) / 100.0
    y_prev = y.shift(1)
    dy = y.diff()
    # Par bond, semi-annual coupons: modified duration D = (1 - (1 + y/2)^-20) / y; convexity ~ D^2 + D/y
    # is close enough at this horizon (the term is second order in the daily change).
    dur = (1 - (1 + y_prev / 2) ** -20) / y_prev
    conv = dur**2 + dur / (2 * (1 + y_prev / 2))
    days = y.index.to_series().diff().dt.days.fillna(1)
    ret = y_prev * days / 365.0 - dur * dy + 0.5 * conv * dy**2
    return ret.dropna().rename("treasury_10y")


def tbill_daily_return(root: Path | None = None) -> pd.Series:
    """Daily cash return from the 3-month T-bill rate, accrued over calendar days."""
    r = load("dtb3", root) / 100.0
    days = r.index.to_series().diff().dt.days.fillna(1)
    return (r.shift(1) * days / 360.0).dropna().rename("tbill")
