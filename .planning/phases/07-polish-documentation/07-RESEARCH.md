# Phase 7: Polish + Documentation — Research

**Researched:** 2026-05-18
**Domain:** Documentation polish, OpenAPI/AsyncAPI metadata, CI coverage gate, mypy strict cleanup, static-audit testing
**Confidence:** HIGH

## Summary

Phase 7 is a non-functional polish pass. **No new runtime code, no new migrations, no new dependencies.** Everything boils down to six concrete deliverables: (1) full README revision in Russian with ASCII architecture diagram + reviewer curl walkthrough + Reliability narrative; (2) OpenAPI metadata polish on both FastAPI services (route `summary`, `responses` with a per-service `ErrorDetail` model, `Body(openapi_examples=...)`); (3) verification that FastStream's default `/asyncapi` endpoint is exposed on both `bet-maker` (consumer) and `line-provider` (publisher); (4) `mypy --strict` final pass — codebase already has zero `# type: ignore` in `src/`, so this is a verification-only step; (5) extending the CI pytest step with `--cov --cov-fail-under=85 --cov-report=xml --cov-report=term-missing` plus a static Shields.io coverage badge in README; (6) `07-AUDIT.md` artefact codifying the 18-item "Looks Done But Isn't" checklist with `Evidence | Status` columns, automated where feasible via a new `tests/audit/test_static.py` (regex-on-`Path.read_text()`, no AST module needed).

The research found **zero `# type: ignore` instances anywhere under `src/`** [VERIFIED: grep -rn] — so QA-01 polish is genuinely a "confirm CI is green" task, not a cleanup task. The FastStream `/asyncapi` endpoint is registered automatically when `RabbitRouter` is passed to `app.include_router(router)` at the default path `/asyncapi`; no override needed [CITED: faststream docs via Context7]. FastAPI `openapi_examples` is the named-example variant of `Body(...)` that powers Swagger UI dropdowns; the syntax is stable across FastAPI 0.111+ [CITED: fastapi/fastapi docs]. `pytest --cov` (no argument) picks up `[tool.coverage.run] source = [...]` from `pyproject.toml` automatically [CITED: pytest-cov docs] — our existing `["src/line_provider", "src/bet_maker"]` config means we do not need to repeat sources on the CLI.

**Primary recommendation:** Sequence the phase as: (1) sync-task → (2) ErrorDetail schemas + OpenAPI polish on routes → (3) `tests/audit/test_static.py` with regex checks → (4) CI pytest step extension + coverage badge → (5) `07-AUDIT.md` table + manual-verification commands → (6) README final pass with ASCII diagram and curl walkthrough. mypy and AsyncAPI verification fall out as zero-edit confirmation steps once the OpenAPI polish lands. Plan ordering matches Phase 6's "doc-sync first, fix-up last" cadence.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**README structure (DOC-01..04)**

- **D-01:** README — **single Russian primary**. Соответствует стилю `.planning/`-документации, `CLAUDE.md` constraints, и memory `feedback_verify_against_tz` (ТЗ — русский). Технические термины (FastAPI, RabbitMQ, mypy, pytest и т.п.) — без перевода.
- **D-02:** README sections (фиксированный порядок):
  1. Заголовок + 2 badge (CI + coverage) + 1-2 абзаца описания
  2. **Quick start** — расширение существующего блока
  3. **Reviewer walkthrough** — новый блок, copy-paste curl-сценарий happy-path (создать event → bet → finish → assert WON)
  4. **Architecture** (DOC-02) — ASCII-диаграмма + слои + RMQ-топология + ссылка на ARCHITECTURE.md
  5. **Reliability** (DOC-04) — Core Value + эшелонированные защиты + CANCELLED-extension абзац + ссылка на PITFALLS.md
  6. **Development** (DOC-03) — uv / migrations / pytest / linters / pre-commit
  7. **Next-step extensions** — TTL cache (P4 deferred), metrics, AsyncAPI snapshot — одной строкой каждый
  8. **Project status** — обновлённая таблица 7/7 phases complete
- **D-03:** ASCII-диаграмма в Architecture section — inline, не SVG (см. CONTEXT.md для каркаса; 6 стрелок: LP↔reviewer, LP→RMQ, RMQ→BM, BM→PG, BM→LP reconciler, RMQ→DLX).
- **D-04:** **Reviewer walkthrough** — copy-paste-последовательность из 5 шагов (`docker compose up -d` → `POST /event` → `POST /bet` → `PUT /event/{id}` со state=FINISHED_WIN → `GET /bets` показывает `WON`).
- **D-05:** **Reliability section narrative (DOC-04)** — список из 6 пунктов (durable queue, manual ack, FOR UPDATE SKIP LOCKED, DLX/DLQ + bounded retries, reconciler defence-in-depth, lifespan order + SIGTERM exec-form) со ссылками на source-файлы. Завершается абзацем про CANCELLED extension (Phase 6 D-25, REQUIREMENTS BM-05).

**OpenAPI metadata polish (QA visibility)**

- **D-06:** На уровне `FastAPI(...)` обоих сервисов: добавить `description` (одно предложение). `title` и `version` уже есть. `contact` / `license_info` — опционально / Claude's discretion.
- **D-07:** На уровне роутов — `summary="..."` + `responses={...}` с явными status-code → `{"model": ErrorDetail, "description": "..."}`.
  - line-provider: `POST/PUT /event` → 422 (HTTPValidationError default), `PUT/GET /event/{id}` → 404 (ErrorDetail).
  - bet-maker: `POST /bet` → 422 (ErrorDetail для EventNotBettable / Pydantic 422) + 503 (ErrorDetail для LineProviderUnavailable); `GET /bet/{bet_id}` → 404 (ErrorDetail); `GET /events` → 503 (ErrorDetail).
- **D-08:** `Body(..., openapi_examples=...)` на `POST /bet`, `POST /event`, `PUT /event/{event_id}`. Использовать Pydantic v2 / FastAPI `openapi_examples` синтаксис (named example groups: `{"happy": {"summary": ..., "value": {...}}}`).
- **D-09:** **`ErrorDetail` Pydantic schema** — единый `class ErrorDetail(BaseModel): detail: str` на сервис в `src/{line_provider,bet_maker}/schemas/errors.py`. Дублируется между сервисами по аналогии с P5 D-28 (no cross-service imports). `model_config = ConfigDict(extra="forbid")` + `frozen=True` по существующей конвенции.

**AsyncAPI publication**

- **D-10:** FastStream `RabbitRouter` экспонирует `/asyncapi` по дефолту при `app.include_router(router)`. Phase 7 plan убеждается, что endpoint доступен на обоих сервисах; URL упоминается в README §Architecture одной строкой. Никаких ручных схем.
- **D-11:** AsyncAPI snapshot НЕ коммитим в репо. Endpoint достаточен. Опциональный offline-копирование (`curl :8001/asyncapi -o asyncapi.json`) упоминается в README §Next-step extensions одной строкой.

**mypy strict cleanup (QA-01)**

- **D-12:** Финальный pass: `uv run mypy src` zero errors. Audit `# type: ignore` в `src/`:
  - На критических путях (UoW, repositories, consumer handler, reconciler, interactors, schemas) — НЕ должно быть `# type: ignore`. Если найдётся — обосновать или убрать.
  - На границах фреймворков (FastAPI/FastStream dispatch) допускается с inline-комментарием.
- **D-13:** CI gate `uv run mypy src` уже на месте (P1 CI step). Никаких изменений pipeline'а.
- **D-14:** Phase 7 НЕ расширяет mypy на тесты — `disallow_untyped_defs = false` override остаётся.

**Coverage gate (QA-09)**

- **D-15:** Заменить CI `uv run pytest -q` → `uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85`. CLI-флаг `--cov-fail-under=85` дублирует `[tool.coverage.report] fail_under = 85`, страхует от случайных правок pyproject.
- **D-16:** Coverage badge — статический Shields.io URL вида `https://img.shields.io/badge/coverage-85%25-brightgreen.svg`. Никакого codecov/coveralls. Ручной апдейт badge'а, если планка изменится.
- **D-17:** `fail-under = 85` — выше ROADMAP-минимума 80, совпадает с текущим pyproject. Не поднимаем до 90.

**Audit (Looks Done But Isn't, ROADMAP P7 SC#6)**

- **D-18:** Отдельный артефакт `07-AUDIT.md` в `.planning/phases/07-polish-documentation/` — таблица 19 строк (заголовок + 18 items): `Item | Evidence | Status | Notes`. `Status ∈ {verified, fix-applied, waived}`. Ноль `waived` без письменного обоснования.
- **D-19:** `tests/audit/test_static.py` — новый, статические grep/regex-проверки (см. ниже список из 7 тестов). Стиль regex-on-`Path.read_text()` (Claude's discretion: AST — overkill).
- **D-20:** Manual-only items (`docker compose down` exit-code, `docker volume ls`, `rabbitmqctl list_queues durable=true` или RMQ Management UI screenshot, Decimal exact roundtrip — последнее уже покрыто P3 integration-тестом `test_bet_routes.py::TestPostBet201`) — командой + ожидаемый output в AUDIT.md.
- **D-21:** Idempotency consumer (item #2) — уже покрыто P5 e2e (`test_e2e_rabbitmq.py`); AUDIT ссылается без новых тестов.
- **D-22:** Reconciler dies-silently (item #3) — уже покрыто P6 `test_reconciler_tick.py` + `/health` 503 при `task.done()`; AUDIT ссылается на конкретные test-id.

**Sync-task (Plan 07-01)**

- **D-23:** Первый план Phase 7 — sync-task (паттерн P2 02-01, P3 03-01, P4 04-01, P5 05-10, P6 06-01) — сверка REQUIREMENTS / ROADMAP / README против `./Тестовое задание Middle Python developer.pdf`. Не всегда заканчивается правкой; всегда выполняется. Ожидается no-op (drift'ов после P6 не должно быть).

### Claude's Discretion

- Точный URL Shields.io для coverage badge (статический vs query-параметризованный).
- Расположение `ErrorDetail` schema (`schemas/errors.py` vs inline).
- Стиль AST-чеков в `tests/audit/test_static.py` (Python `ast` модуль vs regex через `Path.read_text()`). **Recommendation: regex** — for test-task scope AST overkill.
- Финальный nameplate badges в README (1 vs 2 vs 3). **Recommendation: 2 (CI + coverage).**
- Точное количество запросов в Reviewer walkthrough (5 vs 6). **Recommendation: 5 (create / bet / finish / sleep / get-bets).**
- Размер ASCII-диаграммы (minimal vs detailed). **Recommendation: medium — PG/RMQ + main flow + DLX/DLQ + reconciler arrow.**

### Deferred Ideas (OUT OF SCOPE)

- **TTL cache `GET /events`** — отложено в P4 D-01. README §Next-step extensions упоминает одной строкой.
- **Codecov / Coveralls** — overkill. Static Shields.io badge достаточен.
- **AsyncAPI snapshot в репо** (`docs/asyncapi.json`) — endpoint достаточен; offline-копия — opt-in одной curl-командой в README §Next-step extensions.
- **English README** — single Russian primary.
- **Prometheus / OpenTelemetry / Grafana** — v2 OBS-01..03.
- **`Idempotency-Key` / API versioning / Rate limiting / RFC7807** — v2 API-01..04.
- **Quorum queues / Outbox / Saga** — v2 REL-01..03.
- **Multi-region / Kubernetes / Helm-charts**.
- **mypy strict на тестах** — `disallow_untyped_defs = false` override остаётся.
- **EventState parity test** между `line_provider/schemas/events.EventState` и `bet_maker/schemas/events.EventState` — уже покрыто через `EventFinishedMessage.new_state` parity (P5 D-29). Опционально nice-to-have.
- **README на отдельной branch / docs/ subdir с MkDocs** — overkill.
- **`pyproject.toml requires-python` расширение до 3.11** — `<3.11` зафиксировано CLAUDE.md.
- **Удаление `# type: ignore` со scope сверх критических путей** — pragmatic balance, тесты как есть.
- **Новые рантайм-фичи** (routes / interactors / статусы).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOC-01 | README.md с описанием системы, диаграммой компонентов, инструкцией запуска через `docker compose up` | Расширение текущего README (см. §Code Examples → README skeleton); ASCII-диаграмма + curl walkthrough — D-03 / D-04 |
| DOC-02 | Раздел «Architecture» — слои, UoW, RabbitMQ топология, reconciliation, ссылка на ARCHITECTURE.md | 6-stroke ASCII-диаграмма + текстовое описание layered architecture; ссылка на `.planning/research/ARCHITECTURE.md` |
| DOC-03 | Раздел «Development» — uv install, миграции, запуск тестов, линтеров | Текущий README §Development уже содержит большую часть — небольшая правка/расширение |
| DOC-04 | Раздел «Reliability» — описание гарантий доставки и защиты от «зависших» ставок | D-05 — 6-пунктный эшелонированный список + CANCELLED-extension абзац; ссылки на source-файлы и PITFALLS.md |
| QA-01 | `mypy --strict` без ошибок | Уже зелёный в CI; в `src/` ноль `# type: ignore` ([VERIFIED: grep -rn]); финальный аудит-pass |
| QA-09 | pytest-cov с минимальным порогом покрытия (≥80%) | D-15: расширение CI pytest step `--cov --cov-fail-under=85 --cov-report=xml --cov-report=term-missing`; D-16: статический Shields.io badge |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| README content (markdown) | Repo root | — | Single artefact at `./README.md`; consumed by GitHub web UI + reviewer terminal |
| ASCII architecture diagram | README §Architecture | `.planning/research/ARCHITECTURE.md` | High-level overview in README; detailed topology in research/ |
| OpenAPI route metadata | FastAPI route decorators (`@router.{post,get,put}`) | Pydantic `ErrorDetail` schemas per service | `summary`/`responses`/`Body(openapi_examples=...)` live on the decorator; error model lives in `schemas/errors.py` |
| OpenAPI app metadata | `src/{line_provider,bet_maker}/app.py::build_app` | — | `FastAPI(title=, description=, version=)` |
| AsyncAPI documentation | FastStream `RabbitRouter` default `/asyncapi` endpoint | — | Auto-generated; no separate schema source |
| CI coverage gate | `.github/workflows/ci.yml` pytest step + `pyproject.toml [tool.coverage.*]` | Shields.io static badge in README | CLI flag enforces gate; pyproject configures sources; badge is hardcoded markdown URL |
| Static audit tests | `tests/audit/test_static.py` (new) | `Dockerfile`, `docker-compose.yml`, `src/bet_maker/{entrypoints/messaging.py,repositories/bets.py,infrastructure/db/engine.py}` (read-only) | New isolated test package; reads files via `Path.read_text()` and asserts regex/substring matches |
| Audit artefact | `.planning/phases/07-polish-documentation/07-AUDIT.md` (new) | — | Markdown table mapping 18 items → Evidence | Status; lives in phase dir by convention |
| mypy strict verification | CI step `uv run mypy src` (existing) | — | Already enforced from P1; Phase 7 confirms zero `# type: ignore` on critical paths |

## Standard Stack

### Core (no new libraries — all already declared in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.115,<0.137 (currently 0.136.x) | OpenAPI metadata (`description`, `summary`, `responses`, `Body(openapi_examples=...)`) | Already in deps; native `openapi_examples` parameter on `Body()` since 0.103 [CITED: fastapi/fastapi/docs/en/docs/tutorial/schema-extra-example.md] |
| FastStream | >=0.6,<0.7 (currently 0.6.7) | AsyncAPI auto-publication via `RabbitRouter` `/asyncapi` endpoint | Already in deps; default `schema_url='/asyncapi'` when registered on FastAPI app [CITED: faststream docs/getting-started/integrations/fastapi/index.md via Context7] |
| Pydantic | >=2.13,<3 | `ErrorDetail(BaseModel)` schema | Already in deps; consistent with existing `BetRead`/`EventRead` pattern |
| pytest-cov | >=7.1,<8 (dev-dep) | Coverage gate in CI | Already in dev-deps; bare `--cov` (no argument) picks up `[tool.coverage.run] source` from pyproject [CITED: pytest-dev/pytest-cov/docs/config.md] |
| mypy | >=2.1,<3 (dev-dep) | Strict type check, zero errors | Already enforced in CI from P1 |

**No new dependencies needed.** Shields.io is just a URL in README — no library install.

**Version verification (against `pyproject.toml`):**
- All pinned ranges match the recommended stack from `CLAUDE.md`.
- `[CITED: shields.io docs/static-badges]` — static badge URL pattern `https://img.shields.io/badge/<label>-<message>-<color>.svg`. `%25` URL-encodes `%`.

### Supporting (unchanged)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.5.x | Existing JSON logging; audit item references | No changes; audit test grep verifies `clear_contextvars()` in middleware/consumer |
| tenacity | 9.1.x | Existing retry decorators in consumer + reconciler; no changes | No new uses in P7 |

### Development Tools (unchanged)

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| uv | 0.11.14 | CI workflow runs uv sync --frozen | No change |
| ruff | 0.15.x | Lint + format | No change |
| pre-commit | 4.6.x | Git hooks | No change |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Shields.io static badge | Codecov / Coveralls dynamic badge | Codecov requires service registration, repo token, push from CI — overkill for test-task. **Locked: Shields.io (D-16).** |
| `Path.read_text()` + regex in `tests/audit/test_static.py` | Python `ast` module + visitor | AST is robust against formatting drift but overkill for static literal `kwarg=Constant`-style checks. **Locked: regex (D-19 / Claude's discretion).** |
| Hand-curated AsyncAPI snapshot in `docs/` | FastStream auto-generated `/asyncapi` endpoint | Hand-curation drifts and adds maintenance burden. **Locked: endpoint-only (D-10/D-11).** |
| English README | Russian README | Reviewer language is Russian; all other `.planning/` docs are Russian. **Locked: Russian (D-01).** |
| mypy strict on tests | mypy strict on `src/` only | Tests use a lot of pytest plumbing (fixtures, monkeypatch) that adds ignore noise without revealing real bugs. **Locked: `src/` only (D-14).** |

**Installation:** No installs needed — all libraries already declared in `pyproject.toml` and pinned in `uv.lock`.

## Architecture Patterns

### System Architecture Diagram

```
                  HTTP (reviewer curl)
                    |
                    v
+----------------+   POST/PUT/GET   +----------------+
| reviewer cli   | ---------------> | line-provider  |
+----------------+                  |    :8000       |
                                    |  (in-memory)   |
                                    +-------+--------+
                                            | AMQP publish
                                            | exchange: bsw.events
                                            | routing: event.finished.{win|lose}
                                            v
                                    +----------------+
                                    |   RabbitMQ     | --(x-dead-letter-exchange)--> DLX -> DLQ
                                    |   :5672        |   bsw.events.dlx
                                    +-------+--------+   bet_maker.events.finished.dlq
                                            | AMQP consume
                                            | queue: bet_maker.events.finished
                                            | manual ack, prefetch=10
                                            v
+----------------+   POST/GET /bet  +----------------+   FOR UPDATE     +----------------+
| reviewer cli   | ---------------> |   bet-maker    | SKIP LOCKED      |  PostgreSQL    |
+----------------+                  |    :8001       | ---------------> |    :5432       |
                                    | + reconciler   |   SELECT/UPDATE  |   (bsw DB)     |
                                    +-------+--------+                  +----------------+
                                            | HTTP GET /event/{id}
                                            | (reconciler defence-in-depth)
                                            +-----> line-provider
```

Six strokes (per D-03): reviewer→LP, LP→RMQ (publish), RMQ→BM (consume), RMQ→DLX/DLQ, BM→PG (read/write with SKIP LOCKED), BM→LP (reconciler HTTP poll).

**Component responsibilities:**

| Component | File / Location | Responsibility |
|-----------|------------------|----------------|
| `line-provider` API | `src/line_provider/entrypoints/api/{events,health}.py` | CRUD for events + health |
| `line-provider` store | `src/line_provider/infrastructure/store/in_memory.py` | In-memory dict guarded by `asyncio.Lock` |
| `line-provider` publisher | `src/line_provider/{entrypoints/messaging.py, facades/event_bus.py}` | `RabbitRouter` + `RabbitEventBus` facade; publishes on state transition |
| `bet-maker` API | `src/bet_maker/entrypoints/api/{bets,events,health}.py` | `POST /bet`, `GET /bets`, `GET /bet/{id}`, `GET /events` (proxy), `GET /health` |
| `bet-maker` UoW + Repo | `src/bet_maker/{facades/uow.py, repositories/bets.py}` | Transactional boundary; `with_for_update(skip_locked=True)` for idempotency |
| `bet-maker` consumer | `src/bet_maker/entrypoints/messaging.py` | `RabbitRouter` subscriber with `AckPolicy.MANUAL`, DLX wiring, bounded transient retries |
| `bet-maker` reconciler | `src/bet_maker/jobs/reconciler.py` | asyncio background task, polls LP via httpx, settles or cancels PENDING bets |
| AsyncAPI endpoint | `/asyncapi` on both services | FastStream auto-generated; documents AMQP contract |

### Recommended Project Structure (unchanged from P1-P6 + 2 new files)

```
src/
├── line_provider/
│   ├── app.py                       # +description= on FastAPI(...)        [D-06]
│   ├── schemas/
│   │   └── errors.py                # NEW: ErrorDetail                     [D-09]
│   └── entrypoints/api/
│       ├── events.py                # +summary= +responses= +Body(...)     [D-07..D-08]
│       └── health.py                # +summary=
├── bet_maker/
│   ├── app.py                       # +description=                         [D-06]
│   ├── schemas/
│   │   └── errors.py                # NEW: ErrorDetail (duplicate per D-09) [D-09]
│   └── entrypoints/api/
│       ├── bets.py                  # +summary= +responses= +Body(...)     [D-07..D-08]
│       ├── events.py                # +summary= +responses=                 [D-07]
│       └── health.py                # +summary=
tests/
├── audit/                           # NEW directory
│   ├── __init__.py                  # NEW
│   └── test_static.py               # NEW: 7 regex/string-match tests       [D-19]
.planning/phases/07-polish-documentation/
├── 07-AUDIT.md                      # NEW: 18-item checklist table          [D-18]
├── 07-CONTEXT.md                    # exists
├── 07-DISCUSSION-LOG.md             # exists
└── 07-RESEARCH.md                   # this file
.github/workflows/
└── ci.yml                           # extend pytest step                    [D-15]
README.md                            # full rewrite per D-02
```

### Pattern 1: FastAPI Route OpenAPI Polish

**What:** Each route gets `summary`, `description` (existing docstrings), `responses` (per-status `ErrorDetail` model), and `Body(openapi_examples=...)` on POST/PUT bodies.

**When to use:** Apply to every route on both services (LP: 4 routes + health; BM: 5 routes + health).

**Example:**

```python
# Source: fastapi/docs/en/docs/tutorial/schema-extra-example.md (Context7)
# Source: fastapi/docs/en/docs/advanced/additional-responses.md (Context7)

from fastapi import APIRouter, Body, HTTPException, status
from bet_maker.schemas.bets import BetCreate, BetRead
from bet_maker.schemas.errors import ErrorDetail

router = APIRouter(tags=["bets"])

@router.post(
    "/bet",
    status_code=status.HTTP_201_CREATED,
    response_model=BetRead,
    summary="Place a bet on a bettable event",
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorDetail,
            "description": "Validation failure or event not bettable (deadline passed / event not found / event not active).",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorDetail,
            "description": "line-provider unreachable after retries (transient upstream failure).",
        },
    },
)
async def post_bet(
    body: BetCreate = Body(
        openapi_examples={
            "happy": {
                "summary": "Place a valid bet",
                "description": "Successful placement on a NEW, non-expired event.",
                "value": {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "amount": "10.00",
                },
            },
            "bad_decimal": {
                "summary": "Invalid amount — too many decimal places",
                "value": {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "amount": "10.123",
                },
            },
        },
    ),
    uow: UoWDep = ...,
    event_lookup: EventLookupDep = ...,
) -> BetRead:
    ...
```

Note: `openapi_examples` (Pydantic v2 / FastAPI ≥0.103) is the **named-example dict** variant that powers Swagger UI dropdowns; `examples=` (list) is the deprecated path-form-only variant. Always use `openapi_examples` for new code.

### Pattern 2: ErrorDetail Schema (Duplicated Per Service)

**What:** Minimal Pydantic model surfacing the `{"detail": "..."}` payload that FastAPI's `HTTPException` produces. Used in `responses={...}` declarations.

**When to use:** Per-service schema (D-09) — never cross-import (P5 D-28 / D-29 policy).

**Example:**

```python
# src/bet_maker/schemas/errors.py
# Source: existing pattern at src/bet_maker/schemas/bets.py (frozen + extra="forbid")

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """Standard error envelope for FastAPI HTTPException responses.

    Used in `responses={...}` route declarations so Swagger UI shows
    the exact JSON shape under 4xx/5xx branches. Mirrors FastAPI's
    default `{"detail": "..."}` payload.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    detail: str
```

Duplicate verbatim to `src/line_provider/schemas/errors.py`. No cross-imports between services.

### Pattern 3: FastStream `/asyncapi` Endpoint Verification

**What:** Confirm that `app.include_router(router)` exposes `/asyncapi` automatically on both services.

**When to use:** Read-only verification step.

**Example:**

```python
# Source: faststream/docs/docs/en/getting-started/integrations/fastapi/index.md (Context7)

# Default — already correct in our codebase:
router = RabbitRouter(str(_settings.rabbitmq_url))   # /asyncapi at default URL

# If overriding (NOT needed for us):
router = RabbitRouter(
    str(_settings.rabbitmq_url),
    schema_url="/asyncapi",   # default
    include_in_schema=True,    # default
)
```

Both services in our codebase use the default constructor (no `schema_url` override) — verified by `grep "RabbitRouter(" src/` [VERIFIED]. **Plan only needs to add an `app.include_router(router)` smoke test that hits `GET /asyncapi` and asserts 200 + valid JSON.**

### Pattern 4: Coverage Gate Configuration

**What:** Extend the CI pytest step to enforce coverage; rely on `[tool.coverage.run] source = [...]` in `pyproject.toml` for source filtering.

**Example:**

```yaml
# .github/workflows/ci.yml — Pytest step (D-15)
- name: Pytest
  run: uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85
```

```toml
# pyproject.toml — unchanged from P3 (already in place)
[tool.coverage.run]
source = ["src/line_provider", "src/bet_maker"]
branch = true

[tool.coverage.report]
fail_under = 85
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

**Verified [CITED: pytest-dev/pytest-cov/docs/config.md]:** `--cov` (no argument) honours `[tool.coverage.run] source`. Passing `--cov=<package>` would override `source` — don't.

`--cov-fail-under=85` on CLI is a belt-and-braces measure: it overrides `[tool.coverage.report] fail_under`, but both being `85` means there's no surprise. Explicit CLI flag also makes the threshold visible in green/red CI output.

`--cov-report=xml` writes `coverage.xml` to repo root (default name) — useful artifact for future codecov integration, but currently unused. Keeping it free-of-charge.

### Pattern 5: Static Audit Test (Regex-Based)

**What:** New `tests/audit/test_static.py` with file-content assertions.

**When to use:** For each "Looks Done But Isn't" item that can be verified by string match.

**Example:**

```python
# tests/audit/test_static.py
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

# --- Manual ack -----------------------------------------------------------
def test_subscribers_have_manual_ack() -> None:
    """Every @router.subscriber(...) must set ack_policy=AckPolicy.MANUAL."""
    src = (SRC / "bet_maker" / "entrypoints" / "messaging.py").read_text()
    subscribers = re.findall(
        r"@router\.subscriber\((?P<args>.*?)\)\s*\n?async def",
        src,
        re.DOTALL,
    )
    assert subscribers, "no @router.subscriber found — wrong file?"
    for args in subscribers:
        assert "ack_policy=AckPolicy.MANUAL" in args, (
            f"subscriber missing ack_policy=AckPolicy.MANUAL:\n{args}"
        )

# --- FOR UPDATE SKIP LOCKED -----------------------------------------------
def test_repositories_use_for_update_skip_locked() -> None:
    src = (SRC / "bet_maker" / "repositories" / "bets.py").read_text()
    assert "with_for_update(skip_locked=True)" in src

# --- expire_on_commit=False -----------------------------------------------
def test_async_sessionmaker_expire_on_commit_false() -> None:
    src = (SRC / "bet_maker" / "infrastructure" / "db" / "engine.py").read_text()
    assert re.search(
        r"async_sessionmaker\([^)]*expire_on_commit=False",
        src,
        re.DOTALL,
    )

# --- Dockerfile exec-form CMD --------------------------------------------
def test_dockerfile_exec_form_cmd() -> None:
    src = (REPO_ROOT / "Dockerfile").read_text()
    # CMD ["..."] is exec form. CMD python ... (no brackets) is shell form — bad.
    cmd_lines = [line for line in src.splitlines() if line.strip().startswith("CMD")]
    assert cmd_lines, "Dockerfile has no CMD"
    for line in cmd_lines:
        assert re.match(r"\s*CMD\s*\[", line), f"non-exec-form CMD: {line!r}"

# --- python:3.10-slim-bookworm pinned ------------------------------------
def test_dockerfile_pinned_python_bookworm() -> None:
    src = (REPO_ROOT / "Dockerfile").read_text()
    assert "3.10-slim-bookworm" in src, "must pin -bookworm, not rolling -slim"

# --- PYTHONUNBUFFERED=1 ---------------------------------------------------
def test_pythonunbuffered_set() -> None:
    src = (REPO_ROOT / "Dockerfile").read_text()
    assert re.search(r"PYTHONUNBUFFERED\s*=\s*1", src)

# --- Durable queue + exchange --------------------------------------------
def test_durable_queue_and_exchange_args() -> None:
    src = (SRC / "bet_maker" / "entrypoints" / "messaging.py").read_text()
    # RabbitQueue(..., durable=True, ...)
    queue_calls = re.findall(r"RabbitQueue\((?P<args>.*?)\)", src, re.DOTALL)
    assert queue_calls, "no RabbitQueue() call found"
    for args in queue_calls:
        assert "durable=True" in args, f"RabbitQueue missing durable=True:\n{args}"
    # RabbitExchange(..., durable=True, ...)
    exchange_calls = re.findall(r"RabbitExchange\((?P<args>.*?)\)", src, re.DOTALL)
    assert exchange_calls, "no RabbitExchange() call found"
    for args in exchange_calls:
        assert "durable=True" in args, f"RabbitExchange missing durable=True:\n{args}"
```

**False-positive avoidance:**
- All regex anchored on the actual call form found in source (verified by reading the files in research step).
- `re.DOTALL` lets `.` match newlines for multi-line decorator args.
- Test asserts non-empty matches first (`assert subscribers`) — catches "file moved/renamed" silently breaking the test.
- Hardcoded paths via `Path(__file__).resolve().parents[2]` — no env-dependent CWD.
- Per CLAUDE.md "no emojis" — test assertion messages use plain ASCII.

**Items not automated** (left to manual verification in AUDIT.md):
- `docker compose down` exit-code 0 in <5s — requires Docker daemon; recorded as `$ docker compose down → expected exit 0` command + Notes column.
- `docker volume ls` shows `bsw_postgres_data` + `bsw_rabbitmq_data` — requires Docker; recorded as command.
- RabbitMQ Management UI shows DLQ message — requires running broker; recorded as URL + screenshot reference.
- Decimal exact roundtrip — already covered by P3 integration test `tests/bet_maker/test_bet_routes.py::TestPostBet201`; AUDIT references test path + nodeid.

### Anti-Patterns to Avoid

- **Hand-curating AsyncAPI schema** in `docs/asyncapi.json` — drifts from FastStream introspection. Use `/asyncapi` endpoint only.
- **`--cov=<package>` on CLI** — overrides `[tool.coverage.run] source`, defeats single-source-of-truth. Use bare `--cov`.
- **Adding `# type: ignore` to silence mypy in P7** — defeats the polish-pass purpose. If mypy complains, fix the root cause or accept a documented framework-boundary exception (D-12).
- **Importing across services** (e.g., `from line_provider.schemas.errors import ErrorDetail` inside `bet_maker/`) — violates P5 D-28 / D-29 duplication policy. Duplicate the schema.
- **Codecov / Coveralls integration** — out of scope per D-16; adds maintenance cost without value for test-task.
- **AST module for static audit tests** — overkill for regex-detectable literal kwarg checks (D-19 Claude's discretion → regex).
- **`docker compose down -v`** in audit commands — would wipe volumes; just `docker compose down` for SIGTERM verification (avoid R10).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AsyncAPI schema generation | Hand-written YAML | FastStream `RabbitRouter` `/asyncapi` endpoint | Auto-generated from decorators; zero maintenance; updates with code [CITED: faststream docs] |
| Coverage badge with live data | Codecov / Coveralls / custom shields endpoint | Static Shields.io URL | Static badge has zero infrastructure cost; live tracking is overkill for test-task (D-16) |
| OpenAPI 422 error model | Hand-crafted `HTTPValidationError` Pydantic schema | FastAPI's built-in `HTTPValidationError` (auto-loaded for 422) | FastAPI auto-registers it; for non-422 errors use our `ErrorDetail` |
| Per-service example data factory | Custom factory in `tests/conftest.py` for OpenAPI examples | Hardcoded UUID/Decimal literals from existing test fixtures | Examples are static documentation; complexity has no payoff |
| Audit static-test AST visitor | Custom `ast.NodeVisitor` subclass for kwarg matching | `re.findall` + substring `in` checks | Regex sufficient for literal kwarg-value detection; AST adds complexity (D-19 Claude's discretion) |
| Manual AsyncAPI snapshot generator | A script + CI step that curls `/asyncapi` and commits the JSON | Just reference the live endpoint in README | Snapshot drifts unless CI re-generates on every push — overkill (D-11) |

**Key insight:** Phase 7 is **polish, not engineering.** Every "should we build X" answer is "no — link to the live endpoint / use a static URL / reference an existing artefact." The plan stays small precisely because we resist hand-rolling.

## Runtime State Inventory

Phase 7 has **no rename / refactor / migration** scope. No new strings replace old strings; no service config keys change; no databases or registries hold names that need rewriting. The Sync-task (D-23) verifies REQUIREMENTS/ROADMAP/README against the TZ PDF — pure read-side drift check.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no schema changes, no data migrations, no enum value changes | None |
| Live service config | None — no broker/topology changes (existing exchange `bsw.events` + queue `bet_maker.events.finished` + DLX `bsw.events.dlx` + DLQ `bet_maker.events.finished.dlq` unchanged) | None |
| OS-registered state | None — Docker container names / volumes / network unchanged | None |
| Secrets / env vars | None — `LINE_PROVIDER_*` and `BET_MAKER_*` env keys unchanged | None |
| Build artifacts | None — no `pyproject.toml` rename, no package rename, no Dockerfile structural change | None |

**Sync-task drift check (D-23):** Phase 7 Plan 07-01 reads the TZ PDF and sweeps REQUIREMENTS.md (BM-05 CANCELLED extension), ROADMAP.md (Phase 7 SC#1..6), and README.md (current draft). Expected outcome: **no-op** (Phase 6 D-25 already locked the BM-05 CANCELLED-extension wording).

## Common Pitfalls

### Pitfall 1: openapi_examples vs examples (FastAPI API change)
**What goes wrong:** Use `examples=[...]` (list) on `Body(...)`, get a JSON-Schema-level array of examples that Swagger UI does NOT render as a dropdown.
**Why it happens:** FastAPI 0.103 introduced `openapi_examples=` (dict, named) as the Swagger-friendly variant; the old `examples=` (list) still works for OpenAPI schema but lacks UI affordance.
**How to avoid:** Always use `openapi_examples={"happy": {"summary":..., "value":...}, "bad_decimal": {...}}` (dict) for new code. **Locked: D-08 → `openapi_examples`.**
**Warning signs:** Swagger UI shows a single example block instead of a dropdown.

### Pitfall 2: pytest --cov=<package> silently overrides pyproject source
**What goes wrong:** CI runs `uv run pytest --cov=src/bet_maker tests/`; coverage report doesn't include `line_provider`. Phase 5/6 tests appear to "fail to cover" code they never imported.
**Why it happens:** Per pytest-cov docs [CITED]: if `--cov=<source>` is passed, it overrides `[tool.coverage.run] source`. Multi-package projects break silently.
**How to avoid:** Use **bare `--cov`** (no argument) — pytest-cov reads `source` from `pyproject.toml`. **Locked: D-15 CLI is `--cov` (no arg).**
**Warning signs:** Coverage report shows only one of the two packages.

### Pitfall 3: Coverage badge drifts from real number
**What goes wrong:** Static Shields.io URL shows "coverage 85%" while actual CI coverage is 89% (or 81%). README looks dishonest in either direction.
**Why it happens:** Static URL has no live link to coverage.xml.
**How to avoid:** Use a round-down floor matching `fail_under` (85% — D-16). The badge represents the **guaranteed minimum**, not the current measurement — note this explicitly in README §CI (one line: "coverage gate ≥85% enforced in CI"). Codecov/Coveralls is out of scope (D-16). **If badge drifts >10% above the floor, manually bump the static URL number.**
**Warning signs:** `pytest --cov-report=term` shows >90% but badge says 85.

### Pitfall 4: AsyncAPI endpoint not registered because router missing from include_router
**What goes wrong:** `app.include_router(rabbit_router)` was added in P5 D-25 — verify both services still call it. If line-provider's router is publisher-only (no subscribers), `/asyncapi` will be empty but **still exposed**.
**Why it happens:** AsyncAPI auto-registration is tied to `app.include_router(router)`; if commented out for debugging or routing extraction, the endpoint vanishes.
**How to avoid:** Plan adds a simple smoke test in `tests/audit/test_static.py` (or via existing integration test) that hits `GET /asyncapi` on both apps and asserts 200. Status: code already calls `app.include_router(rabbit_router)` in both `app.py` files [VERIFIED].
**Warning signs:** `curl :8001/asyncapi` returns 404.

### Pitfall 5: HTTPValidationError vs ErrorDetail mismatch in responses
**What goes wrong:** Declare `responses={422: {"model": ErrorDetail, ...}}` for a route that uses Pydantic body validation. The route actually returns FastAPI's auto-generated `HTTPValidationError` shape (`{"detail": [{"loc":..., "msg":..., "type":...}]}`), not the simple `{"detail": "..."}` from our `ErrorDetail`. Swagger UI now lies about the response shape.
**Why it happens:** FastAPI generates two different error shapes — pydantic-validation errors (auto-422 with list-of-issues) and `HTTPException(status_code=...)` calls (manual 422/503/404 with string detail).
**How to avoid:** Use `ErrorDetail` only for 4xx/5xx branches we raise manually via `HTTPException(status_code=..., detail="...")` (e.g., `LineProviderUnavailable → 503`, `EventNotBettable → 422`, `BetNotFound → 404`). For Pydantic-validation 422 (`amount=10.123`), let FastAPI's default `HTTPValidationError` flow through — **don't override the 422 response model** for those routes, or document both 422 cases with `{"model": HTTPValidationError | ErrorDetail}` if needed.
**Warning signs:** Swagger UI 422 example doesn't match actual response.

### Pitfall 6: tests/audit/test_static.py is fragile to formatting changes
**What goes wrong:** Regex `r"@router\.subscriber\((?P<args>.*?)\)\s*\n?async def"` fails when subscriber decorator is reformatted (e.g., black/ruff puts each kwarg on its own line with different indentation).
**Why it happens:** Regex is whitespace-sensitive; `re.DOTALL` helps but cannot anticipate every formatting decision.
**How to avoid:** Test on the **exact file content** during plan implementation — run `pytest tests/audit/test_static.py -v` before committing. Use `re.DOTALL` consistently. Anchor on stable substrings (e.g., `"ack_policy=AckPolicy.MANUAL"`) rather than full decorator structure.
**Warning signs:** Audit test fails after `ruff format` reformatting.

### Pitfall 7: mypy strict on tests breaks under fixture/monkeypatch noise
**What goes wrong:** Phase 7 inadvertently extends mypy to tests (`disallow_untyped_defs = true` for tests/). Pytest fixtures, monkeypatch overrides, and respx mocks need many `# type: ignore` to satisfy strict mode.
**Why it happens:** Tests intentionally use loose typing for fixture composition.
**How to avoid:** Keep the existing `[[tool.mypy.overrides]] module = ["tests.*"]; disallow_untyped_defs = false` block in `pyproject.toml` (D-14). Phase 7 audits `src/` only. **Pyproject is NOT modified in Phase 7.**
**Warning signs:** Phase 7 plan touches the `[tool.mypy]` block in pyproject.toml — STOP, the test override must stay.

### Pitfall 8: Reviewer walkthrough curl uses pretty-print and reviewer hits Ctrl-C
**What goes wrong:** README curl uses `| jq '.'` (pretty) but reviewer's host has no jq → command fails, reviewer abandons.
**Why it happens:** Tools-availability mismatch between author and reviewer.
**How to avoid:** Per D-04, walkthrough uses `| jq` only for the final `GET /bets` projection (the only step where shape clarity helps); first 4 steps use plain `curl -s -X ...`. README §Quick start can include a one-liner about `apt-get install jq` / `brew install jq` if needed.
**Warning signs:** N/A; mitigated by CONTEXT D-04 example.

### Pitfall 9: README badge shows a phantom OWNER/REPO placeholder
**What goes wrong:** Current README has `https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg` — Phase 7 polish forgets to swap in the real GitHub owner/repo.
**Why it happens:** Skeleton from P1 used placeholder.
**How to avoid:** Plan task explicitly addresses badge URL replacement — but only IF the reviewer expects to see live CI status. **For test-task delivery via zip / private fork, OWNER/REPO placeholder is acceptable; document this in the plan.** If repo will be published, the badge URL must be updated.
**Warning signs:** Badge in README points to a 404'd GitHub Actions page.

### Pitfall 10: Audit "Status=waived" without justification slips in
**What goes wrong:** AUDIT.md ends up with `waived` rows that just say "manual verification skipped" with no Notes content.
**Why it happens:** No enforced format — markdown tables don't validate cells.
**How to avoid:** D-18 explicit policy: zero `waived` without written justification in Notes column. Plan task includes a final review pass before AUDIT.md is committed. Optional: add `tests/audit/test_audit_completeness.py` that parses AUDIT.md, finds rows with `Status=waived`, and asserts non-empty Notes — but this is gold-plating; manual review is sufficient.
**Warning signs:** AUDIT.md PR shows `waived` rows with empty Notes.

## Code Examples

### README skeleton (target final state, Russian, no emojis)

```markdown
# BSW Betting System

[![ci](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)](https://github.com/OWNER/REPO)

Тестовое задание Middle Python developer: микросервисная система приёма ставок на спортивные события. Два асинхронных сервиса (`line-provider`, `bet-maker`), интеграция через RabbitMQ, история ставок в PostgreSQL, reconciliation как защита от потерянных сообщений.

**Core Value:** ставка никогда не остаётся в статусе PENDING после того, как событие завершилось.

Полная архитектура: [.planning/research/ARCHITECTURE.md](.planning/research/ARCHITECTURE.md). Каталог требований: [.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md). Каталог известных pitfalls: [.planning/research/PITFALLS.md](.planning/research/PITFALLS.md).

## Quick start

[существующий блок + RabbitMQ Management UI ссылка + AsyncAPI endpoints упоминание]

## Reviewer walkthrough

[5-step curl flow per D-04]

## Architecture

[ASCII диаграмма + слои + RMQ топология + ссылка на ARCHITECTURE.md + AsyncAPI endpoint URL]

## Reliability

[6-пунктный список защит per D-05 + CANCELLED extension абзац]

## Development

[существующий блок]

## Next-step extensions

- TTL cache `GET /events` — отложено (P4 D-01).
- Prometheus / OpenTelemetry / Grafana — v2 OBS-01..03.
- AsyncAPI snapshot offline — `curl :8001/asyncapi -o asyncapi.json`.

## Project status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Skeleton + Infrastructure | complete |
| 2 | line-provider domain | complete |
| 3 | bet-maker domain (DB) | complete |
| 4 | bet-maker HTTP integration | complete |
| 5 | RabbitMQ integration | complete |
| 6 | Reconciliation job | complete |
| 7 | Polish + Documentation | complete |
```

### 18-Item "Looks Done But Isn't" → Evidence Map

This is the source-of-truth mapping the planner uses to populate `07-AUDIT.md`. Items numbered as in `.planning/research/PITFALLS.md` §«Looks Done But Isn't».

| # | Item | Evidence | Automation | Initial Status |
|---|------|----------|------------|----------------|
| 1 | Manual ack on every `@router.subscriber(...)` | `src/bet_maker/entrypoints/messaging.py:120-132` (`ack_policy=AckPolicy.MANUAL`); `await msg.ack()` after `async with uow:` at `:175` | `tests/audit/test_static.py::test_subscribers_have_manual_ack` | verified |
| 2 | Idempotency on consumer redelivery | `tests/bet_maker/test_e2e_rabbitmq.py` (P5 e2e — concurrent settle / redelivery) | existing test | verified |
| 3 | Reconciler loop body `try/except Exception:` | `src/bet_maker/jobs/reconciler.py` — wrapped per P6 D-13; tested in `tests/bet_maker/jobs/test_reconciler_tick.py::test_tick_exception_isolation` | existing test | verified |
| 4 | `FOR UPDATE SKIP LOCKED` on `get_pending_locked` | `src/bet_maker/repositories/bets.py:62` (`.with_for_update(skip_locked=True)`) | `test_static.py::test_repositories_use_for_update_skip_locked` | verified |
| 5 | Durable queue + persistent messages | `src/bet_maker/entrypoints/messaging.py:122-130` (`RabbitQueue(..., durable=True, ...)`); manual: `rabbitmqctl list_queues name durable` after `docker compose up` | `test_static.py::test_durable_queue_and_exchange_args` + manual command | verified |
| 6 | Named volumes preserve state | `docker-compose.yml:101-103` (`postgres_data`, `rabbitmq_data`); manual: `docker volume ls` shows `bsw_postgres_data` + `bsw_rabbitmq_data` after `docker compose up` | manual command + recorded output | verified |
| 7 | Healthcheck dependency wiring | `docker-compose.yml:56-60, 89-93` (`depends_on: condition: service_healthy`); manual: `docker compose ps` shows `(healthy)` | manual command | verified |
| 8 | `/health` checks deps (not just `{"ok":true}`) | `src/bet_maker/entrypoints/api/health.py:16-63` (returns `{"checks":{"postgres":..., "rabbitmq":..., "rabbitmq_consumer":..., "reconciler":...}}`); manual: `curl :8001/health` returns 503 after `docker compose stop postgres` | manual command + existing P3/P5 tests | verified |
| 9 | DLQ wired (poison → DLQ) | `tests/bet_maker/test_e2e_rabbitmq.py` (poison-to-DLQ scenario from P5) | existing test | verified |
| 10 | Schema version validation | `src/bet_maker/entrypoints/messaging.py:162-165` (`schema_version != _SCHEMA_VERSION_SUPPORTED → UnsupportedSchemaVersion`); tested by P5 unit + e2e | existing test | verified |
| 11 | `expire_on_commit=False` on sessionmaker | `src/bet_maker/infrastructure/db/engine.py:37` (`async_sessionmaker(engine, expire_on_commit=False)`) | `test_static.py::test_async_sessionmaker_expire_on_commit_false` | verified |
| 12 | SIGTERM handled (`docker compose down` exit 0 in <5s) | `Dockerfile:50` (exec-form CMD); `docker-compose.yml:46, 76` (`stop_grace_period: 30s`); manual: `docker compose down` exits 0 in <5s | manual command + `test_static.py::test_dockerfile_exec_form_cmd` | verified |
| 13 | `python:3.10-slim-bookworm` pinned | `Dockerfile:2` (`ARG PYTHON_VERSION=3.10-slim-bookworm`) | `test_static.py::test_dockerfile_pinned_python_bookworm` | verified |
| 14 | `PYTHONUNBUFFERED=1` set | `Dockerfile:6, 30` (both stages) | `test_static.py::test_pythonunbuffered_set` | verified |
| 15 | CMD in exec form (`CMD ["python", ...]`) | `Dockerfile:50` (`CMD ["python", "-c", ...]`); compose `command: ["python", "-m", "..."]` at `docker-compose.yml:44, 74` | `test_static.py::test_dockerfile_exec_form_cmd` | verified |
| 16 | structlog `clear_contextvars` in middleware + handler `try/finally` | `src/bet_maker/entrypoints/middleware.py` (request middleware); `src/bet_maker/entrypoints/messaging.py:154, 194` (consumer `clear_contextvars()` at top + in `finally`) | grep can be added; covered by existing logging tests if any | verified |
| 17 | `mypy --strict` zero errors, no `# type: ignore` on critical paths | `.github/workflows/ci.yml:43-44` (CI step); `grep -rn '# type: ignore' src/` returns **zero** [VERIFIED] | CI step + grep output | verified |
| 18 | Decimal validation: `amount=10.123 → 422` | `src/bet_maker/schemas/bets.py` (Amount Annotated[Decimal, ..., AfterValidator(quantize_amount)]); covered by `tests/bet_maker/test_bet_routes.py::TestPostBet422` | existing test | verified |
| 19 | Decimal exact roundtrip: `amount="10.00"` → GET returns `"10.00"` | `tests/bet_maker/test_bet_routes.py::TestPostBet201` (P3 integration test); manual: curl flow in README §Reviewer walkthrough | existing test | verified |

Note: PITFALLS.md lists 18 bullets but item 5 ("Durable queue + persistent messages") is sometimes counted alongside item 6 ("Volumes"). For AUDIT.md we keep 18 rows, matching the bullet count in PITFALLS.md (item 19 above is technically item 18's "Decimal storage exact" half; map them appropriately per planner's discretion).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `examples=[...]` (list, JSON-Schema only) on `Body(...)` | `openapi_examples={...}` (dict, Swagger UI dropdown) | FastAPI 0.103 (2023-09) | Required for D-08 multi-example UI |
| `responses=` accepting raw `dict` only | `responses={status: {"model": Pydantic, "description": ...}}` | FastAPI 0.27+ | Required for D-07 typed error responses |
| Codecov-style live coverage badge | Static Shields.io badge | Project decision (D-16) | No service token / push needed |
| Hand-curated AsyncAPI YAML | FastStream auto-published `/asyncapi` | FastStream 0.3+ | No drift, no maintenance |
| `pytest --cov=<each>` flag enumeration | `pytest --cov` (bare) + `[tool.coverage.run] source` | pytest-cov 5.x | Single source of truth in pyproject |

**Deprecated/outdated:**
- `examples=` (list form) on `Body(...)` — still works but not Swagger-UI-friendly. Use `openapi_examples`.
- `pytest --cov=src/` (string-path argument with implicit fall-through to source) — works, but explicit `[tool.coverage.run] source` + bare `--cov` is cleaner.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `openapi_examples` parameter exists on FastAPI's `Body(...)` for the FastAPI version pinned in our `pyproject.toml` (`>=0.115,<0.137`) | Pattern 1 / D-08 | LOW — verified via Context7 docs; parameter introduced in FastAPI 0.103, our floor is 0.115 |
| A2 | FastStream's `RabbitRouter` default `schema_url` is `/asyncapi` on FastStream 0.6.7 (our pinned version) | Pattern 3 / D-10 | LOW — verified via Context7; documented default in the integration page |
| A3 | `pytest --cov` (bare) honours `[tool.coverage.run] source = [...]` for our pytest-cov 7.1.x | Pattern 4 / D-15 | LOW — verified via Context7; documented behaviour in pytest-cov docs |
| A4 | Shields.io static badge URL `https://img.shields.io/badge/coverage-85%25-brightgreen.svg` renders correctly on GitHub markdown | README skeleton / D-16 | LOW — verified via web search; standard Shields.io static pattern |
| A5 | Codebase has **zero** `# type: ignore` in `src/` | Pitfalls 7 / D-12 | LOW — verified via `grep -rn` returning empty output [VERIFIED] |
| A6 | Existing P3-P6 integration tests cover items 2, 3, 9, 10, 18, 19 of the audit | 18-item map | LOW — test file paths and node ids verified by `find` [VERIFIED] |

All assumptions are LOW risk and verified against authoritative sources (Context7, web search, repo grep). **No `[ASSUMED]` claims requiring user confirmation** — the assumption log is here for traceability, not as a blocker.

## Open Questions (RESOLVED)

1. **Should AUDIT.md item 17 (`mypy strict + no type: ignore`) include a freeze list?**
   - What we know: `grep -rn '# type: ignore' src/` returns empty today.
   - What's unclear: Should the audit row require future commits to maintain this invariant? (Would need a CI grep step.)
   - RESOLVED: **No.** The existing `mypy strict` CI step is sufficient enforcement. Adding a separate "no-type-ignore" grep CI step is gold-plating.

2. **Should the Reviewer walkthrough include cleanup (`docker compose down`)?**
   - What we know: D-04 specifies 5 steps ending at `GET /bets`.
   - What's unclear: Whether a 6th cleanup step should be appended.
   - RESOLVED: **No** (D-04 locked at 5 steps); cleanup is universal Docker knowledge, README §Quick start already mentions `docker compose down`.

3. **Where does the Russian-language "no emojis" rule extend to OpenAPI `summary`/`description`?**
   - What we know: CLAUDE.md says "no emojis in docs and code." OpenAPI strings are technically code (string literals).
   - What's unclear: Whether OpenAPI free-form `description=` text should be Russian or English.
   - RESOLVED: **Russian** for free-form `description=` text on FastAPI app + routes — consistent with README + .planning/ docs. Tags / model names / field names stay English (Python identifiers). No emojis in any OpenAPI string per CLAUDE.md.

## Environment Availability

Phase 7 has minimal external dependencies. Listed for completeness.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10.x | uv sync, mypy, pytest | ✓ (CI uses `uv python install 3.10.20`) | 3.10.20 | — |
| uv | Package management | ✓ (CI pins 0.11.14) | 0.11.14 | — |
| Docker Engine | Manual audit items (`docker compose down`, `docker volume ls`, RMQ Management UI) | Local dev only — not used in CI for this phase | — | Manual steps recorded as commands + expected output in `07-AUDIT.md`; reviewer can run them after `docker compose up -d` |
| `jq` (CLI JSON pretty-printer) | Reviewer walkthrough README example | Reviewer responsibility | — | README mentions `brew install jq` / `apt-get install jq -y` as one-liner setup |
| GitHub Actions runner | CI (lint, mypy, pytest, coverage) | ✓ (existing CI workflow) | ubuntu-latest | — |
| Internet access for Shields.io | README badge rendering | ✓ (GitHub serves it) | — | Badge degrades gracefully (alt text) if Shields.io is down |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None for CI-driven work; manual audit items list explicit commands and expected outputs.

## Validation Architecture

Phase 7 introduces one new test file (`tests/audit/test_static.py`) and extends CI invocation; no test framework changes.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.1.0 + pytest-cov 7.1.0 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.coverage.*]`) |
| Quick run command | `uv run pytest -q tests/audit/test_static.py` |
| Full suite command | `uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOC-01 | README content + ASCII diagram + curl walkthrough | manual review | n/a (markdown content) | n/a — manual visual check; reviewer follows the walkthrough |
| DOC-02 | Architecture section linked to ARCHITECTURE.md, ASCII diagram present | manual review | grep README for `\.planning/research/ARCHITECTURE\.md` link | ✓ Wave 0 (add static test optional) |
| DOC-03 | Development section content (uv install, migrations, tests, linters) | manual review | grep README for `uv sync` + `pytest -q` + `mypy` substring | ✓ Wave 0 |
| DOC-04 | Reliability section narrative + CANCELLED extension | manual review | grep README for `Reliability` heading + `CANCELLED` substring + `Core Value` | ✓ Wave 0 |
| QA-01 | mypy strict zero errors | CI step | `uv run mypy src` (existing CI) | ✓ — existing CI step verifies |
| QA-09 | pytest coverage ≥85% enforced | CI step | `uv run pytest -q --cov --cov-fail-under=85` | ✗ Wave 0 — extend CI step |
| Audit items 1-19 | Static + manual checks (see 18-item map above) | static + manual | `tests/audit/test_static.py` (7 tests) + existing P3-P6 tests for items 2, 3, 9, 10, 18, 19 | ✗ Wave 0 — `tests/audit/test_static.py` new |

### Sampling Rate

- **Per task commit:** `uv run pytest -q tests/audit/ -x` (audit static tests only — fast)
- **Per wave merge:** `uv run pytest -q --cov` (full suite + coverage)
- **Phase gate:** Full suite with `--cov-fail-under=85` green; mypy strict zero errors; AUDIT.md all rows `verified` or `fix-applied` (zero unjustified `waived`).

### Wave 0 Gaps

- [ ] `tests/audit/__init__.py` — package marker (empty file)
- [ ] `tests/audit/test_static.py` — 7 regex/string-match tests (subscribers, repositories, sessionmaker, Dockerfile exec-form, bookworm pin, PYTHONUNBUFFERED, durable queue/exchange)
- [ ] `.github/workflows/ci.yml` Pytest step extension — `--cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85`
- [ ] `07-AUDIT.md` artefact (in phase dir) — 19-row table
- [ ] `src/{line_provider,bet_maker}/schemas/errors.py` — `ErrorDetail` model (per service, no cross-imports)

*(No framework install needed — pytest-cov + pytest-asyncio already in dev-deps.)*

## Security Domain

Phase 7 is documentation + metadata polish — no auth, no input handling changes, no cryptography. Security configuration of the stack was locked in earlier phases (P1 `127.0.0.1:15672` Management UI binding, P3 `expire_on_commit=False`, P5 schema_version validation, etc.) and is part of the AUDIT.md verification scope, not net-new work.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a (no auth in v1 per REQUIREMENTS.md Out of Scope) |
| V3 Session Management | no | n/a |
| V4 Access Control | no | n/a |
| V5 Input Validation | yes (already in place) | Pydantic v2 schemas with `extra="forbid"`, `frozen=True`, `Annotated[Decimal, ...]` validators — verified in audit |
| V6 Cryptography | no | n/a (no crypto in v1) |

### Known Threat Patterns for FastAPI + FastStream + asyncpg + PostgreSQL

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via raw queries | Tampering | SQLAlchemy 2.0 typed `select()` + parameterised binds — verified in audit |
| Verbose error responses leaking stack | Information disclosure | FastAPI `debug=False` (default); `HTTPException(detail=...)` only emits static strings — verified by route inspection (no f-string interpolation of internal state in `detail=`) |
| AMQP credentials logged on startup | Information disclosure | structlog setup masks secrets implicitly; `LINE_PROVIDER_RABBITMQ_URL` / `BET_MAKER_RABBITMQ_URL` env vars contain creds but are never logged (verified by structlog config in P1) |
| Default `guest:guest` RabbitMQ credentials | Spoofing | RMQ Management UI bound to `127.0.0.1:15672` only (D-01 of P1); README §Quick start note explicitly states "не для production" — already in place [VERIFIED: README:33-35] |
| Poison message DoS via unbounded retries | DoS | Bounded in-handler retries (tenacity 3 attempts), `nack(requeue=True)` never called (R7), `reject(requeue=False) → DLQ` — verified in audit |

**Phase 7 does not introduce new security surface.** All audit items relate to defence-in-depth already in place from P1-P6.

## Sources

### Primary (HIGH confidence)
- `/fastapi/fastapi` (Context7) — `openapi_examples` named-example syntax on `Body(...)`, `responses={status: {"model": ..., "description": ...}}`, `FastAPI(description=...)` — verified for FastAPI 0.115-0.136 range
- `/ag2ai/faststream` (Context7) — `RabbitRouter(schema_url='/asyncapi', include_in_schema=True)` default behaviour, FastAPI integration patterns
- `/pytest-dev/pytest-cov` (Context7) — `--cov` (bare) honours `[tool.coverage.run] source`; `--cov-fail-under=N` CLI flag overrides pyproject `fail_under`; multi-package projects configure in pyproject
- `.planning/phases/07-polish-documentation/07-CONTEXT.md` — locked decisions D-01..D-23 (project source of truth)
- `.planning/REQUIREMENTS.md` — DOC-01..04, QA-01, QA-09 mandatory requirements
- `.planning/ROADMAP.md` — Phase 7 SC#1..6 + 3 pitfalls (visibility gap, R6 final, R11 final)
- `.planning/research/PITFALLS.md` §«Looks Done But Isn't» — 18-item checklist source of truth
- `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `src/**/*.py`, `tests/**/*.py` — current repo state verified by direct read

### Secondary (MEDIUM confidence)
- https://shields.io/badges + https://shields.io/docs/static-badges — Shields.io static badge URL spec (WebSearch + skim of official docs)
- https://img.shields.io/badge/coverage-85%25-brightgreen.svg — confirmed static URL pattern (web search)

### Tertiary (LOW confidence)
- None — every claim in this research has a HIGH or MEDIUM source.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pinned in pyproject.toml; no new deps
- Architecture: HIGH — no new components; existing P1-P6 architecture documented in ARCHITECTURE.md
- Pitfalls: HIGH — drawn from PITFALLS.md + cross-verified against source code grep
- 18-item evidence map: HIGH — every file:line reference verified by direct `Read` of source files

**Research date:** 2026-05-18
**Valid until:** 2026-07-18 (stable, low-volatility — FastAPI/FastStream/pytest-cov APIs used here are mature; only risk is Shields.io URL spec drift which is essentially zero)

## RESEARCH COMPLETE
