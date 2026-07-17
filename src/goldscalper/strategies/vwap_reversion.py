"""VWAP mean-reversion during the London-NY overlap.

A running session "VWAP" is kept from 00:00 GMT as the tick-count-
weighted mean of bar mid closes (Dukascopy retail volume is not
meaningful, so tick count stands in for volume). During the overlap
(12:00-16:00 GMT), when price stretches more than `entry_k` ATRs from
VWAP, propose a reversion trade back to it: target at VWAP, stop
`stop_k` ATRs beyond entry. Limited entries per day.
"""

from __future__ import annotations

from datetime import date

from goldscalper.data.bars import Bar, atr
from goldscalper.models import Direction, ProposalSource, TradeProposal
from goldscalper.strategies.base import in_overlap


class VwapReversion:
    name = "vwap_reversion"

    def __init__(
        self,
        entry_k: float = 1.5,  # ATRs from VWAP to trigger
        stop_k: float = 1.0,  # ATRs beyond entry for the stop
        atr_period: int = 14,
        max_trades_per_day: int = 2,
    ) -> None:
        self.entry_k = entry_k
        self.stop_k = stop_k
        self.atr_period = atr_period
        self.max_trades_per_day = max_trades_per_day
        self._day: date | None = None
        self._weighted_sum = 0.0
        self._weight = 0
        self._taken = 0
        self._history: list[Bar] = []

    def _roll_day(self, bar: Bar) -> None:
        if bar.time.date() != self._day:
            self._day = bar.time.date()
            self._weighted_sum = 0.0
            self._weight = 0
            self._taken = 0

    def on_bar(self, bar: Bar) -> TradeProposal | None:
        self._roll_day(bar)
        self._weighted_sum += bar.mid_close * bar.ticks
        self._weight += bar.ticks
        self._history.append(bar)
        if len(self._history) > self.atr_period + 1:
            self._history.pop(0)

        if not in_overlap(bar) or self._taken >= self.max_trades_per_day or self._weight == 0:
            return None
        bar_atr = atr(self._history, self.atr_period)
        if bar_atr is None or bar_atr <= 0:
            return None

        vwap = self._weighted_sum / self._weight
        deviation = bar.close - vwap
        threshold = self.entry_k * bar_atr

        if deviation <= -threshold:
            self._taken += 1
            return TradeProposal(
                direction=Direction.BUY,
                entry=bar.close,
                stop_loss=bar.close - self.stop_k * bar_atr,
                take_profit=vwap,
                source=ProposalSource.RULES,
                setup_type=self.name,
                rationale=f"close {bar.close:.2f} is {-deviation:.2f} below vwap {vwap:.2f} (atr {bar_atr:.2f})",
            )
        if deviation >= threshold:
            self._taken += 1
            return TradeProposal(
                direction=Direction.SELL,
                entry=bar.close,
                stop_loss=bar.close + self.stop_k * bar_atr,
                take_profit=vwap,
                source=ProposalSource.RULES,
                setup_type=self.name,
                rationale=f"close {bar.close:.2f} is {deviation:.2f} above vwap {vwap:.2f} (atr {bar_atr:.2f})",
            )
        return None
