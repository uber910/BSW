---
phase: 03-bet-maker-domain-db
plan: 04
subsystem: bet-maker
tags: [bet-maker, sqlalchemy-2.0, alembic, postgres-enum, testcontainers, wave-2]
dependency_graph:
  requires: [03-02, 03-03]
  provides: [Bet ORM model, Base metadata, 0001_bets_initial migration]
  affects: [03-06, 03-07, 03-08]
tech_stack:
  added: []
  patterns:
    - "postgresql.ENUM(create_type=False) inside op.create_table (not sa.Enum) to prevent _create_events re-creation"
    - "pytest.mark.asyncio(loop_scope='session') for tests using session-scoped AsyncEngine"
    - "conditional DSN in env.py: set only if not already overridden by test fixture"
key_files:
  created:
    - src/bet_maker/models/__init__.py
    - src/bet_maker/models/bet.py
    - alembic/versions/20260515_0001_bets_initial.py
    - tests/bet_maker/test_models.py
    - tests/bet_maker/test_alembic.py
  modified:
    - alembic/env.py
    - tests/conftest.py
decisions:
  - "postgresql.ENUM (not sa.Enum) in op.create_table: sa.Enum._create_events=True triggers type re-creation even with create_type=False; postgresql.ENUM respects the flag correctly"
  - "env.py DSN conditional: guard config.get_main_option(None) so test fixture's set_main_option survives env.py load"
  - "loop_scope='session' on TestRuntime and TestMigration: session-scoped AsyncEngine must share event loop with async test methods"
  - "TESTCONTAINERS_RYUK_DISABLED=true in conftest.py: Ryuk reaper fails on macOS Docker Desktop without exposed port 8080"
  - "test_id_default_is_uuid4 uses __module__+__qualname__ not 'is': different module loads produce non-identical function objects"
metrics:
  duration: "~10 min"
  completed: "2026-05-15"
  tasks: 5
  files: 7
---

# Phase 03 Plan 04: Bet ORM + Alembic Initial Migration Summary

**One-liner:** SQLAlchemy 2.0 Bet model (PgUUID, Numeric(12,2), PG native ENUM bet_status) + idempotent Alembic migration (ENUM.create checkfirst=True + postgresql.ENUM create_type=False) + 16 tests (12 model + 4 alembic).

## What Was Built

### Task 1: Bet ORM Model + models package

- `src/bet_maker/models/bet.py` — `class Base(DeclarativeBase)` + `class Bet(Base)` per D-09:
  - `id: Mapped[uuid.UUID]` — `PgUUID(as_uuid=True)`, PK, `default=uuid.uuid4`
  - `event_id: Mapped[uuid.UUID]` — `PgUUID(as_uuid=True)`, NO FK
  - `amount: Mapped[Decimal]` — `Numeric(12, 2)`, `nullable=False`
  - `status: Mapped[BetStatus]` — `SqlEnum(BetStatus, name="bet_status", create_type=True)`, `default=BetStatus.PENDING`
  - `created_at/updated_at: Mapped[datetime]` — `server_default=func.now()`, `onupdate=func.now()` on updated_at
- `src/bet_maker/models/__init__.py` — re-exports `Base, Bet` for Alembic env.py import

### Task 2: alembic/env.py target_metadata

- `target_metadata = Base.metadata` (replaces `= None`)
- Conditional DSN: `if not config.get_main_option("sqlalchemy.url", None)` guards against test fixture overrides

### Task 3: Initial Alembic Migration

- `alembic/versions/20260515_0001_bets_initial.py` — `revision = "0001_bets_initial"`, `down_revision = None`
- `upgrade()`: explicit `postgresql.ENUM.create(bind, checkfirst=True)` + `op.create_table("bets", ...)` with `postgresql.ENUM(create_type=False)` for status column
- `downgrade()`: `op.drop_table("bets")` + `postgresql.ENUM.drop(bind, checkfirst=True)`

### Task 4: test_models.py

- 12 tests in 2 classes:
  - `TestSchema` (9 sync tests): tablename, Numeric(12,2) shape, ENUM name, no FK, uuid4 default, server_default, onupdate, no coefficient, single table
  - `TestRuntime` (3 async tests, `loop_scope="session"`): flush+refresh loads server_defaults (Pitfall 1), Decimal round-trip exact (Pitfall 7), PENDING default

### Task 5: test_alembic.py

- 4 tests in `TestMigration` (`loop_scope="session"`):
  - `test_bets_table_exists_after_migration` — information_schema.tables check
  - `test_bet_status_enum_exists_after_migration` — pg_type check
  - `test_bet_status_enum_has_three_values` — pg_enum sortorder [PENDING, WON, LOST]
  - `test_upgrade_head_third_run_idempotent` — third upgrade head call (no-op)

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest tests/bet_maker/test_models.py -q --no-cov` | 12 passed |
| `uv run pytest tests/bet_maker/test_alembic.py -q --no-cov` | 4 passed |
| `uv run mypy --strict src/bet_maker/models alembic/versions/20260515_0001_bets_initial.py` | 0 issues |
| `uv run pytest -q --no-cov` | 133 passed |
| `Bet.__table__.c.amount.type` precision=12, scale=2, asdecimal=True | PASS |
| `Bet.__table__.c.event_id.foreign_keys == set()` | PASS |
| `target_metadata = Base.metadata` in env.py | PASS |
| `checkfirst=True` occurrences in migration | 3 (upgrade create + downgrade drop) |
| `create_type=False` occurrences in migration | 4 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] alembic/env.py unconditional DSN override broke test isolation**
- **Found during:** Task 4 (`apply_migrations` fixture DSN was silently overwritten by env.py module load)
- **Issue:** `config.set_main_option("sqlalchemy.url", str(settings.postgres_dsn))` runs unconditionally at module load, overwriting the test-injected DSN with production `postgres:5432`
- **Fix:** Wrapped in `if not config.get_main_option("sqlalchemy.url", None):` guard
- **Files modified:** `alembic/env.py`
- **Commit:** 21e8f48

**2. [Rule 1 - Bug] sa.Enum._create_events triggered DuplicateObjectError on second upgrade head**
- **Found during:** Task 4 (runtime test setup)
- **Issue:** `sa.Enum(..., create_type=False)` inside `op.create_table` still registers `_create_events=True`, causing `CREATE TYPE bet_status` on every `op.create_table` call regardless of `create_type=False`. This breaks idempotency on second `upgrade head`.
- **Fix:** Replaced `sa.Enum(...)` with `postgresql.ENUM(...)` in `op.create_table` — the PostgreSQL dialect ENUM respects `create_type=False` correctly
- **Files modified:** `alembic/versions/20260515_0001_bets_initial.py`
- **Commit:** 21e8f48

**3. [Rule 1 - Bug] Testcontainers Ryuk reaper failed on macOS Docker Desktop**
- **Found during:** Task 4 (first test run)
- **Issue:** `ConnectionError: Port mapping for container ... and port 8080 is not available` — Ryuk reaper container tried to expose port 8080 but macOS Docker Desktop blocked it
- **Fix:** `os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")` in `tests/conftest.py`
- **Files modified:** `tests/conftest.py`
- **Commit:** 21e8f48

**4. [Rule 1 - Bug] Session-scoped AsyncEngine event loop mismatch with function-scoped async tests**
- **Found during:** Task 4 (`test_decimal_roundtrip_exact` failed with `RuntimeError: got Future attached to a different loop`)
- **Issue:** `async_engine` and `session_factory` are session-scoped — created in session event loop. Function-scoped async tests by default get a new event loop per test. asyncpg connections bound to session loop cannot be used in function loop.
- **Fix:** `@pytest.mark.asyncio(loop_scope="session")` on `TestRuntime` and `TestMigration` classes
- **Files modified:** `tests/bet_maker/test_models.py`, `tests/bet_maker/test_alembic.py`
- **Commit:** 21e8f48

**5. [Rule 1 - Bug] test_id_default_is_uuid4 used `is` identity check across module loads**
- **Found during:** Task 4 (TestSchema failure)
- **Issue:** `Bet.__table__.c.id.default.arg is uuid.uuid4` fails when `uuid` module is loaded separately by SQLAlchemy and by the test — different function objects in different module loads
- **Fix:** Replaced `is uuid.uuid4` with `callable(fn) and fn.__module__ == uuid.__name__ and fn.__qualname__ == "uuid4"`
- **Files modified:** `tests/bet_maker/test_models.py`
- **Commit:** 21e8f48

## Known Stubs

None — all features fully wired. `BetStatus` imported from `schemas/bets.py` (single source of truth). No placeholder data flowing to any UI.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes at trust boundaries beyond what was planned (bets table is internal DB storage, not exposed externally in this plan).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/bet_maker/models/__init__.py | FOUND |
| src/bet_maker/models/bet.py | FOUND |
| alembic/env.py | FOUND |
| alembic/versions/20260515_0001_bets_initial.py | FOUND |
| tests/bet_maker/test_models.py | FOUND |
| tests/bet_maker/test_alembic.py | FOUND |
| commit d4deff7 | FOUND |
| commit f571172 | FOUND |
| commit 69fc9dd | FOUND |
| commit 21e8f48 | FOUND |
| commit 04f40e7 | FOUND |
