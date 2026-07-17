"""Bar-driven backtest engine.

Deliberately conservative fill model:
- Signals are computed on a CLOSED bar; entries fill at that bar's close
  plus the bar's recorded mean spread (buys pay the ask) plus slippage.
- Intrabar exits use bid OHLC (ask for shorts, approximated as
  bid + mean spread). If both the stop and the target lie inside one
  bar's range, the STOP is assumed hit (worst case wins).
- Slippage is charged on entries and stop exits, not on limit targets.
- Positions still open at `flat_hour` GMT are closed at that bar's close
  (intraday system; avoids swap modelling entirely).

Every proposal goes through the same RiskEngine used live — the
backtest cannot take a trade the live system would refuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from goldscalper.data.bars import Bar
from goldscalper.journal import Journal
from goldscalper.models import (
    AccountState,
    Direction,
    MarketState,
    Position,
    SymbolSpec,
    TradeProposal,
)
from goldscalper.risk import RiskEngine
from goldscalper.strategies.base import Strategy, session_name


@dataclass
class SimTrade:
    ticket: int
    direction: Direction
    lot: float
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    setup_type: str
    exit_time: datetime | None = None
    exit_price: float | None = None
    pnl: float | None = None
    outcome: str | None = None
    mfe: float = 0.0  # best excursion in price units
    mae: float = 0.0  # worst excursion in price units (negative)


@dataclass
class BacktestResult:
    trades: list[SimTrade]
    equity_curve: list[float]
    starting_balance: float
    proposals: int = 0
    rejections: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def pnls(self) -> list[float]:
        return [t.pnl for t in self.trades if t.pnl is not None]


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        risk_engine: RiskEngine,
        spec: SymbolSpec,
        starting_balance: float,
        slippage: float = 0.03,  # $/oz charged on entries and stop exits
        flat_hour: int = 21,  # GMT hour to force-flat
        journal: Journal | None = None,
    ) -> None:
        self.strategy = strategy
        self.risk = risk_engine
        self.spec = spec
        self.slippage = slippage
        self.flat_hour = flat_hour
        self.journal = journal
        self.starting_balance = starting_balance

    # ------------------------------------------------------------------ run

    def run(self, bars) -> BacktestResult:
        balance = self.starting_balance
        peak_equity = self.starting_balance
        equity_curve: list[float] = []
        open_trades: list[SimTrade] = []
        closed: list[SimTrade] = []
        result = BacktestResult([], [], self.starting_balance)
        next_ticket = 1
        day = None
        trades_today = 0
        pnl_today = 0.0
        last_bar: Bar | None = None

        for bar in bars:
            last_bar = bar
            if bar.time.date() != day:
                day = bar.time.date()
                trades_today = 0
                pnl_today = 0.0

            # 1) exits on this bar
            for trade in list(open_trades):
                exit_info = self._check_exit(trade, bar)
                self._update_excursions(trade, bar)
                if exit_info is not None:
                    price, outcome = exit_info
                    self._close(trade, bar, price, outcome)
                    open_trades.remove(trade)
                    closed.append(trade)
                    balance += trade.pnl
                    pnl_today += trade.pnl

            # 2) force-flat at cutoff
            if bar.time.hour >= self.flat_hour:
                for trade in list(open_trades):
                    self._close(trade, bar, self._market_exit_price(trade, bar), "flat_cutoff")
                    open_trades.remove(trade)
                    closed.append(trade)
                    balance += trade.pnl
                    pnl_today += trade.pnl

            # 3) mark to market
            equity = balance + sum(
                self._unrealized(t, bar) for t in open_trades
            )
            peak_equity = max(peak_equity, equity)
            equity_curve.append(equity)

            # 4) strategy signal on the closed bar
            proposal = self.strategy.on_bar(bar)
            if proposal is None:
                continue
            result.proposals += 1

            bar_close_time = bar.time + timedelta(minutes=1)
            market = MarketState(
                bid=bar.close,
                ask=bar.close + bar.mean_spread,
                timestamp=bar_close_time,
            )
            account = AccountState(
                balance=balance,
                equity=equity,
                peak_equity=peak_equity,
                open_positions=[
                    Position(
                        ticket=t.ticket,
                        direction=t.direction,
                        lot=t.lot,
                        entry_price=t.entry_price,
                        stop_loss=t.stop_loss,
                        take_profit=t.take_profit,
                        opened_at=t.entry_time,
                    )
                    for t in open_trades
                ],
                trades_today=trades_today,
                realized_pnl_today=pnl_today,
            )

            decision = self.risk.evaluate(proposal, account, market, bar_close_time)
            if self.journal is not None:
                self.journal.log_decision(bar_close_time, proposal, decision)
            if not decision.approved:
                result.rejections += 1
                for reason in decision.reasons:
                    key = reason.split(":", 1)[0]
                    result.rejection_reasons[key] = result.rejection_reasons.get(key, 0) + 1
                continue

            entry = self._entry_price(proposal, bar)
            trade = SimTrade(
                ticket=next_ticket,
                direction=proposal.direction,
                lot=decision.lot,
                entry_time=bar_close_time,
                entry_price=entry,
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
                setup_type=proposal.setup_type,
            )
            next_ticket += 1
            trades_today += 1
            open_trades.append(trade)
            if self.journal is not None:
                self.journal.open_trade(
                    ticket=trade.ticket,
                    direction=trade.direction.value,
                    lot=trade.lot,
                    entry_time=trade.entry_time,
                    entry_price=trade.entry_price,
                    stop_loss=trade.stop_loss,
                    take_profit=trade.take_profit,
                    setup_type=trade.setup_type,
                    session=session_name(bar),
                    spread_at_entry=bar.mean_spread,
                    rationale=proposal.rationale,
                )

        # end of data: close whatever remains
        if last_bar is not None:
            for trade in open_trades:
                self._close(trade, last_bar, self._market_exit_price(trade, last_bar), "end_of_data")
                closed.append(trade)
                balance += trade.pnl
            if closed:
                equity_curve.append(balance)

        result.trades = closed
        result.equity_curve = equity_curve
        return result

    # ---------------------------------------------------------------- fills

    def _entry_price(self, proposal: TradeProposal, bar: Bar) -> float:
        if proposal.direction is Direction.BUY:
            return bar.close + bar.mean_spread + self.slippage
        return bar.close - self.slippage

    def _exit_side_prices(self, trade: SimTrade, bar: Bar) -> tuple[float, float, float]:
        """(high, low, close) of the price series this trade exits at."""
        if trade.direction is Direction.BUY:
            return bar.high, bar.low, bar.close  # buys exit at bid
        s = bar.mean_spread
        return bar.high + s, bar.low + s, bar.close + s  # sells exit at ask

    def _check_exit(self, trade: SimTrade, bar: Bar) -> tuple[float, str] | None:
        high, low, _ = self._exit_side_prices(trade, bar)
        if trade.direction is Direction.BUY:
            if low <= trade.stop_loss:
                fill = min(trade.stop_loss, high)  # gap: worse of stop/bar
                return fill - self.slippage, "sl"
            if high >= trade.take_profit:
                return trade.take_profit, "tp"
        else:
            if high >= trade.stop_loss:
                fill = max(trade.stop_loss, low)
                return fill + self.slippage, "sl"
            if low <= trade.take_profit:
                return trade.take_profit, "tp"
        return None

    def _market_exit_price(self, trade: SimTrade, bar: Bar) -> float:
        _, _, close = self._exit_side_prices(trade, bar)
        return close

    def _unrealized(self, trade: SimTrade, bar: Bar) -> float:
        return self._pnl_at(trade, self._market_exit_price(trade, bar))

    def _pnl_at(self, trade: SimTrade, exit_price: float) -> float:
        move = exit_price - trade.entry_price
        if trade.direction is Direction.SELL:
            move = -move
        return (move / self.spec.pip_size) * self.spec.pip_value_per_lot * trade.lot

    def _update_excursions(self, trade: SimTrade, bar: Bar) -> None:
        high, low, _ = self._exit_side_prices(trade, bar)
        if trade.direction is Direction.BUY:
            trade.mfe = max(trade.mfe, high - trade.entry_price)
            trade.mae = min(trade.mae, low - trade.entry_price)
        else:
            trade.mfe = max(trade.mfe, trade.entry_price - low)
            trade.mae = min(trade.mae, trade.entry_price - high)

    def _close(self, trade: SimTrade, bar: Bar, price: float, outcome: str) -> None:
        trade.exit_time = bar.time + timedelta(minutes=1)
        trade.exit_price = price
        trade.pnl = self._pnl_at(trade, price)
        trade.outcome = outcome
        if self.journal is not None:
            self.journal.close_trade(
                ticket=trade.ticket,
                exit_time=trade.exit_time,
                exit_price=price,
                pnl=trade.pnl,
                outcome=outcome,
                mfe=trade.mfe,
                mae=trade.mae,
            )
