"""Core value objects shared across the framework.

Conventions (XAUUSD on MT5-style brokers):
- Prices are quoted in USD per oz.
- 1 "pip" = $0.01 price move (one point).
- Pip value for 1.00 lot (100 oz) = $1.00 per pip.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


class Direction(enum.Enum):
    BUY = "buy"
    SELL = "sell"


class ProposalSource(enum.Enum):
    RULES = "rules"
    LLM = "llm"
    MANUAL = "manual"


@dataclass(frozen=True)
class SymbolSpec:
    """Contract specification for the traded symbol."""

    symbol: str = "XAUUSD"
    pip_size: float = 0.01  # price move per pip, in quote currency
    pip_value_per_lot: float = 1.0  # USD per pip for 1.00 lot
    lot_step: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 1.0

    def price_to_pips(self, price_distance: float) -> float:
        return abs(price_distance) / self.pip_size


@dataclass(frozen=True)
class TradeProposal:
    """A structured trade suggestion. Every entry — rules, LLM, or human —
    must go through the risk engine as one of these. The proposal never
    carries a lot size directly; it requests risk and the engine sizes it."""

    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float
    source: ProposalSource
    setup_type: str = ""
    requested_risk_pct: float | None = None  # None -> config default
    confidence: float | None = None
    rationale: str = ""

    def stop_distance(self) -> float:
        return abs(self.entry - self.stop_loss)

    def stop_is_protective(self) -> bool:
        """True when the stop sits on the losing side of the entry."""
        if self.direction is Direction.BUY:
            return self.stop_loss < self.entry
        return self.stop_loss > self.entry

    def target_is_sane(self) -> bool:
        """True when the take-profit sits on the winning side of the entry."""
        if self.direction is Direction.BUY:
            return self.take_profit > self.entry
        return self.take_profit < self.entry


@dataclass(frozen=True)
class MarketState:
    """Point-in-time market snapshot fed to the risk engine."""

    bid: float
    ask: float
    timestamp: datetime
    atr: float | None = None  # in price units, e.g. 3.50 = $3.50

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class Position:
    ticket: int
    direction: Direction
    lot: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime


@dataclass
class AccountState:
    """Broker account snapshot plus session counters the engine gates on."""

    balance: float
    equity: float
    peak_equity: float
    open_positions: list[Position] = field(default_factory=list)
    trades_today: int = 0
    realized_pnl_today: float = 0.0
    session_date: str = ""  # ISO date the daily counters belong to

    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity)


@dataclass(frozen=True)
class CalendarEvent:
    """Economic calendar event used by the news filter."""

    time: datetime
    currency: str
    impact: str  # "high" | "medium" | "low"
    title: str = ""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
