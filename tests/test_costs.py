"""Cost measurements for the daily books: the quoted spread and the wait between the open and 09:35."""

import numpy as np
import pandas as pd
import pytest

from ridethewave.daily.costs import half_spread_bp, long_short_gap, open_to_later

S = 1_000_000_000  # one second in nanoseconds


def test_half_spread_weights_each_quote_by_how_long_it_stood():
    ts = np.array([0, 10 * S, 25 * S])
    bid = np.array([99.9, 99.8, 99.9])
    ask = np.array([100.1, 100.2, 100.1])
    # 10 bp for 10 s, 20 bp for 15 s, 10 bp for the last 5 s of a 30 s window
    assert half_spread_bp(ts, bid, ask, 30 * S) == pytest.approx((10 * 10 + 20 * 15 + 10 * 5) / 30)


def test_locked_crossed_and_empty_quotes_count_for_nothing():
    ts = np.array([0, 10 * S, 20 * S])
    bid = np.array([100.0, 0.0, 99.9])
    ask = np.array([100.0, 100.1, 100.1])  # locked, no bid, then a real 10 bp quote
    assert half_spread_bp(ts, bid, ask, 30 * S) == pytest.approx(10.0)
    assert half_spread_bp(ts[:2], bid[:2], ask[:2], 30 * S) is None
    assert half_spread_bp(np.array([]), np.array([]), np.array([]), 30 * S) is None


def bars(rows):
    return pd.DataFrame(rows, columns=["minute", "open", "close", "vwap"])


def test_move_from_the_opening_trade_to_the_0935_bar():
    b = bars([(0, 100.0, 100.5, 100.2), (1, 100.5, 101.0, 100.8), (5, 101.0, 101.4, 101.2)])
    assert open_to_later(b) == pytest.approx(0.012)  # 09:35 bar's volume-weighted price over the open
    # nothing traded in the 09:35 minute: the last trade before it
    assert open_to_later(b[b["minute"] < 5]) == pytest.approx(0.010)
    # opened late, at 09:32: priced from its own first trade
    late = bars([(2, 50.0, 50.2, 50.1), (5, 50.2, 50.3, 50.25)])
    assert open_to_later(late) == pytest.approx(0.005)
    assert open_to_later(bars([(5, 50.2, 50.3, 50.25)])) is None  # had not traded before 09:35


def test_long_short_gap_hedges_market_and_sector_and_skips_unpriced_names():
    move = pd.Series({"SPY": 0.010, "XLK": 0.020, "L1": 0.030, "L2": 0.012, "S1": 0.010, "NOPRICE": np.nan})
    b_m = pd.Series({"L1": 1.0, "L2": 1.2, "S1": 1.0, "NOPRICE": 1.0})
    b_s = pd.Series({"L1": 1.0, "L2": 0.0, "S1": 0.0, "NOPRICE": 0.0})
    sectors = pd.Series({"L1": "XLK", "L2": "XLK", "S1": "XLK", "NOPRICE": "XLK"})
    gap, priced = long_short_gap(move, ["L1", "L2", "NOPRICE"], ["S1"], b_m, b_s, sectors)
    # L1: 0.030 - 0.010 - (0.020 - 0.010) = 0.010; L2: 0.012 - 0.012 = 0; S1: 0.010 - 0.010 = 0
    assert gap == pytest.approx(0.005) and priced == 3
    assert long_short_gap(move, ["L1"], ["NOPRICE"], b_m, b_s, sectors) == (None, 1)
    assert long_short_gap(move.drop("SPY"), ["L1"], ["S1"], b_m, b_s, sectors) == (None, 0)
