#!/usr/bin/env python3
"""Resilient, resumable bulk download of Dukascopy XAUUSD hour files.

Designed for a slow, rate-limited relay: paces requests, skips hours it
can't fetch, and re-passes the remaining misses until the range is
complete or a pass makes zero progress. Safe to re-run — resumes from
the on-disk cache. Writes newline-delimited progress to a log so a
supervising session can poll without attaching.

    python scripts/download_data.py 2025-01-01 2025-07-01 .cache/dukascopy
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from goldscalper.data.dukascopy import (  # noqa: E402
    download_range,
    missing_hours,
)

LOG = Path(".cache/download_progress.log")
PACE_SECONDS = 3.0  # gentle spacing to respect the relay rate limit
MAX_PASSES = 40


def _day(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")


def main() -> int:
    start, end, cache = _day(sys.argv[1]), _day(sys.argv[2]), sys.argv[3]
    t0 = time.time()
    _log(f"=== START {start.date()}..{end.date()} cache={cache} pace={PACE_SECONDS}s ===")

    remaining = missing_hours("XAUUSD", start, end, cache)
    _log(f"resume: {len(remaining)} hours missing from cache")

    for pass_no in range(1, MAX_PASSES + 1):
        before = len(missing_hours("XAUUSD", start, end, cache))
        if before == 0:
            break

        def progress(i: int, total: int, hour: datetime) -> None:
            if i % 20 == 0:
                elapsed = time.time() - t0
                got = total - len(missing_hours("XAUUSD", start, end, cache))
                _log(f"pass {pass_no}: {i}/{total} scanned, ~{got} cached, {elapsed/3600:.1f}h elapsed")

        # Only attempt the still-missing hours this pass.
        miss = missing_hours("XAUUSD", start, end, cache)
        _, failed = download_range(
            "XAUUSD",
            miss[0],
            miss[-1] + _hour(),
            cache,
            progress_cb=progress,
            pace_seconds=PACE_SECONDS,
            raise_on_fail=False,
        )
        after = len(missing_hours("XAUUSD", start, end, cache))
        _log(f"pass {pass_no} done: {before}->{after} missing ({before-after} fetched, {len(failed)} failed)")
        if after == before:
            _log("no progress this pass; feed likely rate-limited — backing off 300s")
            time.sleep(300)

    final_missing = len(missing_hours("XAUUSD", start, end, cache))
    _log(f"=== DONE missing={final_missing} in {(time.time()-t0)/3600:.2f}h ===")
    return 0 if final_missing == 0 else 2


def _hour():
    from datetime import timedelta

    return timedelta(hours=1)


if __name__ == "__main__":
    raise SystemExit(main())
