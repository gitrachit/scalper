from datetime import timedelta

from goldscalper.models import (
    CalendarEvent,
    Direction,
    MarketState,
    Position,
)
from tests.conftest import NOW, good_proposal


def approve(engine, account, market, proposal=None):
    return engine.evaluate(proposal or good_proposal(), account, market, NOW)


def test_happy_path_sizes_correctly(engine, account, market):
    decision = approve(engine, account, market)
    assert decision.approved
    assert decision.lot == 0.03
    assert decision.risk_amount == 10.0
    assert decision.reasons == ()


def test_requested_risk_is_capped_not_trusted(engine, account, market):
    greedy = good_proposal(requested_risk_pct=0.50)  # LLM asks for 50%
    decision = approve(engine, account, market, greedy)
    assert decision.approved
    assert decision.risk_amount == 10.0  # capped at max_risk_pct (1%)
    assert decision.lot == 0.03


def test_spread_gate(engine, account):
    wide = MarketState(bid=2400.00, ask=2400.90, timestamp=NOW)  # $0.90 spread
    decision = approve(engine, account, wide)
    assert not decision.approved
    assert any("spread_gate" in r for r in decision.reasons)


def test_daily_loss_halt(engine, account, market):
    account.realized_pnl_today = -30.0  # 3% of 1000
    decision = approve(engine, account, market)
    assert not decision.approved
    assert any("daily_loss_halt" in r for r in decision.reasons)


def test_daily_loss_halt_clears_next_day(engine, account, market):
    account.realized_pnl_today = -30.0
    approve(engine, account, market)  # latch the halt

    next_day = NOW + timedelta(days=1)
    fresh_market = MarketState(bid=2400.00, ask=2400.30, timestamp=next_day)
    account.realized_pnl_today = 0.0
    decision = engine.evaluate(good_proposal(), account, fresh_market, next_day)
    assert decision.approved


def test_max_trades_per_day(engine, account, market):
    account.trades_today = 5
    decision = approve(engine, account, market)
    assert not decision.approved
    assert any("max_trades_per_day" in r for r in decision.reasons)


def test_max_concurrent_positions(engine, account, market):
    pos = Position(1, Direction.BUY, 0.01, 2400.0, 2397.0, 2406.0, NOW)
    account.open_positions = [pos, pos]
    decision = approve(engine, account, market)
    assert not decision.approved
    assert any("max_concurrent_positions" in r for r in decision.reasons)


def test_stop_on_wrong_side_rejected(engine, account, market):
    inverted = good_proposal(stop_loss=2403.30)  # stop above a buy entry
    decision = approve(engine, account, market, inverted)
    assert not decision.approved
    assert any("invalid_stop" in r for r in decision.reasons)


def test_target_on_wrong_side_rejected(engine, account, market):
    inverted = good_proposal(take_profit=2398.00)
    decision = approve(engine, account, market, inverted)
    assert not decision.approved
    assert any("invalid_target" in r for r in decision.reasons)


def test_stop_too_tight_rejected(engine, account, market):
    tight = good_proposal(stop_loss=2400.10, take_profit=2400.70)  # 20 pips
    decision = approve(engine, account, market, tight)
    assert not decision.approved
    assert any("stop_too_tight" in r for r in decision.reasons)


def test_stop_too_wide_rejected(engine, account, market):
    wide = good_proposal(stop_loss=2385.00, take_profit=2430.00)  # 1530 pips
    decision = approve(engine, account, market, wide)
    assert not decision.approved
    assert any("stop_too_wide" in r for r in decision.reasons)


def test_unsizeable_trade_rejected(engine, market):
    from goldscalper.models import AccountState

    tiny = AccountState(balance=100.0, equity=100.0, peak_equity=100.0)
    # 1% of $100 = $1 over 300 pips -> 0.0033 lots -> below min -> refuse
    decision = engine.evaluate(good_proposal(), tiny, market, NOW)
    assert not decision.approved
    assert any("unsizeable" in r for r in decision.reasons)


def test_news_blackout(engine, account, market):
    engine.news_filter.load_events(
        [CalendarEvent(time=NOW + timedelta(minutes=10), currency="USD", impact="high", title="CPI")]
    )
    decision = approve(engine, account, market)
    assert not decision.approved
    assert any("news_blackout" in r for r in decision.reasons)


def test_rejection_lists_every_failed_gate(engine, account, market):
    account.trades_today = 99
    account.realized_pnl_today = -500.0
    bad = good_proposal(stop_loss=2403.30, requested_risk_pct=0.5)
    wide = MarketState(bid=2400.00, ask=2402.00, timestamp=NOW)
    decision = engine.evaluate(bad, account, wide, NOW)
    assert not decision.approved
    joined = " ".join(decision.reasons)
    for gate in ("daily_loss_halt", "max_trades_per_day", "spread_gate", "invalid_stop"):
        assert gate in joined
