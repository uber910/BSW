---
phase: 06-reconciliation-job
plan: "08"
subsystem: bet_maker
tags: [lifespan, asyncio-task, deps, health, shutdown-order, reconciler]
dependency_graph:
  requires: [06-07]
  provides: [reconciler-lifespan-wiring, reconciler-health-check, reconciler-deps]
  affects: [lifespan, health, deps]
tech_stack:
  added: []
  patterns: [cancel-first-shutdown, asyncio-create-task-lifespan, annotated-dep-alias]
key_files:
  created: []
  modified:
    - src/bet_maker/entrypoints/lifespan.py
    - src/bet_maker/entrypoints/api/health.py
    - src/bet_maker/facades/deps.py
    - tests/bet_maker/test_lifespan_reconciler.py
    - tests/bet_maker/test_health_reconciler.py
decisions:
  - "D-06: Separate HttpEventLookup for reconciler with own retry params, sharing singleton httpx.AsyncClient"
  - "D-13: /health 4th check uses not task.done() — task.exception() avoided per Pitfall 6"
  - "D-14: Reconciliation task pinned at app.state.reconciliation_task; ReconciliationTaskDep via Depends"
  - "D-15: create_task called AFTER broker.connect() and all app.state pins, BEFORE yield"
  - "D-16: Cancel-first shutdown: reconciliation_task.cancel()+await BEFORE broker.close/http/engine"
  - "D-18: Task name='reconciliation' locked for log grep and asyncio debug output"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-18T11:54:04Z"
  tasks_completed: 2
  files_changed: 5
---

# Phase 06 Plan 08: Lifespan-Health-Wiring Summary

Wired the background reconciler task into the FastAPI app lifecycle: startup order
pinning `app.state.reconciler_event_lookup` + `asyncio.create_task(reconciliation_loop, name="reconciliation")`,
cancel-first shutdown guard, fourth `/health` check `not task.done()`, and two new
`Annotated` dep aliases in `facades/deps.py`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend deps.py + lifespan + lifespan reconciler tests | ad0bac0 | deps.py, lifespan.py, test_lifespan_reconciler.py |
| 2 | Extend /health + replace health reconciler stub | ad0bac0 | health.py, test_health_reconciler.py |

## What Was Built

### lifespan.py changes
- Added `import asyncio` + `from contextlib import suppress` + `from bet_maker.jobs.reconciler import reconciliation_loop`
- After existing `app.state.event_lookup` pin: added `app.state.reconciler_event_lookup = HttpEventLookup(http_client, attempts=settings.line_provider_reconciler_attempts, max_backoff=settings.line_provider_reconciler_backoff_max_s)`
- Created reconciliation task: `asyncio.create_task(reconciliation_loop(app, interval_s=settings.reconciliation_interval_s), name="reconciliation")` pinned to `app.state.reconciliation_task`
- Shutdown finally: `reconciliation_task.cancel()` + `with suppress(asyncio.CancelledError): await reconciliation_task` runs FIRST before broker.close cascade

### deps.py changes
- Added `import asyncio` and `from bet_maker.facades.http_event_lookup import HttpEventLookup`
- Added `get_reconciler_event_lookup(request) -> HttpEventLookup` provider
- Added `get_reconciliation_task(request) -> asyncio.Task[None]` provider
- Added `ReconcilerEventLookupDep` and `ReconciliationTaskDep` Annotated aliases

### health.py changes
- Injected `reconciler_task: ReconciliationTaskDep` alongside existing `engine` and `broker`
- Added `reconciler_ok = not reconciler_task.done()`
- 200 only when all four checks pass; 503 body gains `"reconciler": "ok" | "dead"`

### Tests (Wave-0 stubs replaced)
- `test_lifespan_reconciler.py`: 5 tests — state pins, task name, source-order introspection for startup/shutdown ordering
- `test_health_reconciler.py`: 3 tests — 200 when alive, 503 via dependency_override, key presence

## Test Results

```
24 passed, 6 warnings in 5.65s
```

- `test_lifespan_reconciler.py`: 5/5 passed
- `test_lifespan.py`: 10/10 passed (zero regression)
- `test_health_reconciler.py`: 3/3 passed
- `test_health.py`: 6/6 passed (zero regression)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - ruff UP037] Removed string quote from asyncio.Task[None] return annotation**
- **Found during:** ruff check after Task 1
- **Issue:** `def get_reconciliation_task(...) -> "asyncio.Task[None]"` triggered UP037 (quotes not needed with `from __future__ import annotations`)
- **Fix:** Changed to `-> asyncio.Task[None]`
- **Files modified:** `src/bet_maker/facades/deps.py`
- **Commit:** ad0bac0

**2. [Rule 1 - ruff RUF100] Removed unused noqa directive**
- **Found during:** ruff check after Task 2
- **Issue:** `# noqa: PLW0108` on lambda override was unnecessary (ruff did not flag it)
- **Fix:** Removed the noqa comment
- **Files modified:** `tests/bet_maker/test_health_reconciler.py`
- **Commit:** ad0bac0

## Known Stubs

None — all Wave-0 stubs replaced with real assertions.

## Threat Flags

No new threat surface introduced — all changes are wiring of existing components within the
established lifecycle and health endpoint.

## Self-Check: PASSED

- `src/bet_maker/entrypoints/lifespan.py` — exists, contains `reconciler_event_lookup`, `create_task`, `reconciliation_task.cancel()`
- `src/bet_maker/facades/deps.py` — exists, contains `ReconcilerEventLookupDep`, `ReconciliationTaskDep`
- `src/bet_maker/entrypoints/api/health.py` — exists, contains `ReconciliationTaskDep`, `reconciler_ok`
- `tests/bet_maker/test_lifespan_reconciler.py` — exists, 5 real test methods
- `tests/bet_maker/test_health_reconciler.py` — exists, 3 real test methods
- Commit `ad0bac0` — verified present in git log
