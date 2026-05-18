---
phase: 05
plan: 04
subsystem: bet_maker/interactors
tags: [settle, idempotency, for-update-skip-locked, concurrent, tdd]
dependency_graph:
  requires: [05-01, 05-02, 05-03]
  provides: [settle_bets_for_event, SettleResult]
  affects: [05-05-consumer, 06-reconciler]
tech_stack:
  added: []
  patterns:
    - Idempotent bulk UPDATE via FOR UPDATE SKIP LOCKED status-filter (R3 / D-12)
    - PG server-side settled_at via func.now() in UPDATE statement (D-14)
    - asyncio.gather concurrent settle race test against real PG testcontainer
    - Keyword-only async function signature (D-17)
key_files:
  created:
    - src/bet_maker/interactors/settle_bets_for_event.py
  modified:
    - tests/bet_maker/test_settle.py
decisions:
  - No separate consumed_events table — status filter is the single idempotency source (D-15)
  - settled_at in SettleResult uses Python utc_now() for return DTO; PG func.now() fills the DB column (D-14)
  - settled_via typed as Literal["consumer", "reconciler"] — mypy strict enforces at all call sites (T-05-04-02)
  - No broker dispatch inside interactor — Anti-Pattern 2 guarded by design
metrics:
  duration: ~10 min
  completed: "2026-05-18"
  tasks_completed: 2
  files_changed: 2
---

# Phase 5 Plan 04: Settle Interactor Summary

**One-liner:** Idempotent `settle_bets_for_event` interactor with FOR UPDATE SKIP LOCKED status-filter as the single settle path for both consumer (Plan 05) and reconciler (Phase 6).

## What Was Built

### Settle Interactor (Task 1)

`src/bet_maker/interactors/settle_bets_for_event.py` — the SINGLE source of PENDING→WON/LOST transitions in the system.

Signature (D-17):
```python
async def settle_bets_for_event(
    uow: AsyncUnitOfWork,
    *,
    event_id: UUID,
    terminal_state: EventTerminalState,
    settled_via: Literal["consumer", "reconciler"],
) -> SettleResult: ...
```

Key implementation properties:
- `async with uow:` wraps the entire operation — UoW commits on clean exit, rolls back on exception (R2/F4)
- `uow.bets.get_pending_locked(event_id)` delegates SELECT + FOR UPDATE SKIP LOCKED to repository (Plan 03)
- `bet_ids` captured before UPDATE — no lazy-load after UoW commit (Anti-Pattern A1 guarded)
- `settled_at=func.now()` in UPDATE fills PG server-side timestamp (D-14)
- `settle.noop` structlog info event on 0 rows; `settle.committed` on success
- Zero broker calls — Anti-Pattern 2 (R9/R12) guarded

### Test Suite (Task 2)

`tests/bet_maker/test_settle.py` — complete replacement of Wave 0 stubs.

| Class | Tests | Description |
|-------|-------|-------------|
| `TestSettleHappyPath` | 2 | WON flip for 3 PENDING bets; LOST flip for 1 bet |
| `TestSettleNoop` | 3 | Second call returns 0; WON-only event returns 0; other event unchanged |
| `TestSettleConcurrent` | 2 | asyncio.gather race: sum==3; strong assertion [0,3] |
| `TestSettleResultShape` | 2 | Frozen SettleResult; UTC-aware settled_at |

All 9 tests pass against real PG testcontainer. SQLite is explicitly ruled out (FOR UPDATE SKIP LOCKED not supported).

## Proof of R3 Closure (Concurrent Settle Race)

`TestSettleConcurrent::test_concurrent_settled_via_attribution_is_single_pass` proves exactly-once attribution:
- Inserts 3 PENDING bets under one `event_id`
- Runs `asyncio.gather(settle_consumer(), settle_reconciler())` — both target the same event_id simultaneously
- Asserts `sorted([r1.settled_count, r2.settled_count]) == [0, 3]`

The mechanism: whichever coroutine enters `SELECT ... FOR UPDATE SKIP LOCKED` first acquires row locks on all 3 PENDING rows. The second coroutine's `SKIP LOCKED` returns 0 rows immediately (the locked rows are skipped), resulting in a no-op. PostgreSQL's row-level locking with SKIP LOCKED is the single concurrency primitive — no additional messaging or coordination needed. This satisfies D-12 without a `consumed_events` table.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's threat model covers.

- T-05-04-01: Double-update via consumer+reconciler race — MITIGATED by `with_for_update(skip_locked=True) + WHERE status='PENDING'` (Plan 03 repo) + TestSettleConcurrent proving exactly-once attribution.
- T-05-04-02: settled_via arbitrary text — MITIGATED by `Literal["consumer", "reconciler"]` typing + mypy strict enforcement.
- T-05-04-04: settled_at not recorded — MITIGATED by `settled_at=func.now()` in UPDATE, non-NULL after settle.

## Self-Check: PASSED

Files created/modified:
- `src/bet_maker/interactors/settle_bets_for_event.py` — FOUND
- `tests/bet_maker/test_settle.py` — FOUND

Commits:
- `1fa108c` feat(05-04): implement settle_bets_for_event idempotent interactor — FOUND
- `41e12f3` test(05-04): implement full settle test suite — idempotency + concurrent R3 — FOUND
