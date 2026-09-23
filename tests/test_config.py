from datetime import time

import pytest

from ridethewave.config import EXAMPLE_SETTINGS_PATH, Settings, load_settings


def test_example_settings_load():
    s = load_settings(EXAMPLE_SETTINGS_PATH)
    assert s.alpaca.paper is True
    assert s.alpaca.data_feed == "iex"
    assert s.entry.entry_start == time(9, 31)
    assert s.entry.entry_end == time(11, 30)
    assert s.exit.flatten_time == time(15, 55)
    assert s.entry.green_streak_minutes == 3
    assert s.exit.trail_pct == 1.5 and s.exit.min_gain_pct == 0.5


def test_live_is_rejected():
    with pytest.raises(ValueError):
        Settings.model_validate({"alpaca": {"paper": False}})


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError):
        Settings.model_validate({"entry": {"green_streak_minute": 5}})


def test_static_universe_requires_symbols():
    with pytest.raises(ValueError):
        Settings.model_validate({"universe": {"source": "static"}})
    s = Settings.model_validate({"universe": {"source": "static", "static_symbols": ["aapl"]}})
    assert s.universe.static_symbols == ["AAPL"]


def test_settings_survive_json_roundtrip():
    from ridethewave.config import EXAMPLE_SETTINGS_PATH

    s = load_settings(EXAMPLE_SETTINGS_PATH)
    again = Settings.model_validate(s.model_dump(mode="json"))
    assert again == s
