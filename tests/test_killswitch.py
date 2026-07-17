from goldscalper.models import AccountState
from tests.conftest import NOW, good_proposal


def drawn_down(equity: float) -> AccountState:
    return AccountState(balance=equity, equity=equity, peak_equity=1000.0)


def test_latches_at_max_drawdown(engine, market):
    decision = engine.evaluate(good_proposal(), drawn_down(900.0), market, NOW)
    assert not decision.approved
    assert engine.kill_switch_latched
    assert any("kill_switch" in r for r in decision.reasons)


def test_stays_latched_after_recovery(engine, market):
    engine.evaluate(good_proposal(), drawn_down(900.0), market, NOW)
    assert engine.kill_switch_latched

    # equity recovers, but the latch must hold until a human resets it
    recovered = AccountState(balance=1000.0, equity=1000.0, peak_equity=1000.0)
    decision = engine.evaluate(good_proposal(), recovered, market, NOW)
    assert not decision.approved
    assert any("kill_switch" in r for r in decision.reasons)


def test_manual_reset_clears_latch(engine, market):
    engine.evaluate(good_proposal(), drawn_down(900.0), market, NOW)
    engine.manual_reset()

    healthy = AccountState(balance=1000.0, equity=1000.0, peak_equity=1000.0)
    decision = engine.evaluate(good_proposal(), healthy, market, NOW)
    assert decision.approved


def test_not_latched_below_threshold(engine, market):
    decision = engine.evaluate(good_proposal(), drawn_down(905.0), market, NOW)
    assert decision.approved  # 9.5% drawdown, limit is 10%
    assert not engine.kill_switch_latched
