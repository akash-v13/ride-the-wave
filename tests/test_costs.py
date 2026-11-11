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


def test_auction_price_is_the_largest_opening_print():
    from ridethewave.daily.costs import auction_price

    # an odd-lot print on another venue, a small opening elsewhere, then the listing exchange's cross
    prints = [{"p": 8.54, "s": 1, "c": "Q"}, {"p": 8.5, "s": 1000, "c": "O"}, {"p": 8.51, "s": 1888347, "c": "Q"}]
    assert auction_price(prints) == 8.51
    assert auction_price([]) is None and auction_price(None) is None
    assert auction_price([{"p": None, "s": 5}, {"p": 3.0, "s": 0}]) is None  # no usable print


def test_auction_row_is_matched_on_its_date_not_its_position():
    """Found 2026-11-10: a one-day request returns the day before first for NYSE and ARCA symbols in
    winter (a late closing print stamped 01:00 UTC), and reading the first row lost their opening print."""
    from ridethewave.daily.costs import auction_day, auction_price

    rows = [
        {"d": "2026-11-09", "o": [], "c": [{"p": 171.0, "s": 100}]},
        {"d": "2026-11-10", "o": [{"p": 171.27, "s": 95425}, {"p": 171.155, "s": 5}], "c": []},
    ]
    assert auction_price(auction_day(rows, "2026-11-10")["o"]) == 171.27
    assert auction_day(rows, "2026-11-11") is None
    assert auction_day(None, "2026-11-10") is None and auction_day([], "2026-11-10") is None


def test_opening_auctions_reads_the_asked_day_when_the_day_before_comes_first():
    from datetime import date

    from ridethewave.data.market_data import opening_auctions

    class Client:
        def get(self, path, params):
            assert path == "/stocks/auctions"
            return {
                "auctions": {
                    "BA": [
                        {"d": "2026-11-09", "o": [], "c": [{"p": 170.0, "s": 10}]},
                        {"d": "2026-11-10", "o": [{"p": 171.27, "s": 95425}]},
                    ],
                    "AAPL": [{"d": "2026-11-10", "o": [{"p": 351.36, "s": 439303}, {"p": 351.37, "s": 10}]}],
                    "LATE": [{"d": "2026-11-09", "o": [{"p": 9.0, "s": 500}]}],  # only the day before
                }
            }

    got = opening_auctions(Client(), ["BA", "AAPL", "LATE"], date(2026, 11, 10))
    assert got == {"BA": 171.27, "AAPL": 351.36}
