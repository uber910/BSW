---
phase: 01-skeleton-infrastructure
verified: 2026-05-14T12:30:00Z
status: passed
score: 30/30 must-haves verified
overrides_applied: 0
requirements_covered:
  - INFR-01
  - INFR-02
  - INFR-03
  - INFR-04
  - INFR-05
  - INFR-06
  - INFR-07
  - INFR-08
  - QA-02
  - QA-03
  - QA-10
human_verified_by_operator:
  - "docker compose up brings 4 services to (healthy) in <35s"
  - "/health returns 200 on :8000 and :8001"
  - "RabbitMQ Management UI bound to 127.0.0.1:15672"
  - "PID 1 = python (exec-form D-04) inside both app containers"
  - "Graceful shutdown <30s with JSON shutdown logs"
  - "Named volumes persist across restart"
  - "PG/AMQP ports not exposed on host"
---

# Phase 01 — Skeleton + Infrastructure: Verification Report

**Phase Goal:** Заложить production-grade фундамент BSW Betting System: монорепо pyproject.toml + uv.lock, shared config-пакет, два FastAPI service skeleton'а (line_provider:8000, bet_maker:8001) с /health и RequestContextMiddleware (X-Request-ID), async Alembic env, Dockerfile + docker-compose с healthcheck'ами и graceful shutdown, GitHub Actions CI + pre-commit, smoke-тесты + README stub. Всё это докеризовано, `docker compose up` стартует 4 healthy сервиса, на оба `/health` приходит 200.

**Verified:** 2026-05-14T12:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Plan 01-01 — pyproject + uv.lock + tooling)

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 1  | Один корневой pyproject.toml существует и валиден по PEP 621 | VERIFIED | `pyproject.toml:1-81`; `python3 -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"` exits 0; `name = "bsw"`, `requires-python = ">=3.10,<3.11"` |
| 2  | uv.lock существует и закоммичен (>= 50 строк) | VERIFIED | `wc -l uv.lock` = 1040 строк; `uv lock --check` -> Resolved 68 packages |
| 3  | Distribution name = 'bsw'; requires-python = '>=3.10,<3.11' | VERIFIED | `pyproject.toml:2,6` |
| 4  | Все рантайм-зависимости пиннованы по диапазонам из CLAUDE.md | VERIFIED | `pyproject.toml:8-20` (fastapi, faststream[rabbit], sqlalchemy[asyncio], asyncpg, alembic, httpx, tenacity, structlog, pydantic, pydantic-settings, uvicorn[standard]) |
| 5  | Dev-группа содержит pytest/pytest-asyncio/pytest-cov/ruff/mypy/pre-commit | VERIFIED | `pyproject.toml:22-30` |
| 6  | hatch packages = ['src/line_provider', 'src/bet_maker', 'src/config'] (D-01) | VERIFIED | `pyproject.toml:36-37` |
| 7  | [tool.ruff]/[tool.mypy] корректно настроены (strict, ASYNC, pydantic.mypy) | VERIFIED | `pyproject.toml:39-71`; `select = ["E","W","F","I","B","UP","N","SIM","ASYNC","PL","RUF"]`, `strict = true`, `plugins = ["pydantic.mypy"]` |
| 8  | [tool.pytest.ini_options] asyncio_mode='auto', pythonpath=['src'] | VERIFIED | `pyproject.toml:73-77` |
| 9  | .gitignore исключает .venv/, __pycache__/, .env, кеши | VERIFIED | `.gitignore:9-31` — все требуемые паттерны на месте |

### Observable Truths (Plan 01-02 — src/config/ shared package)

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 10 | src/config/ существует как импортируемый shared пакет (D-02) | VERIFIED | `src/config/{__init__.py,logging.py,settings_base.py,time.py,py.typed}` все на месте; `uv run python -c "from config import configure_structlog, BaseAppSettings, utc_now"` -> "config import OK" |
| 11 | configure_structlog с processors=[contextvars merge, add_log_level, TimeStamper iso utc, dict_tracebacks, JSONRenderer] (D-17) | VERIFIED | `src/config/logging.py:19-31` — все 5 processors в точном порядке |
| 12 | BaseAppSettings(BaseSettings) — родитель с log_level, service_name | VERIFIED | `src/config/settings_base.py:7-22` |
| 13 | utc_now() возвращает aware UTC datetime | VERIFIED | `src/config/time.py:6-7` (`datetime.now(timezone.utc)`) |
| 14 | py.typed marker присутствует (PEP 561) | VERIFIED | `src/config/py.typed` exists |

### Observable Truths (Plan 01-03 — line_provider skeleton)

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 15 | src/line_provider/ — импортируемый пакет с правильным layout | VERIFIED | Все 11 файлов на месте: app.py, __main__.py, entrypoints/{lifespan,middleware,api/health}.py, settings/config.py, __init__.py x3, py.typed |
| 16 | `python -m line_provider` запускает uvicorn factory=True на 0.0.0.0:8000 (D-03, D-08) | VERIFIED | `src/line_provider/__main__.py:10-16`; `uvicorn.run("line_provider.app:build_app", factory=True, host=settings.host, port=settings.port)` |
| 17 | build_app() возвращает FastAPI с lifespan + middleware + /health (D-19) | VERIFIED | `src/line_provider/app.py:10-18` |
| 18 | Lifespan вызывает configure_structlog(settings.log_level) перед yield (D-17) | VERIFIED | `src/line_provider/entrypoints/lifespan.py:14-23` |
| 19 | RequestContextMiddleware: bind_contextvars + clear_contextvars в try/finally (D-18, A7) | VERIFIED | `src/line_provider/entrypoints/middleware.py:12-26` — двойной clear (defensive entry + finally cleanup), 3 occurrences of `clear_contextvars` per grep |
| 20 | GET /health -> 200 {"status":"ok"} (D-19) | VERIFIED | `src/line_provider/entrypoints/api/health.py:8-10` |
| 21 | LineProviderSettings env_prefix=LINE_PROVIDER_, host=0.0.0.0, port=8000 (D-15) | VERIFIED | `src/line_provider/settings/config.py:9-21` |

### Observable Truths (Plan 01-04 — bet_maker + alembic)

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 22 | src/bet_maker/ — импортируемый пакет (зеркальный line_provider, порт 8001) | VERIFIED | `src/bet_maker/{app,__main__,entrypoints/{lifespan,middleware,api/health},settings/config,__init__,py.typed}.py` все на месте |
| 23 | `python -m bet_maker` запускает uvicorn на 0.0.0.0:8001 (D-03) | VERIFIED | `src/bet_maker/__main__.py:10-16` |
| 24 | BetMakerSettings: postgres_dsn, rabbitmq_url, line_provider_base_url, reconciliation_interval_s=30, host=0.0.0.0, port=8001 (D-15) | VERIFIED | `src/bet_maker/settings/config.py:9-31` — все поля по D-15 |
| 25 | RequestContextMiddleware симметрично line_provider (A7) | VERIFIED | `src/bet_maker/entrypoints/middleware.py:12-26` — двойной clear |
| 26 | alembic.ini + alembic/env.py + script.py.mako + versions/.gitkeep (INFR-06) | VERIFIED | Все 4 файла на месте |
| 27 | alembic/env.py читает DSN из BetMakerSettings, alembic.ini НЕ содержит sqlalchemy.url (Anti-Pattern 7) | VERIFIED | `alembic/env.py:11,18-19` импортирует BetMakerSettings и вызывает `config.set_main_option("sqlalchemy.url", str(settings.postgres_dsn))`; `grep -c "^sqlalchemy.url" alembic.ini` = 0 |

### Observable Truths (Plan 01-05 — Dockerfile + docker-compose)

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 28 | Один параметризованный Dockerfile (ARG SERVICE), multi-stage, FROM python:3.10-slim-bookworm (D-04, D-06) | VERIFIED | `Dockerfile:1-50` — ARG PYTHON_VERSION=3.10-slim-bookworm, ARG SERVICE, builder + runtime stages, PYTHONUNBUFFERED=1, PYTHONDONTWRITEBYTECODE=1, USER app (non-root UID 1000), sentinel CMD для fail-loud bare run, runtime command через compose JSON-array exec-form |
| 29 | docker-compose.yml: 4 сервиса с healthchecks + service_healthy + named volumes + 127.0.0.1:15672 + PG/AMQP not exposed + stop_grace_period 30s (D-05, D-08) | VERIFIED | `docker-compose.yml`: 4 services confirmed; service_healthy count = 4; stop_grace_period count = 2; 127.0.0.1:15672 mapped; PG/AMQP ports `"5432:"/"5672:"` count = 0; postgres_data + rabbitmq_data named volumes; hostname: rabbitmq pinned; exec-form `command: ["python", "-m", ...]` для обоих app-сервисов (verified by operator: PID 1 = python in both) |
| 30 | .env.example: все ключи сгруппированы (# shared / # postgres / # rabbitmq / # line-provider / # bet-maker); .env in .gitignore (D-16) | VERIFIED | `.env.example:1-23` — 5 групп заголовков; `grep "^\.env$" .gitignore` = matched |

### Observable Truths (Plan 01-06 — CI + pre-commit)

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 31 | .github/workflows/ci.yml: ruff + ruff format + mypy strict + pytest на push/PR в main, single job, no matrix, no PG/RMQ services (D-06, D-07, D-08, D-09) | VERIFIED | `.github/workflows/ci.yml`: name=ci, triggers push/PR, single quality job, steps = checkout/setup-uv@v3/uv python install 3.10.20/uv sync --frozen --all-extras/ruff check/ruff format --check/mypy src/pytest -q; no `services:` или `matrix:` |
| 32 | .pre-commit-config.yaml: 9 хуков по D-10 (ruff, ruff-format, check-merge-conflict, end-of-file-fixer, trailing-whitespace, check-yaml, check-toml, check-added-large-files, mypy local) | VERIFIED | `.pre-commit-config.yaml:3-31` — ruff rev v0.15.12 совпадает с pyproject pin; mypy local hook с `entry: uv run mypy --strict src`, `pass_filenames: false`, `types_or: [python, pyi]` |

### Observable Truths (Plan 01-07 — tests + README)

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 33 | tests/ дерево создано по D-12 (conftest корень, line_provider/, bet_maker/, e2e/) | VERIFIED | `tests/{__init__.py, conftest.py, line_provider/{__init__,conftest,test_health}.py, bet_maker/{__init__,conftest,test_health}.py, e2e/__init__.py}` |
| 34 | 4 теста проходят: 2 на сервис, использующие ASGITransport (D-11, QA-10) | VERIFIED | `uv run pytest -q` -> `....  4 passed in 0.17s`; `uv run pytest --collect-only -q` подтверждает 2 теста на сервис |
| 35 | test_health_echoes_request_id_header — INFR-08 HTTP-level E2E trace | VERIFIED | `tests/line_provider/test_health.py:21-28` и `tests/bet_maker/test_health.py:21-28`; модуль и docstring содержат "INFR-08" (grep count = 3 в каждом файле) |
| 36 | README.md: H1, Quick start, Development, Architecture (TODO), Reliability (TODO), CI badge, guest:guest disclaimer (D-14) | VERIFIED | `README.md:1-98` — все разделы на месте, CI badge URL присутствует, дисклеймер про guest:guest и loopback на строке 35 |

**Score:** 36/36 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `pyproject.toml` | Root project config | VERIFIED | 81 строка, валиден TOML, все секции присутствуют |
| `uv.lock` | Pinned dep graph >= 50 lines | VERIFIED | 1040 строк; `uv lock --check` зелёный |
| `.python-version` | "3.10.20" | VERIFIED | Single line "3.10.20" |
| `.gitignore` | Python ignores + .env | VERIFIED | Все требуемые паттерны |
| `src/config/__init__.py` | Re-exports | VERIFIED | configure_structlog, BaseAppSettings, utc_now |
| `src/config/logging.py` | configure_structlog | VERIFIED | JSONRenderer + merge_contextvars + dict_tracebacks |
| `src/config/settings_base.py` | BaseAppSettings | VERIFIED | log_level + service_name |
| `src/config/time.py` | utc_now() | VERIFIED | timezone.utc |
| `src/config/py.typed` | PEP 561 marker | VERIFIED | empty file present |
| `src/line_provider/__main__.py` | uvicorn factory entry | VERIFIED | `uvicorn.run("line_provider.app:build_app", factory=True)` |
| `src/line_provider/app.py` | build_app() factory | VERIFIED | FastAPI + lifespan + middleware + health router |
| `src/line_provider/entrypoints/lifespan.py` | structlog setup | VERIFIED | configure_structlog called |
| `src/line_provider/entrypoints/middleware.py` | RequestContextMiddleware | VERIFIED | bind+clear (A7 double-clear) |
| `src/line_provider/entrypoints/api/health.py` | GET /health | VERIFIED | returns {"status":"ok"} |
| `src/line_provider/settings/config.py` | LineProviderSettings | VERIFIED | env_prefix=LINE_PROVIDER_, 0.0.0.0:8000 |
| `src/bet_maker/__main__.py` | uvicorn factory entry | VERIFIED | `uvicorn.run("bet_maker.app:build_app", factory=True)` |
| `src/bet_maker/app.py` | build_app() factory | VERIFIED | FastAPI + lifespan + middleware + health router |
| `src/bet_maker/entrypoints/*` | mirror line_provider | VERIFIED | lifespan + middleware + api/health все на месте |
| `src/bet_maker/settings/config.py` | BetMakerSettings | VERIFIED | env_prefix=BET_MAKER_, 0.0.0.0:8001, postgres_dsn, rabbitmq_url, line_provider_base_url, reconciliation_interval_s |
| `alembic.ini` | Alembic config без sqlalchemy.url | VERIFIED | script_location=alembic, no hardcoded DSN |
| `alembic/env.py` | Async env reading BetMakerSettings | VERIFIED | imports BetMakerSettings; async_engine_from_config; run_async_migrations |
| `alembic/script.py.mako` | Migration template | VERIFIED | standard Alembic 1.18 async template |
| `alembic/versions/.gitkeep` | empty versions dir | VERIFIED | present |
| `Dockerfile` | Multi-stage parametrised | VERIFIED | builder + runtime, slim-bookworm, non-root, sentinel CMD |
| `.dockerignore` | Excludes .venv/.git/tests | VERIFIED | All required patterns present |
| `docker-compose.yml` | 4 services + healthchecks + volumes | VERIFIED | 4 services + 4 service_healthy + named volumes + 127.0.0.1:15672 |
| `.env.example` | All env vars grouped | VERIFIED | 5 group headers, no secrets |
| `.github/workflows/ci.yml` | Quality job | VERIFIED | ruff + mypy strict + pytest single job |
| `.pre-commit-config.yaml` | 9 hooks D-10 | VERIFIED | ruff/ruff-format/5 pre-commit-hooks/local mypy |
| `tests/line_provider/test_health.py` | ASGI smoke + INFR-08 trace | VERIFIED | 2 tests, INFR-08 trace |
| `tests/bet_maker/test_health.py` | ASGI smoke + INFR-08 trace | VERIFIED | 2 tests, INFR-08 trace |
| `tests/conftest.py` + per-service conftest.py | client fixture | VERIFIED | ASGITransport client fixture present per service |
| `tests/e2e/__init__.py` | Empty package (D-12) | VERIFIED | present |
| `README.md` | Stub D-14 + disclaimer | VERIFIED | All required sections, CI badge, guest:guest disclaimer |

---

## Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| pyproject.toml | uv.lock | `uv lock` | WIRED | `uv lock --check` -> "Resolved 68 packages in 2ms" |
| pyproject.toml [tool.hatch...wheel] | src/{line_provider,bet_maker,config} | packages list | WIRED | `packages = ["src/line_provider", "src/bet_maker", "src/config"]` |
| src/line_provider/app.py | entrypoints/lifespan.py | FastAPI(lifespan=lifespan) | WIRED | `lifespan=lifespan` at app.py:14 |
| src/line_provider/app.py | entrypoints/middleware.py | add_middleware | WIRED | app.py:16 |
| src/line_provider/app.py | entrypoints/api/health.py | include_router | WIRED | app.py:17 |
| src/line_provider/entrypoints/lifespan.py | config.logging.configure_structlog | import + call | WIRED | lifespan.py:9,16 |
| src/line_provider/__main__.py | line_provider.app:build_app | uvicorn.run factory=True | WIRED | __main__.py:11-15 |
| src/bet_maker/app.py | entrypoints/lifespan.py | FastAPI(lifespan=lifespan) | WIRED | bet_maker/app.py:14 |
| src/bet_maker/app.py | entrypoints/api/health.py | include_router | WIRED | bet_maker/app.py:17 |
| src/bet_maker/__main__.py | bet_maker.app:build_app | uvicorn.run factory=True | WIRED | bet_maker/__main__.py:11-15 |
| alembic/env.py | BetMakerSettings.postgres_dsn | import + set_main_option | WIRED | alembic/env.py:11,18-19 |
| docker-compose line-provider | Dockerfile (ARG SERVICE=line_provider) | build args | WIRED | docker-compose.yml:42-43 |
| docker-compose bet-maker | Dockerfile (ARG SERVICE=bet_maker) | build args | WIRED | docker-compose.yml:72-73 |
| docker-compose line-provider.command | python -m line_provider | exec-form JSON | WIRED | docker-compose.yml:44 (operator confirmed PID 1 = python) |
| docker-compose bet-maker.command | python -m bet_maker | exec-form JSON | WIRED | docker-compose.yml:74 |
| docker-compose app-services.depends_on | postgres + rabbitmq | condition: service_healthy | WIRED | 4 occurrences |
| .github/workflows/ci.yml | pyproject.toml + uv.lock | uv sync --frozen | WIRED | ci.yml:35 |
| tests/line_provider/test_health.py | src/line_provider/app.py | from line_provider.app import build_app | WIRED | via conftest fixture |
| tests/bet_maker/test_health.py | src/bet_maker/app.py | from bet_maker.app import build_app | WIRED | via conftest fixture |
| tests/*/test_health.py::test_health_echoes_request_id_header | src/*/entrypoints/middleware.py (INFR-08) | asserts X-Request-ID present | WIRED | passing on pytest run |
| README.md | .github/workflows/ci.yml | CI badge URL | WIRED | README.md:3 (OWNER/REPO placeholder — known follow-up for P7) |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| ruff lint clean | `uv run ruff check .` | "All checks passed!" | PASS |
| ruff format clean | `uv run ruff format --check .` | "34 files already formatted" | PASS |
| mypy strict on src | `uv run mypy --strict src` | "Success: no issues found in 24 source files" | PASS |
| pytest collects + passes 4 tests | `uv run pytest -q` | "4 passed in 0.17s" | PASS |
| uv.lock not empty/stale | `uv lock --check` + `wc -l uv.lock` | "Resolved 68 packages" + 1040 lines | PASS |
| Shared config imports | `uv run python -c "from config import configure_structlog, BaseAppSettings, utc_now"` | "config import OK" | PASS |
| build_app imports both services | `uv run python -c "from line_provider.app import build_app; from bet_maker.app import build_app"` | "build_app imports OK" | PASS |
| pytest collect-only confirms 4 tests | `uv run pytest --collect-only -q` | 4 tests, 2 per service | PASS |
| docker compose up -> 4 (healthy) in <35s | `docker compose up -d && sleep 35 && docker compose ps` | verified by operator | PASS (operator) |
| GET /health 200 on :8000 and :8001 | `curl :8000/health` + `curl :8001/health` | verified by operator | PASS (operator) |
| RabbitMQ UI on 127.0.0.1:15672 | `docker compose port rabbitmq 15672` | verified by operator | PASS (operator) |
| PID 1 = python (exec-form) | `docker compose exec X cat /proc/1/comm` | verified by operator | PASS (operator) |
| Graceful shutdown <30s + JSON shutdown logs | `time docker compose down` + logs | verified by operator | PASS (operator) |
| Named volumes persist `down && up` | `docker volume ls \| grep bsw_` after cycle | verified by operator | PASS (operator) |
| PG/AMQP ports not exposed | `nc -z localhost 5432/5672` | verified by operator | PASS (operator) |

---

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| ----------- | ------------ | ----------- | ------ | -------- |
| INFR-01 | 01-01, 01-03, 01-04 | Монорепо src/ layout | SATISFIED | `pyproject.toml:36-37` packages list; `src/{line_provider,bet_maker,config}/` все на месте |
| INFR-02 | 01-01 | uv + uv.lock коммитится | SATISFIED | `uv.lock` (1040 lines), `uv lock --check` зелёный |
| INFR-03 | 01-05 | Dockerfile python:3.10-slim-bookworm (без rolling) | SATISFIED | `Dockerfile:2` `ARG PYTHON_VERSION=3.10-slim-bookworm`; operator confirmed builds work |
| INFR-04 | 01-05 | docker-compose 4 сервиса | SATISFIED | `docker-compose.yml` -> postgres, rabbitmq, line-provider, bet-maker; operator confirmed (healthy) |
| INFR-05 | 01-05 | Healthcheck PG/RMQ + service_healthy | SATISFIED | `docker-compose.yml:14,32` healthchecks; 4x service_healthy depends_on |
| INFR-06 | 01-04 | Alembic async + env.py читает DSN из settings | SATISFIED | `alembic/env.py:11,18-19,42-50`; `alembic.ini` без hardcoded sqlalchemy.url |
| INFR-07 | 01-02, 01-05 | .env.example + pydantic-settings | SATISFIED | `src/config/settings_base.py` BaseAppSettings; `.env.example` 5 групп ключей |
| INFR-08 | 01-02, 01-03, 01-04, 01-07 | structlog JSON + bind_contextvars для request_id | SATISFIED | `src/config/logging.py:19-31` processors с merge_contextvars + JSONRenderer; `src/{line_provider,bet_maker}/entrypoints/middleware.py` bind+clear; HTTP-level E2E через `test_health_echoes_request_id_header` |
| QA-02 | 01-01, 01-06 | ruff check/format clean + config в pyproject | SATISFIED | `pyproject.toml:39-54` ruff config; `uv run ruff check .` = "All checks passed!"; `ruff format --check` = "34 files already formatted" |
| QA-03 | 01-06 | pre-commit hooks: ruff, mypy, end-of-file, trailing-whitespace, toml-lint | SATISFIED | `.pre-commit-config.yaml` все 9 хуков (D-10), ruff rev совпадает с pyproject pin |
| QA-10 | 01-06, 01-07 | GitHub Actions CI: lint + typecheck + unit | SATISFIED | `.github/workflows/ci.yml` quality job со всеми шагами; `uv run pytest -q` зелёный (4 tests) |

**Orphaned requirements:** None. REQUIREMENTS.md перечисляет 11 IDs для Phase 1; все 11 покрыты планами 01-01..01-07 (см. `requirements:` frontmatter в каждом плане). QA-01 (`mypy --strict`) явно отмечен в REQUIREMENTS.md:174 как enforced с Phase 1 но owned by Phase 7 — поэтому не входит в P1 requirements list, и mypy strict gate уже работает (verified above).

---

## Anti-Pattern Scan

| File | Pattern | Severity | Impact |
| ---- | ------- | -------- | ------ |
| src/, tests/, alembic/ | TODO/FIXME/XXX/HACK | None | No matches in source code (only in README.md "TODO" for Architecture/Reliability sections, which is intentional per D-14 spec) |
| src/, tests/, alembic/ | Emoji | None | Programmatic scan: 0 matches across .py/.toml/.yaml/.yml/.ini/.mako files |
| key src files | Inline comments | None | 11 key source files inspected: 0 inline `#` comments — project rule "no comments unless asked" respected |
| alembic.ini | hardcoded sqlalchemy.url | None | `grep -c "^sqlalchemy.url" alembic.ini` = 0 (Anti-Pattern 7 mitigated) |
| Dockerfile | rolling python:3.10-slim | None | Pinned `python:3.10-slim-bookworm` (D-06, Pitfall D6) |
| Dockerfile | sh/bash CMD wrapper | None | Only sentinel `CMD ["python", "-c", ...]` for fail-loud bare-run; runtime command in compose JSON-array exec-form (operator confirmed PID 1 = python) |
| docker-compose.yml | PG/AMQP ports exposed | None | `grep -c '"5432:\|"5672:' docker-compose.yml` = 0 |
| middleware.py | Missing clear_contextvars in finally | None | Both middlewares double-clear (defensive + finally), 3 grep matches per file |
| CI workflow | services PG/RMQ in CI | None | `grep -c "^\s*services:" ci.yml` = 0 (D-08 respected — deferred to P3/P5) |

---

## Human Verification Required

None — operator pre-verified the docker-compose live-stack checkpoint (Plan 01-05 Task 4) on this phase covering all 11 acceptance criteria for that gate (recorded in CONTEXT.md and SUMMARY 01-05). Per task instruction, no additional human verification is requested because no new gaps were found by automated checks.

---

## Gaps Summary

No gaps. Phase 01 goal fully achieved:

- **Build foundation (Plan 01-01):** pyproject.toml + uv.lock + .python-version + .gitignore — все 9 truths verified.
- **Shared config (Plan 01-02):** src/config/ с logging.py, settings_base.py, time.py, py.typed — все 5 truths verified; `from config import ...` импортируется обоими сервисами.
- **line_provider skeleton (Plan 01-03):** 11 файлов под src/line_provider/, build_app + lifespan + middleware (двойной clear_contextvars per A7) + /health; настройки на 0.0.0.0:8000 — все 7 truths verified.
- **bet_maker skeleton + alembic (Plan 01-04):** 11 файлов под src/bet_maker/ + 4 файла alembic, env.py читает DSN из BetMakerSettings (Anti-Pattern 7 закрыт) — все 6 truths verified.
- **Docker (Plan 01-05):** Multi-stage parametrised Dockerfile (slim-bookworm, non-root UID 1000, sentinel CMD) + docker-compose 4 сервиса с service_healthy/named volumes/127.0.0.1:15672/stop_grace_period 30s + .env.example с группами — все 3 truths verified, плюс operator-confirmed: PID 1 = python, graceful shutdown, volumes durable, PG/AMQP not exposed.
- **CI + pre-commit (Plan 01-06):** ci.yml с ruff+mypy strict+pytest на push/PR (single job, no matrix, no PG/RMQ services); .pre-commit-config.yaml с 9 хуками D-10, ruff rev совпадает с pyproject pin — все 2 truths verified.
- **Tests + README (Plan 01-07):** 4 теста через ASGITransport проходят (2 на сервис, включая `test_health_echoes_request_id_header` как HTTP-level E2E доказательство INFR-08); README.md с обязательными разделами + CI badge + guest:guest disclaimer — все 4 truths verified.

Все 11 Phase 1 requirements (INFR-01..08, QA-02, QA-03, QA-10) удовлетворены. Все 6 ROADMAP.md success criteria для Phase 1 закрыты (по automated checks + operator-verified checkpoint). Качественные ворота на месте: ruff clean, ruff format clean, mypy strict clean (24 source files), pytest зелёный (4 tests), uv.lock детерминирован. Code-style правила проекта соблюдены (no emoji, no inline comments в source). Фаза готова к переходу к Phase 2 (line-provider domain) и Phase 3 (bet-maker DB) параллельно.

Known follow-up (не блокер для P1, recorded для P7): CI badge URL в README.md содержит OWNER/REPO placeholder — заменяется после `git remote add origin` в Phase 7 polish.

---

_Verified: 2026-05-14T12:30:00Z_
_Verifier: Claude (gsd-verifier)_
