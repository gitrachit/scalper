"""Asian-range breakout.

Track the Asian session (00:00-07:00 GMT) bid high/low each day. From
London open through the end of the NY overlap (07:00-16:00 GMT), a close
beyond the range plus a buffer proposes a trade in the breakout
direction: stop at half the range width behind entry, target at one full
range width (2R). One trade per direction per day; degenerate (too
narrow/too wide) ranges are skipped.

All parameters are fixed here as the pre-registered defaults; the
optimization grid lives in docs/phase1_criteria.md, not in ad-hoc edits.
"""

from __future__ import annotations

from datetime import date

from goldscalper.data.bars import Bar
from goldscalper.models import Direction, ProposalSource, TradeProposal
from goldscalper.strategies.base import in_asian_session

TRADE_START_H, TRADE_END_H = 7, 16


class AsianBreakout:
    name = "asian_breakout"

    def __init__(
        self,
        buffer: float = 0.20,  # $ beyond the range edge to confirm
        min_range: float = 1.00,  # skip days with < $1 Asian range (dead)
        max_range: float = 8.00,  # skip days with > $8 range (news chaos)
    ) -> None:
        self.buffer = buffer
        self.min_range = min_range
        self.max_range = max_range
        self._day: date | None = None
        self._range_high: float | None = None
        self._range_low: float | None = None
        self._took: set[Direction] = set()

    def _roll_day(self, bar: Bar) -> None:
        if bar.time.date() != self._day:
            self._day = bar.time.date()
            self._range_high = None
            self._range_low = None
            self._took = set()

    def on_bar(self, bar: Bar) -> TradeProposal | None:
        self._roll_day(bar)

        if in_asian_session(bar):
            self._range_high = bar.high if self._range_high is None else max(self._range_high, bar.high)
            self._range_low = bar.low if self._range_low is None else min(self._range_low, bar.low)
            return None

        if not (TRADE_START_H <= bar.time.hour < TRADE_END_H):
            return None
        if self._range_high is None or self._range_low is None:
            return None
        width = self._range_high - self._range_low
        if not (self.min_range <= width <= self.max_range):
            return None

        if bar.close > self._range_high + self.buffer and Direction.BUY not in self._took:
            self._took.add(Direction.BUY)
            entry = bar.close
            return TradeProposal(
                direction=Direction.BUY,
                entry=entry,
                stop_loss=entry - width / 2,
                take_profit=entry + width,
                source=ProposalSource.RULES,
                setup_type=self.name,
                rationale=f"close {bar.close:.2f} broke Asian high {self._range_high:.2f} (range {width:.2f})",
            )
        if bar.close < self._range_low - self.buffer and Direction.SELL not in self._took:
            self._took.add(Direction.SELL)
            entry = bar.close
            return TradeProposal(
                direction=Direction.SELL,
                entry=entry,
                stop_loss=entry + width / 2,
                take_profit=entry - width,
                source=ProposalSource.RULES,
                setup_type=self.name,
                rationale=f"close {bar.close:.2f} broke Asian low {self._range_low:.2f} (range {width:.2f})",
            )
        return None
