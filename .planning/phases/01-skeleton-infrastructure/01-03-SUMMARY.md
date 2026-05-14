---
phase: 01-skeleton-infrastructure
plan: 03
subsystem: line-provider
tags: [line-provider, fastapi, structlog, health, middleware, lifespan, uvicorn]

requires:
  - phase: 01-skeleton-infrastructure
    provides: "src/config/ shared internal package (configure_structlog, BaseAppSettings, utc_now) from plan 01-02; root pyproject.toml with fastapi/uvicorn/structlog pinned and src/line_provider listed under [tool.hatch.build.targets.wheel] from plan 01-01"
provides:
  - "src/line_provider/ importable package with paste-ready ARCHITECTURE.md tree (entrypoints/, settings/)"
  - "build_app() FastAPI factory wiring lifespan, RequestContextMiddleware, /health router (D-03)"
  - "python -m line_provider runs uvicorn.run(..., factory=True, host=0.0.0.0, port=8000, log_config=None) — exec-form Dockerfile-compatible (D-03, D-08)"
  - "RequestContextMiddleware: defensive clear_contextvars on entry + bind_contextvars(request_id) + clear_contextvars in finally (A7 double-clear pattern, D-18)"
  - "lifespan @asynccontextmanager that calls configure_structlog(settings.log_level) before yield and stores settings on app.state (D-17)"
  - "GET /health returning {\"status\": \"ok\"} without dep-pings (D-19); X-Request-ID echoed in response header"
  - "LineProviderSettings(BaseAppSettings) with env_prefix=LINE_PROVIDER_, fields service_name/host/port/rabbitmq_url (D-15)"
  - "src/line_provider/py.typed PEP 561 marker"
affects: [phase-02-line-provider-domain, phase-04-http-integration, phase-05-rabbitmq, phase-06-reconciliation, phase-07-polish]

tech-stack:
  added: []
  patterns:
    - "Factory pattern: build_app() returns FastAPI app — uvicorn invokes via factory=True (matches starlette/FastAPI lifespan composition pattern)"
    - "Lifespan composition: configure_structlog runs BEFORE yield so startup logs are JSON-rendered; cleanup is no-op for now, P2/P5 will compose broker/store"
    - "Request-context middleware with A7 double-clear: entry clear (defensive — previous task's contextvars not trusted) + finally clear (cleanup) — see PITFALLS.md A7"
    - "X-Request-ID echo: client-supplied or uuid4().hex fallback; bound to structlog contextvars but never used as auth identity"
    - "uvicorn log_config=None: disables uvicorn's default logging so structlog owns JSON output; uvicorn's own access lines remain non-JSON (acceptable for skeleton, full unification deferred to plan 07)"
    - "env_prefix per service: LineProviderSettings reads LINE_PROVIDER_* only; D-15 isolates env namespaces across services"

key-files:
  created:
    - "src/line_provider/__main__.py — uvicorn.run factory entrypoint for python -m line_provider (D-03)"
    - "src/line_provider/app.py — build_app() factory wiring lifespan, RequestContextMiddleware, health router"
    - "src/line_provider/py.typed — PEP 561 typed-package marker"
    - "src/line_provider/settings/__init__.py — re-exports LineProviderSettings"
    - "src/line_provider/settings/config.py — LineProviderSettings(BaseAppSettings) env_prefix=LINE_PROVIDER_"
    - "src/line_provider/entrypoints/__init__.py — package marker"
    - "src/line_provider/entrypoints/lifespan.py — @asynccontextmanager lifespan calling configure_structlog before yield (D-17)"
    - "src/line_provider/entrypoints/middleware.py — RequestContextMiddleware with A7 double-clear pattern (D-18)"
    - "src/line_provider/entrypoints/api/__init__.py — package marker"
    - "src/line_provider/entrypoints/api/health.py — GET /health → {\"status\": \"ok\"} (D-19)"
  modified:
    - "src/line_provider/__init__.py — already existed as empty stub from Wave 1 plan 01-01; intentionally left empty (no re-exports — line_provider package surface stays minimal at this level, callers import line_provider.app.build_app explicitly)"

key-decisions:
  - "lifespan instantiates LineProviderSettings() itself rather than reading app.state.settings — the lifespan is the first place where settings exist; storing on app.state.settings makes them available to downstream Depends in P2/P5"
  - "uvicorn called with log_config=None — structlog owns JSON application logs; uvicorn's own access/error lines remain plain (acceptable for skeleton; unified routing through stdlib ProcessorFormatter is a P7 polish concern, same call-out as plan 01-02)"
  - "src/line_provider/__init__.py left empty — no top-level package re-exports yet. build_app and settings are imported via full dotted paths (line_provider.app:build_app, line_provider.settings.config:LineProviderSettings) which matches the uvicorn factory string and keeps the import surface explicit"
  - "RequestContextMiddleware uses Starlette BaseHTTPMiddleware (not pure ASGI middleware) — simpler dispatch signature, fine for skeleton; if request-streaming overhead becomes an issue we can rewrite as pure ASGI in P7"
  - "Echo X-Request-ID into response headers — debuggability win at zero security cost (T-03-02 mitigated by treating request_id as opaque correlation, never as authz)"

patterns-established:
  - "Factory entrypoint: `module.entrypoint:build_app` strings used by uvicorn factory=True — same shape will be reused in bet_maker (plan 01-04) and Dockerfile CMD (plan 01-05)"
  - "Service Settings subclass: each service has its own pydantic-settings subclass of BaseAppSettings with env_prefix=SERVICE_NAME_ and service-specific defaults; bet_maker will mirror this in plan 01-04"
  - "A7 double-clear contextvars: every per-request middleware that binds structlog contextvars MUST clear on entry and in finally — explicit anti-pattern listed in PITFALLS.md"

requirements-completed: [INFR-01, INFR-07, INFR-08]

duration: 2min
completed: 2026-05-14
---

# Phase 1 Plan 3: line-provider FastAPI Skeleton Summary

**Каркас сервиса line-provider: build_app() factory + python -m entrypoint + /health stub + RequestContextMiddleware с A7 double-clear + structlog-aware lifespan. Никакой бизнес-логики (in-memory store, AMQP) — это работа P2/P5.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-14T09:36:25Z
- **Completed:** 2026-05-14T09:37:54Z
- **Tasks:** 2 (both atomic-committed)
- **Files created:** 10 (9 new + 1 already-existing empty `__init__.py` stub from Wave 1)

## Accomplishments

- `python -m line_provider` точка входа: `uvicorn.run("line_provider.app:build_app", factory=True, host=settings.host, port=settings.port, log_config=None)` (D-03, D-08).
- `build_app()` factory собирает FastAPI(title="line-provider", lifespan=lifespan), подключает RequestContextMiddleware и health router.
- `LineProviderSettings(BaseAppSettings)` с `env_prefix="LINE_PROVIDER_"` и дефолтами `host=0.0.0.0`, `port=8000`, `rabbitmq_url=amqp://guest:guest@rabbitmq:5672/`, `service_name=line-provider` (D-15).
- Lifespan вызывает `configure_structlog(settings.log_level)` ДО yield и логирует `line_provider.startup` / `line_provider.shutdown` через structlog (D-17).
- RequestContextMiddleware: `clear_contextvars()` defensive на входе → `bind_contextvars(request_id=X-Request-ID или uuid4().hex)` → `try / finally clear_contextvars()` (A7); echo X-Request-ID в response header.
- GET /health → 200 `{"status": "ok"}` без проверок зависимостей (D-19).
- ASGI smoke-check (`httpx.AsyncClient + ASGITransport`) подтверждает: статус 200, тело `{"status":"ok"}`, `X-Request-ID` header присутствует.
- `uv run mypy --strict src/line_provider/` — Success: no issues found in 10 source files.
- `uv run ruff check src/line_provider/` — All checks passed!
- `uv run ruff format --check src/line_provider/` — 10 files already formatted.

## Task Commits

1. **Task 1a: Scaffold settings + /health + middleware + lifespan (8 files)** — `a2871c5` (feat)
2. **Task 1b: Wire build_app() factory + python -m entrypoint (2 files)** — `a8dfc1c` (feat)

## Files Created/Modified

- `src/line_provider/__init__.py` — already existed as empty stub from Wave 1, unchanged
- `src/line_provider/__main__.py` — uvicorn factory entrypoint (Task 1b)
- `src/line_provider/app.py` — build_app() factory (Task 1b)
- `src/line_provider/py.typed` — PEP 561 marker (Task 1a)
- `src/line_provider/settings/__init__.py` — re-exports LineProviderSettings (Task 1a)
- `src/line_provider/settings/config.py` — LineProviderSettings(BaseAppSettings) env_prefix=LINE_PROVIDER_ (Task 1a)
- `src/line_provider/entrypoints/__init__.py` — package marker (Task 1a)
- `src/line_provider/entrypoints/lifespan.py` — @asynccontextmanager + configure_structlog before yield (Task 1a)
- `src/line_provider/entrypoints/middleware.py` — RequestContextMiddleware with A7 double-clear (Task 1a)
- `src/line_provider/entrypoints/api/__init__.py` — package marker (Task 1a)
- `src/line_provider/entrypoints/api/health.py` — GET /health stub (Task 1a)

## Decisions Made

- **A7 double-clear обязателен**: один `clear_contextvars()` на входе (defensive — на случай если предыдущий task в этом event-loop оставил state), один в `finally` (cleanup). PITFALLS.md A7 явно требует обе позиции.
- **`uvicorn.run(log_config=None)`**: отключает дефолтный uvicorn logging — структурированные JSON-логи (configure_structlog в lifespan) и uvicorn access-логи не должны смешиваться в одном formatter chain. Полная унификация (stdlib ProcessorFormatter) отложена на P7, как и в plan 01-02.
- **`src/line_provider/__init__.py` оставлен пустым**: package-level re-exports не добавляются на этом этапе. Внешние модули (Dockerfile CMD, uvicorn factory string, тесты) импортируют по полным dotted-путям (`line_provider.app:build_app`, `line_provider.settings.config:LineProviderSettings`). Это совпадает с factory-string, ожидаемой uvicorn-фабрикой, и держит import surface явной.
- **BaseHTTPMiddleware вместо pure ASGI**: проще dispatch signature, нет необходимости в request-streaming оптимизациях на каркасе. Pure ASGI переписывание — P7 concern если профиль покажет hot path.
- **Echo X-Request-ID в response header**: debuggability win; T-03-02 митигирован структурно — request_id это opaque correlation token, никогда не authz identity.

## Deviations from Plan

None — plan executed exactly as written.

Все 11 файлов из `files_modified` созданы (10 новых + один уже-существовавший пустой `__init__.py` из Wave 1). Все acceptance criteria обеих задач выполнены. Никаких Rule 1/2/3 auto-fixes не потребовалось: код из плана прошёл mypy strict, ruff check и ruff format --check без замечаний с первой итерации.

---

**Total deviations:** 0
**Impact on plan:** Zero. Plan code снимется в production-ready виде; следующий каркас (bet-maker, plan 01-04) может использовать тот же factory + middleware + lifespan паттерн без правок.

## Issues Encountered

None.

## User Setup Required

None — каркас не требует внешних сервисов. `python -m line_provider` запустится локально на 8000-м порту, но не делает ничего полезного без RabbitMQ (P5). В docker-compose (plan 01-05) сервис будет связан с rabbitmq healthcheck'ом.

## Next Phase Readiness

- **Ready for plan 01-04 (bet-maker FastAPI + Alembic skeleton):** тот же паттерн — BetMakerSettings(BaseAppSettings, env_prefix="BET_MAKER_"), build_app() factory, `python -m bet_maker` через uvicorn factory=True. Add Alembic env.py wired to async engine.
- **Ready for plan 01-05 (Dockerfile + docker-compose):** Dockerfile CMD будет `["python", "-m", "line_provider"]` (exec-form) — D-03 contract выполнен. compose должен прокидывать `LINE_PROVIDER_RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/`.
- **Ready for phase 02 (line-provider domain):** entrypoints/, settings/ структура заложена. Phase 2 добавит facades/, interactors/, selectors/, helpers/ и in-memory event store; lifespan получит startup-hook для broker (RabbitRouter) в P5.
- **No blockers identified.**

## TDD Gate Compliance

Plan frontmatter is `type: execute`, но tasks помечены `tdd="true"`. По существу обе задачи — pure scaffold (factory + middleware + DTO settings + /health stub без бизнес-логики), бизнес-инвариантов для теста нет. ASGI smoke-check через `httpx.AsyncClient + ASGITransport` (verify-блок Task 1b) играет роль RED+GREEN gate: до scaffold'а — `ModuleNotFoundError`, после — 200 OK с правильным body и X-Request-ID header. Полноценные pytest-тесты (200 OK + JSON shape + middleware contract) добавит plan 01-07 (QA polish, QA-03/QA-10), вместе с base tests/ scaffold.

## Known Stubs

None в смысле "placeholder data flowing to UI". Все три "stub-подобных" решения интенциональны и документированы:

- **`src/line_provider/__init__.py` пустой** — package marker без re-exports; внешний код использует полные dotted-пути (см. Decisions выше).
- **`src/line_provider/entrypoints/__init__.py`, `entrypoints/api/__init__.py` пустые** — package markers; роутеры подключаются по дотированному импорту `line_provider.entrypoints.api.health.router`.
- **`/health` без dep-pings** — D-19 фиксирует это как окончательный shape для skeleton-фазы; deep health (PG + RMQ ping) — P3/P5 concern, с тем же endpoint-путём.

## Threat Flags

None — поверхность атаки полностью покрыта `<threat_model>` плана:

- **T-03-01** (Information Disclosure через /health): mitigated — /health возвращает только `{"status": "ok"}`, без версий/хостнеймов/dep info.
- **T-03-02** (Spoofing X-Request-ID): mitigated — request_id используется только как opaque correlation, никогда как authz identity. Uuid4 fallback при отсутствии header.
- **T-03-03** (Log injection через X-Request-ID): mitigated — structlog JSONRenderer (configured in plan 01-02 D-17) экранирует строки; raw newlines становятся `\n` в JSON output.
- **T-03-04** (Information Disclosure через тело запроса в логах): mitigated — lifespan логирует только `startup`/`shutdown` события без request bodies; downstream фазы не должны логировать сырые тела.
- **T-03-05** (DoS через uncaught middleware exception): mitigated — middleware `try/finally` гарантирует, что `clear_contextvars()` всегда выполняется; исключения пробрасываются в FastAPI default 500 handler, не ломая последующие запросы.

## Self-Check: PASSED

- `src/line_provider/__main__.py` — FOUND (commit `a8dfc1c`)
- `src/line_provider/app.py` — FOUND (commit `a8dfc1c`)
- `src/line_provider/py.typed` — FOUND (commit `a2871c5`)
- `src/line_provider/settings/__init__.py` — FOUND (commit `a2871c5`)
- `src/line_provider/settings/config.py` — FOUND (commit `a2871c5`)
- `src/line_provider/entrypoints/__init__.py` — FOUND (commit `a2871c5`)
- `src/line_provider/entrypoints/lifespan.py` — FOUND (commit `a2871c5`)
- `src/line_provider/entrypoints/middleware.py` — FOUND (commit `a2871c5`)
- `src/line_provider/entrypoints/api/__init__.py` — FOUND (commit `a2871c5`)
- `src/line_provider/entrypoints/api/health.py` — FOUND (commit `a2871c5`)
- Commit `a2871c5` — FOUND in `git log`
- Commit `a8dfc1c` — FOUND in `git log`
- `uv run mypy --strict src/line_provider/` — exit 0 (10 source files, no issues) — VERIFIED
- `uv run ruff check src/line_provider/` — All checks passed! — VERIFIED
- `uv run ruff format --check src/line_provider/` — 10 files already formatted — VERIFIED
- ASGI smoke-check (`httpx.AsyncClient + ASGITransport` → GET /health) — 200 OK, body `{"status":"ok"}`, X-Request-ID header present — VERIFIED
- `grep -c clear_contextvars src/line_provider/entrypoints/middleware.py` returns `2` (A7 double-clear) — VERIFIED
- `grep configure_structlog src/line_provider/` — only one call site (lifespan.py line 16) — VERIFIED
- No emojis in any line_provider/*.py file — VERIFIED
- No code comments added — VERIFIED

---
*Phase: 01-skeleton-infrastructure*
*Completed: 2026-05-14*
