#!/usr/bin/env python3
"""Run the pre-registered Phase 1 evaluation over cached Dukascopy bars.

    python scripts/phase1_eval.py 2025-01-01 2025-07-01 .cache/dukascopy \
        --out docs/phase1_results.md

Uses only cached data (no downloads). If any hour is missing from the
cache it reports the gap and refuses to produce a verdict, so a partial
download can never masquerade as the real result.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from goldscalper.backtest.evaluation import (  # noqa: E402
    STRATEGY_GRID,
    evaluate_strategy,
    format_report,
)
from goldscalper.data.bars import aggregate_ticks  # noqa: E402
from goldscalper.data.dukascopy import load_ticks, missing_hours  # noqa: E402


def _day(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("cache")
    ap.add_argument("--timeframe", type=int, default=5)
    ap.add_argument("--out", default="docs/phase1_results.md")
    ap.add_argument("--allow-gaps", action="store_true",
                    help="proceed even if some hours are missing (labels result partial)")
    args = ap.parse_args()

    start, end = _day(args.start), _day(args.end)
    missing = missing_hours("XAUUSD", start, end, args.cache)
    if missing and not args.allow_gaps:
        print(f"REFUSING: {len(missing)} hours missing from cache "
              f"(first {min(missing).isoformat()}). Finish the download or pass --allow-gaps.")
        return 1

    ticks = load_ticks("XAUUSD", start, end, args.cache)
    bars = list(aggregate_ticks(ticks, args.timeframe))
    if len(bars) < 500:
        print(f"REFUSING: only {len(bars)} bars — not enough to evaluate.")
        return 1

    window = f"{args.start}..{args.end} ({len(bars)} M{args.timeframe} bars)"
    if missing:
        window += f" [PARTIAL: {len(missing)} hours missing]"

    evals = [evaluate_strategy(name, bars) for name in STRATEGY_GRID]
    report = format_report(evals, window)
    Path(args.out).write_text(report)
    print(report)
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
