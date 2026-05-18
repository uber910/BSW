# Phase 7: Polish + Documentation - Pattern Map

**Mapped:** 2026-05-18
**Files analyzed:** 17 (7 new, 10 modified)
**Analogs found:** 16 / 17 (1 file — README ASCII diagram — has no in-repo analog; uses `.planning/research/ARCHITECTURE.md` topology as reference)

Phase 7 is a non-functional polish pass. No new interactors / repositories / selectors / facades / migrations / dependencies. The work is concentrated in: (a) markdown documentation, (b) FastAPI decorator metadata, (c) two-line CI yaml extension, (d) two duplicated Pydantic schemas (`ErrorDetail`), and (e) one new static-audit test module.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/line_provider/schemas/errors.py` (NEW) | Pydantic schema | n/a (DTO) | `src/line_provider/schemas/messages.py::EventFinishedMessage` | exact (frozen + extra=forbid + ConfigDict) |
| `src/bet_maker/schemas/errors.py` (NEW) | Pydantic schema | n/a (DTO) | `src/bet_maker/schemas/messages.py::EventFinishedMessage` | exact (mirror duplication policy P5 D-28) |
| `tests/audit/__init__.py` (NEW) | test package marker | n/a | `tests/contract/__init__.py` | exact (empty marker) |
| `tests/audit/test_static.py` (NEW) | static-introspection test | file-I/O (read-only `Path.read_text()` + regex/string match) | `tests/contract/test_event_finished_message_schema.py` (static introspection of `model_json_schema()`) | role-match (both audit code statically without runtime) |
| `tests/bet_maker/test_asyncapi_smoke.py` (NEW) | HTTP smoke test | request-response (httpx AsyncClient over ASGITransport) | `tests/bet_maker/test_health.py::test_health_returns_status_ok` | exact (same fixture pattern + 200-assert) |
| `tests/line_provider/test_asyncapi_smoke.py` (NEW) | HTTP smoke test | request-response | `tests/line_provider/test_health.py::test_health_returns_status_ok` | exact (same fixture pattern + 200-assert) |
| `.planning/phases/07-polish-documentation/07-AUDIT.md` (NEW) | docs (audit table) | n/a | None in-repo (new artefact convention) | n/a — markdown table |
| `README.md` (MODIFIED) | docs (root) | n/a | Current `README.md` itself | self (extend existing skeleton — Quick start + Development sections already exist) |
| `pyproject.toml` (UNCHANGED expected) | config | n/a | Existing pyproject | no change — coverage already configured |
| `.github/workflows/ci.yml` (MODIFIED) | CI config | n/a | Same file, current Pytest step | self (extend pytest line only) |
| `src/line_provider/app.py` (MODIFIED) | FastAPI app factory | n/a | Same file `build_app()` | self (add `description=` kwarg) |
| `src/bet_maker/app.py` (MODIFIED) | FastAPI app factory | n/a | Same file `build_app()` | self (add `description=` kwarg) |
| `src/line_provider/entrypoints/api/events.py` (MODIFIED) | HTTP route metadata | request-response | Same file, current `@router.post` decorators | self (add `summary=` + `responses=` + `Body(openapi_examples=)`) |
| `src/line_provider/entrypoints/api/health.py` (MODIFIED) | HTTP route metadata | request-response | Same file | self (add `summary=`) |
| `src/bet_maker/entrypoints/api/bets.py` (MODIFIED) | HTTP route metadata | request-response | Same file (`post_bet` already has the ladder; add metadata only) | self |
| `src/bet_maker/entrypoints/api/events.py` (MODIFIED) | HTTP route metadata | request-response | Same file | self |
| `src/bet_maker/entrypoints/api/health.py` (MODIFIED) | HTTP route metadata | request-response | Same file | self |

## Pattern Assignments

---

### `src/bet_maker/schemas/errors.py` (Pydantic schema, NEW)

**Analog:** `src/bet_maker/schemas/messages.py::EventFinishedMessage` (closest by `frozen=True` + `extra="forbid"` + minimal field set + duplicated-per-service policy from P5 D-28). Also see `src/bet_maker/schemas/bets.py::BetCreate` for the `extra="forbid"` (non-frozen) variant — `ErrorDetail` is closer to `messages.py` because it is a read-only payload, not a request body.

**Imports pattern** (mirror `src/bet_maker/schemas/messages.py:7-14`):
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
```

**Core schema pattern** (mirror `src/bet_maker/schemas/messages.py:22-30` — `ConfigDict(frozen=True, extra="forbid")`):
```python
# From src/bet_maker/schemas/messages.py:22-23
class EventFinishedMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ...
```

**Concrete `ErrorDetail` to write** (planner copy-paste target):
```python
# src/bet_maker/schemas/errors.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """Standard error envelope for FastAPI HTTPException responses.

    Used in route `responses={...}` so Swagger UI renders the exact JSON
    shape under 4xx/5xx branches. Mirrors FastAPI's default `{"detail": "..."}`
    payload from `HTTPException(detail=...)`.

    D-09 / P5 D-28 duplication policy: this schema is duplicated byte-for-byte
    in src/line_provider/schemas/errors.py. No cross-service imports.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    detail: str
```

**Why this analog (not `bets.py::BetCreate`):** `BetCreate` uses `extra="forbid"` but not `frozen=True`. `ErrorDetail` is an output DTO (returned from FastAPI HTTPException, never user-built) — frozen matches output semantics (parallel to `EventRead`/`BetRead` which are response models). The `messages.py` analog also has the strongest "duplicated byte-for-byte across services" precedent.

---

### `src/line_provider/schemas/errors.py` (Pydantic schema, NEW)

**Analog:** `src/line_provider/schemas/messages.py::EventFinishedMessage` (same as bet_maker — verbatim duplicate per P5 D-28).

**Pattern:** Identical to `src/bet_maker/schemas/errors.py` above — copy verbatim, no cross-imports, no shared base. Mirror of the duplication policy already used for `EventFinishedMessage`.

```python
# src/line_provider/schemas/errors.py — byte-for-byte mirror of bet_maker version
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """Standard error envelope for FastAPI HTTPException responses.

    D-09: duplicated from src/bet_maker/schemas/errors.py per P5 D-28
    (no cross-service imports). Optional parity test in tests/audit/test_static.py
    asserts model_json_schema() equality.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    detail: str
```

---

### `src/{line_provider,bet_maker}/app.py` (FastAPI app factory, MODIFIED)

**Analog:** Self (current `build_app()`). The only change is adding `description=` to the existing `FastAPI(...)` call. `title` and `version` are already present.

**Current state — `src/line_provider/app.py:11-21`:**
```python
def build_app() -> FastAPI:
    app = FastAPI(
        title="line-provider",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(rabbit_router)
    return app
```

**After polish (D-06):**
```python
def build_app() -> FastAPI:
    app = FastAPI(
        title="line-provider",
        description=(
            "Источник событий и их статусов. Хранит события в памяти, "
            "публикует EventFinishedMessage в RabbitMQ exchange `bsw.events` "
            "при переходе в FINISHED_WIN / FINISHED_LOSE. AsyncAPI: /asyncapi."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(rabbit_router)
    return app
```

**Current state — `src/bet_maker/app.py:11-22`:**
```python
def build_app() -> FastAPI:
    app = FastAPI(
        title="bet-maker",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(bets.router)
    app.include_router(events.router)
    app.include_router(rabbit_router)
    return app
```

**After polish (D-06):**
```python
def build_app() -> FastAPI:
    app = FastAPI(
        title="bet-maker",
        description=(
            "Сервис приёма и истории ставок. Хранит ставки в PostgreSQL, "
            "получает финальные статусы событий из RabbitMQ "
            "(queue `bet_maker.events.finished`), reconciler как защита "
            "от потерянных сообщений. AsyncAPI: /asyncapi."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    ...
```

**Notes:** Do NOT add `contact={...}` or `license_info={...}` — they are Claude's-discretion per D-06 and add noise without value for a test-task reviewer.

---

### `src/bet_maker/entrypoints/api/bets.py` (HTTP route metadata, MODIFIED)

**Analog:** Self — current decorators already have `status_code=` and `response_model=`. Add `summary=`, `responses=`, and `Body(openapi_examples=)` only.

**Current decorator + handler — `src/bet_maker/entrypoints/api/bets.py:17-57`:**
```python
@router.post(
    "/bet",
    status_code=status.HTTP_201_CREATED,
    response_model=BetRead,
)
async def post_bet(
    body: BetCreate,
    uow: UoWDep,
    event_lookup: EventLookupDep,
) -> BetRead:
    """POST /bet — place a bet on a bettable event.
    ...
    """
    try:
        return await place_bet(
            uow,
            event_id=body.event_id,
            amount=body.amount,
            event_lookup=event_lookup,
        )
    except LineProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="event validation unavailable: line-provider unreachable",
        ) from exc
    except EventNotBettable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event {body.event_id} is not bettable: {exc.reason}",
        ) from exc
```

**Diff for D-07/D-08 polish (additive only — no handler-body change):**

1. New import at top: `from fastapi import APIRouter, Body, HTTPException, status` (add `Body`) and `from bet_maker.schemas.errors import ErrorDetail`.
2. Replace decorator + signature:

```python
@router.post(
    "/bet",
    status_code=status.HTTP_201_CREATED,
    response_model=BetRead,
    summary="Place a bet on a bettable event",
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorDetail,
            "description": (
                "Validation failure (Pydantic) or event not bettable: "
                "event not found, deadline passed, or event not active."
            ),
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorDetail,
            "description": "line-provider unreachable after retries.",
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
    # handler body UNCHANGED — keeps the LineProviderUnavailable → 503,
    # EventNotBettable → 422 ladder verbatim.
    ...
```

3. For `@router.get("/bets", ...)` add `summary="List all bets (newest first)"` only — no error branches.
4. For `@router.get("/bet/{bet_id}", ...)` add `summary="Fetch single bet by id"` + `responses={status.HTTP_404_NOT_FOUND: {"model": ErrorDetail, "description": "bet not found"}}`.

**Important:** existing docstring stays — FastAPI surfaces it as the route description automatically. Do NOT move docstring into `description=` kwarg (causes duplication).

---

### `src/bet_maker/entrypoints/api/events.py` (HTTP route metadata, MODIFIED)

**Analog:** Self — already follows the `try / raise HTTPException 503` pattern.

**Current — `src/bet_maker/entrypoints/api/events.py:21-38`:**
```python
@router.get(
    "/events",
    response_model=list[EventRead],
)
async def get_events(http_client: LineProviderHttpClientDep) -> list[EventRead]:
    """GET /events — list active events from line-provider.
    ...
    """
    try:
        return await list_active_events(http_client)
    except LineProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="line-provider unreachable",
        ) from exc
```

**After polish:**
```python
@router.get(
    "/events",
    response_model=list[EventRead],
    summary="List active events (proxied from line-provider)",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorDetail,
            "description": "line-provider unreachable after retries.",
        },
    },
)
async def get_events(http_client: LineProviderHttpClientDep) -> list[EventRead]:
    ...  # unchanged
```

Add import: `from bet_maker.schemas.errors import ErrorDetail`.

---

### `src/bet_maker/entrypoints/api/health.py` (HTTP route metadata, MODIFIED)

**Analog:** Self.

**Current — `src/bet_maker/entrypoints/api/health.py:16-22`:**
```python
@router.get("/health")
async def health(
    engine: EngineDep,
    broker: RabbitBrokerDep,
    reconciler_task: ReconciliationTaskDep,
) -> JSONResponse:
```

**After polish (summary only — response payload is `JSONResponse` so no `response_model`):**
```python
@router.get(
    "/health",
    summary="Service health (PG + RMQ + consumer + reconciler)",
    responses={
        503: {
            "description": (
                "Degraded — one of: postgres / rabbitmq / rabbitmq_consumer / "
                "reconciler is down. Payload: {status: 'degraded', checks: {...}}."
            ),
        },
    },
)
async def health(...) -> JSONResponse:
    ...  # unchanged
```

No `ErrorDetail` model here because the 503 payload from this route is the multi-key `checks` dict, not the flat `{"detail": "..."}` shape. Therefore `responses[503]` carries only `description=`, no `model=`.

---

### `src/line_provider/entrypoints/api/events.py` (HTTP route metadata, MODIFIED)

**Analog:** Self — three routes (`POST /event`, `PUT /event/{id}`, `GET /event/{id}`, `GET /events`) all already raise `HTTPException` with the right status codes.

**Current decorator pattern — `src/line_provider/entrypoints/api/events.py:22-26`:**
```python
@router.post(
    "/event",
    status_code=status.HTTP_201_CREATED,
    response_model=EventRead,
)
```

**After polish (additive only):**
```python
@router.post(
    "/event",
    status_code=status.HTTP_201_CREATED,
    response_model=EventRead,
    summary="Create new event in NEW state",
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorDetail,
            "description": "Event with this event_id already exists.",
        },
    },
)
async def post_event(
    body: EventCreate = Body(
        openapi_examples={
            "happy": {
                "summary": "Create new bettable event",
                "value": {
                    "event_id": "00000000-0000-0000-0000-000000000001",
                    "coefficient": "1.50",
                    "deadline": "2030-01-01T00:00:00+00:00",
                },
            },
        },
    ),
    store: StoreDep = ...,
) -> EventRead:
    ...  # unchanged
```

Similar pattern for `@router.put("/event/{event_id}", ...)` — add `summary=`, `responses={404: ErrorDetail, 422: ErrorDetail}`, `Body(openapi_examples=...)` with `state: "FINISHED_WIN"` example. For `@router.get("/event/{event_id}", ...)` and `@router.get("/events", ...)` — `summary=` + `responses={404: ErrorDetail}` for the first, no error branch for the second.

Add import: `from fastapi import APIRouter, Body, HTTPException, Request, status` (add `Body`) and `from line_provider.schemas.errors import ErrorDetail`.

---

### `src/line_provider/entrypoints/api/health.py` (HTTP route metadata, MODIFIED)

**Analog:** Self.

**Current — `src/line_provider/entrypoints/api/health.py:8-10`:**
```python
@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

**After polish:**
```python
@router.get(
    "/health",
    summary="Liveness probe",
)
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

LP health route has no error branch (no PG/RMQ checks — LP is in-memory) so no `responses={}` block.

---

### `tests/audit/test_static.py` (static-introspection test, NEW)

**Primary analog:** `tests/contract/test_event_finished_message_schema.py` (only existing example of a test that introspects code statically — though it introspects `model_json_schema()` rather than file text). Closest by intent: "verify a structural property of the codebase at CI time."

**Secondary analog (test fixture and assertion style):** Plain pytest functions under `tests/line_provider/test_health.py:14-19` — module-level async-free `def` functions, simple `assert`s.

**Imports pattern (mirror `tests/contract/test_event_finished_message_schema.py:1-15`):**
```python
"""Contract test: EventFinishedMessage must be byte-for-byte identical
across line_provider and bet_maker (D-28, D-29 / SC#6).

A failing test here means a developer modified one copy without
updating the other — CI breaks the PR before deployment drift can
occur in production.
"""

from __future__ import annotations

import json

from bet_maker.schemas.messages import EventFinishedMessage as BMMessage
from line_provider.schemas.messages import EventFinishedMessage as LPMessage
```

**Core static-introspection pattern** — for D-19's new file, use `Path.read_text()` + `in`/`re.search` rather than imports + `model_json_schema()`. `ast` is overkill per D-19 Claude's-discretion. Pattern to apply:

```python
# tests/audit/test_static.py
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_subscribers_have_manual_ack() -> None:
    """R1/F1 + D-19: every @router.subscriber in bet_maker.entrypoints.messaging
    must declare ack_policy=AckPolicy.MANUAL. Default AckPolicy.REJECT_ON_ERROR
    would silently drop poison messages, breaking R1.
    """
    src = (REPO_ROOT / "src/bet_maker/entrypoints/messaging.py").read_text()
    subscriber_count = len(re.findall(r"@router\.subscriber\s*\(", src))
    manual_ack_count = len(re.findall(r"ack_policy\s*=\s*AckPolicy\.MANUAL", src))
    assert subscriber_count > 0, "no @router.subscriber found"
    assert subscriber_count == manual_ack_count, (
        f"{subscriber_count} @router.subscriber decorators but only "
        f"{manual_ack_count} declare ack_policy=AckPolicy.MANUAL"
    )


def test_repositories_use_for_update_skip_locked() -> None:
    """R3 + D-19: BetRepository.get_pending_locked must use
    with_for_update(skip_locked=True) — both the row lock and SKIP LOCKED
    are required for idempotent concurrent settle.
    """
    src = (REPO_ROOT / "src/bet_maker/repositories/bets.py").read_text()
    assert "with_for_update(skip_locked=True)" in src, (
        "BetRepository.get_pending_locked must use "
        "with_for_update(skip_locked=True) — see ARCHITECTURE.md R3."
    )


def test_async_sessionmaker_expire_on_commit_false() -> None:
    """D-15 / P3 Pitfall A1 + D-19: async_sessionmaker must pass
    expire_on_commit=False — otherwise post-commit ORM attribute access
    triggers MissingGreenlet errors in the async session.
    """
    src = (REPO_ROOT / "src/bet_maker/infrastructure/db/engine.py").read_text()
    assert "async_sessionmaker(engine, expire_on_commit=False)" in src or re.search(
        r"async_sessionmaker\([^)]*expire_on_commit\s*=\s*False", src
    ), "async_sessionmaker must declare expire_on_commit=False"


def test_dockerfile_pinned_python_bookworm() -> None:
    """P1 D-20 + D-19: Dockerfile must pin python:3.10-slim-bookworm
    explicitly (not rolling 3.10-slim, which now resolves to trixie).
    """
    src = (REPO_ROOT / "Dockerfile").read_text()
    assert "3.10-slim-bookworm" in src, (
        "Dockerfile must pin python:3.10-slim-bookworm, not rolling 3.10-slim."
    )


def test_pythonunbuffered_set() -> None:
    """P1 + D-19: PYTHONUNBUFFERED=1 must be set so stdout flushes
    immediately under docker — required for structlog log visibility.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    assert "PYTHONUNBUFFERED=1" in dockerfile, (
        "Dockerfile must declare PYTHONUNBUFFERED=1."
    )


def test_dockerfile_no_shell_form_cmd() -> None:
    """P1 D-04 / R11 + D-19: Dockerfile CMD must be exec-form (JSON array)
    so the process receives SIGTERM directly. Shell-form `CMD python ...`
    spawns under /bin/sh -c, which traps SIGTERM and prevents graceful
    shutdown (R11 — SIGTERM ignored, docker kills with SIGKILL after grace).
    """
    src = (REPO_ROOT / "Dockerfile").read_text()
    # exec-form CMD always starts with `CMD [` (JSON array)
    assert re.search(r"^CMD \[", src, re.MULTILINE), (
        "Dockerfile CMD must be exec-form (CMD [\"...\", ...]), not shell-form."
    )


def test_durable_queue_and_exchange() -> None:
    """R8 (durable infra) + D-19: bet_maker.entrypoints.messaging RabbitQueue
    and RabbitExchange must declare durable=True so messages survive a
    RabbitMQ restart. Non-durable queues/exchanges are deleted on broker
    restart and silently lose the EventFinishedMessage stream.
    """
    src = (REPO_ROOT / "src/bet_maker/entrypoints/messaging.py").read_text()
    # RabbitQueue("bet_maker.events.finished", durable=True, ...)
    assert re.search(r"RabbitQueue\([^)]*durable\s*=\s*True", src, re.DOTALL), (
        "RabbitQueue must declare durable=True."
    )
    assert re.search(r"RabbitExchange\([^)]*durable\s*=\s*True", src, re.DOTALL), (
        "RabbitExchange must declare durable=True."
    )
```

**Why `Path.read_text()` + regex over Python `ast`:**
- Audit checks target literal kwargs (`ack_policy=AckPolicy.MANUAL`, `durable=True`) at decorator-call sites. AST would require visiting `Call.keywords`, comparing `Name.id` / `Attribute.attr` — 5x more code for the same outcome.
- D-19 explicit Claude's-discretion: regex acceptable.
- Tests live in `tests/audit/` — isolated package, no fixture dependency. No `client` / `app` / `pg_dsn` fixture needed.

**File paths used (all read-only):**
- `REPO_ROOT / "src/bet_maker/entrypoints/messaging.py"`
- `REPO_ROOT / "src/bet_maker/repositories/bets.py"`
- `REPO_ROOT / "src/bet_maker/infrastructure/db/engine.py"`
- `REPO_ROOT / "Dockerfile"`

`REPO_ROOT = Path(__file__).resolve().parents[2]` — `tests/audit/test_static.py` -> `.parents[0]=tests/audit`, `.parents[1]=tests`, `.parents[2]=repo-root`. Verified by file-tree layout.

---

### `tests/audit/__init__.py` (test package marker, NEW)

**Analog:** `tests/contract/__init__.py` (empty file — verified by `ls`).

**Content:** Empty (zero bytes), or single-line docstring at most.

```python
# tests/audit/__init__.py
# Phase 7 D-19: static-audit test package for "Looks Done But Isn't" checklist.
```

---

### `tests/bet_maker/test_asyncapi_smoke.py` (HTTP smoke test, NEW)

**Primary analog:** `tests/bet_maker/test_health.py::TestHealth::test_health_returns_status_ok` (lines 23-34). Identical fixture pattern: session-scoped `client: AsyncClient` from `tests/bet_maker/conftest.py`, simple `assert response.status_code == 200`.

**Imports pattern (mirror `tests/bet_maker/test_health.py:1-17`):**
```python
"""Smoke test: /asyncapi endpoint is exposed by FastStream RabbitRouter.

D-10: FastStream RabbitRouter registers /asyncapi at default URL when
app.include_router(router) is called in build_app(). Phase 7 verification.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
class TestAsyncAPISmoke:
    """AsyncAPI endpoint smoke test — session loop for session-scoped client."""

    async def test_asyncapi_endpoint_returns_200(self, client: AsyncClient) -> None:
        """D-10 / QA visibility: /asyncapi must return 200 with a non-empty
        JSON body. Body should contain `"asyncapi"` key (AsyncAPI 2.x / 3.x
        spec marker).
        """
        response = await client.get("/asyncapi")
        assert response.status_code == 200
        # AsyncAPI doc may be HTML (Redoc/AsyncAPI rendering) — accept either:
        ct = response.headers.get("content-type", "")
        assert any(t in ct for t in ("html", "json")), (
            f"unexpected /asyncapi content-type: {ct}"
        )
```

**Fixture reuse:** Uses existing `client` fixture from `tests/bet_maker/conftest.py:92-99` (session-scoped, lifespan-aware, ASGITransport-backed). No new fixtures needed.

**Caveat (planner):** FastStream's `/asyncapi` may serve HTML (AsyncAPI UI) or JSON depending on the FastStream version. The smoke test should assert 200 + non-empty body; specific schema-validation is out-of-scope for D-10/D-11.

---

### `tests/line_provider/test_asyncapi_smoke.py` (HTTP smoke test, NEW)

**Analog:** `tests/line_provider/test_health.py:14-19` (line-provider has plain async-def style without `@pytest.mark.asyncio` class — see `pyproject.toml [tool.pytest.ini_options] asyncio_mode = "auto"`).

**Pattern (mirror line-provider's plain-function style):**
```python
"""Smoke test: line-provider /asyncapi endpoint exposed by FastStream RabbitRouter.

D-10 (publisher side): line-provider's RabbitRouter (no subscribers, publisher-only)
still registers /asyncapi to document the publish contract. Phase 7 verification.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_asyncapi_endpoint_returns_200(client: AsyncClient) -> None:
    """D-10: /asyncapi available on line-provider for AsyncAPI publish-contract docs."""
    response = await client.get("/asyncapi")
    assert response.status_code == 200
```

**Fixture reuse:** Uses `client` fixture from `tests/line_provider/conftest.py:53-61` (session-scoped, lifespan-aware). No new fixtures.

---

### `.github/workflows/ci.yml` (CI config, MODIFIED)

**Analog:** Self — only the Pytest step changes.

**Current Pytest step — `.github/workflows/ci.yml:46-47`:**
```yaml
      - name: Pytest
        run: uv run pytest -q
```

**After polish (D-15 — one-line replacement):**
```yaml
      - name: Pytest
        run: uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85
```

**Notes for planner:**
- `--cov` with no argument picks up `source = ["src/line_provider", "src/bet_maker"]` from `pyproject.toml:tool.coverage.run`. Verified — already in pyproject (lines 91-93).
- `--cov-fail-under=85` is redundant with `pyproject [tool.coverage.report] fail_under = 85` (line 96), kept as explicit CLI override to guard against pyproject drift.
- `--cov-report=xml` writes `coverage.xml` for optional future codecov integration. No upload step added — D-16 locks Shields.io static badge.
- No new dependencies. `pytest-cov>=7.1,<8` already in `dev` dependency-group (line 27).

---

### `README.md` (docs, MODIFIED)

**Primary analog:** Current `README.md` itself — Quick start (lines 9-41) and Development (lines 43-77) sections are already structured. Phase 7 extends, replaces TODOs, and updates Project status.

**Section-by-section pattern guidance:**

**1. Header + badges (`README.md:1-3` → expand to 2 badges per D-16):**
Current:
```markdown
# BSW Betting System

[![ci](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
```
After polish — add Shields.io static coverage badge (D-16):
```markdown
# BSW Betting System

[![ci](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)]()
```
URL spec for Shields.io: `https://img.shields.io/badge/<label>-<message>-<color>.svg`; `%25` URL-encodes `%`. Per D-16 — hardcoded, no codecov.

**2. Quick start (`README.md:9-41`):** Keep existing block verbatim — it already covers `docker compose up -d`, healthcheck wait, ports, RabbitMQ Management UI, and the `guest:guest` security note. No changes needed.

**3. Reviewer walkthrough (NEW section, insert after Quick start, before Architecture):** No in-repo analog. Use D-04 verbatim sequence:
```bash
# 1. start stack
cp .env.example .env && docker compose up -d
# 2. wait healthy
docker compose ps   # wait for "(healthy)" on postgres / rabbitmq / line-provider / bet-maker

# 3. create event in line-provider
EVENT_ID=00000000-0000-0000-0000-000000000001
curl -s -X POST http://localhost:8000/event \
  -H 'content-type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\",\"coefficient\":\"1.50\",\"deadline\":\"2030-01-01T00:00:00+00:00\"}"

# 4. place bet in bet-maker
curl -s -X POST http://localhost:8001/bet \
  -H 'content-type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\",\"amount\":\"10.00\"}"

# 5. finish event (FINISHED_WIN -> bet should settle to WON)
curl -s -X PUT http://localhost:8000/event/$EVENT_ID \
  -H 'content-type: application/json' \
  -d '{"coefficient":"1.50","deadline":"2030-01-01T00:00:00+00:00","state":"FINISHED_WIN"}'

# 6. observe settled bet (status=WON within ~1s, settled_via=consumer on happy path)
sleep 1
curl -s http://localhost:8001/bets | jq '.[] | {id, status, amount}'
```

**4. Architecture (DOC-02) — replace `README.md:79-81` TODO:** No in-repo analog for ASCII diagram. Reference 6-stroke diagram in `RESEARCH.md:181-208` (already drafted in research). Topology source: `.planning/research/ARCHITECTURE.md`.

**5. Reliability (DOC-04) — replace `README.md:83-85` TODO:** 6-point enumerated list per D-05 with file:line references:
- Durable queue + persistent messages → `src/bet_maker/entrypoints/messaging.py:120-130` (RabbitQueue + RabbitExchange `durable=True`)
- Manual ack after UoW commit → `src/bet_maker/entrypoints/messaging.py:131` (`ack_policy=AckPolicy.MANUAL`) + line 175 (`await msg.ack()` after `async with AsyncUnitOfWork(...)` exits cleanly)
- FOR UPDATE SKIP LOCKED → `src/bet_maker/repositories/bets.py:39-63::get_pending_locked`
- DLX/DLQ + bounded transient retries → `src/bet_maker/entrypoints/messaging.py:125-128` (`x-dead-letter-exchange`) + lines 177-191 (POISON + transient-exhausted both reject with `requeue=False`)
- Reconciler defence-in-depth → `src/bet_maker/jobs/reconciler.py`
- Lifespan order + SIGTERM exec-form CMD → `Dockerfile:50` (exec-form CMD) + lifespan ordering

Close with the CANCELLED-extension paragraph per D-05 — link to `REQUIREMENTS.md` BM-05 and `PITFALLS.md`.

**6. Development — keep `README.md:43-77` as-is, add coverage line:** Just one extra command in the linters/tests block:
```bash
uv run pytest -q --cov --cov-report=term-missing   # local coverage check
```

**7. Project status — replace `README.md:87-98`:** Update all rows to `done` / `complete`.

---

### `.planning/phases/07-polish-documentation/07-AUDIT.md` (docs, NEW)

**Analog:** None in-repo for this exact artefact. The closest convention precedent is the existing `07-CONTEXT.md` / `07-RESEARCH.md` / `07-VALIDATION.md` markdown-table style.

**Structure (D-18):** Markdown table with columns `Item | Evidence | Status | Notes`. 18 rows from `.planning/research/PITFALLS.md` §«Looks Done But Isn't». Each `Status ∈ {verified, fix-applied, waived}`. Zero `waived` without written justification.

**Evidence column conventions:**
- `file:line` (e.g., `src/bet_maker/repositories/bets.py:62`)
- pytest test-id (e.g., `tests/audit/test_static.py::test_subscribers_have_manual_ack`)
- shell command + expected output (e.g., `docker compose down -> exit 0 within 5s`)

Each evidence reference must be concrete (not "see source" or "verified manually" without command). Half the rows will be backed by `tests/audit/test_static.py` (D-19), other half by existing P5/P6 tests (D-21/D-22) and Dockerfile/compose grep.

---

## Shared Patterns

### Pydantic schema config (frozen + extra-forbid)
**Source:** `src/bet_maker/schemas/messages.py:23`
**Apply to:** Both new `ErrorDetail` schemas
```python
model_config = ConfigDict(frozen=True, extra="forbid")
```
Output DTOs use `frozen=True`; request bodies (`BetCreate`/`EventCreate`/`EventUpdate`) use only `extra="forbid"` (no `frozen`).

### Per-service schema duplication (P5 D-28)
**Source:** `src/{line_provider,bet_maker}/schemas/messages.py` (byte-for-byte mirror)
**Apply to:** Both new `ErrorDetail` schemas — duplicate, no cross-imports.
**Contract test pattern:** Already in `tests/contract/test_event_finished_message_schema.py`. Optional new test in `tests/audit/test_static.py` or `tests/contract/` could mirror for `ErrorDetail` parity, but D-19 list does not require it (single-field schema, low drift risk).

### FastAPI route metadata polish
**Source:** Current `src/bet_maker/entrypoints/api/bets.py` (already has `status_code=` + `response_model=` + docstring)
**Apply to:** All 8 route decorators across both services (LP: 4 routes + health; BM: 5 routes + health)
**Pattern:**
1. Keep existing `status_code=` / `response_model=` / handler body
2. Add `summary="..."` (one-liner)
3. Add `responses={<int>: {"model": ErrorDetail, "description": "..."}}` for each HTTPException branch
4. Add `Body(openapi_examples={...})` on `POST` and `PUT` request bodies only
5. Existing docstring stays — FastAPI uses it as `description=` automatically

### Static-audit test idiom
**Source:** Pattern derived in this Phase (no prior in-repo analog)
**Apply to:** `tests/audit/test_static.py`
```python
REPO_ROOT = Path(__file__).resolve().parents[2]
src = (REPO_ROOT / "<relative/path>").read_text()
assert "<literal>" in src  # or re.search(r"<pattern>", src)
```
No fixtures, no async, no `client`. Each test is a one-purpose grep-or-substring check with a descriptive `AssertionError` message that names the relevant decision-id (R1/F1, D-04, R3, etc.).

### HTTP smoke test fixture reuse
**Source:** `tests/bet_maker/conftest.py:62-99` + `tests/line_provider/conftest.py:13-61`
**Apply to:** Both new `test_asyncapi_smoke.py` files
**Pattern:**
- Use existing session-scoped `client: AsyncClient` fixture
- bet_maker side: `@pytest.mark.asyncio(loop_scope="session")` decorator on class (mirror `test_health.py:19`)
- line_provider side: plain `async def test_...(client: AsyncClient)` (mirror `test_health.py:14`)

### CI workflow extension
**Source:** `.github/workflows/ci.yml:46-47`
**Apply to:** Pytest step only
**Pattern:** Single-line replacement — append `--cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85` to the existing `uv run pytest -q` command. No new yaml steps, no codecov upload step.

---

## No Analog Found

| File / Section | Reason | Reference Used Instead |
|----------------|--------|------------------------|
| README ASCII architecture diagram | No existing ASCII art in repo | `.planning/research/ARCHITECTURE.md` topology + `RESEARCH.md:181-208` 6-stroke draft |
| README Reviewer walkthrough (curl sequence) | No existing curl-script in docs | `07-CONTEXT.md` D-04 verbatim sequence |
| `07-AUDIT.md` | First "audit" artefact in the project | `07-CONTEXT.md` D-18 schema (`Item / Evidence / Status / Notes` columns) + `.planning/research/PITFALLS.md` §«Looks Done But Isn't» 18-item source list |

Each of these gets a "from scratch" pattern in the plan, anchored to a non-code reference document.

## Metadata

**Analog search scope:**
- `src/bet_maker/{schemas,entrypoints/api,entrypoints,repositories,infrastructure/db,jobs}`
- `src/line_provider/{schemas,entrypoints/api,entrypoints,facades}`
- `tests/{conftest.py,contract,bet_maker,line_provider}`
- Root: `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `README.md`

**Files scanned:** 22

**Key patterns confirmed by grep:**
- Zero `# type: ignore` in `src/` (verified by RESEARCH.md, line 11) → mypy strict pass is verification-only
- `RabbitRouter(str(_settings.rabbitmq_url))` constructor in both services → `/asyncapi` at default URL (no `schema_url=` override) → AsyncAPI smoke test just hits `/asyncapi`
- `pyproject.toml [tool.coverage.run] source = ["src/line_provider", "src/bet_maker"]` already present → CI extension is single-line
- Both `__init__.py` in `tests/contract/` and the new `tests/audit/` will be empty marker files

**Pattern extraction date:** 2026-05-18
