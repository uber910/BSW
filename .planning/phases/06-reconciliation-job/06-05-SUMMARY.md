---
phase: 06-reconciliation-job
plan: "05"
subsystem: bet_maker/repositories
tags: [repository, sqlalchemy, select-distinct, bug-fix]
requirements: [BM-12]

dependency_graph:
  requires: [06-01, 06-02, 06-03]
  provides: [BetRepository.get_pending_event_ids]
  affects: [06-07-reconciler]

tech_stack:
  added: []
  patterns:
    - "SELECT DISTINCT single-column via .scalars().all() (RESEARCH Pitfall 4)"
    - "SqlEnum values_callable for lowercase PG ENUM values"

key_files:
  created: []
  modified:
    - src/bet_maker/repositories/bets.py
    - src/bet_maker/models/bet.py
    - tests/bet_maker/repositories/test_get_pending_event_ids.py

decisions:
  - "D-01: get_pending_event_ids uses SELECT DISTINCT without FOR UPDATE — reconciler reads first, settle path uses get_pending_locked with row locks"
  - "Rule 1 bug fix: SqlEnum(BetStatus, values_callable=...) added so BetStatus.CANCELLED.value='cancelled' maps to PG ENUM correctly instead of .name='CANCELLED'"

metrics:
  duration: "~12 minutes"
  completed: "2026-05-18"
  tasks: 1
  files_changed: 3
---

# Phase 06 Plan 05: get_pending_event_ids Summary

BetRepository.get_pending_event_ids() returning `list[UUID]` via `SELECT DISTINCT event_id WHERE status='PENDING'` with `.scalars().all()`.

## What Was Built

New read-only method on `BetRepository` (D-01 / D-11):

```python
async def get_pending_event_ids(self) -> list[UUID]:
    result = await self._session.execute(
        select(Bet.event_id).where(Bet.status == BetStatus.PENDING).distinct()
    )
    return list(result.scalars().all())
```

The reconciler tick (Plan 06-07 `_run_tick`) calls this to discover which events still have unsettled bets. No FOR UPDATE, no commit, no flush — Anti-Pattern 1 preserved.

## Tests

4 real assertions replacing the Wave-0 stub in `tests/bet_maker/repositories/test_get_pending_event_ids.py`:

| Test | What it verifies |
|------|-----------------|
| `test_returns_distinct_event_ids_for_pending_bets` | 3 bets on A + 2 on B → set {A, B}, len == 2 |
| `test_excludes_won_lost_cancelled_bets` | WON/LOST/CANCELLED bets excluded; only PENDING returned |
| `test_returns_empty_list_when_no_pending` | Empty table → `[]` |
| `test_no_commit_no_flush` | Source inspection: no `.commit(`, `.flush(`, `.rollback(` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed SqlEnum enum value serialization for BetStatus.CANCELLED**

- **Found during:** Task 1 — `test_excludes_won_lost_cancelled_bets` failed with `asyncpg.exceptions.InvalidTextRepresentationError: invalid input value for enum bet_status: "CANCELLED"`
- **Issue:** `SqlEnum(BetStatus, name="bet_status")` without `values_callable` uses `.name` of enum members for PG ENUM storage. `BetStatus.CANCELLED.name = "CANCELLED"` but PG ENUM was created with `ALTER TYPE bet_status ADD VALUE 'cancelled'` (lowercase). The mismatch caused INSERT to fail for CANCELLED bets. WON/LOST/PENDING were unaffected because their `.name == .value`.
- **Fix:** Added `values_callable=lambda x: [e.value for e in x]` to `SqlEnum` in `src/bet_maker/models/bet.py:Bet.status`. This forces SQLAlchemy to use `.value` (`"cancelled"`) instead of `.name` (`"CANCELLED"`) for PG ENUM serialization.
- **Files modified:** `src/bet_maker/models/bet.py`
- **Commit:** `b878659` (included in same commit)
- **Regression check:** `test_repositories.py` + `test_settle.py` — 17 passed, 0 failures.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `src/bet_maker/repositories/bets.py` exists | FOUND |
| `tests/bet_maker/repositories/test_get_pending_event_ids.py` exists | FOUND |
| `src/bet_maker/models/bet.py` exists | FOUND |
| Commit `b878659` exists | FOUND |
| `get_pending_event_ids` count in bets.py == 1 | 1 |
| `select(Bet.event_id)` count in bets.py == 1 | 1 |
| `.distinct()` count in bets.py == 1 | 1 |
| Wave-0 stub removed | 0 occurrences |
| 4 new tests pass | PASSED |
| 17 existing tests (repositories + settle) pass | PASSED |
| mypy strict exits 0 | PASSED |
| ruff exits 0 | PASSED |
