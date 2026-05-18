---
phase: 06-reconciliation-job
plan: "09"
subsystem: bet_maker/tests/integration
tags: [integration, respx, testcontainers-pg, race, drop-publish, SC#4, SC#1]
dependency_graph:
  requires: [06-07, 06-08]
  provides: [SC#4-coverage, SC#1-coverage]
  affects: [tests/bet_maker/integration/]
tech_stack:
  added: []
  patterns:
    - asyncio.gather on real PG to exercise FOR UPDATE SKIP LOCKED
    - respx.mock(base_url=...) context manager for HttpEventLookup through _reconcile_event
    - duck-typed _FakeLookup for race tests (no real HTTP needed)
key_files:
  created: []
  modified:
    - tests/bet_maker/integration/test_reconciler_consumer_race.py
    - tests/bet_maker/integration/test_reconciler_drop_publish.py
decisions:
  - "SC#4 race test uses duck-typed _FakeLookup, not HttpEventLookup — race is a PG-lock concern, not HTTP"
  - "SC#1 drop-publish tests use throwaway httpx.AsyncClient per test to avoid respx interference with lifespan singleton"
  - "assert_all_called=False on respx.mock — allows retries without assertion failure"
metrics:
  duration: "~5 min"
  completed: "2026-05-18T11:57:59Z"
  tasks_completed: 2
  files_modified: 2
---

# Phase 6 Plan 09: Integration Tests (SC#4 + SC#1) Summary

**One-liner:** 5 real integration tests on real PG proving FOR UPDATE SKIP LOCKED race safety and respx-mocked LP driving production `_reconcile_event` through all decision branches.

## Test Results

| Test | Class | Status | Scenario |
|------|-------|--------|----------|
| `test_concurrent_settle_consumer_and_reconciler_no_double_update` | `TestReconcilerConsumerRace` | PASSED | SC#4: all 3 bets land in WON after gather |
| `test_for_update_skip_locked_one_winner_one_noop` | `TestReconcilerConsumerRace` | PASSED | SC#4: exactly [0,3] split between settle+cancel |
| `test_respx_mocked_lp_terminal_state_triggers_reconciler_settle` | `TestReconcilerDropPublish` | PASSED | SC#1: FINISHED_WIN -> WON, settled_via=reconciler |
| `test_respx_mocked_lp_404_triggers_reconciler_cancel` | `TestReconcilerDropPublish` | PASSED | SC#1: 404 -> CANCELLED, settled_via=reconciler |
| `test_reconciler_skip_when_lp_still_returns_new` | `TestReconcilerDropPublish` | PASSED | SC#1: NEW -> PENDING unchanged |

All 5 tests ran against real PostgreSQL via testcontainers (not SQLite). FOR UPDATE SKIP LOCKED was exercised on real concurrent asyncio.gather coroutines.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1 + Task 2 (atomic) | 8c54913 | test_reconciler_consumer_race.py, test_reconciler_drop_publish.py |

## Deviations from Plan

None — plan executed exactly as written. ruff-format hook reformatted whitespace on first commit attempt; restaged and committed cleanly.

## Known Stubs

None. Wave-0 `pytest.fail(...)` stubs have been fully replaced with real assertions.

## Threat Flags

None. No new network endpoints or auth paths introduced (tests only).

## Self-Check: PASSED

- `tests/bet_maker/integration/test_reconciler_consumer_race.py` — FOUND
- `tests/bet_maker/integration/test_reconciler_drop_publish.py` — FOUND
- Commit `8c54913` — FOUND in git log
- `grep -c "Wave-0 stub" tests/bet_maker/integration/test_reconciler_consumer_race.py` == 0
- `grep -c "Wave-0 stub" tests/bet_maker/integration/test_reconciler_drop_publish.py` == 0
- `uv run pytest tests/bet_maker/integration/` — 5 passed
- `uv run mypy tests/bet_maker/integration/` — no issues
- `uv run ruff check tests/bet_maker/integration/` — all checks passed
