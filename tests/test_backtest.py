from datetime import datetime, timezone

from goldscalper.backtest.metrics import compute_metrics
from goldscalper.backtest.runner import run_backtest
from goldscalper.data.bars import Bar, aggregate_ticks
from goldscalper.data.synthetic import random_walk_ticks, trend_ticks
from goldscalper.journal import Journal
from goldscalper.models import Direction, ProposalSource, TradeProposal
from goldscalper.strategies import AsianBreakout, VwapReversion

START = datetime(2025, 6, 2, 0, 0, tzinfo=timezone.utc)


def _bar(hour, minute, bid, spread=0.30):
    t = datetime(2025, 6, 2, hour, minute, tzinfo=timezone.utc)
    return Bar(t, bid, bid, bid, bid, mean_spread=spread, max_spread=spread, ticks=10)


class _OneShot:
    """Fires a single fixed proposal on a chosen bar, for exercising the
    engine's fill/exit machinery deterministically."""

    name = "oneshot"

    def __init__(self, proposal, fire_hour):
        self._proposal = proposal
        self._fire_hour = fire_hour
        self._fired = False

    def on_bar(self, bar):
        if not self._fired and bar.time.hour == self._fire_hour:
            self._fired = True
            return self._proposal
        return None


def test_metrics_basic_math():
    m = compute_metrics([10.0, -5.0, 8.0, -3.0], [1000, 1010, 1005, 1013, 1010])
    assert m.trades == 4
    assert m.wins == 2 and m.losses == 2
    assert abs(m.net_pnl - 10.0) < 1e-9
    assert abs(m.gross_profit - 18.0) < 1e-9
    assert abs(m.gross_loss - 8.0) < 1e-9
    assert abs(m.profit_factor - 2.25) < 1e-9
    assert abs(m.expectancy - 2.5) < 1e-9


def test_take_profit_exit_pays_spread_and_slippage():
    # long: entry at 2400 close, pays ask spread(0.3)+slip(0.03) => 2400.33
    prop = TradeProposal(Direction.BUY, entry=2400.0, stop_loss=2397.0,
                         take_profit=2406.0, source=ProposalSource.RULES,
                         setup_type="t")
    bars = [
        _bar(12, 0, 2400.0),          # signal bar (fires here)
        _bar(13, 0, 2406.5),          # hits TP 2406.0
    ]
    result, metrics = run_backtest(_OneShot(prop, 12), bars)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.outcome == "tp"
    assert abs(trade.entry_price - 2400.33) < 1e-6
    # pnl = (2406.0 - 2400.33)/0.01 * 1.0 * lot ; lot sized by risk engine
    assert trade.pnl > 0


def test_stop_loss_exit_charges_slippage():
    prop = TradeProposal(Direction.BUY, entry=2400.0, stop_loss=2397.0,
                         take_profit=2406.0, source=ProposalSource.RULES,
                         setup_type="t")
    bars = [
        _bar(12, 0, 2400.0),
        _bar(13, 0, 2396.5),   # gaps below stop
    ]
    result, _ = run_backtest(_OneShot(prop, 12), bars)
    trade = result.trades[0]
    assert trade.outcome == "sl"
    assert trade.pnl < 0


def test_force_flat_at_cutoff():
    prop = TradeProposal(Direction.BUY, entry=2400.0, stop_loss=2397.0,
                         take_profit=2410.0, source=ProposalSource.RULES,
                         setup_type="t")
    bars = [
        _bar(12, 0, 2400.0),
        _bar(20, 0, 2402.0),
        _bar(21, 0, 2403.0),   # flat_hour default 21 -> closed here
        _bar(22, 0, 2404.0),
    ]
    result, _ = run_backtest(_OneShot(prop, 12), bars)
    assert result.trades[0].outcome == "flat_cutoff"


def test_backtest_respects_risk_engine_spread_gate():
    prop = TradeProposal(Direction.BUY, entry=2400.0, stop_loss=2397.0,
                         take_profit=2406.0, source=ProposalSource.RULES,
                         setup_type="t")
    # spread 0.90 > 0.60 gate -> rejected, no trade taken
    bars = [_bar(12, 0, 2400.0, spread=0.90), _bar(13, 0, 2406.5)]
    result, _ = run_backtest(_OneShot(prop, 12), bars)
    assert result.trades == []
    assert result.rejections == 1
    assert "spread_gate" in result.rejection_reasons


def test_full_pipeline_runs_and_journals(tmp_path):
    ticks = random_walk_ticks(START, hours=24 * 3, seed=3)
    bars = list(aggregate_ticks(ticks, 5))
    journal = Journal(tmp_path / "bt.db")
    result, metrics = run_backtest(AsianBreakout(min_range=0.3, max_range=50.0),
                                   bars, journal=journal)
    # every decision the engine saw is journaled
    assert len(journal.decisions()) == result.proposals
    assert metrics.trades == len(result.trades)


def test_trending_market_triggers_breakout_longs():
    # deterministic uptrend: Asian range then sustained rise
    ticks = trend_ticks(START, hours=20, drift=0.02)
    bars = list(aggregate_ticks(ticks, 5))
    result, _ = run_backtest(AsianBreakout(min_range=0.3, max_range=100.0), bars)
    assert result.proposals >= 1
    assert all(t.direction is Direction.BUY for t in result.trades)
