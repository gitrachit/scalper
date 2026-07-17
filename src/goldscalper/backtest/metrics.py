"""Performance metrics over a list of closed trades and an equity curve."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Metrics:
    trades: int
    wins: int
    losses: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    profit_factor: float  # inf when no losses
    expectancy: float  # mean pnl per trade
    max_drawdown_pct: float  # vs running peak equity
    final_equity: float

    def summary(self) -> str:
        return (
            f"trades={self.trades} win_rate={self.win_rate:.1%} "
            f"net=${self.net_pnl:.2f} expectancy=${self.expectancy:.2f}/trade "
            f"PF={self.profit_factor:.2f} maxDD={self.max_drawdown_pct:.1%} "
            f"final_equity=${self.final_equity:.2f}"
        )


def compute_metrics(pnls: list[float], equity_curve: list[float]) -> Metrics:
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)

    peak = float("-inf")
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)

    n = len(pnls)
    return Metrics(
        trades=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / n if n else 0.0,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=gross_profit - gross_loss,
        profit_factor=gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        expectancy=(gross_profit - gross_loss) / n if n else 0.0,
        max_drawdown_pct=max_dd,
        final_equity=equity_curve[-1] if equity_curve else 0.0,
    )
