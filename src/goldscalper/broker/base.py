"""Broker interface. PaperBroker implements it for tests and the demo
simulator; MT5Broker implements it on a Windows host against a live
terminal. The trading loop only ever sees this interface."""

from __future__ import annotations

from typing import Protocol

from goldscalper.models import Direction, MarketState, Position


class Broker(Protocol):
    def market_order(
        self,
        direction: Direction,
        lot: float,
        stop_loss: float,
        take_profit: float,
    ) -> Position: ...

    def close_position(self, ticket: int) -> float:
        """Close and return realized PnL."""
        ...

    def positions(self) -> list[Position]: ...

    def tick(self) -> MarketState: ...

    def balance(self) -> float: ...

    def equity(self) -> float: ...
