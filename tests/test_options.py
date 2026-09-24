"""Options engine: templates, resolver on a synthetic chain, lifecycle rules, the shadow slot."""

from datetime import date, datetime, timedelta, timezone

import pytest

from ridethewave.config import OptionsSpec, Settings
from ridethewave.options.chain import ChainSnapshot, OptionContract, is_option_symbol, parse_occ
from ridethewave.options.greeks import bs_greeks, implied_vol
from ridethewave.options.lifecycle import Structure, exit_reason, fill_value, size_structure, structure_value
from ridethewave.options.resolver import ResolutionError, resolve
from ridethewave.options.slot import OptionsSlot
from ridethewave.options.structures import TEMPLATES, get_template

TODAY = date(2026, 9, 24)
NOW = datetime(2026, 9, 24, 19, 40, tzinfo=timezone.utc)


def synthetic_chain(spot: float = 100.0, today: date = TODAY) -> ChainSnapshot:
    """Strikes every $1 from 88 to 112, two expiries (30 and 60 days), tight quotes."""
    contracts = []
    for dte in (30, 60):
        expiry = today + timedelta(days=dte)
        ymd = expiry.strftime("%y%m%d")
        for k in range(88, 113):
            time_value = max(2.0 + 0.02 * dte - abs(spot - k) * 0.05, 0.10)
            for right, intrinsic in (("C", max(spot - k, 0)), ("P", max(k - spot, 0))):
                mid = intrinsic + time_value
                contracts.append(
                    OptionContract(
                        f"TST{ymd}{right}{k * 1000:08d}",
                        "TST",
                        expiry,
                        right,
                        float(k),
                        round(mid - 0.05, 2),
                        round(mid + 0.05, 2),
                        None,
                        0.2,
                    )
                )
    return ChainSnapshot("TST", spot, datetime.combine(today, datetime.min.time(), timezone.utc), contracts)


def test_templates_and_symbols():
    assert len(TEMPLATES) == 57
    ids = [t.catalog_id for t in TEMPLATES.values()]
    assert len(ids) == len(set(ids)) and all(i.startswith("2.") for i in ids) and "2.52" not in ids
    assert sum(1 for t in TEMPLATES.values() if not t.alpaca_placeable) == 17
    assert all(not t.defined_risk for t in TEMPLATES.values() if not t.alpaca_placeable)
    assert is_option_symbol("SPY261016P00708000") and not is_option_symbol("SPY")
    assert parse_occ("SPY261016P00708000") == ("SPY", date(2026, 10, 16), "P", 708.0)


def test_greeks_and_iv_round_trip():
    g = bs_greeks(100, 100, 30 / 365, 0.2, True)
    assert 0.5 < g.delta < 0.6 and g.price > 0 and g.theta < 0 and g.vega > 0
    iv = implied_vol(g.price, 100, 100, 30 / 365, True)
    assert abs(iv - 0.2) < 1e-3
    assert implied_vol(0.01, 100, 120, 30 / 365, False) is None  # below intrinsic


def test_resolver_shapes():
    ch = synthetic_chain()
    ic = resolve(get_template("long_iron_condor"), ch, target_dte=30)
    pb, ps, cs, cb = ic.legs
    assert pb.strike < ps.strike < cs.strike < cb.strike and ic.net_per_unit > 0
    assert ic.max_profit == pytest.approx(ic.net_per_unit, abs=1e-6)
    assert ic.max_loss == pytest.approx((ps.strike - pb.strike) - ic.net_per_unit, abs=1e-6)
    st = resolve(get_template("long_straddle"), ch, target_dte=30)
    assert st.net_per_unit < 0 and st.legs[0].strike == st.legs[1].strike
    cal = resolve(get_template("calendar_call_spread"), ch, target_dte=30, far_dte_offset=30)
    assert cal.legs[0].expiry != cal.legs[1].expiry and cal.legs[0].strike == cal.legs[1].strike
    cc = resolve(get_template("covered_call"), ch, target_dte=30)
    assert cc.legs[0].instrument == "stock" and cc.legs[0].ratio == 100 and cc.legs[1].side == "sell"
    narrow = synthetic_chain()
    narrow.contracts = [c for c in narrow.contracts if abs(c.strike - 100) < 1]
    with pytest.raises(ResolutionError):
        resolve(get_template("long_iron_condor"), narrow, target_dte=30)


def test_sizing_valuation_and_exit_rules():
    ch = synthetic_chain()
    ic = resolve(get_template("long_iron_condor"), ch, target_dte=30)
    assert size_structure(ic, 10_000, 0.2, 0.6) >= 1
    cc = resolve(get_template("covered_call"), ch, target_dte=30)
    assert size_structure(cc, 5_000, 0.2, 0.6) is None  # 100 shares at $100 exceed the capital
    legs = [
        {
            "symbol": leg.symbol,
            "instrument": leg.instrument,
            "side": leg.side,
            "ratio": leg.ratio,
            "strike": leg.strike,
            "expiry": leg.expiry.isoformat() if leg.expiry else None,
            "mid": leg.mid,
        }
        for leg in ic.legs
    ]
    quotes = {c.symbol: (c.bid, c.ask) for c in ch.contracts}
    v = structure_value(legs, quotes, {})
    assert v == pytest.approx(-ic.net_per_unit, abs=1e-6)  # held package is worth minus the credit
    v_fill = fill_value(legs, quotes, {}, spread_fraction=0.5)
    assert v_fill > v  # paying part of the spread makes the credit smaller
    st = Structure(
        "x",
        "ic",
        "live",
        "shadow",
        "long_iron_condor",
        "TST",
        2,
        legs,
        ic.net_per_unit,
        ic.max_profit,
        ic.max_loss,
        NOW,
    )
    assert exit_reason(st, v, TODAY, 0.5, 2.0, 7) is None
    assert exit_reason(st, v, TODAY + timedelta(days=24), 0.5, 2.0, 7).startswith("dte_exit")
    assert exit_reason(st, -ic.net_per_unit * 0.4, TODAY, 0.5, 2.0, 7).startswith(
        "profit_target"
    )  # package decayed 60%
    assert exit_reason(st, -ic.net_per_unit - 3 * ic.max_profit, TODAY, 0.5, 2.0, 7).startswith("stop")
    assert st.unrealized(-ic.net_per_unit * 0.4) == pytest.approx(0.6 * ic.net_per_unit * 100 * 2, abs=1e-6)


def test_shadow_slot_opens_persists_and_closes(db):
    spec = OptionsSpec(id="ic_tst", template="long_iron_condor", underlying="TST", dte_target=30, spread_fraction=0.0)
    slot = OptionsSlot(spec, db, "live", capital=20_000)
    ch = synthetic_chain()
    quotes = {c.symbol: (c.bid, c.ask) for c in ch.contracts}
    out = slot.decide(TODAY, NOW, 100.0, {}, {"TST": 100.0}, lambda lo, hi: ch)
    assert out["open"] == 1 and out["actions"][0].startswith("opened")
    st = slot.open[0]
    assert st.entry_net > 0 and slot.cash == pytest.approx(20_000 + st.entry_net * 100 * st.qty, abs=1e-6)
    assert abs(slot.equity() - 20_000) < 1e-6  # marked at mid right after entry
    # resume from the database
    again = OptionsSlot(spec, db, "live", capital=20_000)
    again.load()
    assert len(again.open) == 1 and again.open[0].id == st.id and again.cash == pytest.approx(slot.cash)
    # the day before expiry week the DTE rule closes it; every leg decayed to half -> a profit
    decayed = {sym: (b / 2, a / 2) for sym, (b, a) in quotes.items()}
    out2 = again.decide(
        TODAY + timedelta(days=24),
        NOW + timedelta(days=24),
        100.0,
        decayed,
        {"TST": 100.0},
        lambda lo, hi: synthetic_chain(today=TODAY + timedelta(days=24)),
    )
    assert out2["actions"][0].startswith("closed long_iron_condor: dte_exit")
    assert again.trades_today[0].pnl > 0 and again.trades_today[0].exit_reason == "dte_exit"
    statuses = {r["id"]: r["status"] for r in db.structures.recent(5)}
    assert statuses[st.id] == "closed" and db.trades.recent(5, "shadow", "ic_tst")[0].pnl > 0
    assert out2["open"] == 1  # and a fresh one was opened on the new chain
    led = again.ledger("2026-10-18", None, Settings().capital)
    assert led.strategy == "ic_tst" and led.trades == 1 and led.realized_pnl > 0 and led.extra["open_structures"]


def test_config_rules():
    with pytest.raises(ValueError):
        OptionsSpec(id="bad", template="nope")
    with pytest.raises(ValueError):
        OptionsSpec(id="ss", template="short_straddle", mode="live")  # naked short legs: shadow only
    s = Settings.model_validate(
        {"options": [{"id": "ic", "template": "long_iron_condor", "underlying": "SPY", "entry_gate": "vrp"}]}
    )
    assert s.options[0].decision_time.strftime("%H:%M") == "15:40"
    with pytest.raises(ValueError):
        Settings.model_validate({"options": [{"id": "wave_rider", "template": "collar"}]})
