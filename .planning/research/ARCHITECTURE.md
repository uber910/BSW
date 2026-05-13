# Architecture Research

**Domain:** Two-service asynchronous Python betting system — `line-provider` (in-memory FastAPI publisher) + `bet-maker` (FastAPI + asyncpg/SQLAlchemy 2.0 consumer with reconciliation)
**Researched:** 2026-05-13
**Confidence:** HIGH (architectural patterns verified against SQLAlchemy 2.0 async docs and FastStream RabbitRouter docs via Context7)

## Framing

PROJECT.md already locks in the macro-architecture: two FastAPI services, RabbitMQ between them, layered architecture (`entrypoints` → `facades` → `interactors`/`selectors` → `helpers`), Unit of Work + Repository, async everywhere. This document does the deepening: paste-ready directory trees, the concrete shape of UoW + Repository, a specific RabbitMQ topology (with names), a reconciliation-job blueprint, lifespan ordering, build-order signal for the roadmapper, and a layered testing strategy.

The architecture is intentionally **CQRS-lite**:
- `interactors/` own writes (UoW, repositories, transactions).
- `selectors/` own reads (no UoW, plain `AsyncSession` query, returns DTOs).
This split is what most production FastAPI codebases converge to; it keeps the write path serialised and idempotent without dragging read queries through the transaction lifecycle.

## Standard Architecture

### System Overview — both services together

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              line-provider                                  │
├────────────────────────────────────────────────────────────────────────────┤
│  entrypoints/api/       (FastAPI: GET/POST/PATCH /events, /health)         │
│         │                                                                   │
│         v                                                                   │
│  facades/event_bus.py   (wraps RabbitRouter.broker.publish)                 │
│         │                                                                   │
│         v                                                                   │
│  interactors/events     (write use-cases: create_event, set_state)          │
│  selectors/events       (read use-cases: list_active, get_by_id)            │
│         │                                                                   │
│         v                                                                   │
│  infrastructure/store/  (InMemoryEventStore — dict + asyncio.Lock)          │
└────────────────────────────────────────────────────────────────────────────┘
              │                                                  ▲
              │ publish: events.finished                         │ GET /events/{id}
              │ (FINISHED_WIN | FINISHED_LOSE)                   │ (reconciliation pulls)
              v                                                  │
        ╔═════════════════════════════════════════════════════════╗
        ║     RabbitMQ 4.2  —  exchange:  events  (topic)         ║
        ║     queue:        bet_maker.events.finished              ║
        ║     binding key:  event.finished.*                        ║
        ║     DLX:          events.dlx (fanout)                    ║
        ║     DLQ:          bet_maker.events.finished.dlq          ║
        ╚═════════════════════════════════════════════════════════╝
              │                                                  │
              v                                                  │
┌────────────────────────────────────────────────────────────────────────────┐
│                                bet-maker                                    │
├────────────────────────────────────────────────────────────────────────────┤
│  entrypoints/api/                (FastAPI: GET /events, POST /bet,         │
│  entrypoints/consumers/           GET /bets, /health)                       │
│  entrypoints/workers/             (FastStream subscriber: events.finished) │
│         │                         (asyncio task: reconciliation loop)       │
│         v                                                                   │
│  facades/uow.py                  (AsyncUnitOfWork — async_sessionmaker      │
│  facades/event_bus.py             wrapper + repositories)                   │
│  facades/line_provider_client.py (httpx.AsyncClient + tenacity)             │
│         │                                                                   │
│         v                                                                   │
│  interactors/bets               (place_bet, settle_bets_for_event,          │
│  selectors/bets                  reconcile_pending_bets)                    │
│  selectors/events                (list_bets, get_active_events_cached)      │
│         │                                                                   │
│         v                                                                   │
│  repositories/                  (BetRepository — AsyncSession bound,        │
│  models/                         no commit; UoW owns the transaction)       │
│  infrastructure/db/             (engine, async_sessionmaker, lifespan)      │
│  infrastructure/broker/         (RabbitRouter setup)                        │
└────────────────────────────────────────────────────────────────────────────┘
              │                                                                
              v                                                                
        ┌────────────────────────┐                                             
        │  PostgreSQL 16          │  bets table + idempotency unique index    
        └────────────────────────┘                                             
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `entrypoints/api/` | HTTP surface: parse request, validate via Pydantic schemas, call facade/interactor, serialise response. **No business logic.** | FastAPI `APIRouter` + `Depends(...)` |
| `entrypoints/consumers/` | AMQP message handler: bind structlog context, call interactor, manual ack/nack, route to DLQ on poison. | FastStream `@router.subscriber(...)` with `AckPolicy.MANUAL` |
| `entrypoints/workers/` | Background asyncio tasks: reconciliation loop, periodic jobs. Started in lifespan. | `asyncio.create_task` wrapped with shutdown event |
| `facades/` | **Composition glue.** Builds an interactor or selector from its dependencies (UoW, http client, event bus) so entrypoints stay thin. Owns the `Depends` providers. | Plain async functions, `Depends`-wrapped |
| `interactors/` | Write use-cases. Each one represents **one business transaction**. Opens a UoW, calls repositories, commits, emits side-effects last. | Async function `place_bet(uow, dto) -> BetRead` |
| `selectors/` | Read-only queries. Take an `AsyncSession` (not a UoW), return DTOs. No commit, no FOR UPDATE. | Async function `list_bets(session, *, limit, offset) -> list[BetRead]` |
| `repositories/` | Encapsulates SQLAlchemy `select()` / `insert()` / `update()` against one aggregate. **Does not commit.** Bound to an `AsyncSession`. | Class `BetRepository` constructed with a session |
| `helpers/` | Pure functions: status mapping (`event_state -> bet_status`), money-quantization (`Decimal` → 2dp), URL helpers. No IO. | Module-level functions, fully typed |
| `models/` | SQLAlchemy 2.0 typed ORM models (`Mapped[...]`). Schema concerns only. | `class Bet(Base): id: Mapped[UUID] = mapped_column(...)` |
| `schemas/` | Pydantic models for HTTP request/response **and** AMQP message bodies. One source of truth across boundaries. | `class EventFinishedMessage(BaseModel): ...` |
| `infrastructure/` | Process-wide singletons + lifecycle: engine, async_sessionmaker, RabbitRouter, structlog config, http client, settings. | Module-level globals constructed in lifespan |
| `settings/` | `pydantic-settings` typed config per service. | `class BetMakerSettings(BaseSettings): ...` |

**Layer interaction rule (one direction only):**
`entrypoints` → `facades` → `interactors`/`selectors` → `repositories`/`helpers` → `models`/`infrastructure`
A layer never imports from a layer above it. `helpers/` is the only module other layers import from freely (pure functions).

## Recommended Project Structure

### Monorepo top level

```
.
├── pyproject.toml                # single, monorepo-style (see STACK.md)
├── uv.lock
├── docker-compose.yml
├── .env.example
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── alembic.ini                   # for bet-maker; one alembic project at repo root
├── alembic/                      # bet-maker migrations
│   ├── env.py                    # async template (alembic init -t async)
│   ├── script.py.mako
│   └── versions/
│       └── 20260513_0001_initial.py
├── src/
│   ├── line_provider/
│   └── bet_maker/
└── tests/
    ├── line_provider/
    ├── bet_maker/
    └── e2e/                      # cross-service docker-compose tests
```

### `src/line_provider/` — paste-ready tree

```
src/line_provider/
├── __init__.py
├── __main__.py                          # python -m line_provider  (uvicorn entrypoint)
├── app.py                               # build_app() factory
├── settings/
│   ├── __init__.py
│   └── config.py                        # LineProviderSettings(BaseSettings)
├── entrypoints/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── events.py                    # GET/POST/PATCH /events, GET /events/{id}
│   │   └── health.py                    # GET /health
│   └── lifespan.py                      # asynccontextmanager: broker + structlog
├── facades/
│   ├── __init__.py
│   ├── event_bus.py                     # wraps router.broker.publish; injectable
│   └── deps.py                          # FastAPI Depends providers (settings, store, bus)
├── interactors/
│   ├── __init__.py
│   ├── create_event.py                  # write: add to store
│   └── set_event_state.py               # write: transition state + publish to AMQP
├── selectors/
│   ├── __init__.py
│   ├── list_active_events.py            # read: deadline > now, state == NEW
│   └── get_event_by_id.py               # read: single event
├── helpers/
│   ├── __init__.py
│   ├── time.py                          # utc_now()  (centralised so tests can freeze)
│   └── state_machine.py                 # allowed transitions: NEW -> FINISHED_*
├── schemas/
│   ├── __init__.py
│   ├── events.py                        # EventCreate, EventRead, EventStatePatch
│   └── messages.py                      # EventFinishedMessage  (AMQP body)
├── infrastructure/
│   ├── __init__.py
│   ├── store/
│   │   ├── __init__.py
│   │   └── in_memory.py                 # InMemoryEventStore  (dict + asyncio.Lock)
│   ├── broker/
│   │   ├── __init__.py
│   │   └── rabbit.py                    # RabbitRouter instance + exchange/queue decl
│   └── logging.py                       # configure_structlog()
└── py.typed                              # marker for mypy --strict
```

### `src/bet_maker/` — paste-ready tree

```
src/bet_maker/
├── __init__.py
├── __main__.py
├── app.py                               # build_app() factory
├── settings/
│   ├── __init__.py
│   └── config.py                        # BetMakerSettings(BaseSettings)
├── entrypoints/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── bets.py                      # POST /bet, GET /bets
│   │   ├── events.py                    # GET /events (proxy/cache)
│   │   └── health.py                    # GET /health (pings PG + RabbitMQ)
│   ├── consumers/
│   │   ├── __init__.py
│   │   └── event_finished.py            # @router.subscriber("events.finished", ack=MANUAL)
│   ├── workers/
│   │   ├── __init__.py
│   │   └── reconciliation.py            # async loop, started in lifespan
│   └── lifespan.py                      # bootstrap engine/broker/http/log/worker
├── facades/
│   ├── __init__.py
│   ├── uow.py                           # AsyncUnitOfWork  (see code shape below)
│   ├── event_bus.py                     # OPTIONAL: only if bet-maker publishes (we do not — see Q3)
│   ├── line_provider_client.py          # httpx.AsyncClient + tenacity wrapper
│   ├── cache.py                         # tiny TTL dict for GET /events proxy
│   └── deps.py                          # FastAPI Depends providers
├── interactors/
│   ├── __init__.py
│   ├── place_bet.py                     # write: INSERT bet, idempotency check
│   ├── settle_bets_for_event.py         # write: SELECT ... FOR UPDATE + UPDATE; called by consumer
│   └── reconcile_pending_bets.py        # write: bulk settle via HTTP poll; called by worker
├── selectors/
│   ├── __init__.py
│   ├── list_bets.py                     # read: GET /bets
│   ├── list_pending_event_ids.py        # read: distinct event_ids of PENDING bets
│   └── list_active_events.py            # read: from cache/proxy
├── helpers/
│   ├── __init__.py
│   ├── status.py                        # event_state_to_bet_status()  (pure)
│   ├── money.py                         # quantize_amount() -> Decimal(...).quantize(0.01)
│   └── time.py                          # utc_now()
├── schemas/
│   ├── __init__.py
│   ├── bets.py                          # BetCreate, BetRead, BetStatus
│   ├── events.py                        # EventRead  (mirrors line-provider's, validated)
│   └── messages.py                      # EventFinishedMessage  (must match line-provider)
├── repositories/
│   ├── __init__.py
│   ├── base.py                          # BaseRepository (session-bound, no commit)
│   └── bets.py                          # BetRepository
├── models/
│   ├── __init__.py
│   ├── base.py                          # DeclarativeBase
│   └── bet.py                           # Bet(Base): id, event_id, amount, status, ts, idemp_key
├── infrastructure/
│   ├── __init__.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py                    # create_async_engine + async_sessionmaker
│   │   └── pings.py                     # SELECT 1 for /health
│   ├── broker/
│   │   ├── __init__.py
│   │   └── rabbit.py                    # RabbitRouter + exchange/queue/DLX declarations
│   └── logging.py                       # configure_structlog()  (shared shape with line-provider)
└── py.typed
```

### Structure Rationale

- **Split `consumers/` from `api/`** under `entrypoints/`: HTTP and AMQP are different transports with different concerns (manual ack, redelivery, DLQ); keeping them in separate sub-packages prevents a single "routes" folder from quietly mixing the two.
- **`workers/` is also under `entrypoints/`**: the reconciliation loop is conceptually an inbound trigger (timer fires → enter the application). Treating it as an entrypoint keeps the dependency direction clean — workers compose facades just like routes do.
- **`facades/uow.py` lives in `facades/`, not `infrastructure/`**: UoW is a *composition* concern (it bundles repositories + a session into one transactional scope). Engine/sessionmaker construction is `infrastructure/`; the UoW abstraction over them is `facades/`.
- **One `schemas/messages.py` per service that defines the AMQP body, both compatible**: Pydantic v2 models. Identical field names and types on both sides. No shared package — the duplication is intentional so the two services can evolve independently and the contract is explicit in each codebase.
- **`repositories/` is bet-maker-only**: line-provider's only "store" is an in-memory dict, which is a single class in `infrastructure/store/in_memory.py` rather than the full repository pattern. Repository + UoW is only valuable when there is a transactional DB.
- **`alembic/` at repo root, not under `src/bet_maker/`**: Alembic is a tool for one app, but conventionally it sits at the repo root so `alembic upgrade head` works without a `cd`. The `env.py` imports `bet_maker.models` and `bet_maker.settings`. Single alembic project; line-provider has no DB and no migrations.

## Architectural Patterns

### Pattern 1: Async Unit of Work + Repository (concrete shape)

**What:** A `UoW` is an async context manager that owns one `AsyncSession`, exposes the repositories bound to that session, and **owns the transaction lifecycle**. Repositories never call `session.commit()`; only the UoW does (and only on clean exit).

**When to use:** Every write use-case in bet-maker.

**Trade-offs:**
- Pro: every interactor is one transaction by construction; you can't forget to commit; you can't accidentally commit half a workflow.
- Pro: tests can swap the UoW for a fake that exposes the same repositories backed by in-memory lists.
- Con: one more abstraction; for a single-statement write it looks heavy. Acceptable — the test task is explicitly graded on architectural patterns.

**Why `async_sessionmaker.begin()` underneath, not raw `AsyncSession`:** Context7 confirms `async_sessionmaker.begin()` is the idiomatic way to get "session + auto-commit + auto-close + auto-rollback on exception" in SQLAlchemy 2.0 async. We wrap that, not raw `AsyncSession()`, because it makes the transactional guarantee structural.

**Code shape (verified against SQLAlchemy 2.0 async docs):**

```python
# src/bet_maker/facades/uow.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Self
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bet_maker.repositories.bets import BetRepository


class AsyncUnitOfWork:
    """One DB transaction per business operation.

    Usage:
        async with uow:
            bet = await uow.bets.add(bet_dto)
            # auto-commits on __aexit__; auto-rollbacks on exception
    """

    bets: BetRepository
    session: AsyncSession

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._cm: _AsyncSessionContextManager[AsyncSession] | None = None

    async def __aenter__(self) -> Self:
        # async_sessionmaker.begin() returns a context manager that opens
        # AsyncSession + a transaction. We delegate to it.
        self._cm = self._sessionmaker.begin()
        self.session = await self._cm.__aenter__()
        self.bets = BetRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Delegate commit-on-success / rollback-on-exception to SQLAlchemy.
        assert self._cm is not None
        await self._cm.__aexit__(exc_type, exc, tb)
        self._cm = None


# src/bet_maker/facades/deps.py
from functools import lru_cache
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from bet_maker.infrastructure.db.engine import get_sessionmaker
from bet_maker.facades.uow import AsyncUnitOfWork


def get_uow(
    sessionmaker: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
) -> AsyncUnitOfWork:
    # Construct fresh per request — UoW is cheap; session is opened on __aenter__.
    return AsyncUnitOfWork(sessionmaker)


# src/bet_maker/repositories/bets.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet, BetStatus
from bet_maker.schemas.bets import BetCreate


class BetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, dto: BetCreate) -> Bet:
        bet = Bet(event_id=dto.event_id, amount=dto.amount, status=BetStatus.PENDING)
        self._session.add(bet)
        await self._session.flush()       # flush, NOT commit; UoW commits
        return bet

    async def get_pending_locked(self, event_id: int) -> list[Bet]:
        # SELECT ... FOR UPDATE SKIP LOCKED — verified against SQLAlchemy 2.0 docs.
        # Combined with the consumer worker pattern this gives safe concurrent settle.
        stmt = (
            select(Bet)
            .where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def list_pending_event_ids(self) -> list[int]:
        stmt = select(Bet.event_id).where(Bet.status == BetStatus.PENDING).distinct()
        result = await self._session.execute(stmt)
        return list(result.scalars())


# src/bet_maker/interactors/settle_bets_for_event.py
from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.helpers.status import event_state_to_bet_status
from bet_maker.schemas.events import EventTerminalState


async def settle_bets_for_event(
    uow: AsyncUnitOfWork,
    *,
    event_id: int,
    new_state: EventTerminalState,
) -> int:
    """Write use-case. Returns number of bets settled."""
    new_bet_status = event_state_to_bet_status(new_state)
    async with uow:
        pending = await uow.bets.get_pending_locked(event_id)
        for bet in pending:
            bet.status = new_bet_status      # ORM mutation, flushed on __aexit__
        # UoW __aexit__ commits the transaction
        return len(pending)
```

The selector path is deliberately simpler — no UoW:

```python
# src/bet_maker/selectors/list_bets.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetRead


async def list_bets(session: AsyncSession, *, limit: int, offset: int) -> list[BetRead]:
    stmt = select(Bet).order_by(Bet.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars()
    return [BetRead.model_validate(r, from_attributes=True) for r in rows]
```

Selectors take a plain session (from a `Depends(get_session)` that yields from the sessionmaker without `begin()`). They never lock rows, never commit. This is the "read side" of the CQRS-lite split.

### Pattern 2: RabbitMQ topology — line-provider → bet-maker only

**What:** A **topic exchange** on the publish side, one durable queue with a DLX on the consume side. `line-provider` publishes; `bet-maker` consumes only. **bet-maker does not publish** — there is no business reason to (the only outbound integration is reconciliation, which is HTTP, not AMQP).

**Topology — exact names:**

| Object | Type / Name | Notes |
|--------|-------------|-------|
| Exchange | `events` (topic, durable=true) | Topic so routing keys can carry semantics; durable so it survives broker restart. |
| Routing key on publish | `event.finished.win` or `event.finished.lose` | Two keys, one schema. Lets future consumers filter cheaply. |
| Main queue | `bet_maker.events.finished` (durable=true) | Named by *consumer*, not topic — RabbitMQ convention so two consumers don't accidentally compete on the same queue. |
| Binding | `bet_maker.events.finished` ← `events` on key `event.finished.*` | Wildcard so both WIN and LOSE land in the same queue. |
| Queue arguments | `x-dead-letter-exchange: events.dlx`, `x-dead-letter-routing-key: event.finished.dead` | Failed/rejected messages auto-route to DLX. No `x-message-ttl` on the main queue (we don't want lost messages, we want stuck-message visibility). |
| DLX | `events.dlx` (fanout, durable=true) | Fanout — simplest possible; the only consumer of DLQ is human (RabbitMQ Management UI) or a retry worker. |
| DLQ | `bet_maker.events.finished.dlq` (durable=true) | Manually drained from the Management UI for the test task. Real systems add a retry worker that republishes with bounded attempts. |
| Retry mechanism | `manual_ack=False` after N redeliveries (FastStream tracks via headers) → `msg.reject(requeue=False)` → poison message lands in DLX/DLQ | Bounded retries done in application code, not via `x-message-ttl` round-tripping. Simpler and more visible in logs. |

**Why bet-maker does not publish:** the test-task's communication is strictly one-way (event status changes flow from line-provider to bet-maker). bet-maker's only response to a settle is to update its own DB; nothing downstream consumes from it. Adding a back-channel queue would be a fictitious requirement.

**Message schema — exact Pydantic body (single source of truth, mirrored in both services' `schemas/messages.py`):**

```python
# Identical content in src/line_provider/schemas/messages.py
# and        src/bet_maker/schemas/messages.py
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field


class EventTerminalState(StrEnum):
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"


class EventFinishedMessage(BaseModel):
    """AMQP body for routing key event.finished.{win,lose}.

    Versioned via `schema_version` so a future schema change can be
    detected at the consumer (poison-message it instead of mis-parsing).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    event_id: int
    new_state: EventTerminalState
    coefficient: Decimal
    occurred_at: datetime           # UTC, ISO-8601 in JSON
    correlation_id: str             # for log correlation across the boundary
```

**Publish call (line-provider, inside `interactors/set_event_state.py`):**

```python
await event_bus.publish(
    message=EventFinishedMessage(...),
    routing_key=f"event.finished.{new_state.value.split('_')[-1].lower()}",
    # routing_key='event.finished.win' or 'event.finished.lose'
)
# event_bus is router.broker.publish(...) wrapped in a facade
```

**Consumer (bet-maker, inside `entrypoints/consumers/event_finished.py`):**

```python
from faststream import AckPolicy
from faststream.rabbit import RabbitQueue, RabbitExchange
from faststream.rabbit.annotations import RabbitMessage

# Declared once in infrastructure/broker/rabbit.py and imported here
events_exchange = RabbitExchange("events", type="topic", durable=True)
events_finished_queue = RabbitQueue(
    "bet_maker.events.finished",
    durable=True,
    routing_key="event.finished.*",
    arguments={
        "x-dead-letter-exchange": "events.dlx",
        "x-dead-letter-routing-key": "event.finished.dead",
    },
)


@router.subscriber(
    events_finished_queue,
    events_exchange,
    ack_policy=AckPolicy.MANUAL,
)
async def on_event_finished(
    body: EventFinishedMessage,
    msg: RabbitMessage,
    uow: AsyncUnitOfWork = Depends(get_uow),
) -> None:
    structlog.contextvars.bind_contextvars(
        event_id=body.event_id,
        correlation_id=body.correlation_id,
        message_id=msg.message_id,
    )
    try:
        await settle_bets_for_event(uow, event_id=body.event_id, new_state=body.new_state)
    except Exception:
        # Decide based on redelivery count from headers; reject after N to send to DLX
        if msg.raw_message.redelivered and _retries_exceeded(msg):
            await msg.reject(requeue=False)        # -> DLX -> DLQ
        else:
            await msg.nack(requeue=True)
        raise
    else:
        await msg.ack()
```

`AckPolicy.MANUAL` is the canonical FastStream pattern verified in Context7 (`faststream.rabbit.annotations.RabbitMessage` + explicit `ack/nack/reject` calls).

### Pattern 3: Reconciliation job — in-process background task

**What:** A single `asyncio.Task` started in bet-maker's lifespan that loops every `RECONCILIATION_INTERVAL` seconds. Each tick:
1. Selector: collect distinct `event_id`s from PENDING bets.
2. For each `event_id`, fetch event status from line-provider over HTTP via `httpx.AsyncClient` (with `tenacity` exponential backoff).
3. If state is terminal (FINISHED_WIN | FINISHED_LOSE), call `settle_bets_for_event(uow, event_id, state)` — exactly the same interactor the AMQP consumer calls.

**Why in-process, not a separate worker:** for two services with one reconciler each, a separate process means another container, another Dockerfile target, another health check, more compose machinery. The job is IO-bound and runs every `N=30s`; it shares the same DB engine and httpx client as the API — single process, single set of pooled connections, simpler graceful shutdown. **A separate container would be overkill for a test task and arguably worse architecture** because it splits resources unnecessarily.

**Why an asyncio loop, not APScheduler or cron:** APScheduler is fine but adds a dependency for a 20-line loop. We use `asyncio.sleep()` with a `shutdown_event` to make cancellation clean. Cron requires a separate container.

**Concurrency control to avoid double-processing (consumer + reconciler racing on same bet):**
- `BetRepository.get_pending_locked()` uses `SELECT ... FOR UPDATE SKIP LOCKED` (verified above against SQLAlchemy 2.0 docs). The consumer's transaction holds the row lock; the reconciler's concurrent transaction either skips or waits. Combined with the status check `WHERE status = 'PENDING'`, a second write becomes a no-op even if both see the row.
- Additionally, the interactor checks `bet.status` again after acquiring the lock; if some other transaction settled it first, the row is already non-PENDING and is left alone (defensive idempotency).

**Code shape:**

```python
# src/bet_maker/entrypoints/workers/reconciliation.py
import asyncio
import structlog
from contextlib import suppress
from bet_maker.interactors.reconcile_pending_bets import reconcile_pending_bets

log = structlog.get_logger()


async def run_reconciliation_loop(
    *,
    interval_seconds: float,
    shutdown_event: asyncio.Event,
    deps: ReconciliationDeps,        # uow_factory, line_provider_client
) -> None:
    log.info("reconciliation.loop.start", interval=interval_seconds)
    while not shutdown_event.is_set():
        try:
            settled = await reconcile_pending_bets(
                uow=deps.uow_factory(),
                client=deps.line_provider_client,
            )
            log.info("reconciliation.tick.done", settled=settled)
        except Exception as exc:
            log.exception("reconciliation.tick.failed", exc=str(exc))
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
    log.info("reconciliation.loop.stop")
```

Started in lifespan with `task = asyncio.create_task(run_reconciliation_loop(...))`, cancelled on shutdown via `shutdown_event.set()` then `await task`.

### Pattern 4: FastAPI + FastStream lifespan composition

**What:** Both services use a custom `asynccontextmanager` lifespan that bootstraps dependencies in a strict order. For FastAPI ≥ 0.112.2 + FastStream ≥ 0.6, the RabbitRouter's lifespan is **auto-merged** when you `app.include_router(router)`, so you do not need to manually wire `lifespan=router.lifespan_context`. You wire your *own* lifespan and FastStream attaches.

**Startup order (bet-maker, hardest case):**

```
1. Load settings (pydantic-settings)            — pure, no IO; fails fast if env is missing
2. Configure structlog                          — must precede any log lines
3. Create async DB engine + sessionmaker        — pooled; with tenacity retry on connect
   3a. ping PG (SELECT 1) once                  — fail-fast surfaces bad DSN
4. Create httpx.AsyncClient for line-provider   — single instance; closed in shutdown
5. include FastStream RabbitRouter              — connects RabbitMQ, declares exchange/queue
   (this is done at app-build time, BEFORE lifespan; lifespan only kicks off the broker)
6. Start reconciliation worker (asyncio.Task)   — depends on (3) and (4)
7. yield                                        — app is ready
--- shutdown (reverse order) ---
8. Set shutdown_event; await worker task
9. Close httpx client
10. RabbitRouter auto-shutdown                  — drains in-flight subscribers
11. Dispose DB engine                           — closes pool
```

**Why this exact order:**
- DB before broker: the consumer (#5) needs the DB at message time; if the broker started first, a message could arrive before the pool is ready and trigger a nack-storm.
- httpx before worker: the worker calls line-provider via httpx; ordering enforces dependency.
- Shutdown in reverse: stopping the worker before closing the broker is wrong (the worker doesn't use the broker); stopping the worker before the http client is necessary (the worker uses the client). Mirroring is the safe heuristic.

**Lifespan code shape:**

```python
# src/bet_maker/entrypoints/lifespan.py
from contextlib import asynccontextmanager
from typing import AsyncIterator
import asyncio
import httpx
import structlog
from fastapi import FastAPI
from tenacity import retry, stop_after_attempt, wait_exponential

from bet_maker.infrastructure.db.engine import create_engine_and_sessionmaker
from bet_maker.infrastructure.db.pings import ping_postgres
from bet_maker.infrastructure.logging import configure_structlog
from bet_maker.entrypoints.workers.reconciliation import run_reconciliation_loop
from bet_maker.settings.config import BetMakerSettings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = BetMakerSettings()                           # (1)
    configure_structlog(settings.log_level)                 # (2)
    log = structlog.get_logger()

    engine, sessionmaker = create_engine_and_sessionmaker(settings.pg_dsn)  # (3)
    await _ping_with_retry(engine)                          # (3a)

    http_client = httpx.AsyncClient(                        # (4)
        base_url=str(settings.line_provider_base_url),
        timeout=httpx.Timeout(5.0),
    )

    # (5) is wired at app-construction time via app.include_router(router);
    #     FastStream auto-attaches its broker lifespan and starts here.

    shutdown_event = asyncio.Event()                        # (6)
    worker_task = asyncio.create_task(
        run_reconciliation_loop(
            interval_seconds=settings.reconciliation_interval_s,
            shutdown_event=shutdown_event,
            deps=ReconciliationDeps(
                uow_factory=lambda: AsyncUnitOfWork(sessionmaker),
                line_provider_client=http_client,
            ),
        ),
        name="reconciliation",
    )

    # Expose to routes via app.state — tested pattern, doesn't pollute Depends graph
    app.state.sessionmaker = sessionmaker
    app.state.http_client = http_client
    app.state.engine = engine

    try:
        yield                                               # (7)
    finally:
        shutdown_event.set()                                # (8)
        await worker_task
        await http_client.aclose()                          # (9)
        # (10) FastStream auto-shuts the broker
        await engine.dispose()                              # (11)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=0.5, max=8))
async def _ping_with_retry(engine) -> None:
    await ping_postgres(engine)
```

`line-provider`'s lifespan is the same shape but simpler (no DB, no http client, no reconciliation worker — only structlog + broker).

## Data Flow

### Request flow — POST /bet (the canonical write path)

```
[Client]
    │ POST /bet  { event_id, amount }
    v
[FastAPI route in entrypoints/api/bets.py]
    │ validate via BetCreate schema (Decimal>0, 2dp)
    │ resolve Depends(get_uow) -> AsyncUnitOfWork
    v
[facades/deps.py]
    │ build UoW from app.state.sessionmaker
    v
[interactors/place_bet.py]
    │ async with uow:
    │     bet = await uow.bets.add(dto)     -- SQLAlchemy INSERT + flush
    │     (uow commits on __aexit__)
    v
[response] 201 Created, BetRead { id, status: PENDING, ... }
```

### Queue flow — line-provider PATCH → bet-maker consumer

```
[Reviewer]
    │ PATCH /events/{id}  { new_state: FINISHED_WIN }
    v
[line-provider entrypoints/api/events.py]
    │ Depends(get_settings, get_store, get_event_bus)
    v
[interactors/set_event_state.py]
    │ store.set_state(event_id, FINISHED_WIN)   -- in-memory under asyncio.Lock
    │ event_bus.publish(EventFinishedMessage, "event.finished.win")
    v
[RabbitMQ exchange "events", topic, key=event.finished.win]
    │ binding match -> queue bet_maker.events.finished
    v
[bet-maker entrypoints/consumers/event_finished.py @router.subscriber]
    │ structlog bind: event_id, correlation_id, message_id
    │ Depends(get_uow)
    v
[interactors/settle_bets_for_event.py]
    │ async with uow:
    │   pending = await uow.bets.get_pending_locked(event_id)   -- SELECT FOR UPDATE SKIP LOCKED
    │   for bet in pending: bet.status = WON
    │   (uow commits)
    v
[consumer] await msg.ack()
```

### Reconciliation flow — defence in depth

```
[asyncio worker tick every N seconds]
    │
    v
[selectors/list_pending_event_ids.py]
    │ DISTINCT event_id WHERE status=PENDING
    v
[facades/line_provider_client.py]   (httpx + tenacity)
    │ for each event_id: GET /events/{id} on line-provider
    │ skip if state == NEW (not yet finished)
    │ collect terminal events
    v
[interactors/settle_bets_for_event.py]   (SAME interactor as consumer)
    │ async with uow:
    │   pending = await uow.bets.get_pending_locked(event_id)   -- FOR UPDATE SKIP LOCKED
    │   if consumer is currently locking the row, this skips it -> safe race avoidance
    │   else: settle and commit
```

### Healthcheck flow

```
[docker-compose healthcheck: curl /health every 10s]
    │
    v
[entrypoints/api/health.py]
    │ parallel asyncio.gather:
    │   - ping_postgres(engine)        -- SELECT 1 with 1s timeout
    │   - ping_rabbitmq(router.broker) -- channel open check, 1s timeout
    v
    200 { status: ok, postgres: ok, rabbitmq: ok }  if both pass
    503 { ... }                                     if any fails
```

## Suggested Build Order (Roadmapper Signal)

Each phase is "no work in phase N depends on phase N+k". This is the minimum-dependency ordering.

### Phase 1: Skeleton + Infrastructure (no business logic)

**Deliverable:** `docker compose up` runs both services, both return `200 OK` on `/health`, CI is green.

- pyproject.toml (already from STACK.md), uv.lock
- `src/line_provider/app.py` + `src/bet_maker/app.py` — empty FastAPI apps + `/health` returning `{ok: true}`
- Dockerfiles (multi-stage, slim-bookworm, non-root)
- docker-compose.yml: postgres + rabbitmq (with healthchecks) + both services
- structlog configuration (D3)
- pydantic-settings classes (D7)
- pre-commit + ruff + mypy config
- GitHub Actions CI (D10)
- README skeleton

**Blocks:** nothing — this is the foundation.
**Blocked by:** nothing.
**Why first:** every later phase needs `docker compose up` to be working; getting CI green here is one-time cost, then every PR gets the signal.

### Phase 2: line-provider domain (in-memory store, HTTP-only)

**Deliverable:** `POST /events`, `PATCH /events/{id}`, `GET /events`, `GET /events/{id}` all work; line-provider has no AMQP yet.

- `infrastructure/store/in_memory.py` — dict + asyncio.Lock
- `schemas/events.py` — Pydantic models
- `helpers/state_machine.py` — allowed transitions
- `interactors/create_event.py`, `interactors/set_event_state.py` (no publish yet)
- `selectors/list_active_events.py`, `selectors/get_event_by_id.py`
- `entrypoints/api/events.py` — wire all four routes
- Unit tests on interactors/selectors/helpers

**Blocks:** Phase 4 (bet-maker reconciliation needs GET /events/{id}).
**Blocked by:** Phase 1.

### Phase 3: bet-maker domain (DB-only, no AMQP)

**Deliverable:** `POST /bet`, `GET /bets` work against PostgreSQL; Alembic migration applied; UoW + Repository pattern in place.

- `models/bet.py` — SQLAlchemy 2.0 typed model
- Alembic initial migration (async template)
- `infrastructure/db/engine.py` — engine + sessionmaker
- `repositories/bets.py` — BetRepository
- `facades/uow.py` — AsyncUnitOfWork
- `helpers/money.py`, `helpers/status.py`
- `schemas/bets.py`
- `interactors/place_bet.py`
- `selectors/list_bets.py`
- `entrypoints/api/bets.py`
- `/health` upgraded to ping PG (D2)
- Unit tests + integration tests on POST /bet / GET /bets

**Blocks:** Phase 5.
**Blocked by:** Phase 1 (compose has PG); not blocked by Phase 2.
**Parallelisable with Phase 2** if two devs — same blocker (Phase 1), no shared code.

### Phase 4: bet-maker GET /events + line-provider HTTP integration

**Deliverable:** bet-maker exposes `GET /events` by proxying line-provider; tiny TTL cache reduces calls.

- `facades/line_provider_client.py` — httpx + tenacity
- `facades/cache.py` — TTL dict
- `selectors/list_active_events.py` (cached proxy)
- `entrypoints/api/events.py` on bet-maker
- Integration test using `httpx.AsyncClient(transport=ASGITransport(app=line_provider))` to drive both apps in one test

**Blocks:** Phase 6 (reconciliation reuses the client).
**Blocked by:** Phase 2 (needs line-provider GET /events/{id}).

### Phase 5: RabbitMQ integration (publisher + consumer + DLQ)

**Deliverable:** PATCH on line-provider triggers settle in bet-maker via AMQP; DLQ wired; manual ack.

- `infrastructure/broker/rabbit.py` in both services (exchange/queue/DLX declaration)
- `schemas/messages.py` in both services (identical content)
- line-provider `facades/event_bus.py` + publish in `interactors/set_event_state.py`
- bet-maker `entrypoints/consumers/event_finished.py` with `AckPolicy.MANUAL`
- bet-maker `interactors/settle_bets_for_event.py` (FOR UPDATE SKIP LOCKED — D9)
- `/health` upgraded to ping RabbitMQ (completes D2)
- `TestRabbitBroker` unit tests on consumer
- One full e2e test (real RabbitMQ container): PATCH event -> wait -> assert bet status

**Blocks:** Phase 6.
**Blocked by:** Phase 2 + Phase 3.

### Phase 6: Reconciliation job

**Deliverable:** asyncio worker started in lifespan polls line-provider for PENDING bets' events; settles via the same interactor as the consumer.

- `entrypoints/workers/reconciliation.py`
- `interactors/reconcile_pending_bets.py`
- `selectors/list_pending_event_ids.py`
- Lifespan changes: start + cancel worker
- Test that simulates "consumer never received message" by skipping the publish: reconciler must settle within one interval

**Blocks:** Phase 7 (CI must include the reconciliation test).
**Blocked by:** Phase 4 + Phase 5 (needs both the http client and the interactor).

### Phase 7: Documentation polish + final CI

**Deliverable:** README is complete, OpenAPI tags/summaries (D8), AsyncAPI at /asyncapi, CI badge.

- README curl examples, architecture ASCII diagram, "what I'd add next" section
- OpenAPI: tags, summaries, response_model, status_code, response examples
- AsyncAPI URL in README
- pytest-cov threshold in CI
- Verify graceful shutdown (D6) with `docker compose down` log capture

**Blocks:** nothing.
**Blocked by:** Phases 1–6.

### Build-order dependency graph

```
[Phase 1: skeleton] ──┬──> [Phase 2: line-provider HTTP] ──┬──> [Phase 5: RabbitMQ]
                      │                                     │
                      └──> [Phase 3: bet-maker DB] ─────────┘
                                                            │
                                                            v
                                                  [Phase 4: HTTP integration]
                                                            │
                                                            v
                                                  [Phase 6: reconciliation]
                                                            │
                                                            v
                                                  [Phase 7: docs + polish]
```

**Critical path:** 1 → 2 → 5 → 6 → 7 (covers the Core Value).
**Parallelisable:** Phase 2 and Phase 3 can be built in parallel by two devs (different services, no shared code yet).

## Testing Architecture

### Layer-by-layer testing strategy

| Layer | Test type | Tools | Confidence |
|-------|-----------|-------|------------|
| `helpers/` | Pure unit | pytest, no fixtures | HIGH — they're pure functions |
| `selectors/` | Unit with fake `AsyncSession`, OR integration with real PG | pytest + ephemeral PG schema | Prefer integration; selectors are trivially testable against a real DB and selector mocks lie about query semantics |
| `interactors/` (write) | Integration with real PG | pytest + testcontainers / docker-compose PG + Alembic upgrade head before test session | This is the only honest way to test FOR UPDATE SKIP LOCKED, unique constraints, ON CONFLICT |
| `repositories/` | Integration with real PG | Same as above | Same reason — repository correctness IS query correctness |
| `facades/uow.py` | Integration | Same as above | The point of UoW is transactionality; needs a real transaction |
| `entrypoints/api/` | API integration | `httpx.AsyncClient(transport=ASGITransport(app=app))` + ephemeral PG | Tests the whole vertical: validation -> interactor -> DB |
| `entrypoints/consumers/` | Unit-ish with `TestRabbitBroker` (in-memory) | FastStream `TestRabbitBroker` (Context7-verified) | Fast, deterministic; patches publishers/subscribers so handlers run synchronously |
| `entrypoints/workers/` (reconciliation) | Integration | Real PG + mocked httpx (`respx` library) | Don't drive a real line-provider; mock the HTTP response and assert the side effect on bets |
| Cross-service e2e (one big test) | docker-compose | pytest + `docker compose up`-from-fixture + real RabbitMQ | One full happy-path test: place bet → patch event → observe bet settled |

### Concrete fixture shapes

**Real PG via testcontainers (preferred for a test task because it doesn't require docker-compose to be running):**

```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg

@pytest.fixture(scope="session")
async def engine(pg_container):
    dsn = pg_container.get_connection_url().replace("psycopg2", "asyncpg")
    engine = create_async_engine(dsn)
    # Run Alembic upgrade head against this engine (or create_all for speed)
    yield engine
    await engine.dispose()

@pytest.fixture
async def sessionmaker_(engine):
    return async_sessionmaker(engine, expire_on_commit=False)

@pytest.fixture
async def uow(sessionmaker_):
    return AsyncUnitOfWork(sessionmaker_)
```

**Why testcontainers over a docker-compose-shared DB:** parallel test runs need isolated databases; testcontainers gives one per test session for free. Alternative: SQLite in-memory — **reject**, because FOR UPDATE SKIP LOCKED and `with_for_update(skip_locked=True)` is PG-only; running tests on a different DB would hide bugs.

**TestRabbitBroker for consumer (Context7-verified pattern):**

```python
# tests/bet_maker/test_consumer.py
import pytest
from faststream.rabbit import TestRabbitBroker
from bet_maker.infrastructure.broker.rabbit import router
from bet_maker.schemas.messages import EventFinishedMessage, EventTerminalState

async def test_consumer_settles_pending_bets(uow, freeze_time):
    # Arrange: insert a PENDING bet
    async with uow:
        await uow.bets.add(BetCreate(event_id=42, amount=Decimal("10.00")))

    # Act: publish to in-memory broker
    async with TestRabbitBroker(router.broker) as broker:
        await broker.publish(
            EventFinishedMessage(event_id=42, new_state=EventTerminalState.FINISHED_WIN, ...),
            exchange="events",
            routing_key="event.finished.win",
        )

    # Assert: bet status is WON, ack was called once
    async with uow:
        bets = await uow.bets.list_by_event(42)
        assert bets[0].status == BetStatus.WON
```

**Mocked line-provider HTTP for reconciliation (using `respx`):**

```python
# tests/bet_maker/test_reconciliation.py
import respx
from httpx import Response

async def test_reconciliation_settles_finished_event(uow, http_client):
    async with uow:
        await uow.bets.add(BetCreate(event_id=42, amount=Decimal("10.00")))

    with respx.mock(base_url="http://line-provider") as mock:
        mock.get("/events/42").respond(200, json={
            "id": 42, "state": "FINISHED_WIN", "coefficient": "2.5", ...
        })
        await reconcile_pending_bets(uow=uow, client=http_client)

    async with uow:
        bets = await uow.bets.list_by_event(42)
        assert bets[0].status == BetStatus.WON
```

**Inter-service integration (one ASGI transport test, no docker required):**

```python
# tests/e2e/test_cross_service.py
import httpx
from line_provider.app import build_app as build_line_provider
from bet_maker.app import build_app as build_bet_maker

async def test_patch_event_triggers_settle_via_amqp():
    # Use TestRabbitBroker as the shared in-memory broker for both apps
    lp = build_line_provider()
    bm = build_bet_maker()
    async with TestRabbitBroker(lp_router.broker), TestRabbitBroker(bm_router.broker):
        lp_client = httpx.AsyncClient(transport=httpx.ASGITransport(lp))
        bm_client = httpx.AsyncClient(transport=httpx.ASGITransport(bm))

        await lp_client.post("/events", json={"id": 42, "coefficient": "2.0", ...})
        await bm_client.post("/bet", json={"event_id": 42, "amount": "10.00"})
        await lp_client.patch("/events/42", json={"new_state": "FINISHED_WIN"})
        # TestRabbitBroker invokes the consumer synchronously inside the with-block

        resp = await bm_client.get("/bets")
        assert resp.json()[0]["status"] == "WON"
```

**One real-RabbitMQ e2e** (run only in CI's `e2e` job, on the docker-compose stack) covers the gap between TestRabbitBroker (in-memory, no real broker semantics) and production. This is the test that *would* catch a misconfigured DLX or a missing queue argument; TestRabbitBroker won't.

## Scaling Considerations

The test task is fixed-scale (`docker compose up` on one machine), but a reviewer mentally probes "would this scale?" Here is the honest answer per scale tier:

| Scale | Architecture adjustments |
|-------|--------------------------|
| 0–1k bets/day (test task) | Current design as-is. One replica each, single PG, single RabbitMQ. |
| 1k–100k bets/day | Add a horizontal replica of bet-maker behind a load balancer. RabbitMQ distributes messages across competing consumers naturally; `FOR UPDATE SKIP LOCKED` already makes the consumer + reconciler race-safe (D9). Reconciliation should move to its own container at this point so it can be sized independently and disabled in maintenance windows. PG pool size needs tuning (`pool_size=10, max_overflow=20` per replica). |
| 100k+ bets/day | Partition `bets` table by `event_id` hash or `created_at` range. Switch line-provider to publish via a persistent outbox if it ever gains a DB (it doesn't per TZ). Add a Redis cache in front of line-provider's GET /events. RabbitMQ becomes a clustered deployment with quorum queues. |

### Scaling priorities (what breaks first)

1. **First bottleneck:** PG connection pool exhaustion on bet-maker during a settle spike (one event finishes, hundreds of bets get locked simultaneously). Fix: cap pool size, batch the settle (`WHERE event_id = X` is one UPDATE, not N).
2. **Second bottleneck:** Reconciliation loop calling line-provider in a tight loop becomes a hot path. Fix: batch the GET (a `GET /events?ids=1,2,3` extension would be the right move), or skip reconciliation entirely once observed lost-message rate is zero (it's defence in depth, not a hot path).
3. **Third bottleneck:** Single RabbitMQ node fails. Fix: clustered RabbitMQ + quorum queues. Out of scope for the test task.

## Anti-Patterns

### Anti-Pattern 1: Committing in a repository

**What people do:** `await self._session.commit()` inside `BetRepository.add()` for "convenience."
**Why it's wrong:** Repository now owns transaction lifetime, which means an interactor can't compose two repository calls into one transaction. The whole point of UoW dies. Also breaks tests that need to rollback after each test.
**Do this instead:** Repositories call `await self._session.flush()` at most. Only the UoW's `__aexit__` (delegated to `async_sessionmaker.begin()`) commits.

### Anti-Pattern 2: Publishing to AMQP from inside a DB transaction

**What people do:** `async with uow: ...; await event_bus.publish(...)` — but with the `publish` *inside* the `with` block.
**Why it's wrong:** Two failure modes: (a) DB commit succeeds, broker publish fails — you have an orphan state in DB with no AMQP event (you said you do that, you didn't); (b) DB commit fails after broker publish — you have an AMQP event but no DB state (you didn't do it, you said you did). The two systems aren't coordinated; the transactional outbox pattern exists precisely to solve this, and we explicitly ruled it out per the TZ's in-memory constraint on line-provider.
**Do this instead:** For line-provider, publish *after* the in-memory commit (the in-memory store is single-process, atomic enough). For bet-maker, the rule is moot — bet-maker doesn't publish. Generally: side-effects after transactions, never inside.

### Anti-Pattern 3: Sharing one `AsyncSession` across requests

**What people do:** Create one `AsyncSession` at startup and reuse it.
**Why it's wrong:** Sessions aren't thread-safe (or task-safe), accumulate identity-map state, leak memory under load. Concurrent requests will corrupt each other's flush state.
**Do this instead:** One session per UoW instance, one UoW per business operation, one operation per request. `async_sessionmaker` is the factory; call it per request via `Depends`.

### Anti-Pattern 4: Auto-ack consumers

**What people do:** Default FastStream subscriber, no `AckPolicy.MANUAL`, no explicit `msg.ack()`.
**Why it's wrong:** Auto-ack ack-then-process means a crash mid-processing loses the message. The TZ's reliability requirement ("bet never stuck in PENDING") is violated on any consumer crash.
**Do this instead:** `ack_policy=AckPolicy.MANUAL` + explicit `await msg.ack()` only after DB commit succeeds. On exception: `nack(requeue=True)` for transient errors, `reject(requeue=False)` after bounded retries to send to DLQ.

### Anti-Pattern 5: Two `RabbitBroker` instances in the same process

**What people do:** Use FastStream's `RabbitRouter` for subscribers but instantiate a fresh `RabbitBroker` for publishing from HTTP routes.
**Why it's wrong:** Two connection pools, no shared lifespan, duplicate AsyncAPI specs. Subtle bugs where the publisher connects fine but the subscriber doesn't (different config drift).
**Do this instead:** Publish via `router.broker.publish(...)` exposed through a tiny `EventBus` facade. One broker per service.

### Anti-Pattern 6: Reading from the in-memory store via async without a lock

**What people do:** `return self._store[event_id]` directly, treating `dict` access as safe in asyncio.
**Why it's wrong:** Multiple concurrent requests can read-modify-write the same key (status transition) and lose updates. Asyncio doesn't preempt mid-statement, but `await` points between read and write are race windows.
**Do this instead:** Wrap state-mutation methods in `asyncio.Lock()`. Pure reads (no await between fetch and use) can skip the lock, but defaulting to lock is safer and not measurable overhead at this scale.

### Anti-Pattern 7: Mixing alembic configuration with app settings

**What people do:** Read the DB URL from `alembic.ini`'s hardcoded `sqlalchemy.url`.
**Why it's wrong:** Two sources of truth — one for app, one for migrations. Drift inevitable. Real bug: dev runs migrations against staging by accident.
**Do this instead:** `alembic/env.py` imports `bet_maker.settings.config.BetMakerSettings()` and reads `settings.pg_dsn`. One source of truth.

## Integration Points

### External services

| Service | Integration pattern | Notes |
|---------|---------------------|-------|
| PostgreSQL | `postgresql+asyncpg://` via SQLAlchemy 2.0 async engine + pooled `async_sessionmaker` | Driver pinned (`asyncpg>=0.31`). One engine per process. Connection pool size in settings. |
| RabbitMQ | FastStream `RabbitRouter` with `RabbitExchange("events", type="topic")` + `RabbitQueue("bet_maker.events.finished", durable=True, arguments={x-dead-letter-...})` | Single broker connection per service. Manual ack policy. AsyncAPI at `/asyncapi`. |
| line-provider (from bet-maker) | `httpx.AsyncClient` singleton, `tenacity` retry decorator on requests | Base URL via pydantic-settings (`BET_MAKER_LINE_PROVIDER_BASE_URL`). One client per service, closed in shutdown. |

### Internal boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| line-provider entrypoint → in-memory store | Direct call via `Depends(get_store)` | The store is a singleton instance attached to `app.state` in lifespan. |
| line-provider interactor → AMQP | `event_bus.publish()` facade wrapping `router.broker.publish()` | After in-memory commit, never before. |
| bet-maker entrypoint → interactor | Direct call via `Depends(get_uow)` providing `AsyncUnitOfWork` | UoW is per-request, cheap to construct. |
| bet-maker consumer → interactor | Same path as HTTP; consumer is just a different entrypoint | This is why we share `settle_bets_for_event` between consumer and reconciler — one code path, two triggers. |
| bet-maker worker → line-provider | `httpx.AsyncClient` via `Depends(get_line_provider_client)` | Reuse, don't construct per request. |
| bet-maker layers | `entrypoints → facades → interactors/selectors → repositories/helpers → models/infrastructure` | One direction only. `helpers` may be imported from anywhere (pure functions). |

## Sources

- `/websites/sqlalchemy_en_20` (Context7) — `async_sessionmaker.begin()` pattern, `Select.with_for_update(skip_locked=True)` — **HIGH confidence**
- `/ag2ai/faststream` (Context7) — `RabbitRouter` + FastAPI auto-lifespan (≥0.112.2), `AckPolicy.MANUAL` + `RabbitMessage.ack/nack/reject`, `RabbitQueue(arguments={"x-dead-letter-exchange": ...})`, `RabbitExchange(type="topic")`, `TestRabbitBroker` for in-memory tests, `router.broker.publish()` for HTTP-route publishing — **HIGH confidence**
- `/Users/dmitrydankov/Personal/BSW/.planning/PROJECT.md` — TZ requirements, Core Value, locked layered-architecture decision
- `/Users/dmitrydankov/Personal/BSW/.planning/research/STACK.md` — pinned versions for FastAPI, FastStream, SQLAlchemy, Pydantic, httpx, tenacity
- `/Users/dmitrydankov/Personal/BSW/.planning/research/FEATURES.md` — D1–D10 differentiators that influence module shape (reconciliation worker, /health endpoint shape, idempotency at consumer, DLQ topology)

---
*Architecture research for: two-service asynchronous Python betting system (RabbitMQ + PostgreSQL + reconciliation)*
*Researched: 2026-05-13*
