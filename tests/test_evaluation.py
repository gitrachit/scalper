from datetime import datetime, timezone

from goldscalper.backtest.evaluation import (
    ASIAN_GRID,
    VWAP_GRID,
    GridResult,
    _best,
    evaluate_strategy,
    format_report,
    split_is_oos,
)
from goldscalper.backtest.metrics import Metrics, compute_metrics
from goldscalper.data.bars import aggregate_ticks
from goldscalper.data.synthetic import random_walk_ticks

START = datetime(2025, 1, 6, tzinfo=timezone.utc)


def test_grids_match_preregistered_criteria():
    # exactly the grid declared in docs/phase1_criteria.md
    assert [g["buffer"] for g in ASIAN_GRID] == [0.10, 0.20, 0.30]
    assert len(VWAP_GRID) == 4
    assert {(g["entry_k"], g["stop_k"]) for g in VWAP_GRID} == {
        (1.5, 1.0), (1.5, 1.5), (2.0, 1.0), (2.0, 1.5)
    }


def test_split_is_70_30_by_time():
    bars = list(range(100))
    is_bars, oos_bars = split_is_oos(bars)  # type: ignore[arg-type]
    assert len(is_bars) == 70 and len(oos_bars) == 30
    assert is_bars[-1] == 69 and oos_bars[0] == 70  # ordered, no overlap


def _m(expectancy, pf):
    return Metrics(trades=10, wins=5, losses=5, win_rate=0.5, gross_profit=0,
                   gross_loss=0, net_pnl=0, profit_factor=pf,
                   expectancy=expectancy, max_drawdown_pct=0.0, final_equity=0)


def test_best_maximizes_expectancy_then_pf():
    results = [
        GridResult({"a": 1}, _m(0.5, 1.2)),
        GridResult({"a": 2}, _m(1.0, 1.1)),   # higher expectancy wins
        GridResult({"a": 3}, _m(1.0, 1.5)),   # tie on expectancy, better PF
    ]
    assert _best(results).params == {"a": 3}


def test_evaluate_strategy_runs_end_to_end():
    ticks = random_walk_ticks(START, hours=24 * 20, seed=11)
    bars = list(aggregate_ticks(ticks, 5))
    ev = evaluate_strategy("asian_breakout", bars)
    assert ev.best_params in ASIAN_GRID
    assert ev.combined_trades == ev.is_metrics.trades + ev.oos_metrics.trades
    ok, failed = ev.passes()
    assert isinstance(ok, bool)
    # a random walk should NOT pass — sanity that thresholds bite
    assert not ok


def test_report_renders_verdict():
    ticks = random_walk_ticks(START, hours=24 * 20, seed=5)
    bars = list(aggregate_ticks(ticks, 5))
    ev = evaluate_strategy("vwap_reversion", bars)
    report = format_report([ev], window="synthetic")
    assert "vwap_reversion" in report
    assert ("PASS" in report) or ("FAIL" in report)


def test_passes_thresholds_logic():
    from goldscalper.backtest.evaluation import StrategyEvaluation

    strong = Metrics(trades=80, wins=50, losses=30, win_rate=0.62, gross_profit=200,
                     gross_loss=100, net_pnl=100, profit_factor=2.0,
                     expectancy=1.25, max_drawdown_pct=0.08, final_equity=1100)
    ev = StrategyEvaluation("x", [], {}, strong, strong, combined_trades=160)
    ok, failed = ev.passes()
    assert ok and failed == []

    weak = Metrics(trades=40, wins=10, losses=30, win_rate=0.25, gross_profit=50,
                   gross_loss=120, net_pnl=-70, profit_factor=0.42,
                   expectancy=-1.75, max_drawdown_pct=0.30, final_equity=800)
    ev2 = StrategyEvaluation("y", [], {}, weak, weak, combined_trades=80)
    ok2, failed2 = ev2.passes()
    assert not ok2
    assert set(failed2) == {
        "trades>=100", "oos_expectancy>0", "oos_profit_factor>=1.10", "oos_max_drawdown<=15%"
    }
