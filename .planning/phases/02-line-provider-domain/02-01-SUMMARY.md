---
phase: 02-line-provider-domain
plan: 01
subsystem: testing
tags: [line-provider, asgi-lifespan, pytest-coverage, fixture-upgrade, requirements-sync, foundations]

requires:
  - phase: 01-skeleton-infrastructure
    provides: pyproject.toml dev-deps group, tests/line_provider/conftest.py with ASGITransport, REQUIREMENTS.md baseline, 02-VALIDATION.md skeleton, uv.lock
provides:
  - asgi-lifespan>=2.1,<3 in dependency-groups.dev (LifespanManager enabler for integration tests)
  - [tool.coverage.run] source=["src/line_provider"] branch=true
  - [tool.coverage.report] fail_under=85 show_missing=true skip_covered=false (phase-gate for plan 02-07)
  - tests/line_provider/conftest.py with two fixtures (`app` lifespan-aware, `client` AsyncClient bound to app)
  - REQUIREMENTS.md LP-02 = UUID4 (client-generated) per D-05 (synced with CONTEXT.md and ARCHITECTURE.md)
  - 02-VALIDATION.md canonical 20-task verification map, frontmatter wave_0_complete=true + nyquist_compliant=true
affects: [02-02-schemas, 02-03-state-machine, 02-04-store, 02-05-interactors, 02-06-selectors, 02-07-routes]

tech-stack:
  added:
    - asgi-lifespan 2.1.0 (dev only)
    - sniffio 1.3.1 (transitive)
  patterns:
    - "Test fixture split: `app` (lifespan-aware FastAPI) + `client` (AsyncClient bound to it) — enables integration tests to seed app.state directly via the app fixture without touching private _transport"
    - "Coverage gate scoped to line_provider source — bet-maker covers itself in P3/P4 independently"

key-files:
  created: []
  modified:
    - pyproject.toml — added asgi-lifespan dev-dep + [tool.coverage.run] + [tool.coverage.report]
    - uv.lock — regenerated (asgi-lifespan 2.1.0 + sniffio 1.3.1)
    - .planning/REQUIREMENTS.md — LP-02 str → UUID4 client-generated per D-05
    - tests/line_provider/conftest.py — wrap build_app() in LifespanManager, split into app + client fixtures
    - .planning/phases/02-line-provider-domain/02-VALIDATION.md — canonical per-task map (20 rows), wave_0_complete=true

key-decisions:
  - "Conftest split into two fixtures (`app` and `client`) rather than yielding a tuple. Keeps existing tests' `client: AsyncClient` signature working without changes; new integration tests in 02-07 ask for `app: FastAPI` when they need direct app.state access."
  - "Coverage source restricted to src/line_provider only; bet-maker will declare its own coverage scope in P3/P4. Avoids cross-package coverage noise during P2 development."
  - "Premature bet-maker EventFinishedMessage edit (originally listed in 02-VALIDATION.md Wave 0) dropped — bet-maker has no schemas/messages.py yet; D-05 already locks UUID across all three boundaries, drift impossible until P3/P5 creates the module."

patterns-established:
  - "asgi_lifespan.LifespanManager wraps build_app() inside the `app` fixture; ASGITransport+AsyncClient consumes that fixture in the `client` fixture — public pattern from FastAPI advanced testing docs"
  - "Phase-gate coverage threshold declared in pyproject.toml ([tool.coverage.report] fail_under=85) rather than CLI flag — single source of truth, picked up by both local `uv run pytest --cov` and CI"

requirements-completed: [QA-04, QA-05]

duration: 3min
completed: 2026-05-15
---

# Phase 02 Plan 01: Foundations Wave 0 Summary

**Wave 0 foundations for Phase 2: asgi-lifespan dev-dep + coverage 85% gate + LifespanManager fixture + REQUIREMENTS LP-02 UUID4 sync — unblocks all six downstream P2 plans.**

## Performance

- **Duration:** ~3 min (4 tasks, autonomous)
- **Started:** 2026-05-15T08:08:03Z
- **Completed:** 2026-05-15T08:10:40Z
- **Tasks:** 4 / 4
- **Files modified:** 5 (pyproject.toml, uv.lock, .planning/REQUIREMENTS.md, tests/line_provider/conftest.py, .planning/phases/02-line-provider-domain/02-VALIDATION.md)

## Accomplishments

- `asgi-lifespan>=2.1,<3` зафиксирован в `dependency-groups.dev`; `uv.lock` обновлён (2 пакета: asgi-lifespan 2.1.0 + sniffio 1.3.1 transitive). `uv sync --frozen` exit 0; `uv run python -c "import asgi_lifespan"` печатает `2.1.0`.
- `[tool.coverage.run]` (source=src/line_provider, branch=true) + `[tool.coverage.report]` (fail_under=85, show_missing, skip_covered=false, exclude_lines) добавлены в pyproject.toml — phase-gate готов для Plan 02-07.
- `tests/line_provider/conftest.py` переписан в две fixture: `app` оборачивает `build_app()` в `LifespanManager(application)` (поднимает lifespan-asynccontextmanager, готовый к Plan 02-07 wiring `app.state.event_store` + `app.state.event_bus`); `client` зависит от `app` и отдаёт `AsyncClient(transport=ASGITransport(app), base_url="http://test")`. Существующие 2 P1-теста (`test_health_returns_status_ok`, `test_health_echoes_request_id_header`) остались зелёные без изменений в test-файлах — внешний контракт `client: AsyncClient` сохранён.
- `REQUIREMENTS.md` LP-02 синхронизирован: `event_id (str)` → `event_id (UUID4, client-generated)` с явной ссылкой на D-05 (Phase 2 CONTEXT.md). Старая формулировка `event_id (str)` устранена (grep -c == 0).
- `02-VALIDATION.md` финальная per-task verification map (20 task IDs от `2-01-01` до `2-07-06`) синхронизирована с реальной структурой P2-планов. Frontmatter: `status: approved`, `nyquist_compliant: true`, `wave_0_complete: true`. Sign-off `[x]` все 6 пунктов + Approval строка с датой. Преждевременная правка bet-maker `EventFinishedMessage` из Wave 0 убрана — bet-maker `schemas/messages.py` создаётся в P3/P5, drift невозможен.

## Task Commits

1. **Task 1: Add asgi-lifespan dev-dep + coverage config + sync uv.lock** — `b1d3eef` (chore)
2. **Task 2: Sync REQUIREMENTS.md LP-02 (str → UUID4) per D-05** — `6108550` (docs)
3. **Task 3: Upgrade tests/line_provider/conftest.py to LifespanManager + (app, client) fixtures** — `2ce6089` (test)
4. **Task 4: Sync 02-VALIDATION.md per-task map with this PLAN's task IDs** — `8fd4940` (docs)

## Files Created/Modified

- `pyproject.toml` — `+ asgi-lifespan>=2.1,<3` в `[dependency-groups].dev`; `+ [tool.coverage.run]` (source=src/line_provider, branch=true); `+ [tool.coverage.report]` (fail_under=85, show_missing=true, skip_covered=false, exclude_lines включает `pragma: no cover`, `raise NotImplementedError`, `if TYPE_CHECKING:`)
- `uv.lock` — регенерирован, +2 пакета (asgi-lifespan 2.1.0, sniffio 1.3.1)
- `.planning/REQUIREMENTS.md` — LP-02 строка: тип `event_id` → `UUID4 (client-generated)`, deadline → `UTC-aware datetime`, добавлена ссылка `Per D-05 (Phase 2 CONTEXT.md)`
- `tests/line_provider/conftest.py` — две fixture: `app` (lifespan-aware FastAPI) + `client` (AsyncClient bound to it). Docstrings объясняют почему split (плановое seed'ение `app.state.event_store` в Plan 02-07 integration-тестах без `client._transport`).
- `.planning/phases/02-line-provider-domain/02-VALIDATION.md` — canonical 20-task verification map, frontmatter `status: approved` + `nyquist_compliant: true` + `wave_0_complete: true`, Wave 0 Requirements все `[x]`, Validation Sign-Off все `[x]`, Approval line.

## Decisions Made

- **Conftest API: split fixtures vs yield-tuple.** Plan допускал оба варианта. Выбран split (`app` + `client` — две отдельные fixture). Reason: сохраняет существующий контракт тестов (`async def test_x(client: AsyncClient)`) без правок, и Plan 02-07 integration-тесты смогут ask `app: FastAPI` параллельно с `client` через стандартный pytest fixture injection — без частичного распаковывания tuple. Equivalent в expressivness, чище в API.
- **Coverage source restricted to `src/line_provider`.** Bet-maker self-declares scope in P3/P4. Avoids cross-package noise during P2 development.
- **Bet-maker EventFinishedMessage Wave 0 item dropped.** Planner-skeleton VALIDATION.md упоминал правку `src/bet_maker/.../messages.py` (UUID drift fix). В реальности bet-maker schemas/messages.py создаётся только в P3/P5; D-05 уже зафиксировал UUID across all three boundaries в CONTEXT.md/REQUIREMENTS.md — drift невозможен. Пункт убран как преждевременный.

## Deviations from Plan

None — plan executed exactly as written. All 4 tasks landed atomically; all verify-блоки и acceptance_criteria прошли с первой попытки; existing P1 baseline (`uv run pytest tests/line_provider -q`) остался зелёный (2 passed) после fixture upgrade.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Self-Check: PASSED

**Files verified:**
- `pyproject.toml` — FOUND (contains `asgi-lifespan>=2.1,<3` + `[tool.coverage.run]` + `[tool.coverage.report]`)
- `uv.lock` — FOUND (contains asgi-lifespan + sniffio)
- `.planning/REQUIREMENTS.md` — FOUND (LP-02 reflects UUID4 + Per D-05)
- `tests/line_provider/conftest.py` — FOUND (LifespanManager imported and used, 2 fixtures)
- `.planning/phases/02-line-provider-domain/02-VALIDATION.md` — FOUND (20 task IDs, wave_0_complete: true)

**Commits verified:**
- `b1d3eef` — FOUND (Task 1: chore(02-01): add asgi-lifespan dev-dep and coverage config)
- `6108550` — FOUND (Task 2: docs(02-01): sync REQUIREMENTS.md LP-02 to UUID4 per D-05)
- `2ce6089` — FOUND (Task 3: test(02-01): wrap line-provider client fixture in LifespanManager)
- `8fd4940` — FOUND (Task 4: docs(02-01): sync 02-VALIDATION.md per-task map with final P2 task IDs)

**Verification commands re-run:**
- `uv run pytest tests/line_provider -q` → 2 passed
- `uv run mypy --strict src/line_provider tests/line_provider` → 0 errors (13 source files)
- `uv run ruff check src/line_provider tests/line_provider` → All checks passed!
- `grep -q "asgi-lifespan" pyproject.toml uv.lock` → both contain
- `grep -q "UUID4" .planning/REQUIREMENTS.md` → match
- `grep -q "fail_under = 85" pyproject.toml` → match
- `grep -q "wave_0_complete: true" .planning/phases/02-line-provider-domain/02-VALIDATION.md` → match

## Next Phase Readiness

- **Wave 0 закрыт полностью.** Plan 02-02 (Schemas wave 1) и Plan 02-03 (State machine wave 1) разблокированы и могут стартовать параллельно.
- **Integration-test infra готова.** `LifespanManager`-обёрнутый `app` fixture обеспечит, что Plan 02-07 интеграционные тесты увидят `app.state.event_store` и `app.state.event_bus` корректно проинициализированными через lifespan (D-14 / Pitfall 1 mitigation).
- **Coverage gate активен.** Plan 02-07 final task запустит `uv run pytest --cov` и автоматически упадёт если покрытие на `src/line_provider` < 85%.
- **REQUIREMENTS.md и CONTEXT.md теперь согласованы по типу event_id.** Любой будущий планировщик читает оба источника без drift'а.

---
*Phase: 02-line-provider-domain*
*Completed: 2026-05-15*
