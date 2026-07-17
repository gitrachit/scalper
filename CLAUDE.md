# Project conventions for Claude

## Delivery workflow (always, for every unit of work)

1. Develop on the session work branch, never directly on `main`.
2. Run **all checks** before every commit: `python3 -m pytest -q` must be
   100% green. Never commit with failing tests.
3. Push the branch, **raise a PR against `main`**, and **merge it** once
   checks pass. Do not leave finished work sitting unmerged on a branch.
4. After a merge, restart the work branch from the latest `origin/main`
   before the next piece of work.

## Design rules (non-negotiable, from docs/blueprint.md)

- The deterministic `RiskEngine` gates every order. No component — LLM,
  strategy, or script — may bypass it, size positions itself, widen
  stops, or touch the kill-switch.
- LLM involvement is limited to end-of-day analysis and staged config
  proposals in `config/risk.staging.yaml` that a human promotes by hand.
- Pre-register success criteria before optimizing anything; a negative
  backtest/forward-test result is a valid answer, not a bug to fix by
  re-tuning until it passes.
- Demo account only until every Phase 4 go/no-go criterion in the
  blueprint is met.

## Testing

- `pip install -e ".[dev]"` then `pytest`.
- Tests must not touch the network; downloader tests use synthetic bi5
  payloads.
