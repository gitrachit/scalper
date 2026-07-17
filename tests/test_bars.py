from datetime import datetime, timezone

from goldscalper.data.bars import aggregate_ticks, atr
from goldscalper.data.dukascopy import Tick
from goldscalper.data.synthetic import random_walk_ticks

START = datetime(2025, 6, 2, 12, 0, tzinfo=timezone.utc)


def test_ohlc_and_spread_within_one_bar():
    ticks = [
        Tick(START.replace(second=0), bid=2400.0, ask=2400.30),
        Tick(START.replace(second=10), bid=2401.0, ask=2401.20),  # high
        Tick(START.replace(second=20), bid=2399.0, ask=2399.50),  # low
        Tick(START.replace(second=30), bid=2400.5, ask=2400.90),  # close
    ]
    bars = list(aggregate_ticks(ticks, 5))
    assert len(bars) == 1
    bar = bars[0]
    assert (bar.open, bar.high, bar.low, bar.close) == (2400.0, 2401.0, 2399.0, 2400.5)
    assert bar.ticks == 4
    assert abs(bar.max_spread - 0.50) < 1e-6
    # mean spread of 0.30, 0.20, 0.50, 0.40
    assert abs(bar.mean_spread - 0.35) < 1e-6


def test_bars_split_on_interval_boundary():
    ticks = [
        Tick(START.replace(minute=2), bid=2400.0, ask=2400.3),
        Tick(START.replace(minute=4), bid=2400.5, ask=2400.8),
        Tick(START.replace(minute=6), bid=2401.0, ask=2401.3),  # next 5-min bar
    ]
    bars = list(aggregate_ticks(ticks, 5))
    assert len(bars) == 2
    assert bars[0].time == START.replace(minute=0)
    assert bars[1].time == START.replace(minute=5)


def test_empty_interval_produces_no_bar():
    ticks = [
        Tick(START.replace(minute=0), bid=2400.0, ask=2400.3),
        Tick(START.replace(minute=12), bid=2401.0, ask=2401.3),  # skips 5 & 10
    ]
    bars = list(aggregate_ticks(ticks, 5))
    assert [b.time.minute for b in bars] == [0, 10]


def test_atr_none_until_enough_history():
    ticks = random_walk_ticks(START, hours=3, seed=1)
    bars = list(aggregate_ticks(ticks, 5))
    assert atr(bars[:5], period=14) is None
    assert atr(bars, period=14) is not None
    assert atr(bars, period=14) > 0
