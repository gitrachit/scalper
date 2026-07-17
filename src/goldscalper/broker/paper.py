"""Paper broker: deterministic fill simulation for tests and dry runs.

Fills market orders at the current ask (buy) / bid (sell), monitors SL/TP
on every quote update, and tracks balance/equity with XAUUSD pip math.
Conservative fill rule: if a quote gaps through both SL and TP, the SL
fills (worst case wins).
"""

from __future__ import annotations

from datetime import datetime

from goldscalper.models import Direction, MarketState, Position, SymbolSpec


class PaperBroker:
    def __init__(self, spec: SymbolSpec, starting_balance: float) -> None:
        self.spec = spec
        self._balance = starting_balance
        self._positions: dict[int, Position] = {}
        self._next_ticket = 1
        self._market: MarketState | None = None
        self.closed_trades: list[dict] = []

    # ----------------------------------------------------------------- quotes

    def update_quote(self, market: MarketState) -> list[dict]:
        """Feed a new quote; returns any SL/TP fills it triggered."""
        self._market = market
        fills = []
        for ticket in list(self._positions):
            pos = self._positions[ticket]
            exit_price, outcome = self._check_stops(pos, market)
            if outcome is not None:
                fills.append(self._close_at(ticket, exit_price, market.timestamp, outcome))
        return fills

    def _check_stops(
        self, pos: Position, market: MarketState
    ) -> tuple[float, str | None]:
        if pos.direction is Direction.BUY:
            # exits at bid; SL checked first (worst case on a gap)
            if market.bid <= pos.stop_loss:
                return pos.stop_loss if market.bid > pos.stop_loss else market.bid, "sl"
            if market.bid >= pos.take_profit:
                return pos.take_profit, "tp"
        else:
            if market.ask >= pos.stop_loss:
                return pos.stop_loss if market.ask < pos.stop_loss else market.ask, "sl"
            if market.ask <= pos.take_profit:
                return pos.take_profit, "tp"
        return 0.0, None

    # ----------------------------------------------------------------- orders

    def market_order(
        self,
        direction: Direction,
        lot: float,
        stop_loss: float,
        take_profit: float,
    ) -> Position:
        if self._market is None:
            raise RuntimeError("no market quote yet")
        price = self._market.ask if direction is Direction.BUY else self._market.bid
        pos = Position(
            ticket=self._next_ticket,
            direction=direction,
            lot=lot,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            opened_at=self._market.timestamp,
        )
        self._positions[pos.ticket] = pos
        self._next_ticket += 1
        return pos

    def close_position(self, ticket: int) -> float:
        if self._market is None:
            raise RuntimeError("no market quote yet")
        pos = self._positions[ticket]
        price = self._market.bid if pos.direction is Direction.BUY else self._market.ask
        fill = self._close_at(ticket, price, self._market.timestamp, "manual")
        return fill["pnl"]

    def _close_at(
        self, ticket: int, price: float, ts: datetime, outcome: str
    ) -> dict:
        pos = self._positions.pop(ticket)
        pnl = self._pnl(pos, price)
        self._balance += pnl
        fill = {
            "ticket": ticket,
            "exit_price": price,
            "exit_time": ts,
            "pnl": pnl,
            "outcome": outcome,
            "position": pos,
        }
        self.closed_trades.append(fill)
        return fill

    def _pnl(self, pos: Position, exit_price: float) -> float:
        move = exit_price - pos.entry_price
        if pos.direction is Direction.SELL:
            move = -move
        pips = move / self.spec.pip_size
        return pips * self.spec.pip_value_per_lot * pos.lot

    # ------------------------------------------------------------------ state

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def tick(self) -> MarketState:
        if self._market is None:
            raise RuntimeError("no market quote yet")
        return self._market

    def balance(self) -> float:
        return self._balance

    def equity(self) -> float:
        eq = self._balance
        if self._market is not None:
            for pos in self._positions.values():
                price = (
                    self._market.bid
                    if pos.direction is Direction.BUY
                    else self._market.ask
                )
                eq += self._pnl(pos, price)
        return eq
