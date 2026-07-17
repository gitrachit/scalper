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
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

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
    symbol: str,
    hour: datetime,
    cache_dir: str | Path,
    timeout: float = 60.0,
    retries: int = 5,
) -> bytes:
    """Fetch one hour file, using the on-disk cache. A 404 (no data for
    that hour) is cached and returned as empty bytes. Transient network
    failures (timeouts, resets) are retried with exponential backoff; the
    proxy path to Dukascopy is slow and lossy, so this is expected."""
    path = _cache_path(Path(cache_dir), symbol, hour)
    if path.exists():
        return path.read_bytes()

    url = hour_url(symbol, hour)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as err:
            if err.code == 404:
                raw = b""
                break
            last_err = err
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as err:
            last_err = err
        time.sleep(min(2 * (attempt + 1), 15))
    else:
        raise RuntimeError(f"download failed after {retries} tries: {url}") from last_err

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def hours_in_range(start: datetime, end: datetime) -> list[datetime]:
    start = start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = end.astimezone(timezone.utc)
    out = []
    hour = start
    while hour < end:
        out.append(hour)
        hour += timedelta(hours=1)
    return out


def missing_hours(
    symbol: str, start: datetime, end: datetime, cache_dir: str | Path
) -> list[datetime]:
    """Hours in [start, end) not yet in the cache — the resume set."""
    cache = Path(cache_dir)
    return [
        h
        for h in hours_in_range(start, end)
        if not _cache_path(cache, symbol, h).exists()
    ]


def download_range(
    symbol: str,
    start: datetime,
    end: datetime,
    cache_dir: str | Path,
    progress_cb: Callable[[int, int, datetime], None] | None = None,
    pace_seconds: float = 0.0,
    raise_on_fail: bool = True,
) -> tuple[int, list[datetime]]:
    """Pre-fetch every hour file in [start, end) into the cache, resuming
    from whatever is already cached.

    Resilient by default when `raise_on_fail=False`: a per-hour download
    that exhausts its retries is recorded and skipped rather than
    aborting the whole run, so a supervising loop can re-pass the
    returned failures once the feed recovers. `pace_seconds` inserts a
    delay after each *network* fetch (not cache hits) to stay under the
    relay's rate limit. Returns (succeeded, failed_hours)."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    hours = hours_in_range(start, end)
    total = len(hours)
    done = 0
    failed: list[datetime] = []
    for i, hour in enumerate(hours):
        cached = _cache_path(Path(cache_dir), symbol, hour).exists()
        try:
            download_hour(symbol, hour, cache_dir)
            done += 1
        except Exception:
            if raise_on_fail:
                raise
            failed.append(hour)
        if progress_cb is not None:
            progress_cb(i + 1, total, hour)
        if pace_seconds and not cached:
            time.sleep(pace_seconds)
    return done, failed


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
