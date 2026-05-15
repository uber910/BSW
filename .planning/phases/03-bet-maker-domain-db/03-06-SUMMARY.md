---
phase: 03-bet-maker-domain-db
plan: "06"
subsystem: database
tags: [bet-maker, facades, uow, repository, event-lookup, deps, sqlalchemy, pydantic, fastapi, di]

requires:
  - phase: 03-bet-maker-domain-db
    plan: "05"
    provides: "AsyncEngine + async_sessionmaker factory — UoW depends on it"
  - phase: 03-bet-maker-domain-db
    plan: "04"
    provides: "Bet ORM model — BetRepository depends on it"
  - phase: 03-bet-maker-domain-db
    plan: "03"
    provides: "BetMakerSettings, EventState schema — deps.py + event_lookup import them"

provides:
  - "BetRepository.add (no flush, no commit) + get_by_id (scalar_one_or_none)"
  - "AsyncUnitOfWork via async_sessionmaker.begin() — auto-commit on clean exit, auto-rollback on exception"
  - "EventLookup Protocol + EventSnapshot(frozen+forbid) + StubEventLookup(dict-backed seed/seed_active)"
  - "6 FastAPI DI providers (get_settings/engine/sessionmaker/session/uow/event_lookup) + 6 Annotated aliases"
  - "19 tests (test_repositories: 5, test_uow: 5, test_event_lookup: 9) — all passing"

affects:
  - "03-07 interactor place_bet — consumes AsyncUnitOfWork + EventLookup via DI aliases"
  - "03-08 routes + lifespan — consumes all 6 Annotated aliases; lifespan sets app.state.event_lookup"
  - "04-xx HttpEventLookup — replaces StubEventLookup by satisfying same Protocol structurally"

tech-stack:
  added: []
  patterns:
    - "UoW pattern: async_sessionmaker.begin() as context manager — no manual commit/rollback anywhere"
    - "Repository anti-pattern guard: repo.add() calls session.add only; flush is caller's responsibility"
    - "Protocol structural typing: EventLookup Protocol + StubEventLookup (no inheritance) checked by mypy strict"
    - "DI via app.state.*: all singletons pinned in lifespan, retrieved via cast(T, request.app.state.x)"
    - "Test loop scope: @pytest.mark.asyncio(loop_scope='session') on classes using session-scoped session_factory"

key-files:
  created:
    - src/bet_maker/repositories/bets.py
    - src/bet_maker/repositories/__init__.py
    - src/bet_maker/facades/uow.py
    - src/bet_maker/facades/__init__.py
    - src/bet_maker/facades/event_lookup.py
    - src/bet_maker/facades/deps.py
    - tests/bet_maker/test_repositories.py
    - tests/bet_maker/test_uow.py
    - tests/bet_maker/test_event_lookup.py
  modified: []

key-decisions:
  - "_cm typed as Any in AsyncUnitOfWork because async_sessionmaker.begin() returns private SQLAlchemy type not exported in public API"
  - "BetRepository.add() does NOT flush — flush is caller's (interactor) responsibility for session.refresh after INSERT"
  - "StubEventLookup uses instance-level dict (not class-level) to prevent mutation leak across test instances"
  - "EventLookup Protocol NOT @runtime_checkable — structural typing verified by mypy strict via variable annotation"
  - "@pytest.mark.asyncio(loop_scope='session') required on all async test classes using session-scoped session_factory"

patterns-established:
  - "UoW: async_sessionmaker.begin() context manages transactions; no commit/rollback in repositories or interactors"
  - "Repository add-no-flush: add() only queues INSERT; caller controls flush timing for server_default refresh"

requirements-completed: [BM-02, BM-03, BM-06]

duration: 25min
completed: 2026-05-15
---

# Phase 03 Plan 06: Facades & Repositories Summary

**BetRepository (no-commit) + AsyncUnitOfWork (sessionmaker.begin) + EventLookup Protocol/StubEventLookup + 6 FastAPI DI providers with Annotated aliases — full facades layer for bet-maker**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-15T17:39:00Z
- **Completed:** 2026-05-15T18:04:37Z
- **Tasks:** 3 (Task 1 committed in prior session; Tasks 2-3 this session)
- **Files modified:** 9 production + 3 test replacements

## Accomplishments

- BetRepository with Anti-Pattern 1 enforcement: add() → session.add only, no flush, no commit; get_by_id() via scalar_one_or_none; grep-verified at both source-inspection and test level
- AsyncUnitOfWork wrapping async_sessionmaker.begin() — auto-commit on clean exit, auto-rollback on exception, no manual commit/rollback method exposed
- EventLookup Protocol + EventSnapshot(frozen=True, extra="forbid") + StubEventLookup with instance-isolated dict backing; seed()/seed_active()/get_event()
- 6 DI providers + 6 Annotated aliases (SettingsDep/EngineDep/SessionmakerDep/SessionDep/UoWDep/EventLookupDep) — ready for Plan 03-08 routes
- 19 tests replacing 3 Wave 0 stubs; Critical Risk Axes 3 (concurrent UoW isolation via asyncio.gather) and 8 (seed + instance isolation) explicitly covered

## Task Commits

1. **Task 1: repositories/bets.py + facades/uow.py** - `f941bb5` (feat) — committed in prior session
2. **Task 2: facades/event_lookup.py + facades/deps.py** - `0b0cdcb` (feat)
3. **Task 3: replace Wave 0 stubs** - `1b6f11e` (feat)

## Test Coverage

| File | Tests | Scope |
|------|-------|-------|
| test_repositories.py | 5 (1 source-grep + 4 DB) | TestAntiPattern1 + TestRuntime |
| test_uow.py | 5 (2 shape + 2 transaction + 1 concurrency) | TestShape + TestTransactionSemantics + TestConcurrency |
| test_event_lookup.py | 9 (3 snapshot + 6 stub) | TestEventSnapshot + TestStubEventLookup |
| **Total new** | **19** | all passing |

**Critical Risk Axes covered:**
- Axis 3 (concurrent UoW isolation): `test_concurrent_uows_isolated` — asyncio.gather over 5 UoWs, each commits independently
- Axis 8 (EventLookup seeding): `test_seed_then_get_event_returns_snapshot`, `test_seed_active_*`, `test_instance_isolation`

**Full suite delta:** 138 → 157 passed (19 new tests, 0 regressions)

## Files Created

- `src/bet_maker/repositories/__init__.py` — package marker
- `src/bet_maker/repositories/bets.py` — BetRepository (add/get_by_id, no commit)
- `src/bet_maker/facades/__init__.py` — package marker
- `src/bet_maker/facades/uow.py` — AsyncUnitOfWork via sessionmaker.begin()
- `src/bet_maker/facades/event_lookup.py` — EventLookup Protocol + EventSnapshot + StubEventLookup
- `src/bet_maker/facades/deps.py` — 6 DI providers + 6 Annotated aliases
- `tests/bet_maker/test_repositories.py` — replaced Wave 0 stub
- `tests/bet_maker/test_uow.py` — replaced Wave 0 stub
- `tests/bet_maker/test_event_lookup.py` — replaced Wave 0 stub

## Decisions Made

1. `_cm: Any` in `AsyncUnitOfWork.__init__` — `async_sessionmaker.begin()` returns `_AsyncSessionContextManager[AsyncSession]`, a private SQLAlchemy type not exported from public API surface; `Any` with no `# type: ignore` is the documented idiom accepted by mypy strict
2. `add()` does NOT flush — interactor (Plan 03-07) calls `flush()` + `refresh(bet)` explicitly to load server_default created_at/updated_at; flush in repository would prevent the interactor from controlling refresh timing
3. `_events: dict[UUID, EventSnapshot] = {}` as instance attribute (not class-level) — prevents mutation leak across StubEventLookup instances in different tests
4. `@pytest.mark.asyncio(loop_scope="session")` on async test classes — required because `session_factory` fixture is session-scoped; function-scoped event loop (pytest-asyncio default) produces "Future attached to a different loop" error

## mypy strict type-ignore annotations

| File | Line | Annotation | Reason |
|------|------|-----------|--------|
| src/bet_maker/facades/uow.py | 42-43 | none needed — `_cm: Any` used instead | SQLAlchemy private type not exported |
| tests/bet_maker/test_repositories.py | async_sessionmaker args | `# type: ignore[type-arg]` | async_sessionmaker is generic but session_factory fixture typed as unparameterized |
| tests/bet_maker/test_uow.py | same | `# type: ignore[type-arg]` | same |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_source_has_no_commit grep spec too broad**
- **Found during:** Task 3 (test execution)
- **Issue:** Plan spec used `assert "commit" not in source.lower()` but BetRepository docstring contains "The enclosing UoW calls commit on clean exit" — causing false positive failure
- **Fix:** Changed assertion to `re.search(r'session\s*\.\s*commit\s*\(', source)` — tests method call pattern, not word in docstring
- **Files modified:** tests/bet_maker/test_repositories.py
- **Verification:** test passes; actual `session.commit()` call would still be caught
- **Committed in:** `1b6f11e`

**2. [Rule 1 - Bug] Missing @pytest.mark.asyncio(loop_scope="session") on async test classes**
- **Found during:** Task 3 (test execution — "Future attached to a different loop" error)
- **Issue:** Plan test code did not include loop_scope markers; async test classes using session-scoped session_factory failed when run together due to event loop mismatch
- **Fix:** Added `@pytest.mark.asyncio(loop_scope="session")` to TestRuntime, TestShape, TestTransactionSemantics, TestConcurrency — matching pattern established in test_models.py (Plan 03-04)
- **Files modified:** tests/bet_maker/test_repositories.py, tests/bet_maker/test_uow.py
- **Verification:** All 19 tests pass when run together
- **Committed in:** `1b6f11e`

---

**Total deviations:** 2 auto-fixed (both Rule 1 - test correctness bugs)
**Impact on plan:** Both fixes necessary for tests to pass in suite context. No scope creep.

## Issues Encountered

- ruff format reformatted test files on first commit attempt (pre-commit hook) — staged reformatted versions and recommitted successfully

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. All new code is in-process facades and DI providers operating within the existing trust boundary.

## Known Stubs

- `StubEventLookup` in `src/bet_maker/facades/event_lookup.py` — intentional P3 stub for in-process event lookup. Plan 04 replaces with `HttpEventLookup` (httpx → line-provider GET /event/{id}) without modifying the Protocol or EventSnapshot. This stub serves its purpose for P3 testing and does not prevent the plan's goal (facades layer complete).

## Next Phase Readiness

- Plan 03-07 (interactor place_bet) can immediately consume `AsyncUnitOfWork` via `UoWDep` and `EventLookup` via `EventLookupDep`
- Plan 03-08 (routes + lifespan) can use all 6 Annotated aliases; lifespan will set `app.state.event_lookup = StubEventLookup()`
- All building blocks ready: model (03-04), engine+sessionmaker (03-05), repository+uow+event_lookup+deps (03-06)

---
*Phase: 03-bet-maker-domain-db*
*Completed: 2026-05-15*
