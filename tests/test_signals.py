"""Conditions and rankings of the shortlist signals (docs/research/2026-11-10-signals-a-c-d.md)."""

import numpy as np
import pandas as pd

from ridethewave.daily.signals import mean_difference, momentum_12_1, month_position, sector_stress, turn_of_month


def test_turn_of_month_is_the_last_session_and_the_first_three():
    idx = pd.bdate_range("2024-01-01", "2024-03-29")  # Jan, Feb, Mar 2024; weekdays stand in for sessions
    turn = turn_of_month(idx)
    on = [d.strftime("%m-%d") for d in idx[turn]]
    assert on == ["01-01", "01-02", "01-03", "01-31", "02-01", "02-02", "02-05", "02-29", "03-01", "03-04", "03-05"]


def test_the_final_months_end_is_not_guessed():
    idx = pd.bdate_range("2024-01-01", "2024-02-14")  # February is not over
    from_start, from_end = month_position(idx)
    assert from_start.loc["2024-02-01"] == 1 and from_end.loc["2024-01-31"] == 1
    assert from_end.loc["2024-02-14":].isna().all()
    assert not turn_of_month(idx).loc["2024-02-14"]


def test_sector_stress_judges_a_day_against_earlier_days_only():
    idx = pd.bdate_range("2020-01-01", periods=300)
    rng = np.random.default_rng(3)
    market = pd.Series(rng.normal(0, 0.01, 300), index=idx)
    calm = market + pd.Series(rng.normal(0, 0.002, 300), index=idx)
    hit = calm.copy()
    hit.iloc[-1] -= 0.10  # one sector falls 10% beyond the market on the last day
    flags = sector_stress(pd.DataFrame({"CALM": calm, "HIT": hit}), market)
    assert flags["HIT"].iloc[-1] and not flags["CALM"].iloc[-1]
    assert not flags.iloc[:204].any().any()  # 5 sessions for the first sum, then 200 earlier values
    # the threshold on the day before is the same with or without the shock: nothing looks ahead
    assert flags["HIT"].iloc[:-1].equals(sector_stress(pd.DataFrame({"HIT": calm}), market)["HIT"].iloc[:-1])
    # about a tenth of days qualify by construction
    assert 0.03 < flags["CALM"].iloc[205:].mean() < 0.25


def test_momentum_uses_prices_up_to_yesterday():
    idx = pd.bdate_range("2020-01-01", periods=300)
    close = pd.DataFrame({"A": np.arange(1.0, 301.0)}, index=idx)
    m = momentum_12_1(close)
    assert m["A"].iloc[:253].isna().all()
    t = 280
    assert m["A"].iloc[t] == close["A"].iloc[t - 22] / close["A"].iloc[t - 253] - 1
    changed = close.copy()
    changed.iloc[t - 21 :] = 999.0  # the latest month and today do not matter
    assert momentum_12_1(changed)["A"].iloc[t] == m["A"].iloc[t]


def test_mean_difference_matches_the_plain_difference_and_finds_a_real_one():
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2000-01-03", periods=5000)
    flag = turn_of_month(idx)
    noise = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    with_edge = noise + 0.002 * flag
    r = mean_difference(with_edge, flag)
    assert abs(r["difference"] - (with_edge[flag].mean() - with_edge[~flag].mean())) < 1e-12
    assert r["t"] > 4 and r["n_flagged"] == int(flag.sum())
    assert abs(mean_difference(noise, flag)["t"]) < 3
    assert np.isnan(mean_difference(noise.iloc[:5], flag.iloc[:5])["t"])  # too little to say anything


# ---------------------------------------------------------------- the shadow strategies built on them
def _window(close, symbols, held=None, external=None):
    from ridethewave.daily.strategies import Window

    return Window(close=close, open=close, high=close, low=close, volume=close * 0 + 1e6, today=close.index[-1],
                  symbols=symbols, held=held or {}, external=external or {})  # fmt: skip


def test_overnight_momentum_buys_the_top_30_percent_ranked_on_prices_up_to_yesterday():
    from ridethewave.daily.strategies import build_daily

    idx = pd.bdate_range("2025-01-01", periods=300)
    growth = np.linspace(-0.5, 0.8, 40)  # stock k's yearly drift; the last ones are the winners
    close = pd.DataFrame({f"S{k:02d}": 100 * np.exp(g * np.arange(300) / 252) for k, g in enumerate(growth)}, index=idx)
    strat = build_daily("overnight_momentum", {})
    targets = strat.targets(_window(close, list(close.columns)))
    assert sorted(targets) == [f"S{k:02d}" for k in range(28, 40)] and abs(sum(targets.values()) - 1) < 1e-12
    crash = close.copy()
    crash.iloc[-1, -1] = 1.0  # today's unfinished bar is not used
    assert strat.targets(_window(crash, list(close.columns))) == targets
    assert strat.targets(_window(close.iloc[-200:], list(close.columns))) == {}  # under a year of history


def test_turn_of_month_holds_into_turn_days_and_needs_the_calendar():
    from ridethewave.daily.strategies import build_daily

    strat = build_daily("turn_of_month", {})
    ahead = [str(d.date()) for d in pd.bdate_range("2026-11-01", "2026-12-31")]

    def decide(today, held=None, sessions=ahead):
        idx = pd.bdate_range("2026-09-01", today)
        close = pd.DataFrame({"SPY": np.linspace(600, 610, len(idx))}, index=idx)
        return strat.targets(_window(close, ["SPY"], held, {"sessions": sessions} if sessions else {}))

    assert decide("2026-11-10") == {}  # the 11th is the 8th session of November
    assert decide("2026-11-26") == {}  # tomorrow the 27th is not the last session (the 30th is)
    assert decide("2026-11-27") == {"SPY": 1.0}  # tomorrow, Monday the 30th, is the month's last session
    assert decide("2026-11-30") == {"SPY": 1.0} and decide("2026-12-02") == {"SPY": 1.0}  # into sessions 1 and 3
    assert decide("2026-12-03") == {}  # tomorrow is the 4th session: out at today's close
    assert decide("2026-11-27", {"SPY": 5}, sessions=None) == {"SPY": 1.0}  # no calendar: keep what is held
    assert decide("2026-11-27", sessions=None) == {}


def test_sector_stress_picks_only_inside_stressed_sectors_with_enough_names():
    from ridethewave.daily.statarb import pick_in_stressed_sectors

    names = [f"K{i:02d}" for i in range(20)] + [f"F{i:02d}" for i in range(20)] + [f"U{i}" for i in range(5)]
    sig = pd.Series(np.r_[np.arange(20.0), np.arange(20.0), np.arange(5.0)], index=names)
    sectors = pd.Series(["XLK"] * 20 + ["XLF"] * 20 + ["XLU"] * 5, index=names)
    stressed = pd.Series({"XLK": True, "XLF": False, "XLU": True})
    longs, shorts = pick_in_stressed_sectors(sig, sectors, stressed)
    assert longs == ["K00", "K01", "K02", "K03"] and shorts == ["K16", "K17", "K18", "K19"]  # XLU has too few names
    assert pick_in_stressed_sectors(sig, sectors, pd.Series({"XLK": False, "XLF": False, "XLU": True})) == ([], [])
    assert pick_in_stressed_sectors(sig.iloc[:12], sectors.iloc[:12], stressed) == ([], [])  # 2 a side is under 4
