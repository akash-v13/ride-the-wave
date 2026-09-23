from ridethewave.strategy.indicators import green_streak, streak_gain_pct, streak_volume
from tests.conftest import make_bars


def test_green_streak_counts_trailing_rises():
    assert green_streak(make_bars("X", [10, 11, 12, 13])) == 3
    assert green_streak(make_bars("X", [10, 11, 10, 11, 12])) == 2
    assert green_streak(make_bars("X", [10, 9])) == 0
    assert green_streak(make_bars("X", [10])) == 0
    assert green_streak(make_bars("X", [10, 10, 10])) == 0  # flat is not green


def test_streak_gain_and_volume():
    bars = make_bars("X", [100, 101, 102, 103], volume=1000)
    assert abs(streak_gain_pct(bars, 3) - 3.0) < 1e-9
    assert streak_volume(bars, 3) == 3000
    assert streak_gain_pct(bars, 0) == 0.0
    assert streak_gain_pct(bars, 5) == 0.0  # streak longer than history
