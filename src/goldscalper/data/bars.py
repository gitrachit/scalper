"""Tick -> OHLCV bar aggregation.

Bars are bid-price OHLC (the convention MT5 charts use) and carry the
mean and max spread observed inside the bar, plus the tick count — the
backtest cost model uses the *recorded* spread rather than an assumed
constant. Volume is tick count (Dukascopy retail volumes are not
meaningful).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator

from goldscalper.data.dukascopy import Tick


@dataclass(frozen=True)
class Bar:
    time: datetime  # bar open time, UTC
    open: float
    high: float
    low: float
    close: float
    mean_spread: float
    max_spread: float
    ticks: int

    @property
    def mid_close(self) -> float:
        return self.close + self.mean_spread / 2.0


def _bar_start(ts: datetime, minutes: int) -> datetime:
    ts = ts.astimezone(timezone.utc)
    floored_minute = (ts.minute // minutes) * minutes
    return ts.replace(minute=floored_minute, second=0, microsecond=0)


def aggregate_ticks(ticks: Iterable[Tick], minutes: int) -> Iterator[Bar]:
    """Aggregate a time-ordered tick stream into fixed-interval bars.
    Empty intervals produce no bar (standard for FX charts)."""
    current_start: datetime | None = None
    o = h = l = c = 0.0
    spread_sum = 0.0
    spread_max = 0.0
    n = 0

    def flush() -> Bar:
        return Bar(
            time=current_start,
            open=o,
            high=h,
            low=l,
            close=c,
            mean_spread=spread_sum / n,
            max_spread=spread_max,
            ticks=n,
        )

    for tick in ticks:
        start = _bar_start(tick.time, minutes)
        if current_start is None:
            current_start = start
        elif start != current_start:
            yield flush()
            current_start = start
            n = 0
        spread = tick.ask - tick.bid
        if n == 0:
            o = h = l = tick.bid
            spread_sum = 0.0
            spread_max = 0.0
        h = max(h, tick.bid)
        l = min(l, tick.bid)
        c = tick.bid
        spread_sum += spread
        spread_max = max(spread_max, spread)
        n += 1

    if current_start is not None and n > 0:
        yield flush()


def atr(bars: list[Bar], period: int = 14) -> float | None:
    """Simple ATR over the last `period` closed bars (price units).
    Returns None until enough history exists."""
    if len(bars) < period + 1:
        return None
    trs = []
    for prev, cur in zip(bars[-period - 1 : -1], bars[-period:]):
        tr = max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close))
        trs.append(tr)
    return sum(trs) / period
