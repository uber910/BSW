---
phase: 03-bet-maker-domain-db
plan: "08"
subsystem: bet-maker/entrypoints
tags: [bet-maker, routes, lifespan, health, integration, wave-5]
dependency_graph:
  requires:
    - 03-05 (engine + pings)
    - 03-06 (UoW + EventLookup + deps)
    - 03-07 (place_bet interactor + selectors)
  provides:
    - POST /bet → 201 BetRead
    - GET /bets → list[BetRead] ordered DESC
    - GET /bet/{id} → 200/404
    - GET /health → 200/503 with postgres check
    - Full lifespan wiring (engine + sessionmaker + wait_for_postgres + StubEventLookup)
  affects:
    - tests/bet_maker (conftest session-scoped app/client)
    - app.py (bets.router included)
tech_stack:
  added: []
  patterns:
    - asynccontextmanager lifespan with try/finally engine.dispose()
    - session-scoped pytest_asyncio fixtures (app/client) for asyncpg loop compatibility
    - ping_postgres(engine) -> bool for health check route delegation
    - @pytest.mark.asyncio(loop_scope="session") on all bet_maker HTTP integration tests
key_files:
  created:
    - src/bet_maker/entrypoints/api/bets.py
  modified:
    - src/bet_maker/entrypoints/lifespan.py
    - src/bet_maker/entrypoints/api/health.py
    - src/bet_maker/app.py
    - tests/bet_maker/test_health.py
    - tests/bet_maker/test_bet_routes.py
    - tests/bet_maker/test_lifespan.py
    - tests/bet_maker/conftest.py
decisions:
  - "session-scoped app/client fixtures: asyncpg connections are bound to event loop of creation; function-scoped app creates new engine per test => 'Future attached to a different loop' on dispose(); session-scope fixes this"
  - "loop_scope=session on all HTTP integration test classes: matches session-scoped app fixture; consistent with test_uow/test_place_bet/test_selectors pattern established in Plan 03-06"
  - "_clear_event_lookup autouse fixture: session-scoped StubEventLookup would leak seeds between tests without explicit clear; autouse clears _events dict before each test"
  - "conftest seed_event fix: original seed() fallback used wrong kwargs; fixed to pass EventSnapshot(event_id, deadline, state) for non-NEW states"
metrics:
  duration: "~15 min"
  completed: "2026-05-15"
  tasks_completed: 7
  files_changed: 8
---

# Phase 3 Plan 08: HTTP Routes + Lifespan + Health Summary

Wave 5 entrypoints wired: lifespan startup (engine/sessionmaker/wait_for_postgres/StubEventLookup), live PG health check (200/503), full bets CRUD routes (POST /bet 201, GET /bets DESC, GET /bet/{id} 200/404) with 25 new integration tests.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Extend lifespan.py | 1a4728d | src/bet_maker/entrypoints/lifespan.py |
| 2 | Replace health.py stub with PG ping | 1fb6fe0 | src/bet_maker/entrypoints/api/health.py |
| 3+4 | bets.py routes + app.py wire | 00a2f13 | src/bet_maker/entrypoints/api/bets.py, src/bet_maker/app.py |
| 5 | Update test_health.py + 503 test; fix conftest | 18bd0c9 | tests/bet_maker/test_health.py, tests/bet_maker/conftest.py |
| 6 | Replace test_bet_routes Wave 0 stub | 590e650 | tests/bet_maker/test_bet_routes.py |
| 7 | Replace test_lifespan Wave 0 stub | d898182 | tests/bet_maker/test_lifespan.py |

## Verification Results

- `uv run pytest tests/bet_maker/test_bet_routes.py -q --no-cov` → 17 passed
- `uv run pytest tests/bet_maker/test_health.py tests/bet_maker/test_lifespan.py -q --no-cov` → 8 passed
- `uv run mypy --strict src/bet_maker/entrypoints src/bet_maker/app.py` → Success: no issues in 7 source files
- `uv run ruff check src/bet_maker/entrypoints src/bet_maker/app.py tests/bet_maker/test_bet_routes.py tests/bet_maker/test_health.py tests/bet_maker/test_lifespan.py` → All checks passed
- `uv run pytest -q --no-cov` → **193 passed**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] asyncpg event-loop mismatch with function-scoped app fixture**
- **Found during:** Task 5 (test_health.py integration run)
- **Issue:** `conftest.app` fixture was function-scoped; each test created new AsyncEngine in function loop; `LifespanManager` triggered lifespan which opened asyncpg connections in that loop; dispose() in teardown tried to close them from a different loop → `RuntimeError: Future attached to a different loop`
- **Fix:** Made `app` and `client` fixtures session-scoped; added `@pytest.mark.asyncio(loop_scope="session")` to all HTTP integration test classes (consistent with test_uow/test_selectors pattern)
- **Files modified:** tests/bet_maker/conftest.py, tests/bet_maker/test_health.py, tests/bet_maker/test_bet_routes.py, tests/bet_maker/test_lifespan.py
- **Commit:** 18bd0c9

**2. [Rule 2 - Missing] _clear_event_lookup autouse fixture**
- **Found during:** Task 5 (session-scoped StubEventLookup shared between tests)
- **Issue:** Session-scoped app shares single StubEventLookup instance; seeds from one test leak to the next
- **Fix:** Added `_clear_event_lookup` autouse fixture in conftest that calls `app.state.event_lookup._events.clear()` before each test
- **Files modified:** tests/bet_maker/conftest.py
- **Commit:** 18bd0c9

**3. [Rule 1 - Bug] conftest seed_event incorrect fallback for non-NEW states**
- **Found during:** Task 5 (code review)
- **Issue:** Original `seed_event` called `lookup.seed(event_id=..., deadline=..., state=...)` but `StubEventLookup.seed()` accepts `EventSnapshot`, not kwargs
- **Fix:** Replaced with `EventSnapshot(event_id=event_id, deadline=deadline, state=EventState(state))` construction
- **Files modified:** tests/bet_maker/conftest.py
- **Commit:** 18bd0c9

**4. [Rule 2 - Missing] BET_MAKER_POSTGRES_DSN env injection in app fixture**
- **Found during:** Task 5 (first test run with real lifespan)
- **Issue:** lifespan calls `BetMakerSettings()` which reads `BET_MAKER_POSTGRES_DSN` from env; testcontainers PG has dynamic DSN not set in env
- **Fix:** `app` fixture sets `os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn` before building the app, pops it in finally
- **Files modified:** tests/bet_maker/conftest.py
- **Commit:** 18bd0c9

## Known Stubs

None — all stubs from this plan are replaced. `StubEventLookup` remains as the in-process event resolver (intended; Plan 04 will swap to `HttpEventLookup`).

## Self-Check: PASSED

Files exist:
- src/bet_maker/entrypoints/lifespan.py — FOUND
- src/bet_maker/entrypoints/api/health.py — FOUND
- src/bet_maker/entrypoints/api/bets.py — FOUND
- src/bet_maker/app.py — FOUND
- tests/bet_maker/test_health.py — FOUND
- tests/bet_maker/test_bet_routes.py — FOUND
- tests/bet_maker/test_lifespan.py — FOUND
- tests/bet_maker/conftest.py — FOUND

Commits exist:
- 1a4728d — FOUND
- 1fb6fe0 — FOUND
- 00a2f13 — FOUND
- 18bd0c9 — FOUND
- 590e650 — FOUND
- d898182 — FOUND
