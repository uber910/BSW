# Phase 3: bet-maker domain (DB) — Pattern Map

**Mapped:** 2026-05-15
**Files analyzed:** 32 (new/modified files)
**Analogs found:** 30 / 32

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/bet_maker/models/bet.py` | model | CRUD | no direct analog — use RESEARCH.md Pattern 1 | no analog (new pattern) |
| `src/bet_maker/schemas/bets.py` | schema | request-response | `src/line_provider/schemas/events.py` | role-match |
| `src/bet_maker/schemas/events.py` | schema | transform | `src/line_provider/schemas/events.py` (EventState) | exact (intentional duplicate) |
| `src/bet_maker/repositories/bets.py` | repository | CRUD | `src/line_provider/infrastructure/store/in_memory.py` | role-match (different storage) |
| `src/bet_maker/facades/uow.py` | facade | CRUD | no direct analog — use RESEARCH.md Pattern 2 | no analog (new pattern) |
| `src/bet_maker/facades/event_lookup.py` | facade | request-response | `src/line_provider/facades/event_bus.py` | role-match (Protocol+Stub pattern) |
| `src/bet_maker/facades/deps.py` | provider | request-response | `src/line_provider/facades/deps.py` | exact |
| `src/bet_maker/interactors/place_bet.py` | interactor | CRUD | `src/line_provider/interactors/set_event_state.py` | role-match |
| `src/bet_maker/selectors/list_bets.py` | selector | CRUD | `src/line_provider/selectors/list_active_events.py` | role-match |
| `src/bet_maker/selectors/get_bet.py` | selector | request-response | `src/line_provider/selectors/get_event_by_id.py` | exact |
| `src/bet_maker/helpers/money.py` | utility | transform | `src/line_provider/helpers/money.py` | exact |
| `src/bet_maker/helpers/status.py` | utility | transform | `src/line_provider/helpers/state_machine.py` | role-match |
| `src/bet_maker/infrastructure/db/engine.py` | infrastructure | CRUD | no direct analog — use RESEARCH.md Pattern 1 | no analog (new pattern) |
| `src/bet_maker/infrastructure/db/pings.py` | infrastructure | request-response | no direct analog — use RESEARCH.md Pattern 5 | no analog (new pattern) |
| `alembic/versions/0001_bets_initial.py` | migration | CRUD | no direct analog — use RESEARCH.md Pattern 3 | no analog (new pattern) |
| `src/bet_maker/entrypoints/api/health.py` | entrypoint | request-response | `src/line_provider/entrypoints/api/health.py` | role-match (extend to PG ping) |
| `src/bet_maker/entrypoints/api/bets.py` | entrypoint | request-response | `src/line_provider/entrypoints/api/events.py` | role-match |
| `src/bet_maker/entrypoints/lifespan.py` | infrastructure | event-driven | `src/line_provider/entrypoints/lifespan.py` | exact (extend P1) |
| `src/bet_maker/app.py` | infrastructure | request-response | `src/line_provider/app.py` | exact |
| `tests/conftest.py` | test | CRUD | no direct analog — use RESEARCH.md Pattern 4 | no analog (new pattern) |
| `tests/bet_maker/conftest.py` | test | CRUD | `tests/line_provider/conftest.py` | role-match (extend P1) |
| `tests/bet_maker/test_models.py` | test | CRUD | `tests/line_provider/test_create_event.py` | role-match |
| `tests/bet_maker/test_repositories.py` | test | CRUD | `tests/line_provider/test_in_memory_store.py` (if exists) | role-match |
| `tests/bet_maker/test_uow.py` | test | CRUD | no direct analog | no analog |
| `tests/bet_maker/test_event_lookup.py` | test | request-response | `tests/line_provider/test_facades.py` | exact (Protocol+Stub test pattern) |
| `tests/bet_maker/test_place_bet.py` | test | CRUD | `tests/line_provider/test_create_event.py` | role-match |
| `tests/bet_maker/test_selectors.py` | test | CRUD | `tests/line_provider/test_selectors.py` | exact |
| `tests/bet_maker/test_bet_routes.py` | test | request-response | `tests/line_provider/test_event_routes.py` | exact |
| `tests/bet_maker/test_health.py` | test | request-response | `tests/bet_maker/test_health.py` (P1, extend) + `tests/line_provider/test_health.py` | role-match |
| `tests/bet_maker/test_lifespan.py` | test | event-driven | no direct analog | no analog |
| `tests/bet_maker/test_alembic.py` | test | CRUD | no direct analog | no analog |
| `pyproject.toml` | config | — | `pyproject.toml` (current) | exact (modify) |
| `.planning/REQUIREMENTS.md` | doc | — | `.planning/REQUIREMENTS.md` (current) | exact (modify) |
| `.planning/ROADMAP.md` | doc | — | `.planning/ROADMAP.md` (current) | exact (modify) |

---

## Pattern Assignments

### `src/bet_maker/schemas/bets.py` (schema, request-response)

**Analog:** `src/line_provider/schemas/events.py`

**Imports pattern** (`src/line_provider/schemas/events.py` lines 1–13):
```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

from config.time import utc_now
from line_provider.helpers.money import quantize_coefficient
```

**Annotated type alias for validated Decimal** (`src/line_provider/schemas/events.py` lines 31–35):
```python
Coefficient = Annotated[
    Decimal,
    Field(gt=Decimal("0"), max_digits=8, decimal_places=2),
    AfterValidator(_quantize),
]
```

**Schema class with extra="forbid"** (`src/line_provider/schemas/events.py` lines 41–45):
```python
class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    coefficient: Coefficient
```

**Key differences for P3:**
- `Amount` type alias: `Field(gt=Decimal("0"), max_digits=12, decimal_places=2)` (12 digits, not 8)
- AfterValidator calls `quantize_amount` from `bet_maker.helpers.money` (not `quantize_coefficient`)
- Add `BetStatus(str, Enum)` with values `PENDING`, `WON`, `LOST` — same `(str, Enum)` pattern as `EventState` (Python 3.10 compatible, `StrEnum` is 3.11+)
- `BetRead` uses `model_config = ConfigDict(extra="forbid", from_attributes=True)` to enable `model_validate(orm_obj, from_attributes=True)`
- `BetRead` has `id: UUID`, `event_id: UUID`, `amount: Decimal`, `status: BetStatus`, `created_at: datetime` — no `coefficient` (D-01)

---

### `src/bet_maker/schemas/events.py` (schema, transform)

**Analog:** `src/line_provider/schemas/events.py` lines 15–18 — intentional duplication (D-12)

**Core pattern** (`src/line_provider/schemas/events.py` lines 15–18):
```python
class EventState(str, Enum):
    NEW = "NEW"
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"
```

**Key differences for P3:**
- Copy this exact class verbatim into `bet_maker/schemas/events.py` — intentional duplication per D-12 (service boundary isolation, same pattern as `EventFinishedMessage` duplication in P2 D-13)
- No other content in this file at P3 (EventSnapshot lives in `facades/event_lookup.py`, not here)
- Module docstring: `# EventState duplicated from line_provider.schemas.events — intentional service-boundary isolation (D-12)`

---

### `src/bet_maker/facades/event_lookup.py` (facade, request-response)

**Analog:** `src/line_provider/facades/event_bus.py`

**Full file** (`src/line_provider/facades/event_bus.py` lines 1–34):
```python
from __future__ import annotations

from typing import Protocol

import structlog

from line_provider.schemas.messages import EventFinishedMessage


class EventBus(Protocol):
    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None: ...


class NoopEventBus:
    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None:
        structlog.get_logger().info(
            "event_bus.publish.noop",
            routing_key=routing_key,
            event_id=str(message.event_id),
            new_state=message.new_state.value,
            schema_version=message.schema_version,
            correlation_id=message.correlation_id,
        )
```

**Key differences for P3:**
- `EventLookup(Protocol)` has one method: `async def get_event(self, event_id: UUID) -> EventSnapshot | None: ...`
- Add `EventSnapshot(BaseModel, frozen=True)`: fields `event_id: UUID`, `deadline: datetime`, `state: EventState`
- `StubEventLookup` is not a noop logger — it holds `dict[UUID, EventSnapshot]`, method `seed(snapshot: EventSnapshot) -> None`, method `seed_active(event_id: UUID, deadline: datetime | None = None) -> None` (convenience for tests), `get_event` returns dict lookup result
- `EventLookupDep = Annotated[EventLookup, Depends(get_event_lookup)]` defined at module bottom
- No structlog in StubEventLookup (no logging in test doubles per project convention)

---

### `src/bet_maker/facades/deps.py` (provider, request-response)

**Analog:** `src/line_provider/facades/deps.py`

**Full file** (`src/line_provider/facades/deps.py` lines 1–20):
```python
from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from line_provider.facades.event_bus import EventBus
from line_provider.infrastructure.store.in_memory import InMemoryEventStore


def get_store(request: Request) -> InMemoryEventStore:
    return cast(InMemoryEventStore, request.app.state.event_store)


def get_event_bus(request: Request) -> EventBus:
    return cast(EventBus, request.app.state.event_bus)


StoreDep = Annotated[InMemoryEventStore, Depends(get_store)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
```

**Key differences for P3:**
- Replace `get_store` with `get_engine(request) -> AsyncEngine` reading `request.app.state.engine`
- Replace `get_event_bus` with `get_sessionmaker(request) -> async_sessionmaker[AsyncSession]` reading `request.app.state.sessionmaker`
- Add `get_event_lookup(request) -> EventLookup` reading `request.app.state.event_lookup`
- Add `get_uow(request) -> AsyncUnitOfWork` — constructs `AsyncUnitOfWork(get_sessionmaker(request))`
- Add `get_session(request) -> AsyncSession` for read-only selectors — yields from `get_sessionmaker(request)()` (no UoW, no begin)
- Add `get_settings(request) -> BetMakerSettings` reading `request.app.state.settings`
- All `Annotated[..., Depends(...)]` aliases at module bottom: `EngineDep`, `SessionDep`, `UoWDep`, `EventLookupDep`

---

### `src/bet_maker/interactors/place_bet.py` (interactor, CRUD)

**Analog:** `src/line_provider/interactors/set_event_state.py`

**Imports + function signature pattern** (`src/line_provider/interactors/set_event_state.py` lines 1–34):
```python
from __future__ import annotations

from uuid import UUID

from line_provider.facades.event_bus import EventBus
from line_provider.helpers.state_machine import TransitionForbiddenError
from line_provider.infrastructure.store.in_memory import (
    EventNotFoundError,
    InMemoryEventStore,
)
from line_provider.schemas.events import Event, EventState


async def set_event_state(
    store: InMemoryEventStore,
    event_bus: EventBus,
    *,
    event_id: UUID,
    ...
) -> Event:
    current = await store.get_by_id(event_id)
    if current is None:
        raise EventNotFoundError(str(event_id))
```

**Key differences for P3:**
- Domain-specific exception: `class EventNotBettable(Exception): def __init__(self, reason: str)` — single exception class with `reason` attribute (route maps to 422 with `detail=f"event {event_id} is not bettable: {e.reason}"`)
- Arguments: `uow: AsyncUnitOfWork, *, event_id: UUID, amount: Decimal, event_lookup: EventLookup` (not positional store + bus)
- Validation sequence: `get_event(event_id)` → None check → deadline check → state check (all three conditions from D-14)
- Uses `config.time.utc_now` for deadline comparison (same import as `list_active_events.py`)
- `async with uow:` block contains `Bet(...)` construction + `uow.bets.add(bet)` + `await uow.session.flush()` + `await uow.session.refresh(bet)` + `return BetRead.model_validate(bet, from_attributes=True)` — all inside session (A1 mitigation)
- Return type `BetRead` (not raw ORM object — mitigates MissingGreenlet A1)

---

### `src/bet_maker/selectors/list_bets.py` (selector, CRUD)

**Analog:** `src/line_provider/selectors/list_active_events.py`

**Full file** (`src/line_provider/selectors/list_active_events.py` lines 1–11):
```python
from __future__ import annotations

from config.time import utc_now
from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventState


async def list_active_events(store: InMemoryEventStore) -> list[Event]:
    now = utc_now()
    return [e for e in await store.list_all() if e.state == EventState.NEW and e.deadline > now]
```

**Key differences for P3:**
- Parameter: `session: AsyncSession` (not store) — pure read, no UoW
- Uses SQLAlchemy `select(Bet).order_by(Bet.created_at.desc())` (not in-memory filter)
- Returns `list[BetRead]` via `[BetRead.model_validate(r, from_attributes=True) for r in rows]`
- No filtering by state or deadline (returns ALL bets)
- `rows = (await session.execute(stmt)).scalars()` pattern

---

### `src/bet_maker/selectors/get_bet.py` (selector, request-response)

**Analog:** `src/line_provider/selectors/get_event_by_id.py`

**Full file** (`src/line_provider/selectors/get_event_by_id.py` lines 1–14):
```python
from __future__ import annotations

from uuid import UUID

from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event


async def get_event_by_id(
    store: InMemoryEventStore,
    *,
    event_id: UUID,
) -> Event | None:
    return await store.get_by_id(event_id)
```

**Key differences for P3:**
- Parameter: `session: AsyncSession` (not store)
- Uses `await session.execute(select(Bet).where(Bet.id == bet_id))` then `.scalar_one_or_none()`
- Returns `BetRead | None` via `BetRead.model_validate(row, from_attributes=True) if row else None`
- Function name: `get_bet_by_id(session: AsyncSession, bet_id: UUID) -> BetRead | None`

---

### `src/bet_maker/helpers/money.py` (utility, transform)

**Analog:** `src/line_provider/helpers/money.py`

**Full file** (`src/line_provider/helpers/money.py` lines 1–16):
```python
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_TWO_PLACES = Decimal("0.01")


def quantize_coefficient(value: Decimal) -> Decimal:
    """Normalise coefficient to exactly two decimal places.

    Pydantic v2 `decimal_places=2` validates upper bound only — `Decimal("10")`
    passes but serialises as `"10"` not `"10.00"`. The spec requires exactly two
    decimal places; we accept `"10"` and quantize-on-input. Used by
    EventCreate.coefficient and EventUpdate.coefficient (after-validators).
    """
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
```

**Key differences for P3:**
- Rename function to `quantize_amount(value: Decimal) -> Decimal`
- Update docstring: references `BetCreate.amount` instead of `EventCreate.coefficient`
- Everything else identical (same sentinel `_TWO_PLACES`, same `ROUND_HALF_UP`)

---

### `src/bet_maker/helpers/status.py` (utility, transform)

**Analog:** `src/line_provider/helpers/state_machine.py`

**Core pattern** (`src/line_provider/helpers/state_machine.py` lines 1–10):
```python
from __future__ import annotations

from line_provider.schemas.events import EventState

ALLOWED_TRANSITIONS: frozenset[tuple[EventState, EventState]] = frozenset(...)

class TransitionForbiddenError(Exception):
    ...

def is_transition_allowed(current: EventState, new: EventState) -> bool:
    ...
```

**Key differences for P3:**
- P3 creates a stub only: `def event_state_to_bet_status(state: EventState) -> BetStatus: raise NotImplementedError("P5")`
- No class, no frozenset — pure stub for P5 to implement
- Import: `from bet_maker.schemas.bets import BetStatus` and `from bet_maker.schemas.events import EventState`

---

### `src/bet_maker/entrypoints/api/health.py` (entrypoint, request-response)

**Analog:** `src/line_provider/entrypoints/api/health.py` (P1 stub — replace, not extend)

**Current P1 shape to replace** (`src/bet_maker/entrypoints/api/health.py` lines 1–10 — both services identical):
```python
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

**Key differences for P3:**
- Add `from fastapi import Depends` and `from sqlalchemy.ext.asyncio import AsyncEngine`
- Add `from bet_maker.facades.deps import get_engine` and `from bet_maker.infrastructure.db.pings import ping_postgres`
- Signature: `async def health(engine: AsyncEngine = Depends(get_engine)) -> JSONResponse`
- Return type becomes `JSONResponse` (not `dict`) — needed for status_code=503
- 200: `JSONResponse({"status": "ok", "checks": {"postgres": "ok"}})`
- 503: `JSONResponse({"status": "degraded", "checks": {"postgres": "down"}}, status_code=503)`
- structlog binding on failure: `log.warning("health.check.failed", check="postgres")`

---

### `src/bet_maker/entrypoints/api/bets.py` (entrypoint, request-response)

**Analog:** `src/line_provider/entrypoints/api/events.py`

**Router + imports pattern** (`src/line_provider/entrypoints/api/events.py` lines 1–19):
```python
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from line_provider.facades.deps import EventBusDep, StoreDep
from line_provider.helpers.state_machine import TransitionForbiddenError
from line_provider.infrastructure.store.in_memory import (
    EventAlreadyExistsError,
    EventNotFoundError,
)
from line_provider.interactors.create_event import create_event
from line_provider.schemas.events import EventCreate, EventRead, EventUpdate
from line_provider.selectors.get_event_by_id import get_event_by_id

router = APIRouter(tags=["events"])
```

**POST handler pattern** (`src/line_provider/entrypoints/api/events.py` lines 22–35):
```python
@router.post(
    "/event",
    status_code=status.HTTP_201_CREATED,
    response_model=EventRead,
)
async def post_event(body: EventCreate, store: StoreDep) -> EventRead:
    try:
        event = await create_event(store, body=body)
    except EventAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return EventRead.model_validate(event.model_dump())
```

**GET by ID with 404 pattern** (`src/line_provider/entrypoints/api/events.py` lines 71–79):
```python
@router.get(
    "/event/{event_id}",
    response_model=EventRead,
)
async def get_event(event_id: UUID, store: StoreDep) -> EventRead:
    event = await get_event_by_id(store, event_id=event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return EventRead.model_validate(event.model_dump())
```

**Key differences for P3:**
- `router = APIRouter(tags=["bets"])` — not `["events"]`
- POST `/bet` maps `EventNotBettable` → `HTTPException(422, detail=f"event {event_id} is not bettable: {e.reason}")`
- POST handler injects `UoWDep`, `EventLookupDep` (via `Annotated[..., Depends(...)]` aliases)
- GET `/bets` injects `SessionDep` — calls `list_bets(session)` directly, no interactor
- GET `/bet/{bet_id}` injects `SessionDep` — calls `get_bet_by_id(session, bet_id)`, maps None → 404 with `detail=f"bet {bet_id} not found"`
- Response model for POST: `status_code=status.HTTP_201_CREATED, response_model=BetRead`
- Use `response.model_dump()` via `model_validate` pattern only if selector returns ORM object — but selectors return `BetRead` directly, so no extra conversion needed

---

### `src/bet_maker/entrypoints/lifespan.py` (infrastructure, event-driven)

**Analog:** `src/line_provider/entrypoints/lifespan.py` (extend P1 `src/bet_maker/entrypoints/lifespan.py`)

**P1 base to extend** (`src/bet_maker/entrypoints/lifespan.py` lines 1–23):
```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from bet_maker.settings.config import BetMakerSettings
from config.logging import configure_structlog


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = BetMakerSettings()
    configure_structlog(settings.log_level)
    log = structlog.get_logger()
    log.info("bet_maker.startup", service=settings.service_name)
    app.state.settings = settings
    try:
        yield
    finally:
        log.info("bet_maker.shutdown")
```

**line_provider analog for app.state pattern** (`src/line_provider/entrypoints/lifespan.py` lines 22–27):
```python
    app.state.settings = settings
    app.state.event_store = InMemoryEventStore()
    app.state.event_bus = NoopEventBus()
    try:
        yield
    finally:
```

**Key differences for P3:**
- Add imports: `from bet_maker.infrastructure.db.engine import create_engine_and_sessionmaker`, `from bet_maker.infrastructure.db.pings import wait_for_postgres`, `from bet_maker.facades.event_lookup import StubEventLookup`
- After `configure_structlog` and before `yield`: create engine + sessionmaker, call `await wait_for_postgres(engine)` (tenacity-decorated), set `app.state.engine`, `app.state.sessionmaker`, `app.state.event_lookup = StubEventLookup()`
- In `finally:` block: `await engine.dispose()`
- Wrap engine creation + ping in `try/except RuntimeError` to log clearly: `log.critical("bet_maker.startup.failed", reason=str(exc))` then re-raise

---

### `src/bet_maker/app.py` (infrastructure, request-response)

**Analog:** `src/line_provider/app.py`

**Full file** (`src/line_provider/app.py` lines 1–19):
```python
from __future__ import annotations

from fastapi import FastAPI

from line_provider.entrypoints.api import events, health
from line_provider.entrypoints.lifespan import lifespan
from line_provider.entrypoints.middleware import RequestContextMiddleware


def build_app() -> FastAPI:
    app = FastAPI(
        title="line-provider",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(events.router)
    return app
```

**Key differences for P3:**
- Already has this structure (P1). Modify: add `from bet_maker.entrypoints.api import bets` and `app.include_router(bets.router)` — that's the only change needed

---

## Shared Patterns

### Protocol + Stub facade pattern
**Source:** `src/line_provider/facades/event_bus.py`
**Apply to:** `src/bet_maker/facades/event_lookup.py`
```python
from __future__ import annotations
from typing import Protocol
import structlog

class EventBus(Protocol):
    async def publish(self, ...) -> None: ...

class NoopEventBus:
    async def publish(self, ...) -> None:
        structlog.get_logger().info("event_bus.publish.noop", ...)
```
P3 mirrors this: `EventLookup(Protocol)` + `StubEventLookup` (dict-backed, no logging). P4 adds `HttpEventLookup` without touching the Protocol.

### app.state dependency injection pattern
**Source:** `src/line_provider/facades/deps.py`
**Apply to:** `src/bet_maker/facades/deps.py`
```python
def get_store(request: Request) -> InMemoryEventStore:
    return cast(InMemoryEventStore, request.app.state.event_store)

StoreDep = Annotated[InMemoryEventStore, Depends(get_store)]
```
All `app.state.*` reads go through `cast(T, request.app.state.x)`. Never access `app.state` directly in route handlers — always via `Depends(get_x)`.

### `(str, Enum)` for Python 3.10 string enums
**Source:** `src/line_provider/schemas/events.py` line 15, `src/line_provider/schemas/messages.py` line 11
**Apply to:** `BetStatus` in `schemas/bets.py`, `EventState` in `schemas/events.py`
```python
class EventState(str, Enum):
    NEW = "NEW"
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"
```
`StrEnum` is Python 3.11+. Do NOT use `StrEnum`. This is a locked decision from P2 (D-13/D-20).

### Annotated type alias for validated Decimal
**Source:** `src/line_provider/schemas/events.py` lines 31–35
**Apply to:** `Amount` type alias in `schemas/bets.py`
```python
Coefficient = Annotated[
    Decimal,
    Field(gt=Decimal("0"), max_digits=8, decimal_places=2),
    AfterValidator(_quantize),
]
```
P3: `Amount = Annotated[Decimal, Field(gt=Decimal("0"), max_digits=12, decimal_places=2), AfterValidator(quantize_amount)]`

### REQ-ID docstrings in tests
**Source:** `tests/line_provider/test_create_event.py` lines 1–5, `tests/line_provider/test_event_routes.py` lines 1–7
**Apply to:** All `tests/bet_maker/test_*.py` files
```python
"""Unit tests for line_provider.interactors.create_event.

LP-03: create accepts EventCreate body, stores Event(state=NEW).
LP-08: duplicate event_id propagates EventAlreadyExistsError up.
"""
```
Each test function docstring references `BM-XX / QA-07 / D-XX` for grep-traceability.

### `from __future__ import annotations` at top of every file
**Source:** All files in `src/line_provider/` and `src/bet_maker/`
**Apply to:** All new `.py` files in P3
First line of every non-`__init__.py` Python file. Required for Python 3.10 forward-reference support and SQLAlchemy 2.0 typed column annotations.

### `extra="forbid"` on all Pydantic schemas
**Source:** `src/line_provider/schemas/events.py` lines 41–43
**Apply to:** `BetCreate`, `BetRead`, `EventSnapshot`
```python
class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

### Lifespan `app.state.*` initialization
**Source:** `src/line_provider/entrypoints/lifespan.py` lines 22–26
**Apply to:** `src/bet_maker/entrypoints/lifespan.py`
```python
    app.state.settings = settings
    app.state.event_store = InMemoryEventStore()
    app.state.event_bus = NoopEventBus()
    try:
        yield
    finally:
        log.info("line_provider.shutdown")
```
All P3 state goes on `app.state`. No module-level singletons except `AsyncEngine` (which is safe as a module-level pool — but still assigned to `app.state` for testability via dependency override).

---

## Test Pattern Assignments

### `tests/bet_maker/conftest.py` (modify P1)

**Analog:** `tests/line_provider/conftest.py`

**P1 fixture to extend** (`tests/bet_maker/conftest.py` lines 1–16):
```python
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from bet_maker.app import build_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**line_provider pattern to mirror** (`tests/line_provider/conftest.py` lines 13–29):
```python
@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    application = build_app()
    async with LifespanManager(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**Key differences for P3:**
- Add `app` fixture mirroring line_provider's (uses `LifespanManager`) — needed for tests that seed `app.state.event_lookup`
- `client` fixture depends on `app` fixture (not `build_app()` directly) — same as line_provider
- Add `seed_event` fixture: helper that calls `app.state.event_lookup.seed(snapshot)` — tests inject this for interactor/route tests
- P3 does NOT need a PG-backend client fixture yet (the `app` fixture uses `StubEventLookup` in lifespan which does not connect to PG); integration tests with real PG use root `tests/conftest.py` fixtures

### `tests/conftest.py` (extend — root level)

**Analog:** RESEARCH.md Pattern 4 — no existing analog in codebase

**Current state** (`tests/conftest.py` line 1):
```python
"""Root conftest. Shared fixtures land here as the test suite grows (P3+)."""
```

**To add per RESEARCH.md Pattern 4:**
- `postgres_container` fixture (`scope="session"`) using `PostgresContainer("postgres:16-alpine", driver="asyncpg")`
- `pg_dsn` fixture (`scope="session"`) returning `postgres_container.get_connection_url()`
- `run_alembic_migrations` fixture (`scope="session"`, sync, not async) using `alembic.command.upgrade(Config("alembic.ini"), "head")` twice for idempotency check; sets `sqlalchemy.url` via `alembic_cfg.set_main_option()`
- `async_engine` fixture (`scope="session"`, `@pytest_asyncio.fixture`) using `create_async_engine(pg_dsn, pool_pre_ping=True)`
- `session_factory` fixture (`scope="session"`) returning `async_sessionmaker(async_engine, expire_on_commit=False)`
- `truncate_bets` fixture (`autouse=True`, function scope) — teardown: `TRUNCATE bets RESTART IDENTITY CASCADE`

### `tests/bet_maker/test_event_lookup.py`

**Analog:** `tests/line_provider/test_facades.py`

**Structural pattern** (`tests/line_provider/test_facades.py` lines 33–44):
```python
async def test_noop_event_bus_implements_protocol() -> None:
    """D-11: NoopEventBus satisfies EventBus structural typing."""
    bus: EventBus = NoopEventBus()
    assert hasattr(bus, "publish")


async def test_noop_event_bus_publish_returns_none() -> None:
    """D-14: NoopEventBus.publish is a no-op (returns None)."""
    bus = NoopEventBus()
    await bus.publish(_message(), routing_key="event.finished.win")
```

**Key differences for P3:**
- Tests: `StubEventLookup satisfies EventLookup structural typing`, `seed + get_event roundtrip`, `get_event returns None when not seeded`, `seed_active creates snapshot with deadline in future and state=NEW`

### `tests/bet_maker/test_bet_routes.py`

**Analog:** `tests/line_provider/test_event_routes.py`

**Class-based test organization** (`tests/line_provider/test_event_routes.py` lines 45–60):
```python
class TestWiring:
    """LP-03/D-14: lifespan + router wiring smoke tests."""

    async def test_lifespan_wires_event_store_and_bus(self, app: FastAPI) -> None:
        """D-14: lifespan creates InMemoryEventStore + NoopEventBus in app.state."""
        assert isinstance(app.state.event_store, InMemoryEventStore)

class TestCreate:
    async def test_post_event_returns_201(self, client: AsyncClient) -> None:
        """LP-03: POST /event 201 + EventRead with state=NEW."""
```

**Decimal comparison pattern** (`tests/line_provider/test_event_routes.py` line 71):
```python
assert data["coefficient"] == "1.50"
```
P3 critical: `assert body["amount"] == "10.00"` — compare as STRING, never float. D-19.

---

## No Analog Found

Files with no close match in the codebase (planner uses RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason | Use Instead |
|------|------|-----------|--------|-------------|
| `src/bet_maker/models/bet.py` | model | CRUD | No SQLAlchemy ORM models exist yet | RESEARCH.md Pattern 1 (complete code recipe) |
| `src/bet_maker/facades/uow.py` | facade | CRUD | No UoW exists; only in-memory store | RESEARCH.md Pattern 2 (complete code recipe) |
| `src/bet_maker/infrastructure/db/engine.py` | infrastructure | CRUD | No async engine exists; line_provider has no DB | RESEARCH.md §D-16 (`pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800`) |
| `src/bet_maker/infrastructure/db/pings.py` | infrastructure | request-response | No tenacity-decorated ping exists | RESEARCH.md Pattern 5 (complete code recipe) |
| `alembic/versions/0001_bets_initial.py` | migration | CRUD | `alembic/versions/` is empty (`alembic/versions/.gitkeep`) | RESEARCH.md Pattern 3 (idempotent ENUM recipe) |
| `tests/conftest.py` (root, PG fixtures) | test | CRUD | Root conftest is a placeholder — no testcontainers usage exists | RESEARCH.md Pattern 4 (complete fixture recipe) |
| `tests/bet_maker/test_uow.py` | test | CRUD | No UoW in codebase to mirror | RESEARCH.md Pattern 2 shape for behavior expected |
| `tests/bet_maker/test_lifespan.py` | test | event-driven | No lifespan retry tests exist | RESEARCH.md §D-27 (tenacity retry, attempts override for test speed) |
| `tests/bet_maker/test_alembic.py` | test | CRUD | No alembic idempotency tests exist | RESEARCH.md Pitfall 2 + Pattern 3 |

---

## Key Invariants for Planner

1. **Alembic env.py — do not touch.** It already reads `BetMakerSettings().postgres_dsn` and accepts `set_main_option("sqlalchemy.url", ...)` override from tests. `alembic/env.py` line 19 must remain unchanged.

2. **`target_metadata = None` in env.py must become `target_metadata = Base.metadata`.** Currently line 21 is `target_metadata = None` — this means autogenerate will not detect model changes. P3 must update this line to import `Base` from `bet_maker.models.bet` and set `target_metadata = Base.metadata`.

3. **P1 health test assertion will break.** `tests/bet_maker/test_health.py` line 17: `assert response.json() == {"status": "ok"}` — update to `assert response.json()["status"] == "ok"` in first implementing task.

4. **Decimal comparison in tests: always string.** `assert body["amount"] == "10.00"` — never `== 10.0` or `== Decimal("10.00")`.

5. **`app` fixture over `build_app()` direct call.** Route/integration tests must use `app` fixture (with `LifespanManager`) to get live `app.state`, not bare `build_app()`. Only pure unit tests that don't need HTTP may skip the fixture.

6. **`alembic/versions/` ruff rule.** `pyproject.toml` line 51: `"alembic/versions/*.py" = ["E501", "N999"]` — migration filenames may have non-PEP8 names (e.g., `0001_bets_initial`) without linter errors.

---

## Metadata

**Analog search scope:** `src/line_provider/`, `src/bet_maker/`, `src/config/`, `tests/`, `alembic/`
**Files scanned:** 43
**Pattern extraction date:** 2026-05-15
