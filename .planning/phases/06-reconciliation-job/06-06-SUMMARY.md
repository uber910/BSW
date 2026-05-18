---
phase: 06-reconciliation-job
plan: "06"
subsystem: bet_maker
tags: [interactor, cancel, idempotent, uow, for-update-skip-locked, dto]
dependency_graph:
  requires: [06-03, 06-05]
  provides: [cancel_bets_for_event interactor, CancelResult DTO]
  affects: [06-07-reconciler-job]
tech_stack:
  added: []
  patterns:
    - "FOR UPDATE SKIP LOCKED idempotency — reuse of get_pending_locked, identical to settle path"
    - "UoW async context manager — no manual commit/rollback in interactor"
    - "Server-side timestamp via func.now() in UPDATE, Python-side cancelled_at for DTO"
key_files:
  created:
    - src/bet_maker/interactors/cancel_bets_for_event.py
    - tests/bet_maker/interactors/test_cancel_bets_for_event.py (replaced Wave-0 stub)
  modified:
    - src/bet_maker/schemas/settle.py (added CancelResult)
decisions:
  - "D-04: CancelResult has no terminal_state — cancellation has no outcome; cancelled_via is Literal['reconciler']"
  - "Concurrent safety delegated entirely to get_pending_locked (SKIP LOCKED + status filter) — no extra locking logic in interactor"
  - "settled_at / settled_via columns reused for cancel audit trail — same observability semantics as settle path"
metrics:
  duration: "~8 minutes"
  completed: "2026-05-18"
  tasks_completed: 2
  files_changed: 3
---

# Phase 06 Plan 06: Cancel Interactor Summary

**One-liner:** Idempotent `cancel_bets_for_event` interactor with `CancelResult` DTO; 404-branch of reconciler using FOR UPDATE SKIP LOCKED + 9 testcontainer PG tests covering happy path, noop, concurrent settle race, and DTO shape.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add CancelResult DTO to schemas/settle.py | 7fc7801 | src/bet_maker/schemas/settle.py |
| 2 | Implement cancel_bets_for_event + 9 real tests | b09d60d | src/bet_maker/interactors/cancel_bets_for_event.py, tests/bet_maker/interactors/test_cancel_bets_for_event.py |

## What Was Built

### CancelResult DTO (`src/bet_maker/schemas/settle.py`)

Sibling class to `SettleResult`, added after it in the same module:
- `frozen=True, extra="forbid"` — immutable on construction
- `cancelled_via: Literal["reconciler"]` — one call site today, intentionally narrow
- No `terminal_state` field — cancellation has no outcome (D-04)
- Fields: `event_id`, `cancelled_count`, `cancelled_bet_ids`, `cancelled_via`, `cancelled_at`

### cancel_bets_for_event interactor (`src/bet_maker/interactors/cancel_bets_for_event.py`)

Byte-for-byte sibling of `settle_bets_for_event`, differing in:
- Output DTO: `CancelResult` instead of `SettleResult`
- New status: `BetStatus.CANCELLED` instead of WON/LOST
- Log namespaces: `cancel.committed` / `cancel.noop`
- No `_TERMINAL_TO_STATUS` mapping needed

Idempotency mechanism is identical to settle: `get_pending_locked(event_id)` returns `[]` on second call, short-circuiting to a 0-row noop. Concurrent cancel vs settle on the same event_id is safe by construction — both paths use the same `get_pending_locked` lock, so SKIP LOCKED ensures exactly one wins.

### Test Suite (`tests/bet_maker/interactors/test_cancel_bets_for_event.py`)

Replaced Wave-0 stub (9 `pytest.fail()` stubs) with 9 real assertions against testcontainer PG:

| Class | Test | Assertion |
|-------|------|-----------|
| TestCancelHappyPath | test_cancels_two_pending_bets_to_cancelled_status | cancelled_count==2, status==CANCELLED |
| TestCancelHappyPath | test_settled_via_is_reconciler | bet.settled_via=="reconciler" in DB |
| TestCancelHappyPath | test_settled_at_is_filled | bet.settled_at IS NOT NULL |
| TestCancelNoop | test_idempotent_second_call_returns_zero | first=1, second=0 |
| TestCancelNoop | test_noop_when_no_pending_for_event | cancelled_count==0 on empty event |
| TestCancelNoop | test_noop_when_only_already_cancelled_exist | cancelled_count==0 |
| TestCancelConcurrent | test_concurrent_with_settle_no_double_update | sorted([settle,cancel])==[0,3] |
| TestCancelResultShape | test_cancel_result_is_frozen | ValidationError on mutation |
| TestCancelResultShape | test_cancel_result_cancelled_at_is_utc_aware | tzinfo is not None |

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- `uv run pytest -x -q tests/bet_maker/interactors/test_cancel_bets_for_event.py tests/bet_maker/test_settle.py` — 18 passed
- `uv run mypy src/` — Success: no issues found in 81 source files
- `uv run ruff check src/ tests/` — All checks passed

## Known Stubs

None — all 9 Wave-0 stubs replaced with real assertions.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The cancel interactor writes to existing `bets` table columns (`status`, `settled_at`, `settled_via`) already present from Phase 5.

## Self-Check: PASSED

- `src/bet_maker/interactors/cancel_bets_for_event.py` — FOUND
- `src/bet_maker/schemas/settle.py` (CancelResult class) — FOUND
- `tests/bet_maker/interactors/test_cancel_bets_for_event.py` (9 tests, no Wave-0 stubs) — FOUND
- Commit 7fc7801 — FOUND
- Commit b09d60d — FOUND
