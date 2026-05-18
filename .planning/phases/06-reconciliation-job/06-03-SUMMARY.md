---
phase: 06-reconciliation-job
plan: "03"
subsystem: bet_maker/schemas + alembic/versions
tags: [enum, alembic, autocommit-block, cancelled, migration]
dependency_graph:
  requires: [06-01, 06-02]
  provides: [BetStatus.CANCELLED, alembic-0003, PG-bet_status-cancelled]
  affects: [06-05, 06-06, 06-07]
tech_stack:
  added: []
  patterns: [autocommit_block, IF-NOT-EXISTS-idempotency, static-source-introspection-test]
key_files:
  created:
    - alembic/versions/20260518_0003_bet_status_cancelled.py
  modified:
    - src/bet_maker/schemas/bets.py
    - tests/bet_maker/migrations/test_0003_cancelled.py
    - tests/bet_maker/test_schemas.py
decisions:
  - "D-03 verbatim: CANCELLED = 'cancelled' (lower-case) -- distinct recovery status vs terminal outcomes (PENDING/WON/LOST are upper-case)"
  - "autocommit_block required: PG forbids ALTER TYPE ADD VALUE inside a transaction; Alembic async env wraps every migration in one"
  - "IF NOT EXISTS for idempotency -- second alembic upgrade head is a no-op (test fixture runs it twice)"
  - "downgrade() is intentional no-op -- PG DROP VALUE unsupported without full ENUM recreation; acceptable for test-task scope"
metrics:
  duration: ~5 min
  completed: "2026-05-18"
  tasks: 2
  files_created: 1
  files_modified: 3
requirements: [BM-12]
---

# Phase 06 Plan 03: Cancelled Status Migration Summary

BetStatus.CANCELLED Python enum + Alembic 0003 ALTER TYPE migration with autocommit_block, replacing Wave-0 stub with 3 real assertions.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add BetStatus.CANCELLED to Python enum | 8cdc495 | src/bet_maker/schemas/bets.py, tests/bet_maker/test_schemas.py |
| 2 | Create Alembic migration 0003 + real tests | f8ab81d | alembic/versions/20260518_0003_bet_status_cancelled.py, tests/bet_maker/migrations/test_0003_cancelled.py |

## Key Changes

### src/bet_maker/schemas/bets.py

One line added after `LOST = "LOST"`:
```python
CANCELLED = "cancelled"
```
Docstring extended with CANCELLED recovery-status description. The lower-case value is intentional per D-03 — creates a mixed-case PG ENUM (`PENDING`, `WON`, `LOST`, `cancelled`) as a distinct visual marker for the recovery path vs terminal outcomes.

### alembic/versions/20260518_0003_bet_status_cancelled.py

Full migration:
```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'")

def downgrade() -> None:
    pass
```

Critical pattern: `op.get_context().autocommit_block()` exits the surrounding Alembic transaction, runs the DDL under autocommit, then restarts a fresh transaction. Without this PG raises `ActiveSQLTransactionError` because `ALTER TYPE ... ADD VALUE` is forbidden inside a transaction block.

### tests/bet_maker/migrations/test_0003_cancelled.py

Wave-0 stub replaced with 3 real assertions:
1. `test_alter_type_adds_cancelled_value` -- queries `pg_enum` directly, asserts exact 4-label set `{PENDING, WON, LOST, cancelled}`
2. `test_migration_is_idempotent_on_rerun` -- fixture already ran upgrade twice; reaching this test proves idempotency; asserts count == 4
3. `test_autocommit_block_used` -- static source inspection of migration file, asserts both `autocommit_block` and `ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'` in source

### tests/bet_maker/test_schemas.py

`test_betstatus_has_three_members` renamed to `test_betstatus_has_four_members` and updated to include CANCELLED in the expected dict.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_betstatus_has_three_members asserted exactly 3 members**
- **Found during:** Task 1 post-verification
- **Issue:** Existing test `test_betstatus_has_three_members` expected `{"PENDING": "PENDING", "WON": "WON", "LOST": "LOST"}` -- failed after CANCELLED was added
- **Fix:** Renamed test to `test_betstatus_has_four_members`, extended expected dict with `"CANCELLED": "cancelled"`
- **Files modified:** tests/bet_maker/test_schemas.py
- **Commit:** 8cdc495 (same task commit)

## Test Results

```
tests/bet_maker/migrations/test_0003_cancelled.py::TestMigration0003::test_alter_type_adds_cancelled_value PASSED
tests/bet_maker/migrations/test_0003_cancelled.py::TestMigration0003::test_migration_is_idempotent_on_rerun PASSED
tests/bet_maker/migrations/test_0003_cancelled.py::TestMigration0003::test_autocommit_block_used PASSED
92 passed (schema + model + settle + repository + routes + lifespan + migration tests) 4 warnings
```

Wave-0 stubs in other Phase 6 plans (06-04 settings, 06-05 repo, etc.) were already failing before this plan and remain out-of-scope here.

## Acceptance Criteria Check

- [x] `BetStatus.CANCELLED.value == "cancelled"` -- python assertion passes
- [x] `grep -E '^\s+CANCELLED = "cancelled"' src/bet_maker/schemas/bets.py | wc -l` == 1
- [x] `grep -cE '^\s+(PENDING|WON|LOST|CANCELLED) =' src/bet_maker/schemas/bets.py` == 4
- [x] `test -f alembic/versions/20260518_0003_bet_status_cancelled.py` -- exists
- [x] `autocommit_block` present in migration source
- [x] `ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'` present in migration source
- [x] `down_revision = "0002_bets_settled_columns"` in migration
- [x] 3 migration tests pass
- [x] `grep -c "Wave-0 stub" tests/bet_maker/migrations/test_0003_cancelled.py` == 0
- [x] mypy src/ exits 0 (45 files clean)
- [x] ruff check exits 0

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced.
Migration DDL is contained to adding a single ENUM value -- no trust boundary changes beyond what was specified in the plan's threat model.

T-06-03-01 (DoS via broken schema): mitigated -- IF NOT EXISTS + autocommit_block verified by test_autocommit_block_used.
T-06-03-02 (silent enum drift): mitigated -- test_alter_type_adds_cancelled_value asserts exact 4-label set.
T-06-03-03 (untracked DDL): mitigated -- migration file in alembic/versions/ with revision metadata.

## Self-Check: PASSED

- src/bet_maker/schemas/bets.py: FOUND and CANCELLED member confirmed
- alembic/versions/20260518_0003_bet_status_cancelled.py: FOUND
- tests/bet_maker/migrations/test_0003_cancelled.py: FOUND, no Wave-0 stubs
- Commit 8cdc495: FOUND (Task 1)
- Commit f8ab81d: FOUND (Task 2)
