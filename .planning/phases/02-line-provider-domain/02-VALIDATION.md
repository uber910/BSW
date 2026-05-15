---
phase: 2
slug: line-provider-domain
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-14
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.1.0 + pytest-cov 7.1.0 |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) + `tests/line_provider/conftest.py` (P1) |
| **Quick run command** | `uv run pytest tests/line_provider -x -q` |
| **Full suite command** | `uv run pytest tests/line_provider --cov=line_provider --cov-report=term-missing` |
| **Estimated runtime** | ~10 seconds (Phase 2 scope, no DB/AMQP I/O) |

---

## Sampling Rate

- **After every task commit:** Run quick command (single failure stops; <5s typical)
- **After every plan wave:** Run full suite with coverage
- **Before `/gsd-verify-work`:** Full suite green + coverage ≥ 85% for `line_provider/{interactors,helpers,selectors}`
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

Canonical map synchronised with the final PLAN.md task lists of all seven P2 plans (02-01 .. 02-07).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 0 | QA-04, QA-05 | — | asgi-lifespan>=2.1 in dev-deps + coverage config | shell | `uv run python -c "import asgi_lifespan"` && `grep -q "fail_under = 85" pyproject.toml` | W0 | pending |
| 2-01-02 | 01 | 0 | QA-04 | — | REQUIREMENTS.md LP-02 = UUID4 per D-05 | shell | `grep -q "LP-02.*UUID4" .planning/REQUIREMENTS.md` | W0 | pending |
| 2-01-03 | 01 | 0 | QA-05 | — | conftest client fixture wraps LifespanManager | unit | `uv run pytest tests/line_provider -q` | W0 | pending |
| 2-01-04 | 01 | 0 | QA-04, QA-05 | — | This validation map synced | doc | `grep -q "2-07-" .planning/phases/02-line-provider-domain/02-VALIDATION.md` | W0 | pending |
| 2-02-01 | 02 | 1 | LP-02 | T-02-INPUT | EventState enum, EventCreate/EventUpdate/Event/EventRead with frozen + extra="forbid" + AwareDatetime + Coefficient annotated | unit | `uv run pytest tests/line_provider/test_schemas.py -q` | W0 | pending |
| 2-02-02 | 02 | 1 | LP-04 | T-02-INPUT | EventFinishedMessage schema (frozen, extra="forbid", schema_version, EventTerminalState, UUID event_id) | unit | `uv run pytest tests/line_provider/test_schemas.py::TestMessages -q` | W0 | pending |
| 2-03-01 | 03 | 1 | LP-05, LP-08 | T-03-STATE | is_transition_allowed parametrized 9-case table | unit | `uv run pytest tests/line_provider/test_state_machine.py -q` | W0 | pending |
| 2-04-01 | 04 | 1 | LP-01, LP-08 | T-04-RACE | InMemoryEventStore add/update/get/list under asyncio.Lock + concurrent gather safe | unit | `uv run pytest tests/line_provider/test_in_memory_store.py -q` | W0 | pending |
| 2-04-02 | 04 | 1 | LP-01 | T-04-RACE | store.update returns (new, previous_state) tuple | unit | same | W0 | pending |
| 2-05-01 | 05 | 2 | LP-01, LP-03, LP-08 | T-05-ORDER | create_event interactor builds frozen Event(state=NEW) + store.add | unit | `uv run pytest tests/line_provider/test_create_event.py -q` | W0 | pending |
| 2-05-02 | 05 | 2 | LP-03, LP-08 | T-05-ORDER | set_event_state: commit BEFORE publish; reverse → TransitionForbiddenError; no-op state → no publish; FakeEventBus captures call order | unit | `uv run pytest tests/line_provider/test_set_event_state.py -q` | W0 | pending |
| 2-05-03 | 05 | 2 | LP-01 | T-05-FACADE | EventBus Protocol + NoopEventBus + facades/deps DI providers | unit | `uv run pytest tests/line_provider/test_facades.py -q` | W0 | pending |
| 2-06-01 | 06 | 2 | LP-04 | — | get_event_by_id selector (pure read) | unit | `uv run pytest tests/line_provider/test_selectors.py::test_get -q` | W0 | pending |
| 2-06-02 | 06 | 2 | LP-05 | — | list_active_events filters deadline>now AND state==NEW (monkey-patched utc_now) | unit | `uv run pytest tests/line_provider/test_selectors.py::test_list -q` | W0 | pending |
| 2-07-01 | 07 | 3 | LP-03 | T-07-INPUT | POST /event 201 happy + 409 dup + 422 coefficient/deadline | integration | `uv run pytest tests/line_provider/test_event_routes.py::TestCreate -q` | W0 | pending |
| 2-07-02 | 07 | 3 | LP-03, LP-08 | T-07-STATE | PUT /event/{id} 200 update + 404 missing + 422 reverse + no-publish on no-op | integration | `uv run pytest tests/line_provider/test_event_routes.py::TestUpdate -q` | W0 | pending |
| 2-07-03 | 07 | 3 | LP-04 | — | GET /event/{id} 200/404 | integration | `uv run pytest tests/line_provider/test_event_routes.py::TestGet -q` | W0 | pending |
| 2-07-04 | 07 | 3 | LP-05 | — | GET /events filters active | integration | `uv run pytest tests/line_provider/test_event_routes.py::TestList -q` | W0 | pending |
| 2-07-05 | 07 | 3 | LP-07 | — | GET /health 200 stub (deep-pings → P5) | integration | `uv run pytest tests/line_provider/test_health.py -q` | OK | pending |
| 2-07-06 | 07 | 3 | QA-04, QA-05 | — | Full suite green + coverage ≥85% on line_provider domain | shell | `uv run pytest --cov=src/line_provider --cov-report=term-missing` | W0 | pending |

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

- [x] `asgi-lifespan>=2.1,<3` added to dev-dependencies (line-provider package) — required so `httpx.AsyncClient(transport=ASGITransport)` actually triggers FastAPI lifespan and populates `app.state.event_store` / `app.state.event_bus` (R from RESEARCH.md §1).
- [x] `tests/line_provider/conftest.py` — upgraded the P1 `client` fixture in place: split into `app` + `client` fixtures, `app` wraps `LifespanManager(app)`, `client` consumes `app` via `AsyncClient(transport=ASGITransport(app), base_url="http://test")`. Tests can seed/inspect `app.state.event_store` via the `app` fixture without private `_transport` access.
- [x] REQUIREMENTS.md sync: LP-02 `event_id` type `str` → `UUID4` (D-05 override; matches CONTEXT.md and ARCHITECTURE.md `paste-ready tree`).
- [x] pyproject `[tool.pytest.ini_options]` already declares `asyncio_mode = "auto"` (P1) — verified, no change.
- [x] pyproject `[tool.coverage.run]` declares `source = ["src/line_provider"]` + `branch = true`; `[tool.coverage.report]` carries `fail_under = 85` (line-provider scope only — bet-maker covers itself in P3/P4).

Bet-maker EventFinishedMessage создаётся в P3/P5 — UUID уже зафиксирован в D-05, drift невозможен (преждевременная правка bet-maker schemas/messages.py снята из Wave 0).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OpenAPI schema renders all 4 routes with correct request/response models in Swagger UI | LP-01..LP-05, LP-07 | Visual confirmation that examples / status codes render the way the reviewer will see them; automated schema-snapshot is overkill for a test task | `docker compose up line-provider`, открыть `http://localhost:8000/docs`, проверить 4 роута + /health, статусы, схемы запросов/ответов |
| 422 error body for reverse transition is human-readable (not raw `TransitionForbiddenError`) | LP-05 | Asserts UX of error message; integration test asserts status code, this asserts message shape | После предыдущего шага: POST `/event` (создать NEW), затем POST с тем же id и `state=NEW` после перевода в FINISHED_WIN — body должен содержать `"detail"` с понятной строкой |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (asgi-lifespan dev-dep + REQUIREMENTS.md sync + conftest fixtures)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-14 by gsd-planner Phase 2
