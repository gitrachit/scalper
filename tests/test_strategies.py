from datetime import datetime, timezone

from goldscalper.data.bars import aggregate_ticks
from goldscalper.data.dukascopy import Tick
from goldscalper.models import Direction, ProposalSource
from goldscalper.strategies import AsianBreakout, VwapReversion
from goldscalper.strategies.base import in_asian_session, in_overlap, session_name


def _bar(hour, minute=0, bid=2400.0):
    from goldscalper.data.bars import Bar

    t = datetime(2025, 6, 2, hour, minute, tzinfo=timezone.utc)
    return Bar(time=t, open=bid, high=bid, low=bid, close=bid,
               mean_spread=0.30, max_spread=0.30, ticks=10)


def test_session_helpers():
    assert in_asian_session(_bar(3))
    assert not in_asian_session(_bar(13))
    assert in_overlap(_bar(13))
    assert session_name(_bar(3)) == "asian"
    assert session_name(_bar(9)) == "london"
    assert session_name(_bar(13)) == "overlap"


def test_asian_breakout_fires_long_on_upside_break():
    strat = AsianBreakout(buffer=0.20, min_range=0.5, max_range=50.0)
    # Build an Asian range 2398-2402, then break above during London.
    for minute in range(0, 60, 5):
        strat.on_bar(_bar(2, minute, bid=2398.0))
        strat.on_bar(_bar(4, minute, bid=2402.0))
    # a close at 2402.10 is inside the range high(2402) + buffer(0.20) -> no fire
    assert strat.on_bar(_bar(8, 0, bid=2402.10)) is None
    # a close at 2402.30 clears 2402.20 -> fires long
    proposal = strat.on_bar(_bar(8, 10, bid=2402.30))
    assert proposal is not None
    assert proposal.direction is Direction.BUY
    assert proposal.source is ProposalSource.RULES
    assert proposal.stop_loss < proposal.entry < proposal.take_profit
    # target is a full range (4.0) away, stop is half (2.0)
    assert abs((proposal.take_profit - proposal.entry) - 4.0) < 1e-6
    assert abs((proposal.entry - proposal.stop_loss) - 2.0) < 1e-6


def test_asian_breakout_one_trade_per_direction_per_day():
    strat = AsianBreakout(buffer=0.10, min_range=0.5, max_range=50.0)
    for minute in range(0, 60, 5):
        strat.on_bar(_bar(2, minute, bid=2400.0))
        strat.on_bar(_bar(4, minute, bid=2404.0))
    first = strat.on_bar(_bar(8, 0, bid=2405.0))
    second = strat.on_bar(_bar(8, 5, bid=2406.0))
    assert first is not None
    assert second is None  # already took the long today


def test_asian_breakout_skips_degenerate_ranges():
    narrow = AsianBreakout(min_range=1.0, max_range=8.0)
    for minute in range(0, 60, 5):
        narrow.on_bar(_bar(2, minute, bid=2400.0))
        narrow.on_bar(_bar(4, minute, bid=2400.2))  # only $0.2 range
    assert narrow.on_bar(_bar(8, 0, bid=2405.0)) is None


def test_vwap_reversion_shorts_when_stretched_above():
    strat = VwapReversion(entry_k=1.0, stop_k=1.0, atr_period=14, max_trades_per_day=2)
    # feed calm bars to establish vwap and atr, then a spike up in overlap
    ticks = []
    base = datetime(2025, 6, 2, 10, 0, tzinfo=timezone.utc)
    from goldscalper.data.bars import Bar

    bars = []
    price = 2400.0
    for i in range(20):
        t = base.replace(minute=(i * 5) % 60, hour=10 + (i * 5) // 60)
        bars.append(Bar(t, price, price + 0.5, price - 0.5, price,
                        mean_spread=0.3, max_spread=0.3, ticks=10))
    result = None
    for bar in bars:
        result = strat.on_bar(bar)
    # now a big spike above vwap during the overlap
    spike = Bar(datetime(2025, 6, 2, 13, 0, tzinfo=timezone.utc),
                2400, 2410, 2400, 2410, mean_spread=0.3, max_spread=0.3, ticks=10)
    proposal = strat.on_bar(spike)
    assert proposal is not None
    assert proposal.direction is Direction.SELL
    assert proposal.take_profit < proposal.entry  # reverts down toward vwap
    assert proposal.stop_loss > proposal.entry
