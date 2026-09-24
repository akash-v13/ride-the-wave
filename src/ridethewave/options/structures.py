"""The 57 Chapter-2 option structures of *151 Trading Strategies* as declarative leg templates (from TraderPro).

One engine, 57 data entries (2.52 long box is catalog-only: retail-unfillable).
Strike rules are resolved against a live chain by options/resolver.py:
  atm        — strike nearest spot
  otm(n)     — n strike-steps out-of-the-money (calls above / puts below spot)
  itm(n)     — n strike-steps in-the-money
  same(i)    — same strike as leg i
Expiry buckets: "near" (the bot's target DTE) and "far" (target + far_offset)
for calendars/diagonals.

`alpaca_placeable`: False = a naked short leg
somewhere, which Alpaca level 3 rejects in a multi-leg order, so shadow only.
Structures with a stock leg route as sequential orders on Alpaca (stock first).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Instrument = Literal["call", "put", "stock"]
Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class StrikeRule:
    kind: Literal["atm", "otm", "itm", "same"]
    n: int = 0  # steps for otm/itm, leg index for same


ATM = StrikeRule("atm")


def OTM(n: int) -> StrikeRule:  # noqa: N802 - reads like a constructor
    return StrikeRule("otm", n)


def ITM(n: int) -> StrikeRule:  # noqa: N802
    return StrikeRule("itm", n)


def SAME(i: int) -> StrikeRule:  # noqa: N802
    return StrikeRule("same", i)


@dataclass(frozen=True)
class Leg:
    instrument: Instrument
    side: Side
    ratio: int = 1
    strike: StrikeRule | None = None  # None for stock legs
    expiry: Literal["near", "far"] = "near"


@dataclass(frozen=True)
class StructureTemplate:
    id: str
    catalog_id: str
    name: str
    legs: tuple[Leg, ...]
    direction: int  # +1 bullish / −1 bearish / 0 neutral
    vol_bias: int  # +1 long vol / −1 short vol / 0
    defined_risk: bool
    alpaca_placeable: bool
    notes: str = ""

    @property
    def has_stock_leg(self) -> bool:
        return any(leg.instrument == "stock" for leg in self.legs)


def _t(id_, cat, name, legs, direction, vol, defined, placeable, notes=""):
    return StructureTemplate(id_, cat, name, tuple(legs), direction, vol, defined, placeable, notes)


C, P, S = "call", "put", "stock"
B, SL = "buy", "sell"

TEMPLATES: dict[str, StructureTemplate] = {
    t.id: t
    for t in [
        # --- covered / protective (stock leg → sequential routing on Alpaca) ---
        _t("covered_call", "2.2", "Covered call", [Leg(S, B), Leg(C, SL, strike=OTM(2))], +1, -1, True, True),
        _t(
            "covered_put",
            "2.3",
            "Covered put",
            [Leg(S, SL), Leg(P, SL, strike=OTM(2))],
            -1,
            -1,
            False,
            True,
            "unlimited upside risk from short stock",
        ),
        _t("protective_put", "2.4", "Protective put", [Leg(S, B), Leg(P, B, strike=OTM(2))], +1, +1, True, True),
        _t("protective_call", "2.5", "Protective call", [Leg(S, SL), Leg(C, B, strike=OTM(2))], -1, +1, True, True),
        # --- verticals ---
        _t(
            "bull_call_spread",
            "2.6",
            "Bull call spread",
            [Leg(C, B, strike=ATM), Leg(C, SL, strike=OTM(2))],
            +1,
            0,
            True,
            True,
        ),
        _t(
            "bull_put_spread",
            "2.7",
            "Bull put spread",
            [Leg(P, SL, strike=OTM(2)), Leg(P, B, strike=OTM(4))],
            +1,
            -1,
            True,
            True,
        ),
        _t(
            "bear_call_spread",
            "2.8",
            "Bear call spread",
            [Leg(C, SL, strike=OTM(2)), Leg(C, B, strike=OTM(4))],
            -1,
            -1,
            True,
            True,
        ),
        _t(
            "bear_put_spread",
            "2.9",
            "Bear put spread",
            [Leg(P, B, strike=ATM), Leg(P, SL, strike=OTM(2))],
            -1,
            0,
            True,
            True,
        ),
        # --- synthetics & combos (naked short leg → sim-only) ---
        _t(
            "long_synthetic_forward",
            "2.10",
            "Long synthetic forward",
            [Leg(C, B, strike=ATM), Leg(P, SL, strike=SAME(0))],
            +1,
            0,
            False,
            False,
        ),
        _t(
            "short_synthetic_forward",
            "2.11",
            "Short synthetic forward",
            [Leg(P, B, strike=ATM), Leg(C, SL, strike=SAME(0))],
            -1,
            0,
            False,
            False,
        ),
        _t(
            "long_combo",
            "2.12",
            "Long combo",
            [Leg(C, B, strike=OTM(2)), Leg(P, SL, strike=OTM(2))],
            +1,
            0,
            False,
            False,
        ),
        _t(
            "short_combo",
            "2.13",
            "Short combo",
            [Leg(P, B, strike=OTM(2)), Leg(C, SL, strike=OTM(2))],
            -1,
            0,
            False,
            False,
        ),
        # --- ladders ---
        _t(
            "bull_call_ladder",
            "2.14",
            "Bull call ladder",
            [Leg(C, B, strike=ATM), Leg(C, SL, strike=OTM(2)), Leg(C, SL, strike=OTM(4))],
            +1,
            -1,
            False,
            False,
            "extra naked short call",
        ),
        _t(
            "bull_put_ladder",
            "2.15",
            "Bull put ladder",
            [Leg(P, SL, strike=ATM), Leg(P, B, strike=OTM(2)), Leg(P, B, strike=OTM(4))],
            +1,
            +1,
            True,
            True,
        ),
        _t(
            "bear_call_ladder",
            "2.16",
            "Bear call ladder",
            [Leg(C, SL, strike=ATM), Leg(C, B, strike=OTM(2)), Leg(C, B, strike=OTM(4))],
            -1,
            +1,
            True,
            True,
        ),
        _t(
            "bear_put_ladder",
            "2.17",
            "Bear put ladder",
            [Leg(P, B, strike=ATM), Leg(P, SL, strike=OTM(2)), Leg(P, SL, strike=OTM(4))],
            -1,
            -1,
            False,
            False,
            "extra naked short put",
        ),
        # --- calendars & diagonals ---
        _t(
            "calendar_call_spread",
            "2.18",
            "Calendar call spread",
            [Leg(C, SL, strike=ATM, expiry="near"), Leg(C, B, strike=SAME(0), expiry="far")],
            0,
            -1,
            True,
            True,
        ),
        _t(
            "calendar_put_spread",
            "2.19",
            "Calendar put spread",
            [Leg(P, SL, strike=ATM, expiry="near"), Leg(P, B, strike=SAME(0), expiry="far")],
            0,
            -1,
            True,
            True,
        ),
        _t(
            "diagonal_call_spread",
            "2.20",
            "Diagonal call spread",
            [Leg(C, SL, strike=OTM(2), expiry="near"), Leg(C, B, strike=ITM(2), expiry="far")],
            +1,
            -1,
            True,
            True,
        ),
        _t(
            "diagonal_put_spread",
            "2.21",
            "Diagonal put spread",
            [Leg(P, SL, strike=OTM(2), expiry="near"), Leg(P, B, strike=ITM(2), expiry="far")],
            -1,
            -1,
            True,
            True,
        ),
        # --- long volatility ---
        _t(
            "long_straddle",
            "2.22",
            "Long straddle",
            [Leg(C, B, strike=ATM), Leg(P, B, strike=SAME(0))],
            0,
            +1,
            True,
            True,
        ),
        _t(
            "long_strangle",
            "2.23",
            "Long strangle",
            [Leg(C, B, strike=OTM(2)), Leg(P, B, strike=OTM(2))],
            0,
            +1,
            True,
            True,
        ),
        _t("long_guts", "2.24", "Long guts", [Leg(C, B, strike=ITM(2)), Leg(P, B, strike=ITM(2))], 0, +1, True, True),
        # --- short volatility, naked (sim-only) ---
        _t(
            "short_straddle",
            "2.25",
            "Short straddle",
            [Leg(C, SL, strike=ATM), Leg(P, SL, strike=SAME(0))],
            0,
            -1,
            False,
            False,
            "undefined risk both sides — NEVER for live promotion",
        ),
        _t(
            "short_strangle",
            "2.26",
            "Short strangle",
            [Leg(C, SL, strike=OTM(2)), Leg(P, SL, strike=OTM(2))],
            0,
            -1,
            False,
            False,
        ),
        _t(
            "short_guts",
            "2.27",
            "Short guts",
            [Leg(C, SL, strike=ITM(2)), Leg(P, SL, strike=ITM(2))],
            0,
            -1,
            False,
            False,
        ),
        # --- synthetic straddles (stock + ratio options) ---
        _t(
            "long_call_synthetic_straddle",
            "2.28",
            "Long call synthetic straddle",
            [Leg(S, SL), Leg(C, B, ratio=2, strike=ATM)],
            0,
            +1,
            True,
            True,
        ),
        _t(
            "long_put_synthetic_straddle",
            "2.29",
            "Long put synthetic straddle",
            [Leg(S, B), Leg(P, B, ratio=2, strike=ATM)],
            0,
            +1,
            True,
            True,
        ),
        _t(
            "short_call_synthetic_straddle",
            "2.30",
            "Short call synthetic straddle",
            [Leg(S, B), Leg(C, SL, ratio=2, strike=ATM)],
            0,
            -1,
            False,
            False,
        ),
        _t(
            "short_put_synthetic_straddle",
            "2.31",
            "Short put synthetic straddle",
            [Leg(S, SL), Leg(P, SL, ratio=2, strike=ATM)],
            0,
            -1,
            False,
            False,
        ),
        _t(
            "covered_short_straddle",
            "2.32",
            "Covered short straddle",
            [Leg(S, B), Leg(C, SL, strike=ATM), Leg(P, SL, strike=SAME(1))],
            +1,
            -1,
            False,
            False,
        ),
        _t(
            "covered_short_strangle",
            "2.33",
            "Covered short strangle",
            [Leg(S, B), Leg(C, SL, strike=OTM(2)), Leg(P, SL, strike=OTM(2))],
            +1,
            -1,
            False,
            False,
        ),
        # --- straps / strips ---
        _t("strap", "2.34", "Strap", [Leg(C, B, ratio=2, strike=ATM), Leg(P, B, strike=SAME(0))], +1, +1, True, True),
        _t("strip", "2.35", "Strip", [Leg(C, B, strike=ATM), Leg(P, B, ratio=2, strike=SAME(0))], -1, +1, True, True),
        # --- backspreads / ratio spreads ---
        _t(
            "call_ratio_backspread",
            "2.36",
            "Call ratio backspread",
            [Leg(C, SL, strike=ATM), Leg(C, B, ratio=2, strike=OTM(2))],
            +1,
            +1,
            True,
            True,
        ),
        _t(
            "put_ratio_backspread",
            "2.37",
            "Put ratio backspread",
            [Leg(P, SL, strike=ATM), Leg(P, B, ratio=2, strike=OTM(2))],
            -1,
            +1,
            True,
            True,
        ),
        _t(
            "ratio_call_spread",
            "2.38",
            "Ratio call spread",
            [Leg(C, B, strike=ATM), Leg(C, SL, ratio=2, strike=OTM(2))],
            0,
            -1,
            False,
            False,
            "extra naked short call",
        ),
        _t(
            "ratio_put_spread",
            "2.39",
            "Ratio put spread",
            [Leg(P, B, strike=ATM), Leg(P, SL, ratio=2, strike=OTM(2))],
            0,
            -1,
            False,
            False,
            "extra naked short put",
        ),
        # --- butterflies ---
        _t(
            "long_call_butterfly",
            "2.40",
            "Long call butterfly",
            [Leg(C, B, strike=ITM(2)), Leg(C, SL, ratio=2, strike=ATM), Leg(C, B, strike=OTM(2))],
            0,
            -1,
            True,
            True,
        ),
        _t(
            "modified_call_butterfly",
            "2.40.1",
            "Modified call butterfly",
            [Leg(C, B, strike=ITM(2)), Leg(C, SL, ratio=2, strike=ATM), Leg(C, B, strike=OTM(1))],
            +1,
            -1,
            True,
            True,
            "asymmetric wings — bullish tilt",
        ),
        _t(
            "long_put_butterfly",
            "2.41",
            "Long put butterfly",
            [Leg(P, B, strike=ITM(2)), Leg(P, SL, ratio=2, strike=ATM), Leg(P, B, strike=OTM(2))],
            0,
            -1,
            True,
            True,
        ),
        _t(
            "modified_put_butterfly",
            "2.41.1",
            "Modified put butterfly",
            [Leg(P, B, strike=ITM(2)), Leg(P, SL, ratio=2, strike=ATM), Leg(P, B, strike=OTM(1))],
            +1,
            -1,
            True,
            True,
        ),
        _t(
            "short_call_butterfly",
            "2.42",
            "Short call butterfly",
            [Leg(C, SL, strike=ITM(2)), Leg(C, B, ratio=2, strike=ATM), Leg(C, SL, strike=OTM(2))],
            0,
            +1,
            True,
            True,
        ),
        _t(
            "short_put_butterfly",
            "2.43",
            "Short put butterfly",
            [Leg(P, SL, strike=ITM(2)), Leg(P, B, ratio=2, strike=ATM), Leg(P, SL, strike=OTM(2))],
            0,
            +1,
            True,
            True,
        ),
        # --- iron butterflies / condors ---
        _t(
            "long_iron_butterfly",
            "2.44",
            "Long iron butterfly",
            [Leg(P, B, strike=OTM(2)), Leg(P, SL, strike=ATM), Leg(C, SL, strike=SAME(1)), Leg(C, B, strike=OTM(2))],
            0,
            -1,
            True,
            True,
            "income: short straddle + wings",
        ),
        _t(
            "short_iron_butterfly",
            "2.45",
            "Short iron butterfly",
            [Leg(P, SL, strike=OTM(2)), Leg(P, B, strike=ATM), Leg(C, B, strike=SAME(1)), Leg(C, SL, strike=OTM(2))],
            0,
            +1,
            True,
            True,
        ),
        _t(
            "long_call_condor",
            "2.46",
            "Long call condor",
            [Leg(C, B, strike=ITM(4)), Leg(C, SL, strike=ITM(2)), Leg(C, SL, strike=OTM(2)), Leg(C, B, strike=OTM(4))],
            0,
            -1,
            True,
            True,
        ),
        _t(
            "long_put_condor",
            "2.47",
            "Long put condor",
            [Leg(P, B, strike=ITM(4)), Leg(P, SL, strike=ITM(2)), Leg(P, SL, strike=OTM(2)), Leg(P, B, strike=OTM(4))],
            0,
            -1,
            True,
            True,
        ),
        _t(
            "short_call_condor",
            "2.48",
            "Short call condor",
            [Leg(C, SL, strike=ITM(4)), Leg(C, B, strike=ITM(2)), Leg(C, B, strike=OTM(2)), Leg(C, SL, strike=OTM(4))],
            0,
            +1,
            True,
            True,
        ),
        _t(
            "short_put_condor",
            "2.49",
            "Short put condor",
            [Leg(P, SL, strike=ITM(4)), Leg(P, B, strike=ITM(2)), Leg(P, B, strike=OTM(2)), Leg(P, SL, strike=OTM(4))],
            0,
            +1,
            True,
            True,
        ),
        _t(
            "long_iron_condor",
            "2.50",
            "Long iron condor",
            [Leg(P, B, strike=OTM(4)), Leg(P, SL, strike=OTM(2)), Leg(C, SL, strike=OTM(2)), Leg(C, B, strike=OTM(4))],
            0,
            -1,
            True,
            True,
            "the flagship income structure: sell inner strangle, buy outer wings",
        ),
        _t(
            "short_iron_condor",
            "2.51",
            "Short iron condor",
            [Leg(P, SL, strike=OTM(4)), Leg(P, B, strike=OTM(2)), Leg(C, B, strike=OTM(2)), Leg(C, SL, strike=OTM(4))],
            0,
            +1,
            True,
            True,
        ),
        # 2.52 long box: catalog-only (pure rate arb, retail-unfillable) — no template
        # --- collar & seagulls ---
        _t(
            "collar",
            "2.53",
            "Collar",
            [Leg(S, B), Leg(P, B, strike=OTM(2)), Leg(C, SL, strike=OTM(2))],
            +1,
            0,
            True,
            True,
        ),
        _t(
            "bullish_short_seagull",
            "2.54",
            "Bullish short seagull",
            [Leg(P, SL, strike=OTM(2)), Leg(C, B, strike=ATM), Leg(C, SL, strike=OTM(2))],
            +1,
            0,
            False,
            False,
            "naked short put finances the call spread",
        ),
        _t(
            "bearish_long_seagull",
            "2.55",
            "Bearish long seagull",
            [Leg(P, B, strike=OTM(2)), Leg(C, SL, strike=ATM), Leg(C, B, strike=OTM(2))],
            -1,
            0,
            True,
            True,
        ),
        _t(
            "bearish_short_seagull",
            "2.56",
            "Bearish short seagull",
            [Leg(C, SL, strike=OTM(2)), Leg(P, B, strike=ATM), Leg(P, SL, strike=OTM(2))],
            -1,
            0,
            False,
            False,
            "naked short call finances the put spread",
        ),
        _t(
            "bullish_long_seagull",
            "2.57",
            "Bullish long seagull",
            [Leg(C, B, strike=OTM(2)), Leg(P, SL, strike=ATM), Leg(P, B, strike=OTM(2))],
            +1,
            0,
            True,
            True,
        ),
    ]
}


def get_template(template_id: str) -> StructureTemplate:
    return TEMPLATES[template_id]


def by_catalog_id(catalog_id: str) -> StructureTemplate | None:
    return next((t for t in TEMPLATES.values() if t.catalog_id == catalog_id), None)
