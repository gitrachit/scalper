"""Synthetic tick and bi5 generation for tests and offline smoke runs.

Tests must not touch the network (see CLAUDE.md), so downloader and
backtest tests build deterministic tick streams here and, where the .bi5
codec is under test, encode them in the exact Dukascopy wire format.
"""

from __future__ import annotations

import lzma
import random
import struct
from datetime import datetime, timedelta, timezone

from goldscalper.data.dukascopy import XAUUSD_POINT, Tick

_RECORD = struct.Struct(">IIIff")


def encode_bi5(ticks: list[Tick], hour: datetime, point: float = XAUUSD_POINT) -> bytes:
    """Encode ticks into a Dukascopy-format LZMA .bi5 for one hour."""
    payload = bytearray()
    for tick in ticks:
        ms = int((tick.time - hour).total_seconds() * 1000)
        payload += _RECORD.pack(
            ms, round(tick.ask / point), round(tick.bid / point), 1.0, 1.0
        )
    return lzma.compress(bytes(payload), format=lzma.FORMAT_ALONE)


def random_walk_ticks(
    start: datetime,
    hours: int,
    *,
    start_price: float = 2400.0,
    spread: float = 0.30,
    ticks_per_hour: int = 120,
    step: float = 0.05,
    seed: int = 0,
) -> list[Tick]:
    """A seeded random-walk bid series with a fixed spread. Deterministic
    for a given seed."""
    rng = random.Random(seed)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    ticks: list[Tick] = []
    bid = start_price
    interval = timedelta(hours=1) / ticks_per_hour
    t = start
    for _ in range(hours * ticks_per_hour):
        bid = round(bid + rng.uniform(-step, step), 3)
        ticks.append(Tick(time=t, bid=bid, ask=round(bid + spread, 3)))
        t += interval
    return ticks


def trend_ticks(
    start: datetime,
    hours: int,
    *,
    start_price: float = 2400.0,
    spread: float = 0.30,
    ticks_per_hour: int = 120,
    drift: float = 0.02,
) -> list[Tick]:
    """A deterministic upward-drifting bid series (no randomness) — useful
    for asserting a breakout strategy fires in a known direction."""
    ticks: list[Tick] = []
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    bid = start_price
    interval = timedelta(hours=1) / ticks_per_hour
    t = start
    for _ in range(hours * ticks_per_hour):
        bid = round(bid + drift, 3)
        ticks.append(Tick(time=t, bid=bid, ask=round(bid + spread, 3)))
        t += interval
    return ticks
