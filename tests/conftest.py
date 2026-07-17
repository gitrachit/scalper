from __future__ import annotations

from datetime import datetime, timezone

import pytest

from goldscalper.config import RiskConfig
from goldscalper.models import (
    AccountState,
    Direction,
    MarketState,
    ProposalSource,
    SymbolSpec,
    TradeProposal,
)
from goldscalper.risk import RiskEngine

NOW = datetime(2026, 7, 17, 13, 0, tzinfo=timezone.utc)  # London-NY overlap


@pytest.fixture
def spec() -> SymbolSpec:
    return SymbolSpec()


@pytest.fixture
def config() -> RiskConfig:
    return RiskConfig()


@pytest.fixture
def engine(config, spec) -> RiskEngine:
    return RiskEngine(config, spec)


@pytest.fixture
def account() -> AccountState:
    return AccountState(balance=1000.0, equity=1000.0, peak_equity=1000.0)


@pytest.fixture
def market() -> MarketState:
    return MarketState(bid=2400.00, ask=2400.30, timestamp=NOW)


def good_proposal(**overrides) -> TradeProposal:
    """A buy at 2400.30 with a $3 stop and $6 target — sizes to 0.03 lots
    at 1% risk on $1,000."""
    defaults = dict(
        direction=Direction.BUY,
        entry=2400.30,
        stop_loss=2397.30,
        take_profit=2406.30,
        source=ProposalSource.RULES,
        setup_type="test",
    )
    defaults.update(overrides)
    return TradeProposal(**defaults)
