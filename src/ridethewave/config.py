"""Settings (YAML) and secrets (.env), validated with pydantic.

Two separate objects on purpose:
- ``Settings`` is the strategy/runtime configuration, safe to log and commit as an example.
- ``Secrets`` holds API keys and is never logged.

A typo in settings.yaml fails here at startup, not mid-trade.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ridethewave import PROJECT_ROOT

DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
EXAMPLE_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.example.yaml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def _parse_hhmm(value: str | time) -> time:
    """Accept HH:MM or HH:MM:SS (the latter is what model_dump(mode="json") produces)."""
    if isinstance(value, time):
        return value
    parts = str(value).split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"time must be HH:MM, got {value!r}")
    return time(int(parts[0]), int(parts[1]))


class _Strict(BaseModel):
    """Reject unknown keys so a typo in settings.yaml fails at startup."""

    model_config = {"extra": "forbid"}


class AlpacaSettings(_Strict):
    paper: bool = True
    data_feed: Literal["iex", "sip", "delayed_sip"] = "iex"

    @field_validator("paper")
    @classmethod
    def _must_be_paper(cls, v: bool) -> bool:
        if not v:
            raise ValueError("alpaca.paper must be true; live trading is disabled in this project")
        return v


class UniverseSettings(_Strict):
    source: Literal["most_actives", "movers", "static"] = "most_actives"
    top: int = Field(100, ge=1, le=100)
    static_symbols: list[str] = Field(default_factory=list)
    min_price: float = 5.0
    max_price: float = 500.0
    exchanges: list[str] = Field(default_factory=lambda: ["NYSE", "NASDAQ", "ARCA"])
    refresh_minutes: int = 30

    @model_validator(mode="after")
    def _static_needs_symbols(self) -> UniverseSettings:
        if self.source == "static" and not self.static_symbols:
            raise ValueError("universe.source is 'static' but universe.static_symbols is empty")
        self.static_symbols = [s.upper() for s in self.static_symbols]
        return self


class ScanSettings(_Strict):
    poll_interval_seconds: float = Field(15, ge=1)
    warmup_minutes: int = Field(60, ge=0)


class EntryFilterSettings(_Strict):
    """Optional gates applied after the streak rule. ``None`` disables a gate. Values come from
    docs/research feature analysis; see docs/features/11-entry-filters.md."""

    min_rvol_20: float | None = None  # this bar's volume vs prior 20-bar mean
    min_streak_vol_ratio: float | None = None  # streak volume vs the 20 bars before it
    min_trade_count_ratio: float | None = None
    max_trade_count_ratio: float | None = 0.7  # low ratio = streak made by fewer, larger trades
    max_gain_vs_range: float | None = None  # streak gain / normal minute range; large = move already spent
    min_gain_vs_range: float | None = None
    max_vwap_dist_pct: float | None = None  # how far above session VWAP we are willing to buy
    min_vwap_dist_pct: float | None = None
    max_session_ret_pct: float | None = 0.6  # skip stocks already up a lot on the day
    min_session_ret_pct: float | None = None
    min_spy_ret_5m_pct: float | None = None  # require the market to be rising too
    min_spy_ret_session_pct: float | None = 0.1
    max_range_pct_20: float | None = None  # skip very noisy names
    require_spy: bool = False  # if True and SPY data is missing, do not enter


class EntrySettings(_Strict):
    green_streak_minutes: int = Field(3, ge=1)
    min_streak_gain_pct: float = Field(1.0, ge=0)
    min_streak_volume: int = Field(10_000, ge=0)
    max_positions: int = Field(5, ge=1)
    position_size_pct: float = Field(10, gt=0, le=100)
    entry_limit_buffer_pct: float = Field(0.1, ge=0)
    entry_fill_timeout_seconds: float = Field(30, ge=1)
    entry_start: time = time(9, 31)
    entry_end: time = time(11, 30)
    max_entries_per_symbol_per_day: int = Field(1, ge=1)
    filters: EntryFilterSettings = Field(default_factory=EntryFilterSettings)

    @field_validator("entry_start", "entry_end", mode="before")
    @classmethod
    def _times(cls, v):
        return _parse_hhmm(v)


class ExitSettings(_Strict):
    trail_pct: float = Field(1.5, gt=0)
    min_gain_pct: float = Field(0.5, ge=0)
    hard_stop_pct: float = Field(1.0, ge=0)  # 0 disables
    max_hold_minutes: int = Field(60, ge=0)  # 0 disables
    timeout_exit_only_if_profitable: bool = True
    flatten_at_close: bool = True
    flatten_time: time = time(15, 55)
    # Volatility scaling: when on, trail / min gain / hard stop become multiples of the stock's
    # per-minute range at entry (range_pct_20), clamped to [noise_floor_pct, noise_cap_pct].
    vol_scaled: bool = False
    trail_range_mult: float = Field(2.5, gt=0)
    gain_floor_range_mult: float = Field(1.0, ge=0)
    stop_range_mult: float = Field(2.0, ge=0)
    noise_floor_pct: float = Field(0.2, gt=0)
    noise_cap_pct: float = Field(2.0, gt=0)

    def effective(self, noise_pct: float | None) -> tuple[float, float, float]:
        """(trail_pct, min_gain_pct, hard_stop_pct) for a position with the given entry noise."""
        if not self.vol_scaled or noise_pct is None:
            return self.trail_pct, self.min_gain_pct, self.hard_stop_pct
        n = min(max(noise_pct, self.noise_floor_pct), self.noise_cap_pct)
        return n * self.trail_range_mult, n * self.gain_floor_range_mult, n * self.stop_range_mult

    @field_validator("flatten_time", mode="before")
    @classmethod
    def _times(cls, v):
        return _parse_hhmm(v)


class CapitalSettings(_Strict):
    base_allocation: float = Field(10_000, gt=0)
    reinvest_gains_pct: float = Field(50, ge=0, le=100)
    min_allocation_ratio: float = Field(0.5, gt=0, le=1)


class BacktestSettings(_Strict):
    slippage_pct: float = Field(0.05, ge=0)
    feed: Literal["iex", "sip"] = "sip"


class StrategySpec(_Strict):
    """One entry under ``strategies:``. ``id`` is the accounting key (books, ledgers, trades)."""

    id: str
    kind: str  # registry name: wave_rider | spy_intraday | ...
    enabled: bool = True
    mode: Literal["live", "shadow"] = "shadow"  # shadow = simulated fills on live prices, no real orders
    weight: float = Field(1.0, ge=0)  # share of the daily allocation among live strategies
    params: dict = Field(default_factory=dict)


class PortfolioSpec(_Strict):
    """One entry under ``portfolios:``: a daily-bar strategy (registry in ridethewave.daily) decided once a day
    at ``decision_time`` ET, holding overnight, long or short. Shadow mode only for now: fills are simulated
    against live prices and nothing reaches Alpaca. ``id`` is the accounting key (positions, trades, ledger)."""

    id: str
    kind: str  # daily registry name: price_momentum | residual_momentum | vol_targeting | ...
    enabled: bool = True
    mode: Literal["shadow"] = "shadow"
    weight: float = Field(1.0, ge=0)  # capital = base_allocation * weight
    universe: str = (
        "mega_caps_20"  # named universe, comma-separated symbols, or "scan" (the bot's universe, funds removed)
    )
    rebalance_days: int = Field(1, ge=1)
    decision_time: time = time(15, 50)
    slippage_bps: float = Field(5.0, ge=0)
    max_gross: float = Field(1.0, gt=0, le=3)
    params: dict = Field(default_factory=dict)


class RiskSettings(_Strict):
    """Kill switches the bot applies to itself. See docs/features/14-operator.md."""

    max_daily_loss_pct: float = Field(2.0, ge=0)  # of today's allocation; 0 disables. Breach -> flatten, halt entries
    max_open_loss_pct: float = Field(3.0, ge=0)  # realised + unrealised, same treatment
    winrate_floor_enabled: bool = True
    winrate_lookback_trades: int = Field(60, ge=10)
    winrate_min_trades: int = Field(30, ge=5)  # do not judge before this many live trades
    winrate_breakeven: float | None = None  # None = derive from avg win / avg loss of the lookback
    winrate_halt_probability: float = Field(0.9, gt=0, lt=1)  # P(win rate < breakeven) above this -> halt entries


class OperatorSettings(_Strict):
    report_times_et: list[str] = Field(default_factory=lambda: ["09:00", "11:30", "14:00", "16:15", "21:00"])
    heartbeat_stale_seconds: int = Field(90, ge=30)
    notify: bool = True  # macOS notifications for alerts
    report_dir: str = "data/reports"


class StorageSettings(_Strict):
    db_path: str = "data/ridethewave.db"
    log_dir: str = "data/logs"

    def resolved_db_path(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    def resolved_log_dir(self) -> Path:
        p = Path(self.log_dir)
        return p if p.is_absolute() else PROJECT_ROOT / p


class Settings(_Strict):
    alpaca: AlpacaSettings = Field(default_factory=AlpacaSettings)
    universe: UniverseSettings = Field(default_factory=UniverseSettings)
    scan: ScanSettings = Field(default_factory=ScanSettings)
    entry: EntrySettings = Field(default_factory=EntrySettings)
    exit: ExitSettings = Field(default_factory=ExitSettings)
    capital: CapitalSettings = Field(default_factory=CapitalSettings)
    backtest: BacktestSettings = Field(default_factory=BacktestSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    operator: OperatorSettings = Field(default_factory=OperatorSettings)
    strategies: list[StrategySpec] = Field(
        default_factory=lambda: [StrategySpec(id="wave_rider", kind="wave_rider", mode="live", weight=1.0)]
    )

    portfolios: list[PortfolioSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _strategy_ids_unique(self) -> Settings:
        ids = [x.id for x in self.strategies] + [x.id for x in self.portfolios]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate strategy ids: {ids}")
        if not any(x.enabled for x in self.strategies):
            raise ValueError("no enabled strategies")
        return self

    storage: StorageSettings = Field(default_factory=StorageSettings)


class Secrets(BaseSettings):
    """Loaded from .env (or real environment variables). Never log this object."""

    model_config = SettingsConfigDict(env_file=str(DEFAULT_ENV_PATH), env_file_encoding="utf-8", extra="ignore")

    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_paper: bool = True

    @field_validator("alpaca_paper")
    @classmethod
    def _must_be_paper(cls, v: bool) -> bool:
        if not v:
            raise ValueError("ALPACA_PAPER must be true; live trading is disabled in this project")
        return v

    def __repr__(self) -> str:  # pragma: no cover
        return "Secrets(alpaca_api_key='***', alpaca_secret_key='***', alpaca_paper=True)"

    __str__ = __repr__


def load_settings(path: str | Path | None = None) -> Settings:
    """Load settings.yaml. Falls back to settings.example.yaml if no settings.yaml exists."""
    if path is None:
        path = DEFAULT_SETTINGS_PATH if DEFAULT_SETTINGS_PATH.exists() else EXAMPLE_SETTINGS_PATH
    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f) or {}
    return Settings.model_validate(raw)


def load_secrets(env_path: str | Path | None = None) -> Secrets:
    if env_path is None:
        return Secrets()
    return Secrets(_env_file=str(env_path))  # type: ignore[call-arg]
