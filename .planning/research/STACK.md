# Stack Research

**Domain:** Asynchronous Python event-driven microservices (sports-betting test task)
**Researched:** 2026-05-13
**Confidence:** HIGH

All versions below were verified against PyPI / Context7 / official docs on 2026-05-13. The stack itself is fixed by the test-task constraints (FastAPI + asyncpg + SQLAlchemy 2.0 + RabbitMQ + FastStream + Alembic + structlog + uv + ruff + mypy + pytest); this document validates currency, pins versions, and adds the small set of complementary libraries the project genuinely needs.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.10.20 (latest 3.10.x patch) | Runtime — fixed by TZ as "рекомендованная" | TZ-fixed. Note: 3.10 reaches EOL on 2026-10-31; pyproject must pin `requires-python = ">=3.10,<3.11"` to make the constraint explicit. Confidence: HIGH (endoflife.date). |
| FastAPI | 0.136.1 (pin `>=0.115,<0.137` for safety) | HTTP framework for both `line-provider` and `bet-maker` | TZ-recommended. Native Pydantic v2, automatic OpenAPI, async-first. The version floor `>=0.115` is the safe lower bound for the FastStream FastAPI plugin auto-lifespan behavior (it requires `>=0.112.2`). Confidence: HIGH. |
| FastStream | 0.6.7 (pin `>=0.6,<0.7`) | RabbitMQ client + FastAPI integration | Officially supports FastAPI via `faststream.rabbit.fastapi.RabbitRouter`. Declarative `@router.subscriber` / `@router.publisher`. Pulls `aio-pika>=9,<10` automatically — no need to declare aio-pika directly. Confidence: HIGH (Context7 + PyPI). |
| SQLAlchemy | 2.0.49 (pin `>=2.0.40,<2.1`) | ORM + Core for `bet-maker` | TZ-fixed. 2.0 async API (`AsyncSession`, `async_sessionmaker`, `Mapped[...]` typed style) is the modern way; required for Unit of Work + Repository pattern. **Stay on 2.0.x**, do not move to 2.1 alphas. Confidence: HIGH. |
| asyncpg | 0.31.0 | PostgreSQL async driver under SQLAlchemy | TZ-fixed. Fastest async PG driver in Python; SQLAlchemy 2.0 supports it natively via `postgresql+asyncpg://`. Confidence: HIGH. |
| Pydantic | 2.13.4 (pin `>=2.9,<3`) | Schemas (HTTP + AMQP message bodies) | FastAPI 0.136 requires `pydantic>=2.9`; FastStream uses Pydantic for message validation. Single source of truth for DTOs across HTTP and queue. Confidence: HIGH. |
| Alembic | 1.18.4 | DB migrations for `bet-maker` | TZ-fixed. Standard for SQLAlchemy. Use `async` template (`alembic init -t async`) to match the async engine. Confidence: HIGH. |
| RabbitMQ | 4.2 (`rabbitmq:4.2-management` image) | Message broker | TZ-fixed. 4.2 is community-supported through July 2026 — safe for the lifespan of a test task. Avoid 4.3 (just released April 2026, less battle-tested) and avoid 3.13 (community support ended 2024-09). Use the `-management` tag for the UI on :15672 required by TZ. Confidence: HIGH. |
| PostgreSQL | 16.14 (`postgres:16-alpine` image) | Persistent storage for `bet-maker` | TZ-fixed. PG 16 is the conservative production-default choice in 2026 (EOL 2028-11). PG 17 and 18 also work; 16 is preferred for "show I picked a stable LTS-style line" signal. Confidence: HIGH. |

### Supporting Libraries

Libraries the original spec did not mention but the project genuinely needs:

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pydantic-settings** | 2.14.1 | Typed `Settings` class loaded from env / `.env` | **Add to the stack.** Both services need typed config (PG DSN, AMQP URL, log level, reconciliation interval). Replaces ad-hoc `os.getenv`. Confidence: HIGH. |
| **httpx** | 0.28.1 | Async HTTP client for `bet-maker` → `line-provider` calls (reconciliation job, `/events` proxy, integration tests via `AsyncClient`) | **Add to the stack** (the project context already lists it). Same `AsyncClient` is used by both the production reconciliation job and the test suite — single library, two purposes. Confidence: HIGH. |
| **tenacity** | 9.1.4 | Retries with exponential backoff for transient AMQP / HTTP / PG errors | **Add.** Used in the reconciliation job and on startup connection retries to RabbitMQ/Postgres. Decorator-based, type-friendly. Confidence: HIGH. |
| **uvicorn** | 0.46.0 (with `[standard]` extras) | ASGI server for FastAPI | Use `uvicorn[standard]` to get `httptools` + `uvloop` for ~20% faster event loop. In Docker, run as `python -m uvicorn` to avoid PATH issues. Confidence: HIGH. |
| **orjson** | 3.11.9 | Faster JSON encoder | Optional, only if profiling shows JSON as a hotspot. Wire it via `FastAPI(default_response_class=ORJSONResponse)` and as the structlog renderer. **Do not add proactively** for a test task — premature optimization signal. Mentioned for completeness; **default: skip**. |
| **greenlet** | 3.5.0 | SQLAlchemy async runtime dependency | Transitive dep of SQLAlchemy 2.0 async; no need to declare directly, but pin it indirectly if you want reproducible builds. Confidence: HIGH. |
| **aio-pika** | 9.6.2 | Low-level AMQP client | **DO NOT declare directly.** FastStream owns this dependency (`aio-pika>=9,<10`). Listing it manually creates a second source of truth that drifts. Mentioned only so the version is auditable. |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| **uv** | 0.11.14 | Package manager + venv + lockfile | TZ-fixed. Replaces pip + pip-tools + virtualenv. Use `uv sync --frozen` in CI and Docker; `uv lock` to regenerate. Pin via `tool.uv` table in `pyproject.toml`. Confidence: HIGH. |
| **ruff** | 0.15.12 | Linter + formatter | TZ-fixed. Replaces flake8 + isort + black. Enable rule sets: `E`, `W`, `F`, `I`, `B`, `UP`, `N`, `SIM`, `ASYNC`, `PL`, `RUF`. Confidence: HIGH. |
| **mypy** | 2.1.0 | Static type checker (strict mode) | TZ-fixed. Strict mode is non-negotiable per TZ. Configure `[tool.mypy] strict = true` plus `plugins = ["pydantic.mypy"]`. Confidence: HIGH. |
| **pytest** | 9.0.3 | Test runner | TZ-fixed. v9 supports pytest-asyncio 1.x. Confidence: HIGH. |
| **pytest-asyncio** | 1.1.0 | Async test support | TZ-listed. Use `asyncio_mode = "auto"` in `pyproject.toml`. Requires `pytest>=8.2`. **Prefer this over anyio's pytest plugin** because FastAPI ecosystem assumes asyncio and TestClient is asyncio-only; mixing trio adds zero value here. Confidence: HIGH. |
| **pytest-cov** | 7.1.0 | Coverage reporting | **Add to the stack.** TZ requires test coverage as a quality signal; need numbers in CI. Confidence: HIGH. |
| **anyio** | 4.13.0 | Transitive dep (FastAPI/httpx/FastStream all use it) | No need to declare directly. Mentioned for version transparency. |
| **structlog** | 25.5.0 | Structured JSON logging | TZ-fixed. Configure `processors=[contextvars, timestamper, add_log_level, JSONRenderer()]`. Bind request_id at the middleware layer. Confidence: HIGH. |
| **pre-commit** | 4.6.0 | Git hooks orchestration | TZ-fixed. Hooks: `ruff check --fix`, `ruff format`, `mypy`, `check-merge-conflict`, `end-of-file-fixer`. Confidence: HIGH. |

### Infrastructure (Docker)

| Image | Tag | Notes |
|-------|-----|-------|
| Python base | `python:3.10-slim-bookworm` | **Pin to `bookworm` explicitly**, not the rolling `3.10-slim` tag (which now resolves to `trixie` as of May 2026 and ships glibc/openssl changes that may break asyncpg wheels). Bookworm is the conservative choice for a test task. |
| PostgreSQL | `postgres:16-alpine` | Smaller image, faster pulls in CI. Add a `healthcheck` running `pg_isready`. |
| RabbitMQ | `rabbitmq:4.2-management-alpine` | `-management` is required by TZ for the UI on :15672. `alpine` cuts image size by ~60%. |

## Installation

`pyproject.toml` (single-file, monorepo style, two packages under `src/`):

```toml
[project]
name = "bsw"
version = "0.1.0"
requires-python = ">=3.10,<3.11"
dependencies = [
    "fastapi>=0.115,<0.137",
    "uvicorn[standard]>=0.46,<0.47",
    "pydantic>=2.13,<3",
    "pydantic-settings>=2.14,<3",
    "faststream[rabbit]>=0.6,<0.7",
    "sqlalchemy[asyncio]>=2.0.40,<2.1",
    "asyncpg>=0.31,<0.32",
    "alembic>=1.18,<2",
    "httpx>=0.28,<0.29",
    "tenacity>=9.1,<10",
    "structlog>=25.5,<26",
]

[dependency-groups]
dev = [
    "pytest>=9.0,<10",
    "pytest-asyncio>=1.1,<2",
    "pytest-cov>=7.1,<8",
    "ruff>=0.15,<0.16",
    "mypy>=2.1,<3",
    "pre-commit>=4.6,<5",
]

[tool.uv.workspace]
members = ["src/line_provider", "src/bet_maker"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.mypy]
strict = true
plugins = ["pydantic.mypy"]
```

Install commands:

```bash
# First-time setup
uv sync                       # creates .venv and installs runtime + dev deps from uv.lock

# CI / Docker
uv sync --frozen --no-dev     # production install, fails if lock is stale

# Updating
uv lock --upgrade-package faststream
```

## FastStream + FastAPI Integration — Pattern & Caveats

This is the single highest-risk integration point in the project. Confirmed details:

- **Officially supported.** FastStream ships `faststream.rabbit.fastapi.RabbitRouter` specifically for this use case.
- **API:**
  ```python
  from fastapi import FastAPI
  from faststream.rabbit.fastapi import RabbitRouter

  router = RabbitRouter(
      "amqp://guest:guest@rabbitmq:5672/",
      schema_url="/asyncapi",
      include_in_schema=True,
  )

  @router.subscriber("events.finished")  # AMQP consumer
  async def on_event_finished(msg: EventFinishedMessage) -> None: ...

  @router.get("/health")                  # regular FastAPI route
  async def health() -> dict[str, str]: ...

  app = FastAPI()
  app.include_router(router)
  ```
- **Lifespan is automatic** for `fastapi >= 0.112.2`. We are pinning `>=0.115`, so no manual lifespan wiring is needed. For older FastAPI you would have to pass `FastAPI(lifespan=router.lifespan_context)`.
- **Manual ack works** inside FastAPI-integrated subscribers identically to standalone FastStream: inject `msg: RabbitMessage` and call `await msg.ack() / nack() / reject()`. This is exactly what the TZ's "manual ack" reliability requirement needs.
- **AsyncAPI docs** are served at `/asyncapi` (configurable). Free documentation artefact for the reviewer.
- **Caveat — publishing from HTTP routes.** Use `router.broker.publish(...)`; do not instantiate a separate `RabbitBroker` for publishing inside HTTP handlers (it bypasses the shared connection pool). For `line-provider`, the cleanest pattern is a tiny `EventBus` facade that wraps `router.broker.publish` and is injected via FastAPI `Depends`.
- **Caveat — testing.** Use `TestRabbitBroker(router.broker)` (in-memory) for unit-ish tests; spin up a real RabbitMQ container for integration tests. `TestRabbitBroker` patches publishers/subscribers so handlers are invoked synchronously inside `asyncio`.

Confidence on FastStream/FastAPI integration: **HIGH** (verified against FastStream `/ag2ai/faststream` Context7 docs and `faststream.ag2.ai/latest/getting-started/integrations/fastapi/`).

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastStream (RabbitRouter) | aio-pika directly | Only if you need exotic AMQP features FastStream doesn't expose (custom frame handling, low-level confirms). For this TZ — never; FastStream wraps aio-pika and gives you Pydantic validation, DI, AsyncAPI docs for free. |
| FastStream (RabbitRouter) | aiormq directly | Strictly lower-level than aio-pika. Not relevant here. |
| FastStream (RabbitRouter) | pika (sync) | Synchronous; would break the "fully async" TZ requirement. Reject. |
| asyncpg + SQLAlchemy 2.0 | psycopg3 + SQLAlchemy 2.0 (async mode) | psycopg3 supports async natively, but asyncpg is still ~2x faster on raw throughput. Use psycopg3 only if you need server-side cursors with COPY streaming — irrelevant for a bet-history workload. |
| pydantic-settings | dynaconf, environs | pydantic-settings reuses your existing Pydantic v2 validators — zero extra concepts. The alternatives add a parallel validation system. |
| pytest-asyncio | anyio pytest plugin | anyio's plugin supports both asyncio and trio backends. We use only asyncio (FastAPI, FastStream, SQLAlchemy async are asyncio-only). pytest-asyncio is the simpler, more widely-used choice. |
| structlog | loguru | structlog produces structured JSON logs natively and integrates cleanly with stdlib `logging`. loguru is more "convenient print()" and less structured. For a "show production maturity" test task, structlog signals intent better. |
| uv | poetry | Poetry is fine, but uv is ~10–100x faster, has a built-in lockfile, and is what the TZ already specifies. No reason to deviate. |
| httpx | aiohttp | aiohttp is older and has a more sprawling API. httpx has the same `requests`-style API for sync and async, and FastAPI's own `TestClient` uses it internally. Single library for prod + tests. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Python 3.9 or earlier | TZ-fixed at 3.10; PEP 604 `X \| Y` union syntax + `match` statements are used | Python 3.10.x |
| Pydantic v1 | EOL, much slower, incompatible API with FastAPI 0.100+ and FastStream | Pydantic 2.13.x |
| SQLAlchemy 1.4 legacy style | TZ implies 2.0 idioms; mixing styles signals immaturity | SQLAlchemy 2.0 typed `Mapped[...]` + `select()` style |
| Declaring `aio-pika` directly | Drifts away from the FastStream-pinned version, double source of truth | Let `faststream[rabbit]` pull it; never import aio-pika in your own code (use FastStream's `RabbitQueue`/`RabbitExchange` wrappers) |
| `databases` library | Abandoned (no commits since 2023), still depends on SQLAlchemy 1.4 patterns | SQLAlchemy 2.0 async directly |
| flake8 + black + isort | Three tools, three configs, three pre-commit entries | ruff (does all three, faster) |
| `requirements.txt` + `pip install` | No deterministic builds, no resolver guarantees | `pyproject.toml` + `uv.lock` + `uv sync --frozen` |
| `pika` (synchronous) | Synchronous; would force `run_in_executor` wrappers and break the async-throughout requirement | FastStream (which wraps async aio-pika) |
| Rolling `python:3.10-slim` Docker tag | Resolved to `trixie` in May 2026 — newer libc/OpenSSL may break asyncpg wheels in the wild | `python:3.10-slim-bookworm` (pinned distro) |
| RabbitMQ 3.13 image | Community support ended 2024-09 | `rabbitmq:4.2-management-alpine` |
| `python -m unittest` | Inferior async support, no fixtures, no parametrize | pytest + pytest-asyncio |

## Stack Patterns by Variant

**If the reviewer runs `docker compose up` and nothing else:**
- Both services must bind to `0.0.0.0`, not `127.0.0.1`
- Use service names (`postgres`, `rabbitmq`) as hosts in connection URLs, not `localhost`
- All env vars driven through `pydantic-settings` reading from `docker-compose.yml`'s `environment:` block

**If the reviewer reads code first (likely for a test task):**
- Strict `mypy` plus `ruff` zero warnings is the first impression
- Single `pyproject.toml` at repo root is easier to skim than per-package configs
- Keep dependency list minimal — every extra library is something to justify

**If reconciliation job needs to call `line-provider` over HTTP:**
- Use `httpx.AsyncClient` as a singleton (created in lifespan, injected via `Depends`)
- Wrap calls in `tenacity.retry` with `wait_exponential` + `stop_after_attempt(5)`
- Never share an `AsyncClient` instance across event loops (pytest fixture scope must match)

## Version Compatibility Matrix

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `fastapi==0.136.1` | `pydantic>=2.9` | FastAPI's own requirement; we pin `pydantic>=2.13`. |
| `faststream==0.6.7` | `fastapi>=0.112.2` for auto-lifespan | Pinning `fastapi>=0.115` is well above the floor. |
| `faststream[rabbit]==0.6.7` | `aio-pika>=9,<10` | Transitive — do not pin separately. |
| `pydantic-settings==2.14.1` | `pydantic>=2.7` | Compatible with our 2.13. |
| `sqlalchemy==2.0.49 [asyncio]` | `asyncpg>=0.30`, `greenlet>=3` | Driver URL: `postgresql+asyncpg://`. |
| `alembic==1.18.4` | `sqlalchemy>=1.4.23` | Use `alembic init -t async` template. |
| `pytest-asyncio==1.1.0` | `pytest>=8.2,<10` | Compatible with our pytest 9.x. |
| `pytest-cov==7.1.0` | `pytest>=6` | Compatible. |
| `httpx==0.28.1` | Python 3.8+ | Used by FastAPI's `TestClient` internally — same lib for prod + tests. |
| `mypy==2.1.0` | Python 3.10+ | Strict mode + `pydantic.mypy` plugin. |
| Python 3.10.20 | All of the above | Note: EOL 2026-10-31. For a test task delivered in May 2026, fine. |

## Sources

- `/ag2ai/faststream` (Context7) — FastAPI integration patterns, manual ack, TestRabbitBroker, RabbitQueue/Exchange — **HIGH confidence**
- `/fastapi/fastapi` (Context7) — version listing — **HIGH confidence**
- `/websites/sqlalchemy_en_20` (Context7) — async API — **HIGH confidence**
- https://pypi.org/pypi/faststream/json — version 0.6.7, released 2026-03-01, requires aio-pika `>=9,<10` — **HIGH confidence**
- https://pypi.org/pypi/fastapi/json — version 0.136.1, requires `pydantic>=2.9` — **HIGH confidence**
- https://pypi.org/pypi/sqlalchemy/json — version 2.0.49 — **HIGH confidence**
- https://pypi.org/pypi/asyncpg/json — version 0.31.0, supports Python 3.9–3.14, PG 9.5–18 — **HIGH confidence**
- https://pypi.org/pypi/pydantic/json — version 2.13.4 (2026-05-06) — **HIGH confidence**
- https://pypi.org/pypi/pydantic-settings/json — version 2.14.1 (2026-05-08), requires `pydantic>=2.7` — **HIGH confidence**
- https://pypi.org/pypi/alembic/json — version 1.18.4 — **HIGH confidence**
- https://pypi.org/pypi/structlog/json — version 25.5.0 — **HIGH confidence**
- https://pypi.org/pypi/httpx/json — version 0.28.1 — **HIGH confidence**
- https://pypi.org/pypi/tenacity/json — version 9.1.4 (2026-02-07) — **HIGH confidence**
- https://pypi.org/pypi/pytest/json — version 9.0.3 — **HIGH confidence**
- https://pypi.org/pypi/pytest-asyncio/json — version 1.1.0, requires `pytest>=8.2,<10` — **HIGH confidence**
- https://pypi.org/pypi/pytest-cov/json — version 7.1.0 (2026-03-21) — **HIGH confidence**
- https://pypi.org/pypi/anyio/json — version 4.13.0 (2026-03-24) — **HIGH confidence**
- https://pypi.org/pypi/uv/json — version 0.11.14 — **HIGH confidence**
- https://pypi.org/pypi/ruff/json — version 0.15.12 — **HIGH confidence**
- https://pypi.org/pypi/mypy/json — version 2.1.0 — **HIGH confidence**
- https://pypi.org/pypi/pre-commit/json — version 4.6.0 — **HIGH confidence**
- https://pypi.org/pypi/uvicorn/json — version 0.46.0 — **HIGH confidence**
- https://pypi.org/pypi/aio-pika/json — version 9.6.2 (transitive) — **HIGH confidence**
- https://faststream.ag2.ai/latest/getting-started/integrations/fastapi/ — official FastStream/FastAPI integration page, confirms `fastapi>=0.112.2` requirement for auto-lifespan — **HIGH confidence**
- https://endoflife.date/api/python.json — Python 3.10 EOL 2026-10-31, latest patch 3.10.20 — **HIGH confidence**
- https://endoflife.date/api/postgres.json — PG 16.14 current, EOL 2028-11 — **HIGH confidence**
- https://www.rabbitmq.com/release-information — RabbitMQ 4.2 community-supported through 2026-07; 4.3 just released 2026-04 — **HIGH confidence**
- https://hub.docker.com/_/python/tags — `3.10-slim` rolling tag now resolves to `trixie`; recommend pinning `3.10-slim-bookworm` — **HIGH confidence**

---
*Stack research for: asynchronous Python event-driven microservice (betting / RabbitMQ / PostgreSQL)*
*Researched: 2026-05-13*
