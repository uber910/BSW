---
phase: "06-reconciliation-job"
plan: "02"
subsystem: "test-scaffolding"
tags: [test-scaffolding, wave-0, nyquist, reconciliation]
dependency_graph:
  requires: []
  provides: [wave-0-stubs, pytest-collection-gate]
  affects: [06-03, 06-04, 06-05, 06-06, 06-07, 06-08, 06-09, 06-10]
tech_stack:
  added: []
  patterns: [wave-0-nyquist, pytest-fail-stubs, pytest-asyncio-class-scope]
key_files:
  created:
    - tests/bet_maker/jobs/__init__.py
    - tests/bet_maker/jobs/test_reconciler_tick.py
    - tests/bet_maker/jobs/test_reconciler_cancellation.py
    - tests/bet_maker/repositories/__init__.py
    - tests/bet_maker/repositories/test_get_pending_event_ids.py
    - tests/bet_maker/interactors/__init__.py
    - tests/bet_maker/interactors/test_cancel_bets_for_event.py
    - tests/bet_maker/migrations/__init__.py
    - tests/bet_maker/migrations/test_0003_cancelled.py
    - tests/bet_maker/config/__init__.py
    - tests/bet_maker/config/test_settings_reconciler.py
    - tests/bet_maker/test_lifespan_reconciler.py
    - tests/bet_maker/test_health_reconciler.py
    - tests/bet_maker/integration/__init__.py
    - tests/bet_maker/integration/test_reconciler_consumer_race.py
    - tests/bet_maker/integration/test_reconciler_drop_publish.py
    - tests/bet_maker/e2e/__init__.py
    - tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py
  modified: []
decisions:
  - "Wave-0 stubs use pytest.fail (not xfail/skip) so no downstream plan can accidentally go green"
  - "Deferred local imports omitted entirely — no future-module imports at all, stubs are pure pytest.fail"
  - "ruff-format reformats multi-line strings to single-line; all files ruff-clean after pre-commit"
metrics:
  duration: "~3 min"
  completed: "2026-05-18"
---

# Phase 06 Plan 02: Wave-0 Test Scaffolding Summary

Wave-0 Nyquist safety net: 18 new files (11 stubs + 7 `__init__.py`) creating 48 pre-failing pytest methods for all Phase 6 production plans (06-03..06-10).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Unit-level stub test files (jobs, repositories, interactors, migrations, config) | 955aa36 | 11 files (5 `__init__.py` + 6 stub files, 32 stubs) |
| 2 | Integration + e2e + lifespan/health stub test files | ea3f947 | 7 files (2 `__init__.py` + 5 stub files, 16 stubs) |

## New Files and Test Counts

| File | Tests | Target Plan | Requirement |
|------|-------|-------------|-------------|
| tests/bet_maker/jobs/test_reconciler_tick.py | 8 | 06-07 | BM-12 |
| tests/bet_maker/jobs/test_reconciler_cancellation.py | 3 | 06-07 | BM-12 |
| tests/bet_maker/repositories/test_get_pending_event_ids.py | 4 | 06-05 | BM-12 |
| tests/bet_maker/interactors/test_cancel_bets_for_event.py | 9 | 06-06 | BM-05, BM-12 |
| tests/bet_maker/migrations/test_0003_cancelled.py | 3 | 06-03 | BM-05 |
| tests/bet_maker/config/test_settings_reconciler.py | 5 | 06-04 | BM-12 |
| tests/bet_maker/test_lifespan_reconciler.py | 5 | 06-08 | BM-12, SC#3 |
| tests/bet_maker/test_health_reconciler.py | 3 | 06-08 | BM-12, SC#3 |
| tests/bet_maker/integration/test_reconciler_consumer_race.py | 2 | 06-09 | BM-12, SC#4 |
| tests/bet_maker/integration/test_reconciler_drop_publish.py | 3 | 06-09 | BM-12, SC#1 |
| tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py | 3 | 06-10 | BM-12, SC#5, QA-08 |
| **Total** | **48** | | |

## Pytest Collection Result

```
uv run pytest --collect-only -q tests/bet_maker/ 2>&1 | tail -3
236 tests collected in 0.27s
```

(188 pre-existing + 48 new Wave-0 stubs = 236 total)

## Verification

- All 48 stubs collected with 0 collection errors
- `pytest -x tests/bet_maker/jobs/test_reconciler_tick.py` returns 1 FAILED (stubs fail at runtime)
- `ruff check` passes on all 18 new files
- No module-level imports of not-yet-existing production modules
- All `__init__.py` files exist for the 7 new test sub-packages

## Deviations from Plan

None — plan executed exactly as written. Ruff-format reformatted multi-line f-strings to single-line in 8 files during pre-commit; re-staged and committed after format pass.

## Known Stubs

All 48 test methods are intentional stubs. Each uses `pytest.fail("Wave-0 stub for Plan 06-NN — ...")`. These are tracked per VALIDATION.md Wave 0 Requirements and will be replaced by the implementing plans (06-03..06-10).

## Self-Check: PASSED
