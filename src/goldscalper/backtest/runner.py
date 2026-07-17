"""Wire a strategy + risk engine + bars into a backtest and report metrics.

This is the reusable glue the CLI and tests call. It does NOT decide
success — that judgment belongs to docs/phase1_criteria.md and a human.
"""

from __future__ import annotations

from goldscalper.backtest.engine import BacktestEngine, BacktestResult
from goldscalper.backtest.metrics import Metrics, compute_metrics
from goldscalper.config import RiskConfig
from goldscalper.journal import Journal
from goldscalper.models import SymbolSpec
from goldscalper.risk import RiskEngine
from goldscalper.strategies.base import Strategy


def run_backtest(
    strategy: Strategy,
    bars,
    *,
    config: RiskConfig | None = None,
    spec: SymbolSpec | None = None,
    starting_balance: float = 1000.0,
    slippage: float = 0.03,
    journal: Journal | None = None,
) -> tuple[BacktestResult, Metrics]:
    config = config or RiskConfig()
    spec = spec or SymbolSpec()
    engine = BacktestEngine(
        strategy=strategy,
        risk_engine=RiskEngine(config, spec),
        spec=spec,
        starting_balance=starting_balance,
        slippage=slippage,
        journal=journal,
    )
    result = engine.run(bars)
    equity = result.equity_curve or [starting_balance]
    metrics = compute_metrics(result.pnls, equity)
    return result, metrics
