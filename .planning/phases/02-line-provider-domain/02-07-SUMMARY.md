---
phase: 02-line-provider-domain
plan: 07
subsystem: line-provider/http-routes
tags: [line-provider, http-api, routes, lifespan-wiring, integration-tests, phase-gate, coverage, fastapi, httpx, asgi-lifespan]

requires:
  - phase: 01-skeleton-infrastructure
    plan: 03
    provides: line_provider build_app() factory + lifespan skeleton + RequestContextMiddleware (X-Request-ID echo)
  - phase: 01-skeleton-infrastructure
    plan: 07
    provides: tests/line_provider/conftest.py (httpx AsyncClient + ASGITransport fixture infrastructure)
  - phase: 02-line-provider-domain
    plan: 01
    provides: asgi-lifespan dev-dep, conftest LifespanManager+app+client split, coverage config fail_under=85, FakeEventBus shared fake (later landed in Plan 02-05)
  - phase: 02-line-provider-domain
    plan: 02
    provides: EventCreate / EventUpdate / EventRead schemas, EventState enum, FutureDeadline + Coefficient validators (extra=forbid)
  - phase: 02-line-provider-domain
    plan: 03
    provides: TransitionForbiddenError (.current/.new attrs, D-08 message wording)
  - phase: 02-line-provider-domain
    plan: 04
    provides: InMemoryEventStore + EventAlreadyExistsError + EventNotFoundError (lock-protected dict; lock-free reads)
  - phase: 02-line-provider-domain
    plan: 05
    provides: StoreDep + EventBusDep + EventBus Protocol + NoopEventBus; create_event + set_event_state interactors (commit→publish ordering)
  - phase: 02-line-provider-domain
    plan: 06
    provides: get_event_by_id (Event | None) + list_active_events (module-level utc_now monkey-patch friendly)
provides:
  - src/line_provider/entrypoints/api/events.py — APIRouter(tags=['events']) с 4 endpoints: POST /event 201/409/422, PUT /event/{id} 200/404/422, GET /event/{id} 200/404, GET /events 200
  - src/line_provider/app.py — build_app() подключает events router после health router (3 add_middleware/include_router calls в правильном порядке)
  - src/line_provider/entrypoints/lifespan.py — расширен app.state.event_store = InMemoryEventStore() + app.state.event_bus = NoopEventBus() (D-14)
  - tests/line_provider/test_event_routes.py — 23 async integration tests в 7 классах (Wiring/Create/Update/Get/List/RequestId/Health)
affects:
  - Phase 5 (RabbitMQ) — Plan 02-07 routes остаются неизменными при swap NoopEventBus → RabbitEventBus (Protocol structural typing — interactor сигнатура set_event_state не меняется; меняется только app.state.event_bus в lifespan)
  - Phase 4 (bet-maker HTTP integration) — bet-maker.entrypoints.api будет проксировать `GET /events` через httpx, контракт EventRead (этот план) — single source of truth для DTO ответа
  - Phase 7 (Polish + Documentation) — README curl examples будут показывать POST/PUT/GET/GET последовательность через эти 4 endpoint'а; OpenAPI tags=['events'] подхватываются автоматически

tech-stack:
  added: []
  patterns:
    - "Thin route handlers: route только маппит request → interactor/selector → HTTPException. Никакой бизнес-логики в handler'е (state-machine check, store mutation, publish ordering — всё за пределами handler'а)."
    - "Доменные исключения mapped to HTTP через try/except + `raise HTTPException(...) from exc` — соблюдает PEP 3134 chain (ruff B904 ok) и не теряет stack trace."
    - "Round-trip через model_dump: `EventRead.model_validate(event.model_dump())` — явная конверсия Event (frozen) → EventRead. Альтернатива `model_validate(event, from_attributes=True)` отклонена как SQLAlchemy-style flag."
    - "Только PUT инжектирует `Request` параметр — POST/GET/list не нуждаются в headers. correlation_id берётся из `X-Request-ID` с default `\"no-request-id\"` (для тестов без header)."
    - "Lifespan singletons (D-14): event_store + event_bus созданы в lifespan ДО первого request; route handlers получают их через `Depends(get_store)` и `Depends(get_event_bus)` которые читают `request.app.state.event_store` / `.event_bus`. Tests могут swap'нуть `app.state.event_bus = FakeEventBus()` на лету между requests — get_event_bus читает state на каждом вызове, не кэширует."
    - "Integration matrix через `httpx.AsyncClient(transport=ASGITransport(app=app))` + `LifespanManager(app)` (asgi-lifespan dev-dep из Plan 02-01) — единственный способ заставить ASGITransport триггерить lifespan; без LifespanManager все эти тесты упали бы на `AttributeError: app.state.event_store` (Pitfall 1 из 02-RESEARCH)."
    - "monkey-patch testability для time-dependent кода: `monkeypatch.setattr(\"line_provider.selectors.list_active_events.utc_now\", lambda: fixed_now)` — паттерн из Plan 02-06 переиспользуется в integration тестах LP-05."

key-files:
  created:
    - src/line_provider/entrypoints/api/events.py
    - tests/line_provider/test_event_routes.py
  modified:
    - src/line_provider/app.py — added `from line_provider.entrypoints.api import events, health` + `app.include_router(events.router)` after health
    - src/line_provider/entrypoints/lifespan.py — added InMemoryEventStore() + NoopEventBus() в app.state

key-decisions:
  - "PUT routed на `/event/{event_id}` (W-1 revision per D-01/D-06) — суффикс `/state` намеренно отсутствует. PUT = full body upsert на существующем event'е (coefficient + deadline + state), а не «PUT-as-create-or-update». Создание событий остаётся прерогативой POST /event; PUT на несуществующее → 404 (не 201 upsert). Маршрут handler делегирует в `set_event_state` interactor, который содержит state-machine check + commit→publish ordering под одним lock'ом."
  - "Annotation `app.state.event_bus: EventBus = NoopEventBus()` упрощён до `app.state.event_bus = NoopEventBus()` — runtime контракт сохранён через Protocol structural typing на стороне `get_event_bus` (`Annotated[EventBus, Depends(...)]`), что mypy strict проверяет на типе аргумента в interactor. Annotation на attribute assignment на FastAPI's `types.SimpleNamespace` mypy игнорирует."
  - "Только PUT handler инжектирует `Request` параметр (для `X-Request-ID` header) — POST/GET/list не получают `Request`. Решение: явный контракт «correlation_id важен только при publish», нет request-параметра в чистых read/create handler'ах. Default `\"no-request-id\"` срабатывает в тестах без X-Request-ID header'а — RequestContextMiddleware из P1 эхо'ит этот же header в response (test_request_id_echoed_on_post проверяет round-trip)."
  - "`EventRead.model_validate(event.model_dump())` (round-trip через dict) выбран вместо `model_validate(event, from_attributes=True)` — явная конверсия + не использует SQLAlchemy-style flag, лучше читается; performance overhead на dict-trip пренебрежимо мал для нашей нагрузки (≤ O(100) событий)."
  - "TestList использует `monkeypatch.setattr(\"line_provider.selectors.list_active_events.utc_now\", lambda: fixed_now)` (D-19 паттерн из Plan 02-06) — все 3 seed event'а собираются относительно `fixed_now = 2026-06-01T12:00:00Z`. Прочие POST/PUT тесты не зависят от patched-time — они используют `datetime.now(timezone.utc) ± 1h`, что безопасно для AwareDatetime валидатора без clock-drift."
  - "Test classes (Wiring / Create / Update / Get / List / RequestId / Health) — для group-by-behaviour, не для pytest.TestSuite. Каждый класс — namespace для тестов одного route или одного invariant'а; pytest collect'ит их как plain async methods через pytest-asyncio asyncio_mode=auto."
  - "Coverage gate enforce'ен через `--cov-fail-under=85` на pytest CLI (а не только через `[tool.coverage.report] fail_under=85` в pyproject.toml). Причина: pyproject's `fail_under` срабатывает только при отдельной команде `coverage report`; CLI flag заставляет gate работать на каждом pytest run, что подхватит CI workflow в Phase 1 Plan 01-06 без дополнительной правки .github/workflows/ci.yml."

patterns-established:
  - "Pattern 1: Thin HTTP route handlers — handler читает body/path/header, вызывает 1 interactor или 1 selector, маппит доменное исключение в HTTPException, возвращает EventRead.model_validate(event.model_dump()). Никакой бизнес-логики в handler'е."
  - "Pattern 2: PEP 3134 exception chaining через `raise HTTPException(...) from exc` — соблюдает ruff B904, сохраняет stack trace, явно показывает причину reviewer'у."
  - "Pattern 3: Lifespan singletons read via `request.app.state.*` — Depends factory (`get_store`, `get_event_bus` из Plan 02-05) читают state на каждом запросе, не кэшируют — позволяет тестам swap'нуть state на лету между requests."
  - "Pattern 4: Integration test matrix через httpx.AsyncClient + ASGITransport + LifespanManager — единственный способ совместить full-stack ASGI lifespan и in-process тесты без docker. Все Phase 2 integration тесты используют этот паттерн, Phase 4 / Phase 5 / Phase 6 integration тесты будут его наследовать."
  - "Pattern 5: monkey-patch module-level `utc_now` для deterministic timing в integration тестах. `freezegun` НЕ используется — слишком тяжёлый для unit-уровня."
  - "Pattern 6: REQ-ID в docstrings всех тестов (LP-01..LP-08, QA-04/05, D-01..D-19, INFR-08, A7) — grep-traceability на проект. Это convention установлен в Plan 01-07 (Plan 02-07 commit message: `LP-0[1-9]|QA-05|D-0[1-9]|D-1[0-9]|INFR-08|A7`) и теперь устойчив на всю кодовую базу."

requirements-completed: [LP-01, LP-02, LP-03, LP-04, LP-05, LP-07, LP-08, QA-04, QA-05]

duration: ~6min
completed: 2026-05-15
---

# Phase 02 Plan 07: line-provider HTTP routes + lifespan wiring + integration matrix + phase-gate Summary

**4 thin HTTP route handlers (POST /event, PUT /event/{id}, GET /event/{id}, GET /events) wired to interactors+selectors, with lifespan singletons (InMemoryEventStore + NoopEventBus) created in app.state, fully covered by 23-test async integration matrix via httpx.AsyncClient + ASGITransport + LifespanManager; phase-gate green at coverage 96.42% (well above the 85% threshold), mypy strict / ruff clean across 41 source files.**

## Performance

- **Duration:** ~6 min total across two agent sessions (first agent landed implementation commits 2a1f02c..1cfad52 before quota hit; this wrap-up session verified gates, synced docs, wrote SUMMARY)
- **Started:** 2026-05-15 (first agent commits)
- **Completed:** 2026-05-15 (this wrap-up session)
- **Tasks:** 4 / 4 (all auto, all TDD where applicable)
- **Files created:** 2 (`src/line_provider/entrypoints/api/events.py`, `tests/line_provider/test_event_routes.py`)
- **Files modified:** 2 (`src/line_provider/app.py`, `src/line_provider/entrypoints/lifespan.py`)
- **Docs updated:** 4 (`.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, plus this SUMMARY)
- **Tests added:** 23 async integration tests (in 7 test classes)
- **Full suite after this plan:** 97 passed (95 line_provider + 2 bet_maker baseline P1)
- **Coverage gate (src/line_provider):** 96.42% (gate ≥85% passed by 11.42 percentage points)

## Accomplishments

- **4 HTTP endpoints fully wired and tested:**
  - `POST /event` — 201 on new, 409 on duplicate, 422 on invalid coefficient (<=0, >2dp), past deadline, naive deadline, extra field, invalid UUID
  - `PUT /event/{event_id}` — 200 on valid update, 404 on missing, 422 on reverse transition with detail string `state transition FINISHED_WIN->NEW not allowed`, 200 + no publish on no-op state, 200 + publish via FakeEventBus on terminal transition with X-Request-ID propagated as correlation_id
  - `GET /event/{event_id}` — 200 + EventRead on hit, 404 on miss
  - `GET /events` — 200 with only NEW + future events (LP-05), 200 + [] on empty store
- **Lifespan singletons (D-14):** `InMemoryEventStore()` and `NoopEventBus()` created in `app.state` before first request; verified via `TestWiring.test_lifespan_wires_event_store_and_bus` directly on `app: FastAPI` fixture.
- **23-test async integration matrix** in 7 test classes (Wiring, Create, Update, Get, List, RequestId, Health) covers all 6 Phase 2 ROADMAP success criteria + INFR-08 X-Request-ID echo + A7 correlation_id propagation. All tests use `httpx.AsyncClient(transport=ASGITransport(app=app))` from the conftest fixture chain `app -> client` (Plan 02-01), wrapped by `LifespanManager(app)` to trigger lifespan startup/shutdown.
- **Phase-gate verification:** `uv run pytest -q` → 97 passed; coverage on `src/line_provider` = 96.42% (only uncovered: `__main__.py` lines 1-20 which is the `python -m line_provider` entrypoint, plus one `Protocol.publish` `...` branch in `event_bus.py:11->exit` — both expected); `uv run mypy --strict src/line_provider tests/line_provider` → Success, no issues found in 41 source files; `uv run ruff check src/line_provider tests/line_provider` → All checks passed; `uv run ruff format --check src/line_provider tests/line_provider` → 41 files already formatted.
- **REQUIREMENTS / ROADMAP synced:** LP-03 (PUT route), LP-05 (GET /events), LP-07 (GET /health invariant), QA-04 (unit tests on every layer), QA-05 (integration tests via httpx AsyncClient) all promoted from Pending/In-progress to Complete. ROADMAP Phase 2 checkbox flipped to `[x]`, progress table updated to `7/7 Complete 2026-05-15`.

## Task Commits

Implementation commits (from earlier agent session):

1. **Task 1 RED:** `2a1f02c` — test(02-07): add failing smoke test for events router
2. **Task 1 GREEN:** `5b32493` — feat(02-07): add events router with 4 HTTP handlers
3. **Task 2 RED:** `fefaa1f` — test(02-07): add failing tests for lifespan + app wiring
4. **Task 2 GREEN:** `879ba2b` — feat(02-07): wire events router and singletons in app + lifespan
5. **Task 3 expansion:** `1cfad52` — test(02-07): expand to full HTTP integration matrix (23 tests)

Wrap-up commit (this session): final `docs(02-07): complete line-provider HTTP routes plan` commit (hash issued at commit time below) — REQUIREMENTS.md + ROADMAP.md + STATE.md + this SUMMARY.

_Note: Plan-level TDD gate compliance — gate sequence preserved: each task pair is RED `test(02-07)` → GREEN `feat(02-07)`. Task 3 (integration matrix) is REFACTOR-shaped in TDD terms (tests pass immediately against existing GREEN implementation from Tasks 1+2), so it lands as a single `test(02-07)` commit — same convention as Plan 02-04 (`44f071a`) and Plan 02-06 (`ef01829`)._

## Files Created/Modified

- **`src/line_provider/entrypoints/api/events.py`** (created, 89 lines, 0 comments) — 4 route handlers. Imports: `UUID`, `APIRouter`/`HTTPException`/`Request`/`status` from FastAPI, `StoreDep`/`EventBusDep` from facades, `TransitionForbiddenError` from helpers, `EventAlreadyExistsError`/`EventNotFoundError` from infrastructure.store.in_memory, `create_event`/`set_event_state` from interactors, `EventCreate`/`EventRead`/`EventUpdate` from schemas, `get_event_by_id`/`list_active_events` from selectors. Router declared as `APIRouter(tags=["events"])`. Each handler decorated with explicit `status_code=status.HTTP_*` and `response_model=EventRead | list[EventRead]`. Domain exceptions translated via `raise HTTPException(...) from exc` (PEP 3134, ruff B904).
- **`src/line_provider/app.py`** (modified — added 1 import line + 1 include_router line) — `from line_provider.entrypoints.api import events, health` (combined import keeps app.py at ~20 lines); `app.include_router(events.router)` added after `app.include_router(health.router)` (health-first order preserves P1 invariant for the `/health` route's 200 response).
- **`src/line_provider/entrypoints/lifespan.py`** (modified — added 2 imports + 2 state assignments) — `from line_provider.facades.event_bus import NoopEventBus` and `from line_provider.infrastructure.store.in_memory import InMemoryEventStore` added. Inside lifespan, after `app.state.settings = settings` and before `try:`, two assignments: `app.state.event_store = InMemoryEventStore()` and `app.state.event_bus = NoopEventBus()`. structlog `log.info("line_provider.startup", service=settings.service_name)` and the try/yield/finally shutdown log preserved verbatim.
- **`tests/line_provider/test_event_routes.py`** (created, 321 lines) — 23 async tests in 7 test classes. Module docstring cites LP-01..LP-08, QA-05, D-01/D-06, D-19. Three local helpers `_iso_future(seconds=3600)`, `_iso_past()`, `_iso_naive_future()` factor out date string construction. `_create_body(coefficient="1.50", deadline=None)` factors out the 3-field POST body. Tests parameterised on `client: AsyncClient` and (where needed) `app: FastAPI` fixtures from conftest.py. `FakeEventBus` imported from `tests.line_provider._fakes` (Plan 02-05 Task 2). 5 of the 23 tests use `app.state.event_bus = FakeEventBus()` swap mid-test to assert publish behaviour without rewiring the lifespan; 1 of the 23 (TestList.test_get_events_returns_active) uses `monkeypatch.setattr("line_provider.selectors.list_active_events.utc_now", lambda: fixed_now)` for deterministic LP-05 timing.

Documentation files modified in wrap-up:

- **`.planning/REQUIREMENTS.md`** — LP-03/LP-05/LP-07 line items checkbox flipped to `[x]`; QA-04/QA-05 line items checkbox flipped to `[x]` with updated rationale (per-layer + integration tests landed across 02-02..02-07); Traceability table updated for LP-03/LP-05/LP-07/QA-04/QA-05 (`Pending`/`In progress` → `Complete`).
- **`.planning/ROADMAP.md`** — Phase 2 top-level checkbox flipped to `[x]`; Phase 2 plan list line for `02-07-PLAN.md` flipped to `[x]`; Phase 2 plans header changed from `**Plans:** 6/7 plans executed` to `**Plans:** 7/7 plans executed (Phase 2 complete 2026-05-15)`; Progress table row for Phase 2 updated to `7/7 | Complete | 2026-05-15`.
- **`.planning/STATE.md`** — frontmatter `completed_phases: 1 → 2`, `completed_plans: 13 → 14`, `percent: 93 → 100`, `last_updated` bumped to 2026-05-15T09:10:00Z. Current Position section: phase status flipped from `EXECUTING` to `COMPLETE`. Performance metrics: `Phases complete 1/7 → 2/7`, `Plans complete 12/14 → 14/14`, new Plan 02-07 duration row added. Decisions section: new Plan 02-07 decision entry inserted before the Plan 02-05 entry (chronological). Session Continuity: Last Session and Next Session sections updated to point to Phase 3 / `/gsd-plan-phase`.

## Decisions Made

See `key-decisions` in the frontmatter for the full list with rationale. Top three highlights:

1. **PUT routed on `/event/{event_id}` (no `/state` suffix)** — W-1 revision of the original plan that had `PUT /event/{event_id}/state`. D-01/D-06 from 02-CONTEXT.md fixes this: PUT is the full-body update (coefficient + deadline + state) on an existing event, never an upsert-create. POST owns creation, PUT owns update, GET owns read, GET-list owns active-events list. (method, path) pairs are unambiguous: POST /event, PUT /event/{id}, GET /event/{id}, GET /events — no route conflicts.
2. **Annotation `app.state.event_bus: EventBus = NoopEventBus()` simplified to `app.state.event_bus = NoopEventBus()`** — runtime contract is preserved via Protocol structural typing at the consumption sites (interactor signatures use `bus: EventBus`); mypy strict ignores annotation on attribute assignment to `types.SimpleNamespace` anyway, so the annotation was visual noise.
3. **Coverage gate via `--cov-fail-under=85` CLI flag (not only pyproject.toml's `[tool.coverage.report].fail_under`)** — pyproject's setting only triggers under the standalone `coverage report` command; the CLI flag makes the gate fail the pytest exit code directly. Both layers stay in place as defence-in-depth: CLI for pytest-driven gates (and CI), pyproject for `coverage report` after-the-fact inspection.

## Deviations from Plan

None — plan executed exactly as written.

The first agent session followed the Task 1 → Task 2 → Task 3 TDD discipline verbatim; the wrap-up session (this one) executed Task 4 (phase-gate + REQUIREMENTS/ROADMAP sync) and produced this SUMMARY + the final docs commit. No Rule 1 / Rule 2 / Rule 3 auto-fixes were needed. No Rule 4 architectural decisions raised. No checkpoints raised. No deferred items added to `deferred-items.md`. The plan as written in `02-07-PLAN.md` was executable end-to-end without revision.

(Minor observation, not a deviation: pytest emits one DeprecationWarning during `test_put_reverse_returns_422_with_detail` because `fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in favour of `HTTP_422_UNPROCESSABLE_CONTENT` in the version of FastAPI present in `uv.lock`. Renaming the constant across `events.py` would be a one-line change with no behavioural impact — deferred to Phase 7 polish to keep this plan's diff minimal and avoid drift between PLAN.md acceptance criteria text `status.HTTP_422_UNPROCESSABLE_ENTITY` and code. Logged for Phase 7 audit.)

## Issues Encountered

None. The first agent session hit its quota after the 5th implementation commit (`1cfad52`), at which point all implementation and tests were committed and green — only docs sync + SUMMARY remained, which is what this wrap-up session handled.

## Verification (Phase-Gate)

All Plan 02-07 acceptance criteria for Task 4 re-verified in this wrap-up session:

```text
uv run pytest -q
  -> 97 passed, 1 warning in 0.37s

uv run pytest --cov=src/line_provider --cov-fail-under=85 --cov-report=term-missing tests/line_provider
  -> 95 passed; coverage 96.42%; Required test coverage of 85% reached.

uv run coverage report
  -> 287 stmts, 8 missed, 20 branches, 1 partial branch, TOTAL 96%

uv run mypy --strict src/line_provider tests/line_provider
  -> Success: no issues found in 41 source files

uv run ruff check src/line_provider tests/line_provider
  -> All checks passed!

uv run ruff format --check src/line_provider tests/line_provider
  -> 41 files already formatted
```

Coverage detail (only uncovered code):

- `src/line_provider/__main__.py` (8 stmts, 8 missed, 0% — this is the `python -m line_provider` entrypoint that calls `uvicorn.run(factory=True)`; never invoked from pytest. Expected.)
- `src/line_provider/facades/event_bus.py:11->exit` (Protocol method with `...` body — `EventBus.publish` ABC stub; the `...` body is never executed by either NoopEventBus or FakeEventBus, which implement the method concretely. Expected.)

All other 38 source files: 100% line + branch coverage.

ROADMAP.md Phase 2 success criteria audit:

1. **POST/PUT /event creates or updates** — closed by `TestCreate.test_post_event_returns_201` + `TestUpdate.test_put_event_returns_200` + validation matrix (8 422-cases) ✔
2. **GET /event/{event_id} 200/404** — closed by `TestGet.test_get_event_by_id_returns_200` + `TestGet.test_get_missing_returns_404` ✔
3. **GET /events returns only active** — closed by `TestList.test_get_events_returns_active` (monkey-patched utc_now, asserts only NEW+future surfaces) + `TestList.test_get_events_empty` ✔
4. **Reverse transitions → 422** — closed by `TestUpdate.test_put_reverse_returns_422_with_detail` (asserts exact detail string `state transition FINISHED_WIN->NEW not allowed`) ✔
5. **GET /health 200** — closed by `TestHealth.test_health_still_returns_ok_after_events_router` (P1 invariant preserved after events router added) ✔
6. **Unit + integration tests cover all layers** — closed by Plan 02-02 schemas tests (22), Plan 02-03 state-machine tests (12), Plan 02-04 store tests (13), Plan 02-05 interactor + facades tests (15), Plan 02-06 selectors tests (8), Plan 02-07 integration matrix (23), Plan 01-07 health smoke (2 per service). 95 tests on line_provider + 2 on bet_maker = 97 total. ✔

## Threat Surface Scan

No new surface beyond the plan's `<threat_model>`. All T-07-01..T-07-10 dispositions addressed:

- **T-07-01 (Tampering / Malformed JSON body)** — mitigated. FastAPI parses JSON via starlette + Pydantic before the handler runs; malformed bodies return 422 with structured detail. Verified by 8 of the 9 TestCreate 422-cases.
- **T-07-02 (Tampering / UUID path injection)** — mitigated. FastAPI's `event_id: UUID` parses the path param before the handler; invalid UUID → 422. Verified by `TestCreate.test_post_invalid_uuid_returns_422`.
- **T-07-03 (Information Disclosure / 422 leak stack trace)** — mitigated. All HTTPException raises are explicit with structured `detail`; no bare `raise` without catch. Verified by inspection of `events.py` — all exception flows have `try/except + raise HTTPException(...) from exc`.
- **T-07-04 (Information Disclosure / 404/409 leak existence)** — accepted per API design. No authentication on read endpoints (out of scope per ТЗ).
- **T-07-05 (DoS / Unbounded POST body)** — mitigated by Starlette default body limit (~1MB).
- **T-07-06 (Repudiation / Publish without correlation_id)** — mitigated. PUT handler reads `request.headers.get("X-Request-ID", "no-request-id")` and passes it to `set_event_state`. `correlation_id` is a required field on `EventFinishedMessage`. Verified by `TestRequestId.test_request_id_propagated_to_event_bus`.
- **T-07-07 (Log injection / X-Request-ID with newlines)** — mitigated by structlog JSONRenderer (P1 baseline); no f-string concatenation in log calls.
- **T-07-08 (Spoofing / Lifespan NoopEventBus swap)** — accepted. Lifespan is server-side code, attacker has no access. Tests' `app.state.event_bus = FakeEventBus()` swap is intentional test-only path.
- **T-07-09 (Authorisation / No auth)** — accepted per ТЗ.
- **T-07-10 (Tampering / Race POST + PUT same id)** — mitigated. `store.add` and `store.update` both hold `asyncio.Lock`; `set_event_state` uses `previous_state` from the atomic update tuple to gate publish. Verified by Plan 02-04 concurrent gather tests (carried forward) and Plan 02-05 publish-once-on-concurrent-terminal-transitions test.

## Known Stubs

None. Both production files are wired with their final P2 implementations:

- `NoopEventBus.publish(...)` returns `None` — this is **intentional and contract-compliant** for Phase 2. The contract is "no AMQP yet; publish is observable via FakeEventBus in tests; P5 swaps to RabbitEventBus without route changes." This is NOT a stub-as-bug — it's the lifespan singleton chosen by D-14 for Phase 2.
- Routes return concrete EventRead / list[EventRead]; no placeholder fields, no NotImplementedError.

Phase 3 (bet-maker DB) is fully unblocked — no Phase 2 outputs are required for Phase 3 (parallelizable per ROADMAP). Phase 5 (RabbitMQ) will swap `NoopEventBus()` → `RabbitEventBus()` in `lifespan.py` only; the routes in this plan stay byte-for-byte unchanged.

## User Setup Required

None. Pure-Python, in-process integration tests; no external services, no env vars, no manual verification, no auth gates. `docker compose up` from Phase 1 continues to work unchanged (line-provider service exposes the 4 new endpoints automatically; healthcheck via `curl http://line-provider:8000/health` still returns `{"status":"ok"}`).

## TDD Gate Compliance

Plan-level TDD cycle confirmed in git log (most recent first):

1. `1cfad52` test(02-07): expand to full HTTP integration matrix (23 tests) — REFACTOR-shaped (tests pass immediately against existing GREEN implementation; pattern matches Plan 02-04 `44f071a` and Plan 02-06 `ef01829`)
2. `879ba2b` feat(02-07): wire events router and singletons in app + lifespan — GREEN gate (Task 2)
3. `fefaa1f` test(02-07): add failing tests for lifespan + app wiring — RED gate (Task 2)
4. `5b32493` feat(02-07): add events router with 4 HTTP handlers — GREEN gate (Task 1)
5. `2a1f02c` test(02-07): add failing smoke test for events router — RED gate (Task 1)

RED → GREEN → coverage-extension sequence preserved for both Task 1 and Task 2.

## Self-Check: PASSED

**Files verified:**

- `src/line_provider/entrypoints/api/events.py` — FOUND (89 lines, 4 `@router.` decorators, 0 comments, all 4 `status.HTTP_*` constants present, PUT routed on `/event/{event_id}` per D-01/D-06, no `/state` suffix anywhere)
- `src/line_provider/app.py` — FOUND (20 lines, both routers included, health-first order, lifespan attached)
- `src/line_provider/entrypoints/lifespan.py` — FOUND (28 lines, InMemoryEventStore + NoopEventBus assigned to app.state, settings preserved)
- `tests/line_provider/test_event_routes.py` — FOUND (321 lines, 7 test classes, 23 async test functions, FakeEventBus import + 5 swap-sites, monkey-patch of utc_now on the LP-05 list test)
- `.planning/phases/02-line-provider-domain/02-07-SUMMARY.md` — FOUND (this file)
- `.planning/REQUIREMENTS.md` — UPDATED (LP-03/LP-05/LP-07/QA-04/QA-05 → Complete in both line items and Traceability table)
- `.planning/ROADMAP.md` — UPDATED (Phase 2 checkbox `[x]`, Plan 02-07 checkbox `[x]`, Plans header `7/7 plans executed (Phase 2 complete 2026-05-15)`, Progress table row `7/7 Complete 2026-05-15`)
- `.planning/STATE.md` — UPDATED (frontmatter completed_phases 2/7, completed_plans 14/14, percent 100; Current Position Phase 2 COMPLETE; new Plan 02-07 decision entry; Last Session + Next Session pointing to Phase 3)

**Commits verified:**

- `2a1f02c` — FOUND (test(02-07): add failing smoke test for events router)
- `5b32493` — FOUND (feat(02-07): add events router with 4 HTTP handlers)
- `fefaa1f` — FOUND (test(02-07): add failing tests for lifespan + app wiring)
- `879ba2b` — FOUND (feat(02-07): wire events router and singletons in app + lifespan)
- `1cfad52` — FOUND (test(02-07): expand to full HTTP integration matrix (23 tests))

**Verification commands re-run in this wrap-up session:**

- `uv run pytest -q` → 97 passed, 1 warning ✔
- `uv run pytest --cov=src/line_provider --cov-fail-under=85 --cov-report=term-missing tests/line_provider` → 95 passed, coverage 96.42% ≥ 85% ✔
- `uv run coverage report` → 287 stmts, TOTAL 96% ✔
- `uv run mypy --strict src/line_provider tests/line_provider` → Success: no issues found in 41 source files ✔
- `uv run ruff check src/line_provider tests/line_provider` → All checks passed! ✔
- `uv run ruff format --check src/line_provider tests/line_provider` → 41 files already formatted ✔
- `grep -c "^class Test" tests/line_provider/test_event_routes.py` → 7 (>=6 required) ✔
- `grep -c "^    async def test_" tests/line_provider/test_event_routes.py` → 23 (>=20 required) ✔
- `grep -c "^- \[x\] \*\*LP-0[12345789]\*\*" .planning/REQUIREMENTS.md` → 7 (LP-01..05, 07, 08) ✔
- `grep -c "^- \[x\] \*\*QA-0[45]\*\*" .planning/REQUIREMENTS.md` → 2 (QA-04, QA-05) ✔
- `grep -q "Phase 2 complete" .planning/ROADMAP.md` → exit 0 ✔
- `grep -c "/event/.*/state" tests/line_provider/test_event_routes.py` → 0 (W-1 revision verified) ✔
- `grep -c "/event/.*/state" src/line_provider/entrypoints/api/events.py` → 0 (W-1 revision verified) ✔

## Next Phase Readiness

- **Phase 2 closed.** All 7 Phase 2 plans complete; all 9 Phase 2 requirements (LP-01, LP-02, LP-03, LP-04, LP-05, LP-07, LP-08, QA-04, QA-05) marked Complete in REQUIREMENTS.md. ROADMAP.md Phase 2 entry marked `[x]` with 7/7 progress.
- **Phase 3 unblocked.** Phase 3 (bet-maker domain DB) does not depend on any Phase 2 outputs. ROADMAP.md Phase 3 success criteria are well-defined; planner can decompose them into atomic plans on the next `/gsd-plan-phase` call. Phase 3's contracts (BM-01 SQLAlchemy 2.0 async, BM-02 UoW, BM-03 layered arch, BM-05 POST /bet, BM-07 GET /bets, BM-08 /health PG ping) are entirely independent of Phase 2 modules.
- **Phase 5 unblocked from Phase 2 side.** When Phase 5 (RabbitMQ integration) lands, the only change to Phase 2 code will be a 1-line edit in `lifespan.py`: `app.state.event_bus = NoopEventBus()` → `app.state.event_bus = RabbitEventBus(...)`. The interactor and route signatures stay unchanged because `EventBus` is structurally typed (Protocol). The TestUpdate.test_put_publishes_via_event_bus_on_terminal_transition test already exercises the swap-on-the-fly invariant.
- **Phase 7 polish backlog:**
  - Rename `status.HTTP_422_UNPROCESSABLE_ENTITY` → `status.HTTP_422_UNPROCESSABLE_CONTENT` in `src/line_provider/entrypoints/api/events.py` once FastAPI's deprecation lands. One-line trivial change; deferred only to keep this plan's diff aligned with PLAN.md acceptance criteria text.
  - README curl examples for the 4 new routes (POST event → PUT terminal-state → GET bets — once bet-maker exists in Phase 3 / Phase 5).
  - OpenAPI tag descriptions and per-route summaries (currently `tags=["events"]` is the only OpenAPI metadata; Phase 7 polish will add response examples + per-route summaries).

- **Open Todos:** None. Recommended next command: `/gsd-plan-phase` for Phase 3.

---
*Phase: 02-line-provider-domain*
*Completed: 2026-05-15*
