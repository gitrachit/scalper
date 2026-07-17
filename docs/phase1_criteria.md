# Phase 1 — Pre-registered success criteria

Registered BEFORE any backtest is run or any parameter is touched, per
the blueprint. This file is the contract; results are judged against it,
not the other way around.

## Data

- Source: Dukascopy XAUUSD tick data (free feed), aggregated to M5 bars
  with per-bar recorded mean/max spread.
- Target window: as much history as the environment can hold, minimum
  6 months for a full run; any smaller window is a *pipeline smoke test*,
  not a verdict.
- Split: first 70% of the window is in-sample (IS), last 30% is
  out-of-sample (OOS). OOS is touched exactly once, after IS work is
  frozen.

## Cost model (fixed)

- Spread: the recorded per-bar mean spread from the tick data (buys pay
  ask on entry; shorts exit at ask).
- Slippage: $0.03/oz charged on every entry and every stop exit;
  take-profits fill at the limit price with no positive slippage.
- Intrabar ambiguity: if a bar's range covers both stop and target, the
  stop is assumed hit (worst case).
- All trades pass the live RiskEngine (1% risk, spread gate $0.60, news
  filter off in backtest — noted as an optimistic bias to remember).

## Strategies and allowed optimization

Two strategies, defaults as coded:

1. `asian_breakout(buffer=0.20, min_range=1.00, max_range=8.00)`
2. `vwap_reversion(entry_k=1.5, stop_k=1.0, atr_period=14)`

The ONLY optimization permitted is this pre-declared grid, evaluated on
IS only:

- `asian_breakout.buffer ∈ {0.10, 0.20, 0.30}`
- `vwap_reversion.entry_k ∈ {1.5, 2.0}` × `stop_k ∈ {1.0, 1.5}`

The best IS config per strategy (by expectancy, tie-break profit factor)
is then run ONCE on OOS. No second grid, no added filters, no re-runs
"to check something".

## Success criteria (all must hold on OOS)

| Metric | Threshold |
|---|---|
| Closed trades (IS+OOS combined) | ≥ 100 |
| OOS expectancy after costs | > $0 per trade |
| OOS profit factor | ≥ 1.10 |
| OOS max drawdown | ≤ 15% |

## Interpretation rules

- If a strategy fails: that is the expected outcome per the literature.
  It is recorded as a negative result and the strategy is NOT re-tuned.
  Phase 2 (LLM analyst) may still proceed as a learning exercise, on the
  frozen loser or a shelved system — but Phase 4 (real money) is dead
  until something passes Phase 3 forward-testing.
- If a strategy passes: it graduates to Phase 3 demo forward-testing
  with the exact OOS config, frozen. Backtest success alone authorizes
  nothing beyond a demo.
