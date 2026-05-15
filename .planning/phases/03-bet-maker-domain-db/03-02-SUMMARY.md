---
phase: 03-bet-maker-domain-db
plan: 02
subsystem: testing
tags: [testcontainers, alembic, sqlalchemy, asyncio, pytest-asyncio, fixtures, wave-0]

requires:
  - phase: 03-bet-maker-domain-db
    provides: "Plan 03-01: REQUIREMENTS.md and VALIDATION.md skeleton for Phase 3"

provides:
  - "testcontainers>=4.9,<5 in dev-deps with uv.lock updated (7 new packages)"
  - "tests/conftest.py: 6 PG-backed session/function-scoped fixtures"
  - "tests/bet_maker/conftest.py: lifespan-aware app+client+seed_event fixtures"
  - "11 Wave 0 test stub files with pytest.mark.skip covering all Phase 3 implementing plans"
  - "03-VALIDATION.md: wave_0_complete=true, 31-row Per-Task Verification Map"

affects: [03-03, 03-04, 03-05, 03-06, 03-07, 03-08, 03-09]

tech-stack:
  added:
    - "testcontainers 4.14.2 (resolved from >=4.9,<5 constraint)"
    - "docker 7.1.0 (transitive testcontainers dep)"
    - "requests 2.34.2 (transitive testcontainers dep)"
  patterns:
    - "session-scoped testcontainers PostgresContainer with asyncpg driver"
    - "programmatic alembic upgrade head x2 for idempotency assertion"
    - "async_engine session-scoped fixture with pool_pre_ping=True and dispose on teardown"
    - "truncate_bets: explicit (not autouse) — autouse responsibility delegated to service-specific conftest"
    - "bet_maker/conftest.py mirrors line_provider/conftest.py: app fixture with LifespanManager + separate client"

key-files:
  created:
    - "tests/bet_maker/test_schemas.py"
    - "tests/bet_maker/test_models.py"
    - "tests/bet_maker/test_db_engine.py"
    - "tests/bet_maker/test_repositories.py"
    - "tests/bet_maker/test_uow.py"
    - "tests/bet_maker/test_event_lookup.py"
    - "tests/bet_maker/test_place_bet.py"
    - "tests/bet_maker/test_selectors.py"
    - "tests/bet_maker/test_bet_routes.py"
    - "tests/bet_maker/test_lifespan.py"
    - "tests/bet_maker/test_alembic.py"
  modified:
    - "pyproject.toml"
    - "uv.lock"
    - "tests/conftest.py"
    - "tests/bet_maker/conftest.py"
    - ".planning/phases/03-bet-maker-domain-db/03-VALIDATION.md"

key-decisions:
  - "truncate_bets не autouse в root conftest — autouse=True там ломал P1 test_health.py (PG фикстура тянулась для тестов без PG); исправлено как Rule 1 bug (fixture explicit, autouse будет в bet_maker integration tests в 03-08)"
  - "testcontainers[postgresql] extras не используется — postgres-модуль уже в base пакете testcontainers 4.x"
  - "asyncio_default_fixture_loop_scope = 'session' добавлен в pytest.ini_options — без этого pytest-asyncio 1.x создаёт новый event loop per function => ScopeMismatch на session-scoped async fixtures"
  - "import bet_maker.app inside app() function (noqa: PLC0415) — delayed import предотвращает circular import риски пока bet_maker модули не сформированы"

patterns-established:
  - "Wave 0 stub pattern: pytestmark = pytest.mark.skip(reason='Wave 0 stub: implemented in plan 03-NN') на module level"
  - "PG fixture chain: postgres_container → pg_dsn → apply_migrations → async_engine → session_factory → truncate_bets"

requirements-completed: [QA-07]

duration: 8min
completed: 2026-05-15
---

# Phase 3 Plan 02: Wave 0 Test Scaffolding Summary

**testcontainers PostgreSQL session fixture + 6 PG fixtures in root conftest + LifespanManager bet_maker app + 11 Wave 0 skip-stubs covering all Phase 3 implementing plans (03-03..03-08)**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-15T14:57:10Z
- **Completed:** 2026-05-15T15:05:00Z
- **Tasks:** 5
- **Files modified:** 16 (2 config + 2 conftest + 11 stubs + 1 planning doc)

## Accomplishments

- testcontainers 4.14.2 добавлен в dev-deps; `uv sync --frozen` exit 0; import PostgresContainer работает
- Root `tests/conftest.py` расширен 6 session/function-scoped PG fixtures по RESEARCH Pattern 4
- `tests/bet_maker/conftest.py` обновлён: app fixture с LifespanManager + seed_event helper; зеркалит P2 line_provider/conftest.py pattern
- 11 test stub файлов созданы с `pytestmark = pytest.mark.skip`; ruff + mypy strict чисты
- P1 baseline 97 passed сохранён — test_health.py не затронут

## Task Commits

1. **Task 1: testcontainers + coverage + asyncio_default_fixture_loop_scope** — `bc05fe6` (chore)
2. **Task 2: tests/conftest.py PG fixtures** — `86140ef` (feat)
3. **Task 3: tests/bet_maker/conftest.py LifespanManager + Rule 1 autouse fix** — `37f2c19` (feat)
4. **Task 4: 11 Wave 0 stub files** — `1a57b9f` (feat)
5. **Task 5: 03-VALIDATION.md wave_0_complete** — `a38e6a0` (docs)

## Files Created/Modified

| File | Change | Notes |
|------|--------|-------|
| `pyproject.toml` | modified | testcontainers dev-dep; coverage source += src/bet_maker; asyncio_default_fixture_loop_scope |
| `uv.lock` | modified | +7 packages (testcontainers, docker, requests, urllib3, charset-normalizer, wrapt) |
| `tests/conftest.py` | modified (96 lines → 97 lines added) | 6 PG fixtures: postgres_container, pg_dsn, apply_migrations, async_engine, session_factory, truncate_bets |
| `tests/bet_maker/conftest.py` | modified (16 → 69 lines) | app fixture + LifespanManager; client depends on app; seed_event helper |
| `tests/bet_maker/test_schemas.py` | created | Wave 0 stub → plan 03-03 (BM-05/BM-06) |
| `tests/bet_maker/test_models.py` | created | Wave 0 stub → plan 03-04 (BM-01) |
| `tests/bet_maker/test_alembic.py` | created | Wave 0 stub → plan 03-04 (SC-5 idempotency) |
| `tests/bet_maker/test_db_engine.py` | created | Wave 0 stub → plan 03-05 (BM-02/BM-08) |
| `tests/bet_maker/test_repositories.py` | created | Wave 0 stub → plan 03-06 (BM-02) |
| `tests/bet_maker/test_uow.py` | created | Wave 0 stub → plan 03-06 (D-17) |
| `tests/bet_maker/test_event_lookup.py` | created | Wave 0 stub → plan 03-06 (D-11) |
| `tests/bet_maker/test_place_bet.py` | created | Wave 0 stub → plan 03-07 (BM-05/BM-06) |
| `tests/bet_maker/test_selectors.py` | created | Wave 0 stub → plan 03-07 (BM-07/BM-13) |
| `tests/bet_maker/test_bet_routes.py` | created | Wave 0 stub → plan 03-08 (routes integration) |
| `tests/bet_maker/test_lifespan.py` | created | Wave 0 stub → plan 03-08 (D-27 tenacity retry) |
| `.planning/phases/03-bet-maker-domain-db/03-VALIDATION.md` | modified | frontmatter approved; Wave 0 all [x]; 31-row Per-Task map |

## Wave 0 Stub Distribution

| Plan | Stubs |
|------|-------|
| 03-03 (schemas) | test_schemas.py |
| 03-04 (model + migration) | test_models.py, test_alembic.py |
| 03-05 (DB engine infra) | test_db_engine.py |
| 03-06 (UoW + repo + event_lookup) | test_repositories.py, test_uow.py, test_event_lookup.py |
| 03-07 (interactor + selectors) | test_place_bet.py, test_selectors.py |
| 03-08 (routes + lifespan) | test_bet_routes.py, test_lifespan.py |

## Test Results

```
uv run pytest -q → 97 passed, 1 warning (P1+P2 baseline preserved)
```

P1 file `tests/bet_maker/test_health.py` НЕ был изменён в этом плане. Изменение P1 assertion (`body == {"status":"ok"}` → `body["status"] == "ok"`) выполняется атомарно в Plan 03-08 Task 4 вместе с replace health.py — это предотвращает breakage baseline до готовности реализации.

## Decisions Made

- **truncate_bets не autouse в root conftest**: autouse=True в root conftest.py вызвал бы запуск postgres_container для test_health.py (нет PG dependency). Исправлено как Rule 1: truncate_bets объявлен explicit в root conftest; autouse вариант будет добавлен в tests/bet_maker/conftest.py в Plan 03-08 когда появятся реальные integration тесты требующие изоляции.

- **asyncio_default_fixture_loop_scope = "session"**: Добавлен в pyproject.toml для session-scoped async fixtures (postgres_container chain). Без этого pytest-asyncio 1.x создаёт новый event loop per function => ScopeMismatch.

- **testcontainers base package (no extras)**: `testcontainers>=4.9,<5` без `[postgresql]` extras — postgres support включён в base пакет с версии 4.x (RESEARCH §A4 verified).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] truncate_bets autouse=True ломал P1 baseline test_health.py**
- **Found during:** Task 3 (tests/bet_maker/conftest.py update)
- **Issue:** autouse=True в root conftest.py тянет postgres_container session fixture для ВСЕХ тестов включая test_health.py; без реального Docker-контейнера тесты падали с `socket.gaierror: [Errno 8] nodename nor servname provided`
- **Fix:** Убран autouse=True из truncate_bets в root conftest; fixture остаётся explicit; autouse-версия будет добавлена в tests/bet_maker/conftest.py в Plan 03-08 (тогда же когда появятся реальные PG integration tests)
- **Files modified:** tests/conftest.py (Task 2 commit 86140ef), tests/bet_maker/conftest.py (Task 3 commit 37f2c19)
- **Verification:** `uv run pytest tests/bet_maker/test_health.py -q` → 2 passed

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug)
**Impact on plan:** Автофикс необходим для сохранения P1 baseline. Plan 03-02 must_have "97 P1+P2 tests pass" выполнен.

## Issues Encountered

None beyond the autouse deviation documented above.

## Known Stubs

Все 11 Wave 0 стабов намеренно пусты (только pytestmark). Реальные тесты будут добавлены в implementing plans:
- 03-03, 03-04, 03-05, 03-06, 03-07, 03-08

Эти stubs не являются дефектом функциональности — их цель зафиксировать ожидаемую структуру тестового файла и предотвратить ImportError до готовности реализации.

## Next Phase Readiness

- Plans 03-03..03-08 могут использовать root conftest PG fixtures без дополнительной настройки
- seed_event helper в bet_maker/conftest.py готов к wire-up в Plan 03-06 (StubEventLookup)
- test_health.py НЕ изменён — baseline тесты зелёные; изменение ожидает Plan 03-08

## Self-Check: PASSED

- tests/conftest.py: FOUND
- tests/bet_maker/conftest.py: FOUND
- tests/bet_maker/test_schemas.py: FOUND
- tests/bet_maker/test_db_engine.py: FOUND
- tests/bet_maker/test_alembic.py: FOUND
- .planning/phases/03-bet-maker-domain-db/03-02-SUMMARY.md: FOUND
- bc05fe6 (chore 03-02 testcontainers): FOUND in git log
- 86140ef (feat 03-02 PG fixtures): FOUND in git log
- 37f2c19 (feat 03-02 bet_maker conftest): FOUND in git log
- 1a57b9f (feat 03-02 stubs): FOUND in git log
- a38e6a0 (docs 03-02 VALIDATION): FOUND in git log
- 4779668 (docs 03-02 SUMMARY/STATE): FOUND in git log

---
*Phase: 03-bet-maker-domain-db*
*Completed: 2026-05-15*
