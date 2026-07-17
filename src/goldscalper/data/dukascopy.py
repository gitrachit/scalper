"""Dukascopy historical tick data.

Dukascopy publishes free per-hour tick files at
`https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM}/{DD}/{HH}h_ticks.bi5`
(month is ZERO-indexed). Each .bi5 is LZMA-compressed records of 20
bytes: big-endian uint32 ms-offset-in-hour, uint32 ask, uint32 bid,
float32 ask volume, float32 bid volume. XAUUSD prices are scaled by
1/1000 (point = 0.001).

Files are cached on disk so a backtest window is only downloaded once.
An empty file (weekend/holiday hour) is cached as an empty file.
"""

from __future__ import annotations

import lzma
import struct
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
XAUUSD_POINT = 0.001
_RECORD = struct.Struct(">IIIff")


@dataclass(frozen=True)
class Tick:
    time: datetime
    bid: float
    ask: float


def hour_url(symbol: str, hour: datetime) -> str:
    return (
        f"{BASE_URL}/{symbol}/{hour.year:04d}/{hour.month - 1:02d}/"
        f"{hour.day:02d}/{hour.hour:02d}h_ticks.bi5"
    )


def decode_bi5(raw: bytes, hour: datetime, point: float = XAUUSD_POINT) -> list[Tick]:
    """Decode one hour file's bytes into ticks. `raw` may be empty
    (no trading that hour)."""
    if not raw:
        return []
    data = lzma.decompress(raw)
    ticks = []
    for offset in range(0, len(data) - len(data) % _RECORD.size, _RECORD.size):
        ms, ask_raw, bid_raw, _ask_vol, _bid_vol = _RECORD.unpack_from(data, offset)
        ticks.append(
            Tick(
                time=hour + timedelta(milliseconds=ms),
                bid=bid_raw * point,
                ask=ask_raw * point,
            )
        )
    return ticks


def _cache_path(cache_dir: Path, symbol: str, hour: datetime) -> Path:
    return (
        cache_dir
        / symbol
        / f"{hour.year:04d}"
        / f"{hour.month:02d}"
        / f"{hour.day:02d}"
        / f"{hour.hour:02d}h_ticks.bi5"
    )


def download_hour(
    symbol: str, hour: datetime, cache_dir: str | Path, timeout: float = 30.0
) -> bytes:
    """Fetch one hour file, using the on-disk cache. A 404 (no data for
    that hour) is cached and returned as empty bytes."""
    path = _cache_path(Path(cache_dir), symbol, hour)
    if path.exists():
        return path.read_bytes()

    url = hour_url(symbol, hour)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raw = b""
        else:
            raise

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def load_ticks(
    symbol: str,
    start: datetime,
    end: datetime,
    cache_dir: str | Path,
    point: float = XAUUSD_POINT,
) -> Iterator[Tick]:
    """Yield ticks for [start, end), downloading (or reading cached)
    hour files as needed. Times must be timezone-aware UTC."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    hour = start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    while hour < end:
        raw = download_hour(symbol, hour, cache_dir)
        for tick in decode_bi5(raw, hour, point):
            if start <= tick.time < end:
                yield tick
        hour += timedelta(hours=1)
