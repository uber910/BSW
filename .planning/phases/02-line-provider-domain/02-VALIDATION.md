---
phase: 2
slug: line-provider-domain
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-14
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.1.0 + pytest-cov 7.1.0 |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) + `services/line-provider/tests/conftest.py` |
| **Quick run command** | `uv run --package line-provider pytest services/line-provider/tests -x -q` |
| **Full suite command** | `uv run --package line-provider pytest services/line-provider/tests --cov=line_provider --cov-report=term-missing` |
| **Estimated runtime** | ~10 seconds (Phase 2 scope, no DB/AMQP I/O) |

---

## Sampling Rate

- **After every task commit:** Run quick command (single failure stops; <5s typical)
- **After every plan wave:** Run full suite with coverage
- **Before `/gsd-verify-work`:** Full suite green + coverage ≥ 85% for `line_provider/{interactors,helpers,selectors}`
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

To be populated by `gsd-planner` based on the wave/task breakdown produced in PLAN.md. Required columns: Task ID · Plan · Wave · Requirement · Threat Ref · Secure Behavior · Test Type · Automated Command · File Exists · Status.

Suggested skeleton (planner refines IDs):

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 0 | LP-07 | — | dev-dep `asgi-lifespan` installed; lockfile updated | shell | `uv run python -c "import asgi_lifespan"` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 0 | QA-04 | — | REQUIREMENTS.md LP-02 reflects UUID4 event_id (D-05 sync) | doc | `grep "UUID4" .planning/REQUIREMENTS.md` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 1 | LP-01 | A6 | `EventState` enum has exactly 3 members; transitions table covers 9 cases | unit | `pytest services/line-provider/tests/unit/test_state_machine.py -x` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02 | 1 | LP-04 | — | `coefficient` rejects ≤0, > 2dp, non-Decimal | unit | `pytest services/line-provider/tests/unit/test_schemas.py::test_coefficient -x` | ❌ W0 | ⬜ pending |
| 2-02-03 | 02 | 1 | LP-04 | — | `deadline` rejects naive datetime and past timestamps | unit | `pytest services/line-provider/tests/unit/test_schemas.py::test_deadline -x` | ❌ W0 | ⬜ pending |
| 2-03-01 | 03 | 1 | LP-03 | A6 | `InMemoryEventStore` serialises writes via `asyncio.Lock`; concurrent upserts produce single consistent state | unit | `pytest services/line-provider/tests/unit/test_store.py -x` | ❌ W0 | ⬜ pending |
| 2-03-02 | 03 | 1 | LP-05 | R9/R12 | `update()` returns `(event, previous_state)` so interactor can decide publish in P5 without refactor | unit | `pytest services/line-provider/tests/unit/test_store.py::test_update_returns_previous -x` | ❌ W0 | ⬜ pending |
| 2-04-01 | 04 | 1 | LP-05 | R9/R12 | `set_event_state` mutates store BEFORE invoking event-bus stub | unit | `pytest services/line-provider/tests/unit/test_interactors.py::test_publish_ordering -x` | ❌ W0 | ⬜ pending |
| 2-04-02 | 04 | 1 | LP-05 | — | Reverse transitions raise `TransitionForbiddenError` (no mutation) | unit | `pytest services/line-provider/tests/unit/test_interactors.py::test_reject_reverse -x` | ❌ W0 | ⬜ pending |
| 2-05-01 | 05 | 1 | LP-03 | — | `select_active_events` returns only `state==NEW AND deadline>now` | unit | `pytest services/line-provider/tests/unit/test_selectors.py -x` | ❌ W0 | ⬜ pending |
| 2-06-01 | 06 | 2 | LP-01 | — | `POST /event` returns 201 on create, 200 on update | integration | `pytest services/line-provider/tests/integration/test_event_routes.py::test_upsert -x` | ❌ W0 | ⬜ pending |
| 2-06-02 | 06 | 2 | LP-02 | — | `GET /event/{id}` returns 200 with body, 404 on miss | integration | `pytest services/line-provider/tests/integration/test_event_routes.py::test_get -x` | ❌ W0 | ⬜ pending |
| 2-06-03 | 06 | 2 | LP-03 | — | `GET /events` filters only active events | integration | `pytest services/line-provider/tests/integration/test_event_routes.py::test_list -x` | ❌ W0 | ⬜ pending |
| 2-06-04 | 06 | 2 | LP-05 | — | Reverse transition returns 422 with descriptive body | integration | `pytest services/line-provider/tests/integration/test_event_routes.py::test_reverse_422 -x` | ❌ W0 | ⬜ pending |
| 2-07-01 | 07 | 2 | LP-07 | — | `GET /health` returns 200 always (no AMQP yet) | integration | `pytest services/line-provider/tests/integration/test_health.py -x` | ❌ W0 | ⬜ pending |
| 2-08-01 | 08 | 2 | LP-08, A7 | — | request-id middleware binds id to structlog ctx and calls `clear_contextvars` on response | integration | `pytest services/line-provider/tests/integration/test_request_id.py -x` | ❌ W0 | ⬜ pending |
| 2-09-01 | 09 | 2 | QA-04, QA-05 | — | Full suite green; coverage ≥ 85% on `interactors,helpers,selectors` | shell | full suite command above | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Planner MUST replace this skeleton with the canonical per-task verification map derived from the final PLAN.md task list. Threat refs left empty here are filled in step 5.55 (Security Threat Model).*

---

## Wave 0 Requirements

- [ ] `asgi-lifespan>=2.1,<3` added to dev-dependencies (line-provider package) — required so `httpx.AsyncClient(transport=ASGITransport)` actually triggers FastAPI lifespan and populates `app.state.event_store` / `app.state.event_bus` (R from RESEARCH.md §1).
- [ ] `services/line-provider/tests/conftest.py` — async client fixture wrapping `LifespanManager(app)` + `AsyncClient(transport=ASGITransport(app), base_url="http://testserver")`; yields tuple `(client, app)` for white-box access to `app.state.event_store` when tests need to seed/inspect state.
- [ ] `services/line-provider/tests/unit/__init__.py`, `services/line-provider/tests/integration/__init__.py` — empty packages.
- [ ] REQUIREMENTS.md sync: LP-02 `event_id` type str → UUID4 (D-05 override; matches CONTEXT.md and ARCHITECTURE).
- [ ] `EventFinishedMessage.event_id` schema corrected to UUID (was int in legacy stub) — needed before P5, fixed here to avoid drift.
- [ ] pyproject `[tool.pytest.ini_options]` carries `asyncio_mode = "auto"` (single source of truth for both services).
- [ ] pyproject `[tool.coverage.run]` carries `source = ["line_provider"]` + `branch = true`; `[tool.coverage.report]` carries `fail_under = 85`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OpenAPI schema renders all 4 routes with correct request/response models in Swagger UI | LP-01..LP-05, LP-07 | Visual confirmation that examples / status codes render the way the reviewer will see them; automated schema-snapshot is overkill for a test task | `docker compose up line-provider`, открыть `http://localhost:8000/docs`, проверить 4 роута + /health, статусы, схемы запросов/ответов |
| 422 error body for reverse transition is human-readable (not raw `TransitionForbiddenError`) | LP-05 | Asserts UX of error message; integration test asserts status code, this asserts message shape | После предыдущего шага: POST `/event` (создать NEW), затем POST с тем же id и `state=NEW` после перевода в FINISHED_WIN — body должен содержать `"detail"` с понятной строкой |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (asgi-lifespan dev-dep + REQUIREMENTS.md sync + conftest fixtures)
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
