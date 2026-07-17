"""Deterministic position sizing.

Lot = RiskAmount / (StopLossPips * PipValuePerLot), rounded DOWN to the
lot step. If the result is below the broker minimum, the answer is "no
trade" — never "trade the minimum anyway", because that would exceed the
risk budget.
"""

from __future__ import annotations

import math

from goldscalper.models import SymbolSpec


def size_position(
    risk_amount: float,
    stop_pips: float,
    spec: SymbolSpec,
) -> float:
    """Return the lot size for the given risk budget, or 0.0 if the trade
    cannot be taken within budget."""
    if risk_amount <= 0 or stop_pips <= 0:
        return 0.0

    raw_lot = risk_amount / (stop_pips * spec.pip_value_per_lot)

    # Round down to the lot step (guard float error with a tiny epsilon so
    # e.g. 0.03 / 0.01 = 2.9999999 still counts as 3 steps).
    steps = math.floor(raw_lot / spec.lot_step + 1e-9)
    lot = steps * spec.lot_step
    lot = round(lot, 8)

    if lot < spec.min_lot:
        return 0.0
    return min(lot, spec.max_lot)


def risk_at_lot(lot: float, stop_pips: float, spec: SymbolSpec) -> float:
    """Dollar loss if the stop is hit at the given lot size (spread/slippage
    excluded — those are gated separately)."""
    return lot * stop_pips * spec.pip_value_per_lot
