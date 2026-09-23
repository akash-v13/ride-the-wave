"""Strategy registry: name -> factory. Add a strategy here and in config/settings.yaml."""

from __future__ import annotations

from collections.abc import Callable

from ridethewave.config import Settings
from ridethewave.strategy.base import Strategy


def _wave_rider(settings: Settings, params: dict) -> Strategy:
    from ridethewave.config import EntrySettings, ExitSettings
    from ridethewave.strategy.wave_rider import WaveRider

    entry = EntrySettings.model_validate({**settings.entry.model_dump(mode="json"), **params.get("entry", {})})
    exit_ = ExitSettings.model_validate({**settings.exit.model_dump(mode="json"), **params.get("exit", {})})
    return WaveRider(entry, exit_, bar_minutes=int(params.get("bar_minutes", 1)))


def _spy_intraday(settings: Settings, params: dict) -> Strategy:
    from ridethewave.strategy.spy_intraday import SpyIntradayMomentum

    return SpyIntradayMomentum(params)


def _orb(settings: Settings, params: dict) -> Strategy:
    from ridethewave.strategy.orb import OpeningRangeBreakout

    return OpeningRangeBreakout(params)


REGISTRY: dict[str, Callable[[Settings, dict], Strategy]] = {
    "wave_rider": _wave_rider,
    "spy_intraday": _spy_intraday,
    "orb": _orb,
}


def build(kind: str, settings: Settings, params: dict | None = None) -> Strategy:
    if kind not in REGISTRY:
        raise KeyError(f"unknown strategy '{kind}'; known: {sorted(REGISTRY)}")
    return REGISTRY[kind](settings, params or {})
