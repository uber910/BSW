---
phase: 01-skeleton-infrastructure
plan: 04
subsystem: bet-maker
tags: [bet-maker, fastapi, alembic, structlog, health, middleware, lifespan, uvicorn, async]

requires:
  - phase: 01-skeleton-infrastructure
    provides: "src/config/ shared internal package (configure_structlog, BaseAppSettings, utc_now) from plan 01-02; root pyproject.toml with fastapi/uvicorn/structlog/alembic pinned and src/bet_maker listed under [tool.hatch.build.targets.wheel] from plan 01-01"
  - phase: 01-skeleton-infrastructure
    provides: "line_provider FastAPI skeleton shape from plan 01-03 — same factory + middleware + lifespan pattern mirrored here, with port 8001 and extended settings"
provides:
  - "src/bet_maker/ importable package mirroring line_provider tree (entrypoints/, settings/)"
  - "build_app() FastAPI factory wiring lifespan, RequestContextMiddleware, /health router (D-03)"
  - "python -m bet_maker runs uvicorn.run(..., factory=True, host=0.0.0.0, port=8001, log_config=None) — exec-form Dockerfile-compatible (D-03, D-08)"
  - "BetMakerSettings(BaseAppSettings) with env_prefix=BET_MAKER_, fields service_name/host/port/postgres_dsn/rabbitmq_url/line_provider_base_url/reconciliation_interval_s (D-15)"
  - "RequestContextMiddleware: defensive clear_contextvars on entry + bind_contextvars(request_id) + clear_contextvars in finally (A7 double-clear pattern, D-18)"
  - "lifespan @asynccontextmanager that calls configure_structlog(settings.log_level) before yield and stores settings on app.state (D-17)"
  - "GET /health returning {\"status\": \"ok\"} without dep-pings (D-19); X-Request-ID echoed in response header"
  - "alembic.ini at repo root pointing script_location=alembic, prepend_sys_path=. src, NO sqlalchemy.url line (Anti-Pattern 7 mitigated)"
  - "alembic/env.py async template (async_engine_from_config + run_async_migrations) that reads settings.postgres_dsn from BetMakerSettings (INFR-06)"
  - "alembic/script.py.mako standard 1.18 template; alembic/versions/.gitkeep keeps empty dir tracked"
  - "src/bet_maker/py.typed PEP 561 marker"
affects: [phase-03-bet_maker-domain-and-db, phase-04-http-integration, phase-05-rabbitmq, phase-06-reconciliation, phase-07-polish]

tech-stack:
  added: []
  patterns:
    - "Factory pattern mirrored from line_provider: build_app() returns FastAPI app — uvicorn invokes via factory=True"
    - "Lifespan composition mirrored: configure_structlog runs BEFORE yield so startup logs are JSON-rendered; P3/P5 will compose DB engine / broker"
    - "A7 double-clear middleware reused verbatim from line_provider (defensive entry + finally cleanup)"
    - "env_prefix per service: BetMakerSettings reads BET_MAKER_* only; D-15 isolates env namespaces across services"
    - "Alembic env.py reads DSN from BetMakerSettings at runtime via config.set_main_option — single source of truth, eliminates the Anti-Pattern 7 of hardcoding sqlalchemy.url in alembic.ini"
    - "Typed DSN fields (PostgresDsn, AmqpDsn, HttpUrl) — pydantic validates URL shape at Settings construction; misconfigured env fails fast"

key-files:
  created:
    - "src/bet_maker/__main__.py — uvicorn.run factory entrypoint for python -m bet_maker (D-03)"
    - "src/bet_maker/app.py — build_app() factory wiring lifespan, RequestContextMiddleware, health router"
    - "src/bet_maker/py.typed — PEP 561 typed-package marker"
    - "src/bet_maker/settings/__init__.py — re-exports BetMakerSettings"
    - "src/bet_maker/settings/config.py — BetMakerSettings(BaseAppSettings) env_prefix=BET_MAKER_ with postgres_dsn/rabbitmq_url/line_provider_base_url/reconciliation_interval_s"
    - "src/bet_maker/entrypoints/__init__.py — package marker"
    - "src/bet_maker/entrypoints/lifespan.py — @asynccontextmanager lifespan calling configure_structlog before yield (D-17)"
    - "src/bet_maker/entrypoints/middleware.py — RequestContextMiddleware with A7 double-clear pattern (D-18)"
    - "src/bet_maker/entrypoints/api/__init__.py — package marker"
    - "src/bet_maker/entrypoints/api/health.py — GET /health → {\"status\": \"ok\"} (D-19)"
    - "alembic.ini — Alembic config at repo root (no sqlalchemy.url; env.py supplies it)"
    - "alembic/env.py — async migration env reading DSN from BetMakerSettings (INFR-06, Anti-Pattern 7 mitigation)"
    - "alembic/script.py.mako — standard Alembic 1.18 migration template"
    - "alembic/versions/.gitkeep — keep empty versions dir tracked in git"
  modified:
    - "src/bet_maker/__init__.py — already existed as empty stub from Wave 1 plan 01-01; intentionally left empty (no re-exports — bet_maker package surface stays minimal; callers import bet_maker.app.build_app explicitly via uvicorn factory string)"

key-decisions:
  - "Typed DSN fields (PostgresDsn, AmqpDsn, HttpUrl) used in BetMakerSettings — pydantic validates URL shape on Settings instantiation; deviates from line_provider's plain-str rabbitmq_url but follows the plan spec verbatim. Trade-off: typed DSNs catch malformed env values at process start, no extra runtime cost."
  - "Alembic env.py reads settings.postgres_dsn at module-import time and calls config.set_main_option('sqlalchemy.url', str(...)) — the alembic.ini has NO sqlalchemy.url line at all, so there is no possible drift between two config sources (Anti-Pattern 7 mitigation, T-04-03)"
  - "alembic.ini's [logger_sqlalchemy] level=WARNING so the engine does not echo full DSN at INFO level during migration runs (T-04-02 mitigation)"
  - "target_metadata=None in env.py — no models exist in P1; P3 will replace with the actual SQLAlchemy declarative metadata import"
  - "lifespan instantiates BetMakerSettings() itself, identical to line_provider lifespan — the lifespan is the first place where settings exist; storing on app.state.settings makes them available to downstream Depends in P3/P5/P6"
  - "uvicorn called with log_config=None — same call-out as line_provider (plan 01-03): structlog owns JSON application logs; uvicorn's own access/error lines remain plain text — full unification deferred to P7"
  - "src/bet_maker/__init__.py left empty (no top-level re-exports) — same convention as line_provider; uvicorn factory string and Dockerfile CMD reference full dotted paths"

patterns-established:
  - "Service-specific Settings subclass: BetMakerSettings(BaseAppSettings) with env_prefix=BET_MAKER_ and service-specific fields (PG DSN, AMQP URL, line-provider base URL, reconciliation interval). Mirrors LineProviderSettings shape from plan 01-03; both services share BaseAppSettings parent for service_name/log_level."
  - "Alembic single-source-of-truth pattern: alembic.ini contains NO DSN; env.py imports Settings and sets sqlalchemy.url at runtime. Reusable for any other CLI tool that needs the same DSN — they all import BetMakerSettings."
  - "Typed DSN at the Settings boundary: PostgresDsn / AmqpDsn / HttpUrl validate URL shape on `BetMakerSettings()` instantiation; downstream code can rely on URL well-formedness without re-parsing."

requirements-completed: [INFR-01, INFR-06, INFR-07, INFR-08]

duration: 2min
completed: 2026-05-14
---

# Phase 1 Plan 4: bet-maker FastAPI + Alembic Skeleton Summary

**Каркас сервиса bet-maker — структурно зеркальный line_provider (build_app factory, python -m entrypoint, /health stub, RequestContextMiddleware с A7 double-clear, structlog-aware lifespan), отличается портом 8001 и расширенным BetMakerSettings (postgres_dsn, rabbitmq_url, line_provider_base_url, reconciliation_interval_s). Добавлен async Alembic-каркас: alembic.ini + env.py, читающий DSN из BetMakerSettings (Anti-Pattern 7 mitigation), пустая versions/ директория готова к миграциям в P3.**

## Performance

- **Duration:** ~2 min (~135s)
- **Started:** 2026-05-14T09:42:32Z
- **Completed:** 2026-05-14T09:44:47Z
- **Tasks:** 3 (Task 1a scaffold 8 files; Task 1b wiring 2 files; Task 2 alembic 4 files) — all atomic-committed
- **Files created:** 14 (10 в src/bet_maker/ + 4 alembic/) — src/bet_maker/__init__.py уже существовал как пустой стаб от Wave 1, не изменялся
- **Files modified:** 0

## Accomplishments

- `python -m bet_maker` точка входа: `uvicorn.run("bet_maker.app:build_app", factory=True, host=settings.host, port=settings.port, log_config=None)` (D-03, D-08).
- `build_app()` factory собирает FastAPI(title="bet-maker", lifespan=lifespan), подключает RequestContextMiddleware и health router — точно той же формы, что и в line_provider.
- `BetMakerSettings(BaseAppSettings)` с `env_prefix="BET_MAKER_"` и дефолтами: `host=0.0.0.0`, `port=8001`, `postgres_dsn=postgresql+asyncpg://bsw:bsw@postgres:5432/bsw`, `rabbitmq_url=amqp://guest:guest@rabbitmq:5672/`, `line_provider_base_url=http://line-provider:8000`, `reconciliation_interval_s=30.0`, `service_name=bet-maker` (D-15). Типизация DSN через pydantic `PostgresDsn / AmqpDsn / HttpUrl`.
- Lifespan вызывает `configure_structlog(settings.log_level)` ДО yield и логирует `bet_maker.startup` / `bet_maker.shutdown` через structlog (D-17). Подтверждено runtime-смоком: `python -m bet_maker` выдаёт `{"service": "bet-maker", "event": "bet_maker.startup", "level": "info", "timestamp": "..."}` на stdout, биндится на `0.0.0.0:8001`, корректно завершается с `bet_maker.shutdown`.
- RequestContextMiddleware: `clear_contextvars()` defensive на входе → `bind_contextvars(request_id=X-Request-ID или uuid4().hex)` → `try / finally clear_contextvars()` (A7 double-clear). `grep -c clear_contextvars` returns `2`.
- GET /health → 200 `{"status": "ok"}` без проверок зависимостей (D-19); X-Request-ID echoed в response header.
- ASGI smoke-check (`httpx.AsyncClient + ASGITransport`) подтверждает: статус 200, тело `{"status":"ok"}`, `X-Request-ID` header присутствует.
- Async Alembic skeleton:
  - `alembic.ini` в корне: `script_location=alembic`, `prepend_sys_path=. src`, UTC timezone, file_template с датой, `[logger_sqlalchemy] level=WARNING` чтобы не светить DSN. **Нет строки `sqlalchemy.url`** — `grep -c '^sqlalchemy.url' alembic.ini` returns `0` (Anti-Pattern 7 mitigation).
  - `alembic/env.py` — async template (async_engine_from_config + run_async_migrations), импортирует BetMakerSettings и вызывает `config.set_main_option("sqlalchemy.url", str(settings.postgres_dsn))` при загрузке модуля. Поддерживает offline mode (literal_binds) и online async mode.
  - `alembic/script.py.mako` — стандартный шаблон Alembic 1.18.4 с типизированными revision identifiers.
  - `alembic/versions/.gitkeep` — пустой файл удерживает директорию в git.
  - `uv run alembic --help` отрабатывает без traceback. `uv run python -c "from alembic.config import Config; Config('alembic.ini')"` exit 0.
- `uv run mypy --strict src/bet_maker/` — Success: no issues found in 10 source files.
- `uv run mypy --strict alembic/env.py` — Success: no issues found in 1 source file.
- `uv run ruff check src/bet_maker/` — All checks passed!
- `uv run ruff format --check src/bet_maker/` — 10 files already formatted.
- `uv run ruff check alembic/env.py` — All checks passed!

## Task Commits

1. **Task 1a: Scaffold bet_maker settings, /health route, middleware, lifespan (8 files)** — `2234cb3` (feat)
2. **Task 1b: Wire bet_maker — build_app factory + __main__ uvicorn entrypoint (2 files)** — `5f2b74c` (feat)
3. **Task 2: Initialise async Alembic skeleton (4 files)** — `114d40e` (feat)

## Files Created/Modified

- `src/bet_maker/__init__.py` — already existed as empty stub from Wave 1, unchanged
- `src/bet_maker/__main__.py` — uvicorn factory entrypoint (Task 1b)
- `src/bet_maker/app.py` — build_app() factory (Task 1b)
- `src/bet_maker/py.typed` — PEP 561 marker (Task 1a)
- `src/bet_maker/settings/__init__.py` — re-exports BetMakerSettings (Task 1a)
- `src/bet_maker/settings/config.py` — BetMakerSettings(BaseAppSettings) env_prefix=BET_MAKER_ (Task 1a)
- `src/bet_maker/entrypoints/__init__.py` — package marker (Task 1a)
- `src/bet_maker/entrypoints/lifespan.py` — @asynccontextmanager + configure_structlog before yield (Task 1a)
- `src/bet_maker/entrypoints/middleware.py` — RequestContextMiddleware with A7 double-clear (Task 1a)
- `src/bet_maker/entrypoints/api/__init__.py` — package marker (Task 1a)
- `src/bet_maker/entrypoints/api/health.py` — GET /health stub (Task 1a)
- `alembic.ini` — Alembic config at repo root, no sqlalchemy.url (Task 2)
- `alembic/env.py` — async env reading DSN from BetMakerSettings (Task 2)
- `alembic/script.py.mako` — standard Alembic 1.18 template (Task 2)
- `alembic/versions/.gitkeep` — empty versions dir marker (Task 2)

## Decisions Made

- **Typed DSN fields в BetMakerSettings**: использовал `PostgresDsn / AmqpDsn / HttpUrl` из pydantic вместо plain `str`. Это отличается от line_provider, где `rabbitmq_url: str`, но соответствует тексту плана и даёт раннюю валидацию формата URL на старте процесса. Если в .env прилетит мусор — `BetMakerSettings()` упадёт сразу, а не в P5 при попытке connect.
- **A7 double-clear обязателен и здесь**: один `clear_contextvars()` на входе (defensive — на случай если предыдущий task в event-loop оставил state), один в `finally` (cleanup). Симметрично line_provider. PITFALLS.md A7 явно требует обе позиции.
- **`uvicorn.run(log_config=None)`**: отключает дефолтный uvicorn logging — структурированные JSON-логи (configure_structlog в lifespan) и uvicorn access-логи не должны смешиваться в одном formatter chain. Полная унификация (stdlib ProcessorFormatter) отложена на P7, как и в plan 01-02 / 01-03.
- **`src/bet_maker/__init__.py` оставлен пустым**: package-level re-exports не добавляются. Внешние модули (Dockerfile CMD, uvicorn factory string, тесты, alembic/env.py) импортируют по полным dotted-путям (`bet_maker.app:build_app`, `bet_maker.settings.config:BetMakerSettings`).
- **alembic.ini БЕЗ sqlalchemy.url**: Anti-Pattern 7 — две независимые точки конфигурации DSN. env.py при загрузке модуля вызывает `config.set_main_option('sqlalchemy.url', str(settings.postgres_dsn))`, так что единственный источник истины — BetMakerSettings (а её источник — environment variables). `grep -c '^sqlalchemy.url' alembic.ini` returns 0 (T-04-03).
- **`[logger_sqlalchemy] level=WARNING` в alembic.ini**: дефолтный INFO будет печатать SQL-statements и иногда DSN в connect-логах. Для миграционного раннера это лишний шум и потенциальная утечка credentials в CI-логи (T-04-02).
- **target_metadata=None**: в P1 моделей нет; в P3 будет заменено на импорт декларативной metadata из bet_maker.infrastructure.db (placeholder для autogenerate).
- **BaseHTTPMiddleware вместо pure ASGI**: проще dispatch signature, без request-streaming оптимизаций. Pure ASGI переписывание — P7 concern.
- **X-Request-ID echo в response header**: debuggability win; T-04-05 митигирован структурно — request_id это opaque correlation token, никогда не authz identity.

## Deviations from Plan

None — plan executed exactly as written.

Все 14 файлов из `files_modified` фронтматтера созданы (10 в src/bet_maker/ + 4 в alembic/; `src/bet_maker/__init__.py` уже существовал как пустой стаб от Wave 1). Все acceptance criteria всех трёх задач выполнены с первой итерации. Никаких Rule 1/2/3 auto-fixes не потребовалось: код из плана прошёл mypy strict, ruff check и ruff format --check без замечаний. Runtime smoke (`python -m bet_maker`) подтвердил bind на 0.0.0.0:8001 и корректные структурированные JSON-логи startup/shutdown.

---

**Total deviations:** 0
**Impact on plan:** Zero. Скелет bet_maker структурно идентичен line_provider; Alembic env.py готов к появлению ORM-моделей в P3 (нужно будет заменить `target_metadata = None` на импорт declarative metadata).

## Issues Encountered

None.

## User Setup Required

None — каркас не требует внешних сервисов. `python -m bet_maker` запустится локально на 8001-м порту, но `/health` это stub без проверки зависимостей. Полноценные проверки PG/RMQ в /health — P3/P5. Alembic команды (`uv run alembic upgrade head`) потребуют живой PG, который появится в P3 через docker-compose (plan 01-05).

## Next Phase Readiness

- **Ready for plan 01-05 (Dockerfile + docker-compose):** Dockerfile CMD будет `["python", "-m", "bet_maker"]` (exec-form) — D-03 contract выполнен. docker-compose должен прокидывать `BET_MAKER_POSTGRES_DSN=postgresql+asyncpg://bsw:bsw@postgres:5432/bsw`, `BET_MAKER_RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/`, `BET_MAKER_LINE_PROVIDER_BASE_URL=http://line-provider:8000`. Alembic будет вызываться отдельной командой / init-контейнером перед стартом bet_maker.
- **Ready for phase 03 (bet_maker domain + DB):** entrypoints/, settings/ структура заложена; alembic.ini + env.py готовы к появлению declarative metadata и первой миграции (init schema со ставками). target_metadata=None заменится на импорт из bet_maker.infrastructure.db.metadata. Lifespan получит startup-hook для AsyncEngine + sessionmaker.
- **Ready for phase 04 (HTTP integration with line_provider):** `BetMakerSettings.line_provider_base_url` уже на месте; в P4 lifespan заинжектит `httpx.AsyncClient(base_url=settings.line_provider_base_url)` как app.state.http_client.
- **Ready for phase 05 (RabbitMQ):** `BetMakerSettings.rabbitmq_url` готов; lifespan получит FastStream RabbitRouter wiring.
- **Ready for phase 06 (reconciliation):** `BetMakerSettings.reconciliation_interval_s=30.0` зафиксирован; в P6 lifespan стартует background task с этим интервалом.
- **No blockers identified.**

## TDD Gate Compliance

Plan frontmatter is `type: execute`, обе sub-task Task 1a/1b помечены `tdd="true"`. По существу обе задачи — pure scaffold (factory + middleware + DTO settings + /health stub без бизнес-логики), бизнес-инвариантов для теста нет. ASGI smoke-check через `httpx.AsyncClient + ASGITransport` (verify-блок Task 1b) играет роль RED+GREEN gate: до scaffold'а — `ModuleNotFoundError`, после — 200 OK с правильным body и X-Request-ID header. Полноценные pytest-тесты (200 OK + JSON shape + middleware contract + BetMakerSettings reads env correctly) добавит plan 01-07 (QA polish), вместе с base tests/ scaffold.

## Known Stubs

None в смысле "placeholder data flowing to UI". Все "stub-подобные" решения интенциональны и документированы:

- **`src/bet_maker/__init__.py` пустой** — package marker без re-exports; внешний код использует полные dotted-пути (см. Decisions).
- **`src/bet_maker/entrypoints/__init__.py`, `entrypoints/api/__init__.py` пустые** — package markers; роутеры подключаются по дотированному импорту `bet_maker.entrypoints.api.health.router`.
- **`/health` без dep-pings** — D-19 фиксирует это как окончательный shape для skeleton-фазы; deep health (PG + RMQ ping) — P3/P5 concern, с тем же endpoint-путём.
- **`alembic/versions/` пустая** — миграции создаются в P3.
- **`target_metadata=None` в env.py** — placeholder до появления declarative metadata в P3.
- **`alembic/versions/.gitkeep` пустой** — стандартный приём, директория попадает в git без содержимого.

## Threat Flags

None — поверхность атаки полностью покрыта `<threat_model>` плана:

- **T-04-01** (Information Disclosure через /health): mitigated — /health возвращает только `{"status": "ok"}`, без версий/хостнеймов/dep info.
- **T-04-02** (Information Disclosure: Alembic печатает DSN в логах): mitigated — `[logger_sqlalchemy] level=WARNING` в alembic.ini, env.py не вызывает print(settings.postgres_dsn), structlog не используется в migration-time.
- **T-04-03** (Tampering: alembic.ini hardcoded URL clashes с env.py override): mitigated — в alembic.ini физически нет строки `sqlalchemy.url` (verified: `grep -c '^sqlalchemy.url' alembic.ini` returns 0). Единственный источник истины — env.py через BetMakerSettings.
- **T-04-04** (Elevation of Privilege: unintended downgrade): accept (out of scope для P1, в P3 будет initial migration с upgrade only).
- **T-04-05** (Spoofing X-Request-ID): mitigated — uuid4 fallback, request_id используется только как opaque correlation, никогда как authz identity.

## Self-Check: PASSED

- `src/bet_maker/__main__.py` — FOUND (commit `5f2b74c`)
- `src/bet_maker/app.py` — FOUND (commit `5f2b74c`)
- `src/bet_maker/py.typed` — FOUND (commit `2234cb3`)
- `src/bet_maker/settings/__init__.py` — FOUND (commit `2234cb3`)
- `src/bet_maker/settings/config.py` — FOUND (commit `2234cb3`)
- `src/bet_maker/entrypoints/__init__.py` — FOUND (commit `2234cb3`)
- `src/bet_maker/entrypoints/lifespan.py` — FOUND (commit `2234cb3`)
- `src/bet_maker/entrypoints/middleware.py` — FOUND (commit `2234cb3`)
- `src/bet_maker/entrypoints/api/__init__.py` — FOUND (commit `2234cb3`)
- `src/bet_maker/entrypoints/api/health.py` — FOUND (commit `2234cb3`)
- `alembic.ini` — FOUND (commit `114d40e`)
- `alembic/env.py` — FOUND (commit `114d40e`)
- `alembic/script.py.mako` — FOUND (commit `114d40e`)
- `alembic/versions/.gitkeep` — FOUND (commit `114d40e`)
- Commit `2234cb3` — FOUND in `git log`
- Commit `5f2b74c` — FOUND in `git log`
- Commit `114d40e` — FOUND in `git log`
- `uv run mypy --strict src/bet_maker/` — exit 0 (10 source files, no issues) — VERIFIED
- `uv run mypy --strict alembic/env.py` — exit 0 (1 source file, no issues) — VERIFIED
- `uv run ruff check src/bet_maker/` — All checks passed! — VERIFIED
- `uv run ruff format --check src/bet_maker/` — 10 files already formatted — VERIFIED
- `uv run ruff check alembic/env.py` — All checks passed! — VERIFIED
- ASGI smoke-check (`httpx.AsyncClient + ASGITransport` → GET /health) — 200 OK, body `{"status":"ok"}`, X-Request-ID header present — VERIFIED
- Runtime smoke (`python -m bet_maker`) — bound on 0.0.0.0:8001, structlog JSON startup/shutdown events emitted — VERIFIED
- `grep -c clear_contextvars src/bet_maker/entrypoints/middleware.py` returns `2` (A7 double-clear) — VERIFIED
- `grep -c '^sqlalchemy.url' alembic.ini` returns `0` (Anti-Pattern 7 mitigation) — VERIFIED
- `uv run python -c "from alembic.config import Config; Config('alembic.ini')"` — exit 0 — VERIFIED
- `uv run alembic --help` — help output emitted without traceback — VERIFIED
- No emojis in any bet_maker/*.py or alembic/* file — VERIFIED
- No code comments added — VERIFIED

---
*Phase: 01-skeleton-infrastructure*
*Completed: 2026-05-14*
