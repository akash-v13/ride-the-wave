"""The universe must recover on its own when the start-up build fails (October 2026: six sessions of none)."""

from types import SimpleNamespace

import ridethewave.runner as runner_mod
from ridethewave.runner import BotRunner


class _Builder:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def build(self):
        self.calls += 1
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _runner(db, results):
    r = BotRunner.__new__(BotRunner)
    r.db = db
    r._stop = False
    r.universe = []
    r.universe_builder = _Builder(results)
    r.slots = [SimpleNamespace(strategy=None, symbols=[], book=SimpleNamespace(positions={}, pending_entries={}))]
    r.portfolios = [SimpleNamespace(spec=SimpleNamespace(universe="scan"), universe=[])]
    r._symbols_for = lambda strategy: list(r.universe)
    r._portfolio_universe = lambda spec: [s for s in r.universe if s != "SOXL"]
    r.warmed, r.session_starts = [], []
    r._warmup = lambda symbols=None: r.warmed.append(symbols)
    r._session_start = lambda today: r.session_starts.append(today)
    return r


def test_start_up_build_retries_with_backoff(db, monkeypatch):
    slept = []
    monkeypatch.setattr(runner_mod.time, "sleep", lambda s: slept.append(s))
    r = _runner(db, [ConnectionError("Remote end closed"), ValueError("TXSE"), ["AAPL", "NVDA"]])
    assert r._rebuild_universe(attempts=3) is True
    assert r.universe == ["AAPL", "NVDA"] and r.universe_builder.calls == 3
    assert len(slept) == sum(runner_mod.UNIVERSE_RETRY_WAITS)  # waited 15 s, then 45 s, one second at a time
    assert db.state.get("universe") == ["AAPL", "NVDA"]


def test_failed_build_keeps_the_previous_universe(db, monkeypatch):
    monkeypatch.setattr(runner_mod.time, "sleep", lambda s: None)
    r = _runner(db, [ConnectionError("down")])
    r.universe = ["AAPL"]
    assert r._rebuild_universe() is False and r.universe == ["AAPL"]


def test_recovery_from_empty_warms_up_and_restarts_the_session(db):
    r = _runner(db, [["AAPL", "NVDA", "SOXL"], ["AAPL", "NVDA", "TSLA"]])
    r._refresh_universe("2026-10-28")
    assert r.slots[0].symbols == ["AAPL", "NVDA", "SOXL"]
    assert r.portfolios[0].universe == ["AAPL", "NVDA"]
    assert r.warmed == [["AAPL", "NVDA", "SOXL"]] and r.session_starts == ["2026-10-28"]  # SPY: watched already
    # a routine refresh warms up only the newcomer and leaves the strategies' day state alone
    r._refresh_universe("2026-10-28")
    assert r.warmed[-1] == ["TSLA"] and r.session_starts == ["2026-10-28"]


def test_refresh_that_fails_changes_nothing(db, monkeypatch):
    monkeypatch.setattr(runner_mod.time, "sleep", lambda s: None)
    r = _runner(db, [ConnectionError("down"), ConnectionError("down")])
    r._refresh_universe("2026-10-28", attempts=2)
    assert r.universe == [] and r.slots[0].symbols == [] and r.warmed == [] and r.session_starts == []
