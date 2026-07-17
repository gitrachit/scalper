"""Risk and engine configuration.

The live values are loaded from a version-controlled YAML file so every
change is auditable. LLM-proposed changes are written to a *staging* file
and must be promoted by a human — never applied directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RiskConfig:
    # Per-trade
    default_risk_pct: float = 0.01  # 1% of balance
    max_risk_pct: float = 0.01  # hard ceiling regardless of what is requested
    min_stop_pips: float = 50.0  # reject stops tighter than this (spread noise)
    max_stop_pips: float = 1000.0  # reject absurd stops ($10)

    # Session limits
    max_daily_loss_pct: float = 0.03  # 3% -> halt until next day
    max_trades_per_day: int = 5
    max_concurrent_positions: int = 2

    # Account-level kill-switch
    max_drawdown_pct: float = 0.10  # 10% from peak equity -> latch, manual reset

    # Market gates
    max_spread: float = 0.60  # USD/oz; reject entries above this
    news_blackout_minutes: int = 30  # +/- window around high-impact events
    news_currencies: tuple[str, ...] = ("USD",)

    # Sizing floor: if the sized lot rounds below min_lot, the trade is
    # rejected rather than upsized (min_lot would exceed the risk budget).

    def __post_init__(self) -> None:
        if not 0 < self.default_risk_pct <= self.max_risk_pct:
            raise ValueError("default_risk_pct must be in (0, max_risk_pct]")
        if self.max_risk_pct > 0.02:
            raise ValueError("max_risk_pct above 2% is not permitted by design")
        if self.max_daily_loss_pct <= 0 or self.max_drawdown_pct <= 0:
            raise ValueError("loss limits must be positive")
        if self.min_stop_pips <= 0 or self.max_stop_pips <= self.min_stop_pips:
            raise ValueError("invalid stop pip bounds")


def load_risk_config(path: str | Path) -> RiskConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    known = {f.name for f in fields(RiskConfig)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown risk config keys: {sorted(unknown)}")
    if "news_currencies" in raw:
        raw["news_currencies"] = tuple(raw["news_currencies"])
    return RiskConfig(**raw)


def dump_risk_config(config: RiskConfig, path: str | Path) -> None:
    data = asdict(config)
    data["news_currencies"] = list(data["news_currencies"])
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False))
