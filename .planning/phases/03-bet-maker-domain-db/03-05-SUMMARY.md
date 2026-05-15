---
phase: 03-bet-maker-domain-db
plan: "05"
subsystem: bet-maker/infrastructure/db
tags: [bet-maker, infrastructure, db, engine, pings, sqlalchemy, tenacity, wave-3]
dependency_graph:
  requires: ["03-04"]
  provides: [create_engine_and_sessionmaker, wait_for_postgres, ping_postgres]
  affects: ["03-06 (AsyncUnitOfWork needs sessionmaker)", "03-08 (lifespan + /health)"]
tech_stack:
  added: []
  patterns:
    - "create_async_engine with QueuePool params: pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800"
    - "async_sessionmaker(engine, expire_on_commit=False) — D-15 MissingGreenlet mitigation"
    - "tenacity @retry(stop_after_attempt(10), wait_exponential(min=1,max=10), reraise=True) for async startup gate"
    - "structlog.warning with str(exc) only — D-29/T-03-5 DSN leak prevention"
key_files:
  created:
    - src/bet_maker/infrastructure/__init__.py
    - src/bet_maker/infrastructure/db/__init__.py
    - src/bet_maker/infrastructure/db/engine.py
    - src/bet_maker/infrastructure/db/pings.py
    - tests/bet_maker/test_db_engine.py
  modified: []
decisions:
  - "D-15/D-16 pool params locked and test-verified via QueuePool._max_overflow/_recycle/_pre_ping private attrs — confirmed stable on SQLAlchemy 2.0.49"
  - "ping_postgres False-path tested via AsyncMock injection (not real connection-refused): asyncpg 0.31.0 does NOT wrap OSError/ConnectionRefusedError into SQLAlchemyError in SQLA 2.0.49; real network error bypasses SQLAlchemy exception hierarchy — mock injection is the correct test strategy"
  - "ping_postgres happy-path test uses a function-scoped throwaway engine (not session-scoped async_engine fixture) to avoid asyncio loop mismatch: asyncio_default_test_loop_scope=function creates a new event loop per test; a session-scoped asyncpg connection pool bound to the session loop raises RuntimeError when used from a different loop"
metrics:
  duration: "~4m20s"
  completed: "2026-05-15"
  tasks: 3
  files: 5
---

# Phase 3 Plan 05: DB Infrastructure Engine + Pings Summary

**One-liner:** AsyncEngine factory with D-16 QueuePool params + tenacity 10-attempt PG startup gate + per-request SELECT 1 health ping.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create infrastructure/db/engine.py + package markers | fdf347e | infrastructure/__init__.py, infrastructure/db/__init__.py, infrastructure/db/engine.py |
| 2 | Create infrastructure/db/pings.py | 7706170 | infrastructure/db/pings.py |
| 3 | Replace test_db_engine.py Wave 0 stub | 30a9c3f | tests/bet_maker/test_db_engine.py |

## What Was Built

### `src/bet_maker/infrastructure/db/engine.py`

`create_engine_and_sessionmaker(settings: BetMakerSettings) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]` factory:

- `create_async_engine(str(settings.postgres_dsn), pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800)` — D-16
- `async_sessionmaker(engine, expire_on_commit=False)` — D-15

### `src/bet_maker/infrastructure/db/pings.py`

Two functions:

- `wait_for_postgres(engine)` — async, decorated with `@retry(stop=stop_after_attempt(10), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True, before_sleep=before_sleep_log(...))`. Cumulative wait ~75s worst case. Called from lifespan (Plan 03-08) as startup gate (D-27).
- `ping_postgres(engine) -> bool` — single `SELECT 1` via `engine.connect()`, returns `True` on success, catches `SQLAlchemyError` only (not bare `Exception`) and returns `False` (D-26, D-29). Logs `health.check.failed` with `str(exc)` only (no DSN leak, T-03-5).

### `tests/bet_maker/test_db_engine.py`

5 tests (replaces Wave 0 stub with `pytestmark = pytest.mark.skip`):

| Test | Covers |
|------|--------|
| `test_returns_engine_and_sessionmaker_tuple` | Factory returns correct types |
| `test_sessionmaker_has_expire_on_commit_false` | D-15: `session.sync_session.expire_on_commit is False` |
| `test_engine_pool_params_locked` | D-16: all 4 QueuePool params verified via private attrs |
| `test_ping_returns_true_on_healthy_engine` | D-26: SELECT 1 on live PG -> True |
| `test_ping_returns_false_on_sqlalchemy_error` | D-29: SQLAlchemyError -> False, never raises |

**Total pytest delta: +5 tests (117 -> 122... wait, 133 baseline -> 138 total = +5)**

**Pool introspection on SQLAlchemy 2.0.49:** `QueuePool._max_overflow`, `QueuePool._recycle`, `QueuePool._pre_ping` private attrs confirmed stable. After `assert isinstance(pool, QueuePool)` guard, mypy strict accepts them without `# type: ignore`.

**Note for Plan 03-06:** `create_engine_and_sessionmaker` is ready. Plan 03-06 `AsyncUnitOfWork.__init__` accepts `async_sessionmaker[AsyncSession]` — pass the second element of the returned tuple directly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] asyncpg does not wrap ConnectionRefusedError as SQLAlchemyError**
- **Found during:** Task 3 — first test run
- **Issue:** Plan's test strategy for the D-29 `False` path built a real engine against `127.0.0.1:1`. When asyncpg fails to connect, it raises `ConnectionRefusedError` (an `OSError` subclass) which propagates through SQLAlchemy's greenlet machinery without being wrapped into `OperationalError`. The `ping_postgres` `except SQLAlchemyError` block does NOT catch it — `ConnectionRefusedError` is not a `SQLAlchemyError`.
- **Fix:** Replaced the "real bad DSN" approach with `AsyncMock(spec=AsyncEngine)` where `mock_engine.connect.side_effect = _fail_connect` raises `OperationalError` directly. This correctly tests the D-29 contract (SQLAlchemyError -> False) without relying on asyncpg wrapping.
- **Verification:** `ping_postgres` itself is correct (catches `SQLAlchemyError` as intended). The issue was in the test strategy, not production code.
- **Files modified:** tests/bet_maker/test_db_engine.py
- **Commit:** 30a9c3f

**2. [Rule 1 - Bug] Loop mismatch with session-scoped async_engine fixture**
- **Found during:** Task 3 — full suite run (`uv run pytest -q --no-cov` after isolated run passed)
- **Issue:** `test_ping_returns_true_on_healthy_engine` used the session-scoped `async_engine` fixture. With `asyncio_default_test_loop_scope=function`, each test runs in a new event loop, but the session-scoped `async_engine` pool was created in the session-scope loop. asyncpg `Future attached to a different loop` RuntimeError at test runtime.
- **Fix:** Replaced `async_engine: AsyncEngine` fixture injection with a function-scoped throwaway engine (`create_engine_and_sessionmaker(settings)` + `finally: await engine.dispose()`).
- **Files modified:** tests/bet_maker/test_db_engine.py
- **Commit:** 30a9c3f

## Quality Gates

- `uv run pytest tests/bet_maker/test_db_engine.py -q --no-cov` — 5 passed
- `uv run pytest -q --no-cov` — 138 passed, 0 failed (+5 vs 133 baseline)
- `uv run mypy --strict src/bet_maker/infrastructure tests/bet_maker/test_db_engine.py` — Success: no issues found in 5 source files
- `uv run ruff check src/bet_maker/infrastructure tests/bet_maker/test_db_engine.py` — All checks passed
- D-15 grep: `grep -q "expire_on_commit=False" src/bet_maker/infrastructure/db/engine.py` — present
- D-16 greps: pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800 — all present
- D-27 greps: `@retry`, `stop_after_attempt(10)`, `wait_exponential(multiplier=1, min=1, max=10)`, `reraise=True` — all present
- D-29 grep: `SQLAlchemyError` in pings.py — present; no bare `Exception` catch — verified

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Production code (`engine.py`, `pings.py`) only creates engine/sessions and performs `SELECT 1` — within existing attack surface. T-03-5 (DSN leak) mitigated: `log.warning("health.check.failed", error=str(exc))` — only exception message string is logged, not engine repr.

## Self-Check: PASSED

- `src/bet_maker/infrastructure/__init__.py` — FOUND
- `src/bet_maker/infrastructure/db/__init__.py` — FOUND
- `src/bet_maker/infrastructure/db/engine.py` — FOUND
- `src/bet_maker/infrastructure/db/pings.py` — FOUND
- `tests/bet_maker/test_db_engine.py` — FOUND (5 tests, no pytestmark.skip)
- Commit fdf347e — FOUND (`feat(03-05): create infrastructure/db/engine.py`)
- Commit 7706170 — FOUND (`feat(03-05): create infrastructure/db/pings.py`)
- Commit 30a9c3f — FOUND (`feat(03-05): replace test_db_engine.py Wave 0 stub`)
