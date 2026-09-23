from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ridethewave.config import Settings
from ridethewave.features.live import LiveFeatureRecorder
from ridethewave.models import Bar
from tests.conftest import make_bars

ET = ZoneInfo("America/New_York")


def test_recorder_records_in_window_and_labels_after_close(db):
    s = Settings.model_validate(
        {
            "entry": {
                "entry_start": "09:30",
                "entry_end": "11:30",
                "green_streak_minutes": 3,
                "min_streak_gain_pct": 0.5,
                "min_streak_volume": 100,
            }
        }
    )
    rec = LiveFeatureRecorder(db, s, feed="iex")
    session = datetime(2026, 9, 22, 9, 30, tzinfo=ET).astimezone(timezone.utc)
    closes = [100.0] * 24 + [100.3, 100.6, 101.0] + [101.5, 102, 102.5, 101.9] + [101.8] * 60
    bars = make_bars("AAPL", closes, start=session, volume=500)
    spy = make_bars("SPY", [500 + 0.05 * i for i in range(len(closes))], start=session, volume=1)
    hist = {"AAPL": [], "SPY": []}

    def history(sym):
        return hist[sym]

    for a, b in zip(bars, spy, strict=True):
        hist["SPY"].append(b)
        hist["AAPL"].append(a)
        rec.on_bar(b, history, a.ts)  # SPY bars are ignored
        rec.on_bar(a, history, a.ts)
    rec.flush()
    assert rec.rows == len(bars) and rec.candidates >= 1
    assert len(db.features.unlabelled("2026-09-22", "iex")) == len(bars)

    # bars after 11:30 must not be recorded
    late = Bar("AAPL", datetime(2026, 9, 22, 12, 0, tzinfo=ET).astimezone(timezone.utc), 101, 101, 101, 101, 10)
    hist["AAPL"].append(late)
    rec.on_bar(late, history, late.ts)
    rec.flush()
    assert rec.rows == len(bars)

    n = rec.finalize("2026-09-22", lambda syms: bars + spy)
    assert n == len(bars) - 1  # the last bar has no future
    rows = db.features.rows("iex", "2026-09-22")
    labelled = [r for r in rows if r["labels_json"]]
    assert len(labelled) == n
    assert '"strat_exit_reason"' in labelled[0]["labels_json"]
    assert db.features.days("iex") == ["2026-09-22"]


def test_recorder_never_raises(db):
    s = Settings()
    rec = LiveFeatureRecorder(db, s, feed="iex")
    rec.on_bar(Bar("AAPL", datetime(2026, 9, 22, 14, tzinfo=timezone.utc), 1, 1, 1, 1, 1), lambda sym: None, None)
    assert rec.rows == 0
