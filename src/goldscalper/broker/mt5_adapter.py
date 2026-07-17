"""MT5 broker adapter (Windows-only).

The `MetaTrader5` pip package only exists on Windows and requires a
running MT5 terminal with "Allow algorithmic trading" enabled. This
module imports lazily so the rest of the framework (risk engine, tests,
paper trading) runs anywhere. Wire it up in Phase 0's VPS step; until
then it raises a clear error instead of half-working.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from goldscalper.models import Direction, MarketState, Position, SymbolSpec


def _mt5():
    if sys.platform != "win32":
        raise RuntimeError(
            "The MetaTrader5 package is Windows-only. Use PaperBroker for "
            "development, or run this on the Windows VPS next to the MT5 terminal."
        )
    import MetaTrader5 as mt5  # type: ignore[import-not-found]

    return mt5


class MT5Broker:
    """Thin adapter over the MetaTrader5 package implementing the Broker
    protocol. Orders reaching this class have ALREADY passed the risk
    engine — it performs no risk logic of its own."""

    def __init__(self, spec: SymbolSpec, magic: int = 900_001) -> None:
        self.spec = spec
        self.magic = magic
        self._mt5 = _mt5()
        if not self._mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {self._mt5.last_error()}")
        if not self._mt5.symbol_select(spec.symbol, True):
            raise RuntimeError(f"could not select symbol {spec.symbol}")

    def market_order(
        self,
        direction: Direction,
        lot: float,
        stop_loss: float,
        take_profit: float,
    ) -> Position:
        mt5 = self._mt5
        tick = mt5.symbol_info_tick(self.spec.symbol)
        is_buy = direction is Direction.BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.spec.symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": tick.ask if is_buy else tick.bid,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": 20,
            "magic": self.magic,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"order_send failed: {result}")
        return Position(
            ticket=result.order,
            direction=direction,
            lot=lot,
            entry_price=result.price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            opened_at=datetime.now(timezone.utc),
        )

    def close_position(self, ticket: int) -> float:
        mt5 = self._mt5
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise RuntimeError(f"position {ticket} not found")
        pos = positions[0]
        tick = mt5.symbol_info_tick(self.spec.symbol)
        is_buy = pos.type == mt5.POSITION_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.spec.symbol,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 20,
            "magic": self.magic,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"close failed: {result}")
        return float(pos.profit)

    def positions(self) -> list[Position]:
        mt5 = self._mt5
        out = []
        for pos in mt5.positions_get(symbol=self.spec.symbol) or []:
            if pos.magic != self.magic:
                continue
            out.append(
                Position(
                    ticket=pos.ticket,
                    direction=Direction.BUY if pos.type == mt5.POSITION_TYPE_BUY else Direction.SELL,
                    lot=pos.volume,
                    entry_price=pos.price_open,
                    stop_loss=pos.sl,
                    take_profit=pos.tp,
                    opened_at=datetime.fromtimestamp(pos.time, tz=timezone.utc),
                )
            )
        return out

    def tick(self) -> MarketState:
        tick = self._mt5.symbol_info_tick(self.spec.symbol)
        return MarketState(
            bid=tick.bid,
            ask=tick.ask,
            timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc),
        )

    def balance(self) -> float:
        return float(self._mt5.account_info().balance)

    def equity(self) -> float:
        return float(self._mt5.account_info().equity)
