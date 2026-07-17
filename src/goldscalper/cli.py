"""Command-line entry point for Phase 1 backtests.

Usage:
    python -m goldscalper.cli backtest \
        --strategy asian_breakout \
        --start 2025-01-01 --end 2025-07-01 \
        --cache .cache/dukascopy

    python -m goldscalper.cli smoke      # offline synthetic-data check

Downloading real Dukascopy data touches the network and so lives only
here, never in the test suite.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from goldscalper.backtest.runner import run_backtest
from goldscalper.data.bars import aggregate_ticks
from goldscalper.strategies import AsianBreakout, VwapReversion

STRATEGIES = {
    "asian_breakout": AsianBreakout,
    "vwap_reversion": VwapReversion,
}


def _parse_day(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def cmd_backtest(args: argparse.Namespace) -> int:
    from goldscalper.data.dukascopy import load_ticks

    strategy = STRATEGIES[args.strategy]()
    ticks = load_ticks("XAUUSD", _parse_day(args.start), _parse_day(args.end), args.cache)
    bars = list(aggregate_ticks(ticks, args.timeframe))
    if not bars:
        print("No bars in range (weekend/holiday window or empty cache).")
        return 1
    result, metrics = run_backtest(strategy, bars, slippage=args.slippage)
    print(f"strategy={args.strategy} bars={len(bars)}")
    print(f"proposals={result.proposals} rejected={result.rejections} {dict(result.rejection_reasons)}")
    print(metrics.summary())
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    from goldscalper.data.synthetic import random_walk_ticks

    ticks = random_walk_ticks(_parse_day("2025-06-02"), hours=24 * 5, seed=7)
    bars = list(aggregate_ticks(ticks, 5))
    for name, cls in STRATEGIES.items():
        result, metrics = run_backtest(cls(), bars)
        print(f"[{name}] {metrics.summary()} (proposals={result.proposals})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goldscalper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="run a backtest over Dukascopy data")
    bt.add_argument("--strategy", choices=list(STRATEGIES), required=True)
    bt.add_argument("--start", required=True)
    bt.add_argument("--end", required=True)
    bt.add_argument("--cache", default=".cache/dukascopy")
    bt.add_argument("--timeframe", type=int, default=5)
    bt.add_argument("--slippage", type=float, default=0.03)
    bt.set_defaults(func=cmd_backtest)

    sm = sub.add_parser("smoke", help="offline synthetic-data sanity run")
    sm.set_defaults(func=cmd_smoke)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
