from datetime import timedelta

from goldscalper.broker import PaperBroker
from goldscalper.models import Direction, MarketState
from tests.conftest import NOW


def quote(bid: float, minutes: int = 0) -> MarketState:
    return MarketState(bid=bid, ask=bid + 0.30, timestamp=NOW + timedelta(minutes=minutes))


def make_broker(spec) -> PaperBroker:
    b = PaperBroker(spec, starting_balance=1000.0)
    b.update_quote(quote(2400.00))
    return b


def test_buy_fills_at_ask(spec):
    b = make_broker(spec)
    pos = b.market_order(Direction.BUY, 0.03, 2397.30, 2406.30)
    assert pos.entry_price == 2400.30


def test_take_profit_fill_and_pnl(spec):
    b = make_broker(spec)
    b.market_order(Direction.BUY, 0.03, 2397.30, 2406.30)
    fills = b.update_quote(quote(2406.30, minutes=10))
    assert len(fills) == 1
    assert fills[0]["outcome"] == "tp"
    # 600 pips * $1/pip/lot * 0.03 = $18
    assert abs(fills[0]["pnl"] - 18.0) < 1e-9
    assert abs(b.balance() - 1018.0) < 1e-9


def test_stop_loss_fill_and_pnl(spec):
    b = make_broker(spec)
    b.market_order(Direction.BUY, 0.03, 2397.30, 2406.30)
    fills = b.update_quote(quote(2397.30, minutes=10))
    assert fills[0]["outcome"] == "sl"
    assert abs(fills[0]["pnl"] + 9.0) < 1e-9  # 300 pips * 0.03


def test_gap_through_stop_fills_at_market(spec):
    b = make_broker(spec)
    b.market_order(Direction.BUY, 0.03, 2397.30, 2406.30)
    fills = b.update_quote(quote(2395.00, minutes=1))  # gaps past the stop
    assert fills[0]["outcome"] == "sl"
    assert fills[0]["exit_price"] == 2395.00  # slippage, not the stop price


def test_sell_side_lifecycle(spec):
    b = make_broker(spec)
    pos = b.market_order(Direction.SELL, 0.02, 2403.00, 2394.00)
    assert pos.entry_price == 2400.00  # sells fill at bid
    fills = b.update_quote(quote(2393.70, minutes=5))  # ask 2394.00 hits TP
    assert fills[0]["outcome"] == "tp"
    assert abs(fills[0]["pnl"] - 12.0) < 1e-9  # 600 pips * 0.02


def test_equity_reflects_open_position(spec):
    b = make_broker(spec)
    b.market_order(Direction.BUY, 0.03, 2397.30, 2406.30)
    b.update_quote(quote(2402.00, minutes=2))
    # bid 2402.00 vs entry 2400.30 = +170 pips * 0.03 = $5.10 unrealized
    assert abs(b.equity() - 1005.10) < 1e-9
    assert b.balance() == 1000.0


def test_manual_close(spec):
    b = make_broker(spec)
    pos = b.market_order(Direction.BUY, 0.01, 2397.30, 2406.30)
    b.update_quote(quote(2401.00, minutes=3))
    pnl = b.close_position(pos.ticket)
    assert abs(pnl - 0.70) < 1e-9  # bid 2401.00 - 2400.30 = 70 pips * 0.01
    assert b.positions() == []
