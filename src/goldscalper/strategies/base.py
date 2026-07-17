"""Strategy interface.

A strategy sees closed bars one at a time and may emit a TradeProposal.
It NEVER sizes the trade or checks risk — that is the RiskEngine's job.
Session boundaries follow the blueprint (GMT): Asian 00:00-07:00,
London open 07:00, London-NY overlap 12:00-16:00.
"""

from __future__ import annotations

from typing import Protocol

from goldscalper.data.bars import Bar
from goldscalper.models import TradeProposal

ASIAN_START_H, ASIAN_END_H = 0, 7
OVERLAP_START_H, OVERLAP_END_H = 12, 16


def in_asian_session(bar: Bar) -> bool:
    return ASIAN_START_H <= bar.time.hour < ASIAN_END_H

def in_overlap(bar: Bar) -> bool:
    return OVERLAP_START_H <= bar.time.hour < OVERLAP_END_H

def session_name(bar: Bar) -> str:
    if in_asian_session(bar):
        return "asian"
    if in_overlap(bar):
        return "overlap"
    if ASIAN_END_H <= bar.time.hour < OVERLAP_START_H:
        return "london"
    return "ny_late"


class Strategy(Protocol):
    name: str

    def on_bar(self, bar: Bar) -> TradeProposal | None:
        """Called once per closed bar, in time order."""
        ...
