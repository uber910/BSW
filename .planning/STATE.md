---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-05-15T08:11:00Z"
progress:
  total_phases: 7
  completed_phases: 1
  total_plans: 14
  completed_plans: 8
  percent: 57
---

# Project State: BSW Betting System

**Last updated:** 2026-05-15 (after Phase 2 Plan 01 — Wave 0 foundations complete)

## Project Reference

**Core Value:** Ставка никогда не остаётся в статусе PENDING после того, как её событие завершилось.

**Current focus:** Phase 02 — line-provider-domain

## Current Position

Phase: 02 (line-provider-domain) — EXECUTING
Plan: 2 of 7 (Plan 01 complete — Wave 0 foundations)

- **Milestone:** v1
- **Phase:** 2
- **Plan:** 02-01 complete (Wave 0); next 02-02 (Schemas, Wave 1)
- **Status:** Executing Phase 02
- **Progress:** [█░░░░░░░░░] 14% (1/7 Phase 2 plans complete)

```
[█░░░░░░] 1/7 phases (14%)
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases planned | 2/7 |
| Phases complete | 1/7 |
| Requirements mapped | 42/42 (100%) |
| Plans complete | 8/14 (Phase 1 complete; Phase 2 1/7 plans complete) |
| Plan 01-01 duration | ~4 min |
| Plan 01-02 duration | ~4 min |
| Plan 01-03 duration | ~2 min (2 tasks, 10 files) |
| Plan 01-04 duration | ~2 min (3 tasks, 14 files) |
| Plan 01-05 duration | ~2 min autonomous + operator verification (4 tasks: 3 file-creation + 1 checkpoint:human-verify; 4 files) |
| Plan 01-06 duration | ~2 min (2 tasks, 3 files) |
| Plan 01-07 duration | ~2.5 min (2 tasks, 10 files) |
| Plan 02-01 duration | ~3 min (4 tasks, 5 files) |

## Accumulated Context

### Decisions

(See PROJECT.md "Key Decisions" — locked at initialization. Phase-level decisions accumulate here at each transition.)

- **2026-05-13**: 7-phase build order adopted from research/ARCHITECTURE.md (validated minimum-dependency DAG); Phase 2 and Phase 3 parallelizable after Phase 1.
- **2026-05-13**: Critical path = 1 → 2 → 5 → 6 → 7 (covers Core Value end-to-end).
- **2026-05-13**: Phase 5 is the risk-heavy phase (~50% of identified pitfalls cluster there) and warrants double code-review attention.
- **2026-05-14 (Plan 01-01)**: Root pyproject.toml established with hatch packages = src/line_provider, src/bet_maker, src/config (D-01); no [tool.uv.workspace] section. uv.lock locks 68 packages, deterministic via uv sync --frozen.
- **2026-05-14 (Plan 01-01)**: Python pinned to 3.10.20 via .python-version (D-09). Pytest configured with asyncio_mode=auto, pythonpath=['src'] (D-13). ruff rule set includes E,W,F,I,B,UP,N,SIM,ASYNC,PL,RUF; mypy strict=true with pydantic.mypy plugin (QA-02 / QA-01 baseline).
- **2026-05-14 (Plan 01-01)**: Rule 3 deviation — empty __init__.py stubs created for src/line_provider, src/bet_maker, src/config plus placeholder README.md; required for hatch editable build during `uv sync --frozen`. No code or behaviour added. Plans 02/03/04 will populate.
- **2026-05-14 (Plan 01-02)**: src/config/ shared internal-only package created (D-02). configure_structlog locked to D-17 processors chain [merge_contextvars, add_log_level, TimeStamper(iso,utc), dict_tracebacks, JSONRenderer]; wrapper_class=make_filtering_bound_logger(level), logger_factory=PrintLoggerFactory(stdout). BaseAppSettings(BaseSettings) is the parent for service-specific settings classes (service_name required, log_level default INFO, .env utf-8, case-insensitive, extra=ignore). utc_now() centralised in src/config/time.py for freeze_time. py.typed PEP 561 marker present. Closes INFR-07 + INFR-08.
- **2026-05-14 (Plan 01-03)**: line_provider FastAPI skeleton — build_app() factory, `python -m line_provider` entrypoint via uvicorn.run(factory=True, host=0.0.0.0, port=8000, log_config=None) (D-03, D-08). LineProviderSettings(BaseAppSettings) with env_prefix=LINE_PROVIDER_ and defaults host/port/rabbitmq_url (D-15). Lifespan calls configure_structlog before yield (D-17). RequestContextMiddleware uses A7 double-clear: defensive clear on entry + finally clear in cleanup (D-18). GET /health returns {"status":"ok"} without dep-pings (D-19). Closes INFR-01 (line-provider runnable skeleton), reaffirms INFR-07/INFR-08.
- **2026-05-14 (Plan 01-04)**: bet_maker FastAPI skeleton mirrors line_provider shape — build_app() factory, `python -m bet_maker` via uvicorn.run(factory=True, host=0.0.0.0, port=8001, log_config=None) (D-03, D-08). BetMakerSettings(BaseAppSettings) with env_prefix=BET_MAKER_ and typed DSN fields (PostgresDsn, AmqpDsn, HttpUrl) plus reconciliation_interval_s=30 (D-15). A7 double-clear middleware reused verbatim (D-18). Async Alembic skeleton: alembic.ini at repo root with NO sqlalchemy.url line; alembic/env.py imports BetMakerSettings and calls config.set_main_option('sqlalchemy.url', str(settings.postgres_dsn)) at module load — single source of truth (Anti-Pattern 7 mitigated). target_metadata=None placeholder until P3 declarative models land. Closes INFR-06 (Alembic async env wired), reaffirms INFR-01/INFR-07/INFR-08.
- **2026-05-14 (Plan 01-06)**: CI workflow .github/workflows/ci.yml — one quality job on ubuntu-latest with D-06 step chain (checkout v4 → setup-uv@v3 version 0.11.14 with uv.lock-keyed cache → uv python install 3.10.20 → uv sync --frozen --all-extras → ruff check + ruff format --check + mypy src + pytest -q). D-07 triggers: push on any branch, pull_request to main. D-08: no PG/RMQ services in P1 (deferred to P3/P5). D-09: single Python pin, no matrix. permissions: contents: read at workflow level (T-06-01) and concurrency cancel-in-progress (T-06-05) added. .pre-commit-config.yaml with all 9 D-10 hooks: ruff v0.15.12 (matched to pyproject pin — T-06-04), ruff-format, check-merge-conflict, end-of-file-fixer, trailing-whitespace, check-yaml, check-toml, check-added-large-files --maxkb=500 (T-06-06), local mypy strict via `uv run mypy --strict src` with pass_filenames=false (NOT mirrors-mypy — preserves pydantic.mypy plugin). Closes QA-03 (pre-commit). One Rule 3 auto-fix: out-of-scope trailing-whitespace fixes in two planning docs reverted and logged in .planning/phases/01-skeleton-infrastructure/deferred-items.md.
- **2026-05-14 (Plan 01-07)**: tests/ scaffold per D-12 — root conftest + line_provider/ + bet_maker/ + e2e/ (last empty until P6). Per-service `client` fixture: `httpx.AsyncClient + ASGITransport(app=build_app())`. 4 smoke tests collected (2 per service); `test_health_returns_status_ok` closes QA-10 (200 + `{status:ok}`); `test_health_echoes_request_id_header` is the only HTTP-level E2E proof of INFR-08 (X-Request-ID echo through RequestContextMiddleware). README.md expanded from 5-line placeholder to D-14 stub: Quick start (docker compose + curl both /health), Development (uv commands), Architecture and Reliability sections marked TODO with links to research/, CI badge with OWNER/REPO placeholder (P7 follow-up), explicit `guest:guest` disclaimer (loopback-only, test-task scope, not for production — T-07-01 mitigation). Project-wide convention established: REQ-IDs cited in test docstrings for grep-traceability. Closes QA-10; reaffirms INFR-08.
- **2026-05-14 (Plan 01-05)**: Docker-каркас закрывает Phase 1. Один параметризованный multi-stage Dockerfile (ARG SERVICE, FROM `python:3.10-slim-bookworm` pinned — Pitfall D6, builder с `uv sync --frozen --no-dev` → /opt/venv, runtime с non-root app:1000 + `USER app`, sentinel CMD — fail-loud на bare `docker run`). docker-compose.yml: 4 сервиса (postgres, rabbitmq, line-provider, bet-maker) + 2 named volumes (postgres_data, rabbitmq_data) + per-service `command: ["python","-m","<svc>"]` JSON-array exec-form (D-04 буквально, Pitfall D4 mitigation: Python = PID 1, SIGTERM долетает напрямую без shell-wrapper'а — альтернатива `CMD ["sh","-c","exec python -m $SERVICE"]` отвергнута, оставляет shell в startup chain). Healthchecks `pg_isready -U $${POSTGRES_USER}` (start_period 15s покрывает initdb — Pitfall D2), `rabbitmq-diagnostics -q check_port_connectivity` (start_period 15s — Pitfall D1), `curl -fsS http://localhost:{PORT}/health` (start_period 10s). depends_on с `condition: service_healthy` на app-сервисах (Pitfall D1). `hostname: rabbitmq` pinned (R10 — mnesia node name стабилен через recreate). Management UI bound `127.0.0.1:15672:15672` (D-05, D-08, T-05-01: закрывает Open Question — Management UI binding). **PG 5432 и AMQP 5672 НЕ публикуются** в host network (T-05-02, T-05-03). `stop_grace_period: 30s` на app-сервисах (Pitfall R11, T-05-05). .env.example в D-16-структуре (shared / postgres / rabbitmq / line-provider / bet-maker секции). **Live `docker compose up` smoke-test APPROVED оператором по 12-step protocol**: все 4 сервиса (healthy) за <=35s, оба /health 200 `{"status":"ok"}`, `docker volume ls | grep bsw_` shows postgres_data + rabbitmq_data, `docker compose port rabbitmq 15672` returns `127.0.0.1:15672`, `cat /proc/1/comm` в обоих app возвращает `python` (D-04 буквально подтверждён), `time docker compose down` exit 0 в <30s с JSON `*.shutdown` events видимыми в логах, volumes survive `down && up` без `-v`, `nc -z localhost 5432` exit non-zero, `nc -z localhost 5672` exit non-zero. Closes INFR-03/INFR-04/INFR-05. Phase 1 complete (7/7 plans).
- **2026-05-15 (Plan 02-01)**: Phase 2 Wave 0 foundations — единый блокирующий plan для всех 6 downstream P2 планов. `asgi-lifespan>=2.1,<3` в `dependency-groups.dev` (uv.lock +asgi-lifespan 2.1.0 +sniffio 1.3.1 transitive). `[tool.coverage.run]` source=src/line_provider branch=true + `[tool.coverage.report]` fail_under=85 (phase-gate Plan 02-07; bet-maker coverage self-declares в P3/P4). `tests/line_provider/conftest.py` переписан: split на `app` (lifespan-aware FastAPI через `LifespanManager(application)`) + `client` (AsyncClient bound to app fixture) — выбран split вместо yield-tuple, потому что сохраняет существующий контракт `client: AsyncClient` без правок test-файлов и Plan 02-07 integration-тесты смогут просить `app: FastAPI` параллельно через стандартный pytest fixture injection. RESEARCH Pattern 7 / Pitfall 1 mitigated: без LifespanManager все P2 integration-тесты упали бы на `AttributeError: app.state.event_store` (ASGITransport не триггерит lifespan). `REQUIREMENTS.md` LP-02 синхронизирован: `event_id (str)` → `UUID4 (client-generated)` с цитатой D-05 — drift между REQUIREMENTS.md и CONTEXT.md устранён. `02-VALIDATION.md`: skeleton-таблица заменена на canonical 20-task verification map (2-01-01 .. 2-07-06); frontmatter status=approved + nyquist_compliant=true + wave_0_complete=true; все Wave 0 Requirements и Validation Sign-Off `[x]`. Преждевременная правка `bet-maker schemas/messages.py` снята из Wave 0 — bet-maker schemas/messages.py создаётся только в P3/P5, D-05 уже фиксирует UUID; drift невозможен. Existing P1 baseline (`uv run pytest tests/line_provider -q`) остался зелёный (2 passed) после fixture upgrade. Closes QA-04 / QA-05 в части тестового скелета. No deviations.

### Open Todos

(None yet — populated by `/gsd-plan-phase` and during phase execution.)

### Blockers

(None.)

### Insights / Learnings

(Populated at phase transitions.)

## Session Continuity

### Last Session

- **Started:** 2026-05-15T08:08:03Z
- **Ended:** 2026-05-15T08:11:00Z
- **Activity:** Executed 02-01-PLAN.md (Phase 2 Wave 0 foundations) — единый блокирующий план для всех 6 downstream P2 планов. Task 1: `uv add --dev "asgi-lifespan>=2.1,<3"` (lockfile регенерирован) + добавлены `[tool.coverage.run]` source=src/line_provider branch=true и `[tool.coverage.report]` fail_under=85 в pyproject.toml. Task 2: REQUIREMENTS.md LP-02 синхронизирован (str → UUID4 client-generated, ссылка на D-05). Task 3: `tests/line_provider/conftest.py` переписан в две fixture (`app` lifespan-aware через `LifespanManager(application)` + `client` AsyncClient bound to app); существующие 2 P1-теста (`test_health_*`) остались зелёные без правок. Task 4: 02-VALIDATION.md skeleton заменён на canonical 20-task verification map; frontmatter status=approved + nyquist_compliant=true + wave_0_complete=true; преждевременная bet-maker правка убрана.
- **Outcome:** 4 atomic commits (b1d3eef chore deps+coverage, 6108550 docs REQUIREMENTS LP-02, 2ce6089 test conftest LifespanManager, 8fd4940 docs VALIDATION map) + финальный docs commit (02-01-SUMMARY.md + STATE.md + ROADMAP.md + REQUIREMENTS.md traceability). Verification: pytest 2 passed, mypy strict 0 errors на 13 source files, ruff check All checks passed, `grep -q "asgi-lifespan" pyproject.toml uv.lock` OK, `grep -q "wave_0_complete: true"` OK. No deviations. Phase 2 Wave 0 закрыт; Plan 02-02 (Schemas) и Plan 02-03 (State machine) разблокированы.

### Next Session

- **Recommended command:** `/gsd-execute-phase` (Phase 2 Plan 02 — Schemas, Wave 1) или параллельный запуск Plan 02-02 + Plan 02-03 (state machine pure helper, оба Wave 1 без shared code).
- **Goal:** Phase 2 Schemas (EventState enum + EventCreate/EventUpdate/Event/EventRead + EventFinishedMessage с frozen+extra=forbid+AwareDatetime+Coefficient annotated) и parallelно — pure state-machine helper (`is_transition_allowed` parametrized 9-case table).

### Open Questions for Next Phase

(From research/SUMMARY.md "Gaps to Address" — decide during Phase 1 / Phase 5 planning):

- **Classic vs quorum queues** — Phase 5 planning will lock this in. Research recommends classic for the test task (with app-level redelivery tracking); quorum noted as production upgrade.
- **Idempotency variant** — variant (b) at queue consumer is must-have (covered by Phase 5 `FOR UPDATE SKIP LOCKED` + `WHERE status='PENDING'`); variant (a) `Idempotency-Key` header on `POST /bet` deferred to README "what I'd add next".
- **Reconciliation interval** — Phase 6 default 30s via `BET_MAKER_RECONCILIATION_INTERVAL_S`.
- **RabbitMQ Management UI binding** — RESOLVED in Plan 01-05: bound `127.0.0.1:15672:15672`, verified by operator (Step 7 of smoke-test).

---
*State file initialized: 2026-05-13*
