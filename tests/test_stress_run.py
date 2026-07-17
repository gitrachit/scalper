"""Phase 0 exit benchmark from the blueprint: the risk engine must
refuse every out-of-bounds order in a simulated stress run, and the
journal must hold a complete audit trail of the refusals."""

import json
from datetime import timedelta

from goldscalper.journal import Journal
from goldscalper.models import (
    AccountState,
    CalendarEvent,
    Direction,
    MarketState,
    ProposalSource,
)
from tests.conftest import NOW, good_proposal


def test_stress_run_refuses_every_out_of_bounds_order(engine, tmp_path):
    journal = Journal(tmp_path / "stress.db")
    engine.news_filter.load_events(
        [CalendarEvent(time=NOW + timedelta(minutes=90), currency="USD",
                       impact="high", title="FOMC")]
    )

    healthy = lambda: AccountState(balance=1000.0, equity=1000.0, peak_equity=1000.0)
    normal_market = MarketState(bid=2400.00, ask=2400.30, timestamp=NOW)

    # (label, proposal, account, market, time) — every one must be refused
    hostile: list[tuple] = []

    # LLM requests absurd risk with a hair-thin stop
    hostile.append((
        "greedy_llm",
        good_proposal(source=ProposalSource.LLM, requested_risk_pct=0.9,
                      stop_loss=2400.25, take_profit=2400.80),
        healthy(), normal_market, NOW,
    ))
    # stop on the wrong side (would lock in a loss path with no protection)
    hostile.append((
        "inverted_stop",
        good_proposal(stop_loss=2405.00),
        healthy(), normal_market, NOW,
    ))
    # trading into a news window
    hostile.append((
        "news_window",
        good_proposal(),
        healthy(), MarketState(bid=2400.00, ask=2400.30,
                               timestamp=NOW + timedelta(minutes=70)),
        NOW + timedelta(minutes=70),
    ))
    # spread blowout (Asian session / news spike conditions)
    hostile.append((
        "spread_blowout",
        good_proposal(),
        healthy(), MarketState(bid=2400.00, ask=2401.80, timestamp=NOW), NOW,
    ))
    # already lost the daily budget
    down = healthy(); down.realized_pnl_today = -35.0
    hostile.append(("daily_loss", good_proposal(), down, normal_market, NOW))
    # overtrading
    churner = healthy(); churner.trades_today = 12
    hostile.append(("overtrading", good_proposal(), churner, normal_market, NOW))
    # account in deep drawdown
    blown = AccountState(balance=880.0, equity=880.0, peak_equity=1000.0)
    hostile.append(("drawdown", good_proposal(), blown, normal_market, NOW))
    # sell with stop and target both inverted
    hostile.append((
        "inverted_sell",
        good_proposal(direction=Direction.SELL, entry=2400.00,
                      stop_loss=2397.00, take_profit=2406.00),
        healthy(), normal_market, NOW,
    ))

    for label, proposal, account, market, when in hostile:
        decision = engine.evaluate(proposal, account, market, when)
        journal.log_decision(when, proposal, decision)
        assert not decision.approved, f"stress case '{label}' was wrongly approved"
        assert decision.lot == 0.0
        assert decision.reasons, f"stress case '{label}' rejected without reasons"

    # audit trail: one journal row per refusal, each with recorded reasons
    rows = journal.decisions()
    assert len(rows) == len(hostile)
    assert all(row["approved"] == 0 for row in rows)
    assert all(json.loads(row["reject_reasons"]) for row in rows)

    # after the kill-switch latched (drawdown case), even a perfect setup
    # on a healthy snapshot must stay refused until a human resets
    decision = engine.evaluate(good_proposal(), healthy(), normal_market, NOW)
    assert not decision.approved

    # a human reset clears the kill-switch, but the daily-loss halt still
    # holds for the rest of the day
    engine.manual_reset()
    decision = engine.evaluate(good_proposal(), healthy(), normal_market, NOW)
    assert not decision.approved
    assert any("daily_loss_halt" in r for r in decision.reasons)

    # next day with a healthy account, everything trades normally again
    tomorrow = NOW + timedelta(days=1)
    fresh_market = MarketState(bid=2400.00, ask=2400.30, timestamp=tomorrow)
    decision = engine.evaluate(good_proposal(), healthy(), fresh_market, tomorrow)
    assert decision.approved and decision.lot == 0.03
