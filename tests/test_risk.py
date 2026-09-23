from datetime import datetime, timezone

from ridethewave.config import RiskSettings
from ridethewave.models import Trade
from ridethewave.operator.risk import RiskMonitor, beta_prob_below

T0 = datetime(2026, 9, 22, 14, tzinfo=timezone.utc)


def trade(pnl: float) -> Trade:
    return Trade("A", 1, 100, T0, 100 + pnl, T0, "x", 100, run_id="live")


def test_beta_prob_below_matches_known_values():
    assert abs(beta_prob_below(0.5, 1, 1) - 0.5) < 1e-3  # uniform
    assert beta_prob_below(0.3, 42, 76) < 0.15  # 41 wins / 75 losses, mean 0.356
    assert beta_prob_below(0.45, 42, 76) > 0.95


def test_daily_loss_flattens_and_halts():
    m = RiskMonitor(RiskSettings(max_daily_loss_pct=2.0, max_open_loss_pct=3.0), allocation=10_000)
    assert m.check_pnl(-150, 0).halt_entries is False
    d = m.check_pnl(-200, 0)
    assert d.halt_entries and d.flatten and "daily loss" in d.reason
    # once halted, stays halted for the day
    assert m.check_pnl(0, 0).halt_entries and m.halted_reason


def test_open_loss_uses_unrealised():
    m = RiskMonitor(RiskSettings(max_daily_loss_pct=0, max_open_loss_pct=3.0), allocation=10_000)
    assert not m.check_pnl(-100, -150).halt_entries
    assert m.check_pnl(-100, -200).flatten


def test_winrate_floor_halts_without_flattening():
    cfg = RiskSettings(winrate_min_trades=20, winrate_lookback_trades=60, winrate_halt_probability=0.9)
    m = RiskMonitor(cfg, 10_000)
    # 5 wins of +10, 35 losses of -10: break-even 0.5, posterior far below
    trades = [trade(10)] * 5 + [trade(-10)] * 35
    d = m.check_winrate(trades)
    assert d.halt_entries and not d.flatten and "posterior" in d.reason
    # healthy record: no halt
    m2 = RiskMonitor(cfg, 10_000)
    assert not m2.check_winrate([trade(15)] * 20 + [trade(-10)] * 20).halt_entries
    # too few trades: no judgement
    m3 = RiskMonitor(cfg, 10_000)
    assert not m3.check_winrate([trade(-10)] * 10).halt_entries
