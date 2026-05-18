---
phase: 06-reconciliation-job
plan: 10
subsystem: bet_maker/e2e
tags: [e2e, testcontainers, rabbitmq, postgres, drop-publish, sc5, qa-08]
dependency_graph:
  requires: [06-09, 05-09]
  provides: [QA-08, SC#5]
  affects: [tests/bet_maker/e2e/]
tech_stack:
  added: []
  patterns:
    - "_swap_to_fast_reconciler / _restore_default_reconciler — cancel-and-recreate reconciler task with 1.0s interval for fast test feedback"
    - "patch('line_provider.facades.event_bus.RabbitEventBus.publish', AsyncMock()) — class-level patch to suppress AMQP publish"
    - "InMemoryEventStore._data.pop(UUID) — direct in-process dict mutation to simulate event deletion"
key_files:
  created: []
  modified:
    - tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py
    - tests/bet_maker/conftest.py
    - tests/bet_maker/test_alembic.py
decisions:
  - "Both app.state.event_lookup AND app.state.reconciler_event_lookup must be swapped to lp_client — reconciler uses a separate lookup instance, not the same one used by HTTP routes"
  - "InMemoryEventStore internal dict is _data (not _events as planner template assumed) — verified by reading src/line_provider/infrastructure/store/in_memory.py"
  - "BetStatus.CANCELLED.value == 'cancelled' (lowercase), unlike WON='WON' and LOST='LOST' — must use BetStatus.CANCELLED.value in assert, not string literal"
metrics:
  duration_minutes: 25
  completed_date: "2026-05-18"
  tasks_completed: 1
  files_modified: 3
---

# Phase 06 Plan 10: E2E Drop-Publish Reconciler Tests Summary

Real-RMQ + real-PG e2e test suite with 3 scenarios proving the Core Value invariant: a bet never stays PENDING after its event finishes, even when the AMQP publish is dropped.

## What Was Built

`tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` — 3 real e2e tests replacing Wave-0 stubs.

| Scenario | Method | What Proves |
|----------|--------|-------------|
| a — consumer happy path | `test_consumer_happy_path_settles_won` | Phase 5 consumer still works; no regression from reconciler wiring |
| b — drop publish recovery (QA-08 main) | `test_drop_publish_reconciler_recovers_won` | AMQP publish silenced via `patch(RabbitEventBus.publish)` → reconciler sweeps PENDING bet → WON |
| c — event deleted → cancel | `test_delete_event_reconciler_cancels_bet` | LP event physically removed from in-memory store → reconciler sees 404 → CANCELLED |

All 3 tests use:
- Real RabbitMQ testcontainer (session-scoped, from `tests/conftest.py`)
- Real PostgreSQL testcontainer (session-scoped, from `tests/conftest.py`)
- Full bet-maker lifespan (consumer + reconciler both running)
- Full line-provider lifespan (RabbitEventBus wired to real RMQ)
- Reconciler overridden to 1.0s interval via `_swap_to_fast_reconciler` / `_restore_default_reconciler` (D-24)

Runtime: ~10s for all 3 scenarios on warm testcontainer cache.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] event_store internal dict is `_data` not `_events`**

- **Found during:** Task 1 implementation (Scenario c)
- **Issue:** Planner template used `event_store._events.pop(UUID(event_id), None)` but `InMemoryEventStore` uses `self._data` as its internal dict
- **Fix:** Used `event_store._data.pop(UUID(event_id), None)`
- **Files modified:** `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py`
- **Commit:** 3168ad3

**2. [Rule 1 - Bug] Reconciler uses `app.state.reconciler_event_lookup`, not `event_lookup`**

- **Found during:** First test run — Scenario b failed with ConnectError to production LP URL
- **Issue:** Plan template only swapped `app.state.event_lookup` for the test LP client. But the reconciler reads `app.state.reconciler_event_lookup` (a separate HttpEventLookup instance per D-06). Without swapping it too, the reconciler tried to reach the production line-provider URL and got ConnectError.
- **Fix:** Swap both `app.state.event_lookup` and `app.state.reconciler_event_lookup` to `HttpEventLookup(http_client=lp_client, ...)` in every test; restore both in `finally`.
- **Files modified:** `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py`
- **Commit:** 3168ad3

**3. [Rule 1 - Bug] `BetStatus.CANCELLED.value == 'cancelled'` (lowercase mismatch)**

- **Found during:** Scenario c test run — `AssertionError: 'cancelled' == 'CANCELLED'`
- **Issue:** Scenario c asserted `bet["status"] == "CANCELLED"` (uppercase), but `BetStatus.CANCELLED = "cancelled"` (lowercase, unlike WON/LOST which are uppercase)
- **Fix:** Changed assert to `bet["status"] == BetStatus.CANCELLED.value`
- **Files modified:** `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py`
- **Commit:** 3168ad3

**4. [Rule 1 - Bug] `test_alembic.py::test_bet_status_enum_has_three_values` failed — stale after Phase 6 migration**

- **Found during:** Full suite run (`tests/bet_maker/`)
- **Issue:** Test asserted `labels == ["PENDING", "WON", "LOST"]` but Phase 6 Plan 06-03 added `ALTER TYPE betstatus ADD VALUE IF NOT EXISTS 'cancelled'`, making the enum have 4 values
- **Fix:** Updated test to `test_bet_status_enum_has_four_values` with `labels == ["PENDING", "WON", "LOST", "cancelled"]`
- **Files modified:** `tests/bet_maker/test_alembic.py`
- **Commit:** 3168ad3

**5. [Rule 1 - Bug] Cross-test contamination via `app.state.reconciler_event_lookup` mutation**

- **Found during:** Full suite run — `test_lifespan_reconciler.py::test_reconciler_event_lookup_pinned_on_state` failed when run after `test_reconciler_tick.py`
- **Issue:** `test_reconciler_tick.py` tests set `app.state.reconciler_event_lookup = _FakeLookup()` but never restore it. Since `app` is session-scoped, the fake lookup persisted into subsequent tests.
- **Fix:** Added autouse fixture `_restore_reconciler_event_lookup` in `tests/bet_maker/conftest.py` that captures and restores the original `reconciler_event_lookup` around each test
- **Files modified:** `tests/bet_maker/conftest.py`
- **Commit:** 3168ad3

## Target Path Adjustments vs Planner Template

| Planner path | Actual path | Source |
|---|---|---|
| `line_provider.facades.event_bus.RabbitEventBus.publish` | Same — no change needed | `grep -rE "class RabbitEventBus"` |
| `event_store._events` | `event_store._data` | `src/line_provider/infrastructure/store/in_memory.py:26` |
| only swap `event_lookup` | swap both `event_lookup` + `reconciler_event_lookup` | CONTEXT.md D-06 re-read |

## Scenario Outcomes

| Scenario | Expected | Actual | Time |
|----------|----------|--------|------|
| a: consumer happy path | WON | PASSED | ~3s |
| b: drop-publish recovery | WON via reconciler | PASSED | ~4s |
| c: event deleted → CANCELLED | CANCELLED via reconciler | PASSED | ~4s |
| Full suite `tests/bet_maker/` | 236 passed | 236 passed | ~25s |

## Self-Check

- tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py: FOUND
- tests/bet_maker/conftest.py: FOUND
- tests/bet_maker/test_alembic.py: FOUND
- commit 3168ad3: verified via `git log`

## Self-Check: PASSED
