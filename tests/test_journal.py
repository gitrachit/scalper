import json
from datetime import timedelta

from goldscalper.journal import Journal
from goldscalper.risk.engine import RiskDecision
from tests.conftest import NOW, good_proposal


def make_journal(tmp_path) -> Journal:
    return Journal(tmp_path / "journal.db")


def test_logs_approved_decision(tmp_path):
    j = make_journal(tmp_path)
    decision = RiskDecision(approved=True, lot=0.03, risk_amount=10.0)
    j.log_decision(NOW, good_proposal(), decision)
    rows = j.decisions()
    assert len(rows) == 1
    assert rows[0]["approved"] == 1
    assert rows[0]["lot"] == 0.03
    assert json.loads(rows[0]["reject_reasons"]) == []


def test_logs_rejection_with_reasons(tmp_path):
    j = make_journal(tmp_path)
    decision = RiskDecision.rejected(["spread_gate: 0.90 > 0.60", "kill_switch: latched"])
    j.log_decision(NOW, good_proposal(), decision)
    reasons = json.loads(j.decisions()[0]["reject_reasons"])
    assert len(reasons) == 2
    assert "spread_gate" in reasons[0]


def test_trade_lifecycle_and_daily_stats(tmp_path):
    j = make_journal(tmp_path)
    j.open_trade(
        ticket=1, direction="buy", lot=0.03, entry_time=NOW, entry_price=2400.30,
        stop_loss=2397.30, take_profit=2406.30, setup_type="breakout",
        session="overlap", spread_at_entry=0.30, atr_at_entry=3.5,
    )
    j.close_trade(
        ticket=1, exit_time=NOW + timedelta(hours=1), exit_price=2406.30,
        pnl=18.0, outcome="tp", mfe=6.2, mae=-0.8,
    )
    trades = j.trades()
    assert len(trades) == 1
    assert trades[0]["outcome"] == "tp"
    assert trades[0]["pnl"] == 18.0

    stats = j.daily_stats(NOW.date().isoformat())
    assert stats == {"trades": 1, "pnl": 18.0, "wins": 1}


def test_close_only_touches_open_trade(tmp_path):
    j = make_journal(tmp_path)
    j.open_trade(ticket=7, direction="buy", lot=0.01, entry_time=NOW,
                 entry_price=2400.0, stop_loss=2397.0, take_profit=2406.0)
    j.close_trade(ticket=7, exit_time=NOW, exit_price=2397.0, pnl=-3.0, outcome="sl")
    # second close on the same ticket must be a no-op
    j.close_trade(ticket=7, exit_time=NOW, exit_price=9999.0, pnl=999.0, outcome="tp")
    assert j.trades()[0]["pnl"] == -3.0
