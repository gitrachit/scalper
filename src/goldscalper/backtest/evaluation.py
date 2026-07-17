"""Phase 1 pre-registered evaluation protocol (docs/phase1_criteria.md).

Pure functions over an already-loaded list of bars so this is unit-
testable with synthetic data and never touches the network. The CLI
script wires it to cached Dukascopy bars.

Protocol, exactly as registered:
1. Split the window 70/30 into in-sample (IS) and out-of-sample (OOS)
   by time.
2. For each strategy, evaluate ONLY the pre-declared parameter grid on
   IS. Pick the best config by expectancy, tie-break profit factor.
3. Run that single best config ONCE on OOS.
4. Judge OOS against the fixed thresholds. Do not re-tune on a miss.
"""

from __future__ import annotations

from dataclasses import dataclass

from goldscalper.backtest.metrics import Metrics
from goldscalper.backtest.runner import run_backtest
from goldscalper.data.bars import Bar
from goldscalper.strategies import AsianBreakout, VwapReversion

# Pre-registered grids — the ONLY optimization permitted.
ASIAN_GRID = [{"buffer": b} for b in (0.10, 0.20, 0.30)]
VWAP_GRID = [
    {"entry_k": ek, "stop_k": sk} for ek in (1.5, 2.0) for sk in (1.0, 1.5)
]

STRATEGY_GRID = {
    "asian_breakout": (AsianBreakout, ASIAN_GRID),
    "vwap_reversion": (VwapReversion, VWAP_GRID),
}

# Pass thresholds (all must hold on OOS).
MIN_TRADES = 100
MIN_OOS_EXPECTANCY = 0.0
MIN_OOS_PROFIT_FACTOR = 1.10
MAX_OOS_DRAWDOWN = 0.15


@dataclass
class GridResult:
    params: dict
    metrics: Metrics


@dataclass
class StrategyEvaluation:
    strategy: str
    is_grid: list[GridResult]
    best_params: dict
    is_metrics: Metrics
    oos_metrics: Metrics
    combined_trades: int

    def passes(self) -> tuple[bool, list[str]]:
        checks = {
            "trades>=100": self.combined_trades >= MIN_TRADES,
            "oos_expectancy>0": self.oos_metrics.expectancy > MIN_OOS_EXPECTANCY,
            "oos_profit_factor>=1.10": self.oos_metrics.profit_factor >= MIN_OOS_PROFIT_FACTOR,
            "oos_max_drawdown<=15%": self.oos_metrics.max_drawdown_pct <= MAX_OOS_DRAWDOWN,
        }
        failed = [name for name, ok in checks.items() if not ok]
        return (not failed), failed


def split_is_oos(bars: list[Bar], is_fraction: float = 0.70) -> tuple[list[Bar], list[Bar]]:
    cut = int(len(bars) * is_fraction)
    return bars[:cut], bars[cut:]


def _best(results: list[GridResult]) -> GridResult:
    # maximize expectancy, tie-break on profit factor; treat inf PF (no
    # losses) as very good but finite for ordering stability
    def key(r: GridResult) -> tuple[float, float]:
        pf = r.metrics.profit_factor
        pf = 1e9 if pf == float("inf") else pf
        return (r.metrics.expectancy, pf)

    return max(results, key=key)


def evaluate_strategy(strategy_name: str, bars: list[Bar], **bt_kwargs) -> StrategyEvaluation:
    cls, grid = STRATEGY_GRID[strategy_name]
    is_bars, oos_bars = split_is_oos(bars)

    is_results = []
    for params in grid:
        _, metrics = run_backtest(cls(**params), is_bars, **bt_kwargs)
        is_results.append(GridResult(params=params, metrics=metrics))

    best = _best(is_results)
    _, oos_metrics = run_backtest(cls(**best.params), oos_bars, **bt_kwargs)

    return StrategyEvaluation(
        strategy=strategy_name,
        is_grid=is_results,
        best_params=best.params,
        is_metrics=best.metrics,
        oos_metrics=oos_metrics,
        combined_trades=best.metrics.trades + oos_metrics.trades,
    )


def format_report(evals: list[StrategyEvaluation], window: str) -> str:
    lines = [f"# Phase 1 evaluation results\n", f"Window: {window}\n"]
    for ev in evals:
        ok, failed = ev.passes()
        lines.append(f"## {ev.strategy}\n")
        lines.append(f"Best IS config: `{ev.best_params}`\n")
        lines.append("| split | " + " | ".join(
            ["trades", "win%", "net$", "expectancy$", "PF", "maxDD%"]) + " |")
        lines.append("|" + "---|" * 7)
        for label, m in (("IS", ev.is_metrics), ("OOS", ev.oos_metrics)):
            pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
            lines.append(
                f"| {label} | {m.trades} | {m.win_rate:.0%} | {m.net_pnl:.2f} | "
                f"{m.expectancy:.3f} | {pf} | {m.max_drawdown_pct:.1%} |"
            )
        verdict = "PASS ✅" if ok else f"FAIL ❌ ({', '.join(failed)})"
        lines.append(f"\n**Verdict: {verdict}** (combined trades: {ev.combined_trades})\n")
    lines.append(
        "\n> Per docs/phase1_criteria.md a failure is the expected outcome and is "
        "recorded as a negative result, not re-tuned away.\n"
    )
    return "\n".join(lines)
