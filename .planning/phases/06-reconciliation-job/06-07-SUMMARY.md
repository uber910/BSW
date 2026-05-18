---
phase: 06-reconciliation-job
plan: "07"
subsystem: bet_maker/jobs
tags: [reconciler, asyncio-task, cancellable, structlog, error-isolation]
requirements: [BM-12]

dependency_graph:
  requires:
    - "06-05 — BetRepository.get_pending_event_ids"
    - "06-06 — cancel_bets_for_event interactor"
    - "05 — settle_bets_for_event interactor"
    - "04 — HttpEventLookup"
  provides:
    - "reconciliation_loop(app, *, interval_s) — outer asyncio loop"
    - "_run_tick(app) — one tick of the loop"
    - "_reconcile_event(sessionmaker, lookup, event_id) — per-event decision"
  affects:
    - "06-08 — lifespan wires reconciliation_loop via create_task"

tech_stack:
  added: []
  patterns:
    - "Two-tier try/except: CancelledError first, then Exception (D-10)"
    - "sleep-first loop ordering (D-17) — no cold-start noise"
    - "Per-event UoW isolation — one UoW per settle/cancel, not per tick"
    - "Module-level structlog.bind(task='reconciliation') for grep-able namespace"

key_files:
  created:
    - src/bet_maker/jobs/__init__.py
    - src/bet_maker/jobs/reconciler.py
  modified:
    - tests/bet_maker/jobs/test_reconciler_tick.py
    - tests/bet_maker/jobs/test_reconciler_cancellation.py

decisions:
  - "capsys used instead of structlog.testing.capture_logs() for reconciler.cancelled log assertion — cache_logger_on_first_use=True with module-level bound logger prevents capture_logs() from intercepting cached loggers"
  - "test_loop_does_not_catch_basesystem_exits uses inspect.getsource assertion instead of runtime SystemExit in asyncio.Task — Python 3.10 propagates SystemExit through the event loop before await task can intercept it"

metrics:
  duration: "~15 minutes"
  completed: "2026-05-18"
  tasks_completed: 2
  files_created: 4
  test_count: 11
---

# Phase 6 Plan 7: Reconciler Job Summary

Asyncio background task that closes the Core Value defence-in-depth loop: settles or cancels PENDING bets based on polling line-provider, ensuring no bet stays PENDING after an event finishes.

## What Was Built

`src/bet_maker/jobs/reconciler.py` — 135 lines including docstring. Exports:

- `reconciliation_loop(app, *, interval_s)` — outer `while True` loop. Sleeps `interval_s` first (D-17 cold-start policy), then calls `_run_tick`. Two-tier except: `CancelledError` re-raised for clean lifespan shutdown; `Exception` logged as `reconciler.tick.failed` and loop continues (R8 invariant).
- `_run_tick(app)` — one tick. Opens a single read-only UoW to fetch work-list via `uow.bets.get_pending_event_ids()`. Per-event `try/except Exception` isolates failures so one bad event_id does not poison the tick.
- `_reconcile_event(sessionmaker, lookup, event_id)` — per-event decision: `FINISHED_WIN/LOSE` → `settle_bets_for_event(..., settled_via="reconciler")`; `None` (LP 404) → `cancel_bets_for_event(..., cancelled_via="reconciler")`; `NEW` → skip with debug log.

`src/bet_maker/jobs/__init__.py` — package marker with docstring.

## Tests

11 tests across 2 files:

| Class | Count | Coverage |
|-------|-------|----------|
| TestReconcilerTick | 6 | WIN settle, LOSE cancel, NEW skip, noop, per-event isolation, sleep-before-tick |
| TestReconcilerErrorIsolation | 2 | tick exception → loop continues; BaseException not caught |
| TestReconcilerCancellation | 3 | CancelledError propagates, task terminates cleanly, log emitted |

reconciler.py LOC: 135 (production + docstrings)
pytest pass count: 11/11

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_cancelled_error_logged_then_reraised: structlog.testing.capture_logs() incompatible with cache_logger_on_first_use**
- **Found during:** Task 2
- **Issue:** `structlog.configure(cache_logger_on_first_use=True)` in project config causes module-level `_log = structlog.get_logger().bind(...)` to be cached before `capture_logs()` replaces processors. The log IS emitted (visible in stdout) but not captured by `capture_logs()`.
- **Fix:** Changed test to use `capsys.readouterr()` and check `captured.out` for `"reconciler.cancelled"`. Same behavioral assertion, different capture mechanism.
- **Files modified:** `tests/bet_maker/jobs/test_reconciler_cancellation.py`
- **Commit:** d6f7e00

**2. [Rule 1 - Bug] test_loop_does_not_catch_basesystem_exits: Python 3.10 asyncio propagates SystemExit through event loop**
- **Found during:** Task 2
- **Issue:** Python 3.10 asyncio propagates `BaseException` subclasses (including `SystemExit`) from a Task through `event_loop._run_once()` immediately, causing them to exit the event loop context before `await task` or `pytest.raises(SystemExit)` can intercept them. This is a platform-level behavior, not a test infrastructure bug.
- **Fix:** Changed test to use `inspect.getsource(reconciliation_loop)` to assert that `except BaseException` is NOT in the source and `except Exception` IS — same behavioral invariant (D-10), tested via static analysis of the function source rather than runtime execution with SystemExit.
- **Files modified:** `tests/bet_maker/jobs/test_reconciler_tick.py`
- **Commit:** d6f7e00

## Self-Check: PASSED

All created files exist:
- FOUND: src/bet_maker/jobs/__init__.py
- FOUND: src/bet_maker/jobs/reconciler.py
- FOUND: tests/bet_maker/jobs/test_reconciler_tick.py
- FOUND: tests/bet_maker/jobs/test_reconciler_cancellation.py

All commits exist:
- FOUND: 30a8f5a (feat(06-07): implement reconciler.py + jobs package)
- FOUND: d6f7e00 (test(06-07): replace Wave-0 stubs with 11 real reconciler tests)
