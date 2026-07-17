# goldscalper

A risk-gated XAUUSD trading framework built to the plan in
[docs/blueprint.md](docs/blueprint.md): a **deterministic Python execution
and risk engine that nothing can override**, with an LLM (later phases)
sitting *outside* the hot path — end-of-day journal analysis and
human-gated strategy proposals only, never tick-level decisions, never
sizing, never risk.

> **This is a learning project, not a money machine.** The independent
> evidence (DeepFund, FINSABER, ESMA base rates — see the blueprint's
> Reality Check) says an LLM-driven retail gold scalper is very unlikely
> to be reliably profitable. Everything here runs against a demo account
> until the Phase 4 go/no-go criteria are met, which they may never be.

## Current status: Phase 0

Deterministic risk engine + structured journaling + broker abstraction.
No strategy, no LLM, no live orders yet.

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Risk engine, journaling, paper broker, unit tests | ✅ this repo |
| 1 | Dukascopy tick data + rules baseline backtest (pre-registered criteria) | — |
| 2 | Claude as EOD analyst; staging-only self-improvement loop | — |
| 3 | ≥3-month / ≥100-trade demo forward test vs frozen baseline | — |
| 4 | Go/no-go on real money (expectancy > 0 after costs, PF ≥ 1.1, DD ≤ 15%) | — |

## Architecture

```
                       ┌────────────────────────────┐
 proposals from        │        RiskEngine          │      approved orders
 rules / LLM / human ─▶│  (pure code, unit-tested,  │─▶ Broker (Paper now,
 (TradeProposal)       │   no bypass path exists)   │    MT5 on Windows VPS)
                       └────────────┬───────────────┘
                                    │ every decision, approved or refused
                                    ▼
                          Journal (SQLite audit trail)
```

- `src/goldscalper/risk/engine.py` — the gate. Position sizing, per-trade
  risk cap (requested risk is **capped, never trusted**), daily-loss halt,
  max trades/day, max concurrent positions, spread gate, news blackout,
  stop/target sanity, and a 10%-drawdown kill-switch that latches until a
  human calls `manual_reset()`.
- `src/goldscalper/risk/sizing.py` — `Lot = Risk / (StopPips × PipValue)`,
  rounded **down**; a trade that can't fit the budget is refused, never
  upsized to the broker minimum.
- `src/goldscalper/journal/` — SQLite journal: every proposal + decision
  (with full rejection reasons) and every trade with the features the
  future EOD analysis needs (setup, session, spread at entry, ATR,
  MFE/MAE, outcome, rationale).
- `src/goldscalper/broker/` — `Broker` protocol; `PaperBroker` (runs
  anywhere, conservative gap-fill rules) and `MT5Broker` (Windows-only
  adapter over the `MetaTrader5` package; contains **zero** risk logic —
  orders reaching it have already passed the gate).
- `config/risk.yaml` — version-controlled limits. LLM-proposed changes go
  to `config/risk.staging.yaml` (gitignored) and are promoted by a human.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

The suite includes the Phase 0 exit benchmark from the blueprint
(`tests/test_stress_run.py`): a simulated stress run of hostile
proposals — 50%-risk LLM requests, inverted stops, news-window entries,
spread blowouts, overtrading, blown daily budgets, deep drawdown — every
one of which must be refused and journaled.

## Non-negotiable design rules

1. The risk engine is pure code. No component — LLM or otherwise — has an
   API path around it.
2. The LLM never sizes positions, never widens stops, never adds to
   losers, never touches the kill-switch.
3. Config changes are staged, human-promoted, git-versioned, and
   walk-forward-validated before promotion. One change per cycle.
4. Real money requires all Phase 4 criteria; a negative demo result is
   the expected outcome and is treated as a valid answer, not a bug.
