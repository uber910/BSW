# Phase 5: RabbitMQ Integration — Pattern Map

**Mapped:** 2026-05-18
**Files analyzed:** 26 (new/modified files from CONTEXT.md integration points)
**Analogs found:** 24 / 26

---

## File Inventory

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/bet_maker/entrypoints/messaging.py` | consumer entrypoint | event-driven (broker → handler → UoW → PG) | `src/bet_maker/entrypoints/middleware.py` (clear/bind contextvars shape) + `src/bet_maker/facades/line_provider_client.py` (tenacity shape) | role-match composite |
| `src/bet_maker/interactors/settle_bets_for_event.py` | interactor | CRUD + batch | `src/bet_maker/interactors/place_bet.py` | exact role-match |
| `src/bet_maker/schemas/messages.py` | schema | — | `src/line_provider/schemas/messages.py` | exact (byte-for-byte copy) |
| `src/bet_maker/schemas/settle.py` | schema / DTO | — | `src/bet_maker/schemas/bets.py` (Pydantic BaseModel + ConfigDict) | exact role-match |
| `src/bet_maker/messaging/routing.py` | config / constants | — | `src/line_provider/interactors/set_event_state.py` lines 19-22 (`_TERMINAL_TO_ROUTING`) | partial (same constants, different module) |
| `src/line_provider/messaging/routing.py` | config / constants | — | same as above | partial |
| `src/bet_maker/entrypoints/lifespan.py` (modified) | lifespan | startup/shutdown | `src/bet_maker/entrypoints/lifespan.py` itself (current version) | self-extension |
| `src/line_provider/entrypoints/lifespan.py` (modified) | lifespan | startup/shutdown | `src/line_provider/entrypoints/lifespan.py` itself (current version) | self-extension |
| `src/bet_maker/entrypoints/api/health.py` (modified) | controller | request-response | `src/bet_maker/entrypoints/api/health.py` itself (current version) | self-extension |
| `src/bet_maker/facades/deps.py` (modified) | DI | — | `src/bet_maker/facades/deps.py` itself + `src/line_provider/facades/deps.py` | self-extension |
| `src/bet_maker/repositories/bets.py` (modified) | repository | CRUD + FOR UPDATE SKIP LOCKED | `src/bet_maker/repositories/bets.py` itself (current version) | self-extension |
| `src/bet_maker/models/bet.py` (modified) | model | — | `src/bet_maker/models/bet.py` itself (current version) | self-extension |
| `src/line_provider/facades/event_bus.py` (modified) | publisher facade | event-driven | `src/line_provider/facades/event_bus.py` itself (current version) | self-extension |
| `alembic/versions/20260518_0002_bets_settled_columns.py` | migration | — | `alembic/versions/20260515_0001_bets_initial.py` | exact role-match |
| `tests/contract/__init__.py` | test package init | — | `tests/e2e/__init__.py` | exact |
| `tests/contract/test_event_finished_message_schema.py` | contract test | — | `tests/line_provider/test_schemas.py` | role-match |
| `tests/bet_maker/test_messaging.py` | unit test (TestRabbitBroker) | event-driven | `tests/line_provider/test_set_event_state.py` (FakeEventBus + asyncio pattern) | role-match |
| `tests/bet_maker/test_settle.py` | unit + integration test | CRUD + concurrent | `tests/bet_maker/test_repositories.py` + `tests/line_provider/test_set_event_state.py` | role-match composite |
| `tests/bet_maker/test_e2e_rabbitmq.py` | e2e test | event-driven + HTTP | `tests/bet_maker/conftest.py` (testcontainers + LifespanManager pattern) | role-match |
| `tests/bet_maker/test_health.py` (modified) | unit test | request-response | `tests/bet_maker/test_health.py` itself | self-extension |
| `tests/bet_maker/test_lifespan.py` (modified) | integration test | startup/shutdown | `tests/bet_maker/test_lifespan.py` itself | self-extension |
| `tests/line_provider/test_lifespan.py` | integration test | startup/shutdown | `tests/bet_maker/test_lifespan.py` | exact role-match |
| `tests/line_provider/test_event_bus.py` | unit test | event-driven | `tests/line_provider/test_set_event_state.py` | role-match |
| `tests/conftest.py` (modified) | test fixtures | — | `tests/conftest.py` itself (session-scoped PG testcontainer) | self-extension |
| `pyproject.toml` (modified) | config / packaging | — | existing `[dependency-groups.dev]` block | self-extension |
| `.planning/REQUIREMENTS.md` (modified) | docs sync | — | — | no-analog (doc-only) |

---

## Per-File Patterns

### `src/bet_maker/entrypoints/messaging.py` (consumer entrypoint, event-driven)

**Primary analog:** `src/bet_maker/entrypoints/middleware.py` (structlog contextvars clear/bind/finally shape)
**Secondary analog:** `src/bet_maker/facades/line_provider_client.py` (tenacity `retry()` + `_is_retryable` + `_log_before_sleep`)

**Imports pattern** — from RESEARCH.md (all verified against 0.6.7):
```python
from __future__ import annotations

import asyncio

import structlog
from faststream import AckPolicy
from faststream.exceptions import DecodeError
from faststream.rabbit.annotations import RabbitMessage
from faststream.rabbit.fastapi import RabbitRouter
from faststream.rabbit.schemas import Channel, ExchangeType, RabbitExchange, RabbitQueue
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from structlog.contextvars import bind_contextvars, clear_contextvars
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
from bet_maker.schemas.messages import EventFinishedMessage
from bet_maker.settings.config import BetMakerSettings
```

**RabbitRouter construction pattern** (RESEARCH §1, VERIFIED):
```python
settings = BetMakerSettings()

router = RabbitRouter(
    str(settings.rabbitmq_url),
    default_channel=Channel(prefetch_count=10),
)
```

**Subscriber decoration pattern** — `routing_key` on `RabbitQueue`, NOT on decorator (RESEARCH §2, VERIFIED):
```python
@router.subscriber(
    queue=RabbitQueue(
        "bet_maker.events.finished",
        durable=True,
        routing_key="event.finished.*",
        arguments={
            "x-dead-letter-exchange": "bsw.events.dlx",
            "x-dead-letter-routing-key": "bet_maker.events.finished",
        },
    ),
    exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
    ack_policy=AckPolicy.MANUAL,
)
async def on_event_finished(
    payload: EventFinishedMessage,
    msg: RabbitMessage,
) -> None: ...
```

**structlog contextvars pattern** — analog: `src/bet_maker/entrypoints/middleware.py:18-26`:
```python
# middleware.py lines 18-26 — same clear→bind→try→finally clear shape:
structlog.contextvars.clear_contextvars()
structlog.contextvars.bind_contextvars(request_id=request_id)
try:
    response = await call_next(request)
    ...
finally:
    structlog.contextvars.clear_contextvars()
```

Handler must follow the same pattern (D-27):
```python
log = structlog.get_logger()
clear_contextvars()
try:
    bind_contextvars(
        message_id=msg.message_id,
        correlation_id=msg.correlation_id,
        event_id=str(payload.event_id),
    )
    ...
finally:
    clear_contextvars()
```

**tenacity inline retry pattern** — analog: `src/bet_maker/facades/line_provider_client.py:51-96`:

The Phase 4 factory uses `_is_retryable` and `_log_before_sleep`. Phase 5 uses the same tenacity API but with a DB-specific predicate and inline application (not factory). Copy structure from `line_provider_client.py:51-78` but replace the predicate:

```python
# line_provider_client.py:51-62 — template for _is_retryable shape:
def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= _HTTP_5XX_FLOOR
    return False
```

Phase 5 version replaces with DB transient check (D-09):
```python
def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, Exception) and getattr(exc, "connection_invalidated", False):
        return True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    return False
```

Inline retry applied at call site (D-08 — 3 attempts, multiplier=0.2, min=0.2, max=2):
```python
_settle_with_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
    retry=retry_if_exception(_is_transient),
    before_sleep=_log_before_sleep,
    reraise=True,
)(settle_bets_for_event)
```

**ack/reject ladder pattern** (D-09/D-10/D-11):
```python
try:
    if payload.schema_version != 1:
        raise UnsupportedSchemaVersion(f"schema_version={payload.schema_version}")

    async with AsyncUnitOfWork(sessionmaker) as uow:
        result = await _settle_with_retry(uow, event_id=payload.event_id, ...)

    await msg.ack()

except (ValidationError, DecodeError, UnsupportedSchemaVersion, IntegrityError) as exc:
    log.warning("settle.poison_to_dlq", exc_type=type(exc).__name__, ...)
    await msg.reject(requeue=False)

except Exception as exc:
    log.error("settle.transient_exhausted", exc_type=type(exc).__name__, ...)
    await msg.reject(requeue=False)

finally:
    clear_contextvars()
```

**Custom exception**:
```python
class UnsupportedSchemaVersion(ValueError):
    pass
```

**Deviation from analogs:** No existing FastStream consumer in codebase. structlog shape copied from middleware.py, tenacity shape from line_provider_client.py but with different predicate and inline application. `sessionmaker` must be read from `app.state` — inject via a module-level reference or pass through DI (see deps.py section below).

---

### `src/bet_maker/interactors/settle_bets_for_event.py` (interactor, CRUD + batch)

**Analog:** `src/bet_maker/interactors/place_bet.py`

**Imports pattern** — analog `place_bet.py:1-16`:
```python
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, update

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.messages import EventTerminalState
```

**Result DTO pattern** — analog `bet_maker/schemas/bets.py:53-64` (BetRead with frozen ConfigDict):
```python
class SettleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    terminal_state: EventTerminalState
    settled_count: int
    settled_bet_ids: list[UUID]
    settled_via: Literal["consumer", "reconciler"]
    settled_at: datetime
```

**async with uow pattern** — analog `place_bet.py:76-87`:
```python
# place_bet.py:76-87:
async with uow:
    bet = Bet(event_id=event_id, amount=quantize_amount(amount))
    uow.bets.add(bet)
    await uow.session.flush()
    await uow.session.refresh(bet)
    log.info("place_bet.created", bet_id=str(bet.id), ...)
    return BetRead.model_validate(bet, from_attributes=True)
```

Phase 5 pattern — UoW wraps the bulk UPDATE (not INSERT), `settled_at` from PG `func.now()`:
```python
async with uow:
    bets = await uow.bets.get_pending_locked(event_id)
    if not bets:
        log.info("settle.noop", event_id=str(event_id), reason="no PENDING bets")
        return SettleResult(settled_count=0, settled_bet_ids=[], ...)

    new_status = BetStatus.WON if terminal_state == EventTerminalState.FINISHED_WIN else BetStatus.LOST
    bet_ids = [b.id for b in bets]

    await uow.session.execute(
        update(Bet)
        .where(Bet.id.in_(bet_ids))
        .values(status=new_status, settled_at=func.now(), settled_via=settled_via)
    )
    # UoW auto-commits on clean exit
```

**structlog logging pattern** — analog `place_bet.py:56-73` (module-level logger + keyword args):
```python
log = structlog.get_logger()

log.info(
    "settle.committed",
    event_id=str(event_id),
    settled_count=len(bet_ids),
    settled_via=settled_via,
)
```

**Deviation from place_bet.py:** No validation before `async with uow` (no event lookup); uses bulk UPDATE via `session.execute(update(...))` instead of `session.add`; function signature uses keyword-only args (same style as `set_event_state`). `settled_at` is NOT read back from DB after UPDATE (populated by PG `func.now()` — value in `SettleResult.settled_at` should come from `utc_now()` from `config.time` to avoid an extra flush+refresh round-trip).

---

### `src/bet_maker/schemas/messages.py` (schema, byte-for-byte copy)

**Analog:** `src/line_provider/schemas/messages.py` (exact copy — D-28)

Full file `src/line_provider/schemas/messages.py:1-25`:
```python
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class EventTerminalState(str, Enum):
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"


class EventFinishedMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    event_id: UUID
    new_state: EventTerminalState
    coefficient: Annotated[Decimal, Field(gt=Decimal("0"), max_digits=8, decimal_places=2)]
    occurred_at: AwareDatetime
    correlation_id: str
```

**Deviation:** Copy verbatim. Only change: module docstring noting this is the bet-maker copy (D-28 contract: no cross-service imports). Add `UnsupportedSchemaVersion` here or in `messaging.py` — either is valid; prefer `messaging.py` to keep schema file pure.

---

### `src/bet_maker/schemas/settle.py` (schema / DTO)

**Analog:** `src/bet_maker/schemas/bets.py:43-64` (Pydantic BaseModel with `ConfigDict(extra="forbid")`)

**Pattern** — `bets.py:53-64` (BetRead):
```python
class BetRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    event_id: UUID
    amount: Decimal
    status: BetStatus
    created_at: datetime
```

Phase 5 `SettleResult` uses `frozen=True` (not `from_attributes=True`) because it is constructed in Python code, not from ORM:
```python
class SettleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    terminal_state: EventTerminalState
    settled_count: int
    settled_bet_ids: list[UUID]
    settled_via: Literal["consumer", "reconciler"]
    settled_at: datetime
```

**Deviation:** `frozen=True` instead of `from_attributes=True`. Import `EventTerminalState` from `bet_maker.schemas.messages` (same package — no cross-service import).

---

### `src/bet_maker/messaging/routing.py` (constants module)

**Analog:** `src/line_provider/interactors/set_event_state.py:19-22`

Full constants block from `set_event_state.py:19-22`:
```python
_TERMINAL_TO_ROUTING: dict[EventState, str] = {
    EventState.FINISHED_WIN: "event.finished.win",
    EventState.FINISHED_LOSE: "event.finished.lose",
}
```

Phase 5 pattern — `Final[str]` typed constants (D-05):
```python
from __future__ import annotations

from typing import Final

EVENT_FINISHED_WIN: Final[str] = "event.finished.win"
EVENT_FINISHED_LOSE: Final[str] = "event.finished.lose"
EVENT_FINISHED_WILDCARD: Final[str] = "event.finished.*"
```

**Deviation:** Immutable `Final[str]` instead of dict (dict allowed mutation). Public names (no leading underscore). New `messaging/` sub-package — needs `src/bet_maker/messaging/__init__.py`.

---

### `src/line_provider/messaging/routing.py` (constants module)

**Analog:** Same as above — `src/line_provider/interactors/set_event_state.py:19-22`

Identical structure to `bet_maker/messaging/routing.py`. Additionally, `set_event_state.py` should import from this module after Phase 5 (CONTEXT.md D-05: re-export `_TERMINAL_TO_ROUTING` constants). New `src/line_provider/messaging/__init__.py` needed.

---

### `src/bet_maker/entrypoints/lifespan.py` (modified — add broker layer)

**Analog:** Current `src/bet_maker/entrypoints/lifespan.py` (self-extension)

**Current shutdown pattern** — `lifespan.py:61-70`:
```python
try:
    yield
finally:
    log.info("bet_maker.shutdown")
    try:
        await http_client.aclose()
    finally:
        await engine.dispose()
```

**Extension — add broker connect after httpx, add broker close as outermost try/finally:**

New imports to add:
```python
from faststream.rabbit.schemas import ExchangeType, RabbitExchange, RabbitQueue
from bet_maker.entrypoints.messaging import router as rabbit_router
```

New startup block after `http_client` creation (D-21 ordering):
```python
await rabbit_router.broker.connect()
await rabbit_router.broker.declare_exchange(
    RabbitExchange("bsw.events.dlx", type=ExchangeType.DIRECT, durable=True)
)
dlq = await rabbit_router.broker.declare_queue(
    RabbitQueue("bet_maker.events.finished.dlq", durable=True)
)
await dlq.bind(exchange="bsw.events.dlx", routing_key="bet_maker.events.finished")
```

New shutdown — broker close is the outermost try/finally (reverse order of startup):
```python
try:
    yield
finally:
    log.info("bet_maker.shutdown")
    try:
        await rabbit_router.broker.close()
    finally:
        try:
            await http_client.aclose()
        finally:
            await engine.dispose()
```

**Deviation:** Broker connect happens AFTER httpx singleton (D-21). Broker close is outermost shutdown (reverse order). `rabbit_router` imported from `messaging.py` — circular import risk is zero since `messaging.py` does not import from `lifespan.py`.

---

### `src/line_provider/entrypoints/lifespan.py` (modified — add broker layer)

**Analog:** Current `src/line_provider/entrypoints/lifespan.py` (self-extension)

Current full file `lifespan.py:1-28` (already read). Extension pattern (D-24):

New imports to add:
```python
from faststream.rabbit.schemas import ExchangeType, RabbitExchange
from line_provider.entrypoints.messaging import router as rabbit_router
from line_provider.facades.event_bus import RabbitEventBus
```

Remove `NoopEventBus` import. New startup:
```python
await rabbit_router.broker.connect()
await rabbit_router.broker.declare_exchange(
    RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
)
app.state.event_bus = RabbitEventBus(rabbit_router.broker)
```

New shutdown:
```python
try:
    yield
finally:
    log.info("line_provider.shutdown")
    await rabbit_router.broker.close()
```

**Deviation:** `NoopEventBus()` replaced by `RabbitEventBus(router.broker)`. Broker connect before `app.state` assignment (so `event_bus` is always initialized after connect).

Note: line-provider needs a `src/line_provider/entrypoints/messaging.py` module that declares the `RabbitRouter` instance (even if no subscribers). This module needs to exist so lifespan can import `router`.

---

### `src/bet_maker/entrypoints/api/health.py` (modified — add RMQ checks)

**Analog:** Current `src/bet_maker/entrypoints/api/health.py` (self-extension)

Current pattern `health.py:1-31`:
```python
from bet_maker.facades.deps import EngineDep
from bet_maker.infrastructure.db.pings import ping_postgres

@router.get("/health")
async def health(engine: EngineDep) -> JSONResponse:
    pg_ok = await ping_postgres(engine)
    if pg_ok:
        return JSONResponse(status_code=200, content={"status": "ok", "checks": {"postgres": "ok"}})
    return JSONResponse(status_code=503, content={"status": "degraded", "checks": {"postgres": "down"}})
```

Extension — add `RabbitBrokerDep` injection (D-20):
```python
from bet_maker.facades.deps import EngineDep, RabbitBrokerDep

@router.get("/health")
async def health(engine: EngineDep, broker: RabbitBrokerDep) -> JSONResponse:
    pg_ok = await ping_postgres(engine)
    rmq_ok = await broker.ping(timeout=1.0)
    subs_ok = len(broker.subscribers) > 0

    if pg_ok and rmq_ok and subs_ok:
        return JSONResponse(status_code=200, content={
            "status": "ok",
            "checks": {"postgres": "ok", "rabbitmq": "ok", "rabbitmq_consumer": "ok"},
        })
    return JSONResponse(status_code=503, content={
        "status": "degraded",
        "checks": {
            "postgres": "ok" if pg_ok else "down",
            "rabbitmq": "ok" if rmq_ok else "down",
            "rabbitmq_consumer": "ok" if subs_ok else "no subscribers",
        },
    })
```

**Deviation:** Add two new checks, keep same JSON response shape convention.

---

### `src/bet_maker/facades/deps.py` (modified — add RabbitBroker provider)

**Analog:** Current `src/bet_maker/facades/deps.py` (self-extension) + `src/line_provider/facades/deps.py`

Line-provider pattern `deps.py:12-20` (cast from app.state):
```python
def get_event_bus(request: Request) -> EventBus:
    return cast(EventBus, request.app.state.event_bus)

EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
```

Bet-maker existing pattern `deps.py:41-48`:
```python
def get_uow(request: Request) -> AsyncUnitOfWork:
    sessionmaker = get_sessionmaker(request)
    return AsyncUnitOfWork(sessionmaker)

UoWDep = Annotated[AsyncUnitOfWork, Depends(get_uow)]
```

New provider to add (same cast-from-app.state pattern):
```python
from faststream.rabbit import RabbitBroker

def get_rabbit_broker(request: Request) -> RabbitBroker:
    from bet_maker.entrypoints.messaging import router  # noqa: PLC0415
    return router.broker

RabbitBrokerDep = Annotated[RabbitBroker, Depends(get_rabbit_broker)]
```

**Note:** `router.broker` is module-level singleton. Reading it directly (not from `app.state`) is safe because there is only one `RabbitRouter` instance per process (F5/Anti-Pattern 5). Alternatively, lifespan can pin `app.state.rabbit_broker = router.broker` and cast here — both work. The direct reference avoids an extra `app.state` key.

**Deviation from line-provider deps.py:** No `EventBusDep` needed on bet-maker side (bet-maker is consumer, not publisher). Add `RabbitBrokerDep` only. `SettleInteractorDep` is not needed — `settle_bets_for_event` is a plain async function (not a class), injected via UoWDep the same way `place_bet` is.

---

### `src/bet_maker/repositories/bets.py` (modified — add get_pending_locked)

**Analog:** Current `src/bet_maker/repositories/bets.py:26-37` (`get_by_id` pattern)

Existing `get_by_id` method `bets.py:32-37`:
```python
async def get_by_id(self, bet_id: UUID) -> Bet | None:
    result = await self._session.execute(select(Bet).where(Bet.id == bet_id))
    return result.scalar_one_or_none()
```

New method — same SELECT pattern with `with_for_update(skip_locked=True)` and `WHERE status=PENDING`:
```python
async def get_pending_locked(self, event_id: UUID) -> list[Bet]:
    result = await self._session.execute(
        select(Bet)
        .where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())
```

Import to add: `from bet_maker.schemas.bets import BetStatus`

**Deviation:** Returns `list[Bet]` (not `Bet | None`). Uses `with_for_update(skip_locked=True)` — no existing analog in current repo, but SQLAlchemy 2.0 API confirmed in RESEARCH.md. No flush, no commit — same anti-pattern protection as existing methods.

---

### `src/bet_maker/models/bet.py` (modified — add settled_at, settled_via)

**Analog:** Current `src/bet_maker/models/bet.py:66-74` (existing nullable `Mapped` column pattern)

Existing timestamp columns pattern `bet.py:66-74`:
```python
created_at: Mapped[datetime] = mapped_column(
    server_default=func.now(),
    nullable=False,
)
updated_at: Mapped[datetime] = mapped_column(
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False,
)
```

New columns to append (D-13):
```python
import sqlalchemy as sa

settled_at: Mapped[datetime | None] = mapped_column(
    sa.DateTime(timezone=True), nullable=True
)
settled_via: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
```

Import to add: `import sqlalchemy as sa` (if not already aliased; current file uses `from sqlalchemy import Enum as SqlEnum, Numeric, func` — add `DateTime, Text` to that import or use `sa.DateTime`, `sa.Text` with `import sqlalchemy as sa`).

**Deviation:** `nullable=True` (no `server_default`). `Mapped[datetime | None]` syntax already used in Python 3.10 style. `sa.Text()` for `settled_via` (convention: short string, not ENUM).

---

### `src/line_provider/facades/event_bus.py` (modified — add RabbitEventBus)

**Analog:** Current `src/line_provider/facades/event_bus.py:19-34` (NoopEventBus pattern)

Existing `NoopEventBus.publish` `event_bus.py:19-34`:
```python
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

New `RabbitEventBus` class follows same interface (D-23):
```python
from faststream.rabbit import RabbitBroker
from faststream.rabbit.schemas import ExchangeType, RabbitExchange


class RabbitEventBus:
    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker

    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None:
        await self._broker.publish(
            message,
            routing_key=routing_key,
            exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
            persist=True,
            correlation_id=message.correlation_id,
        )
        structlog.get_logger().info(
            "line_provider.publish",
            routing_key=routing_key,
            event_id=str(message.event_id),
            new_state=message.new_state.value,
            correlation_id=message.correlation_id,
        )
```

**Deviation from NoopEventBus:** Constructor takes `RabbitBroker`. `structlog.info` after publish (not as substitute for publish). `persist=True` + `correlation_id=message.correlation_id` passed to broker (RESEARCH §4 + Pitfall 6 fix).

---

### `alembic/versions/20260518_0002_bets_settled_columns.py` (migration)

**Analog:** `alembic/versions/20260515_0001_bets_initial.py`

Existing pattern `0001_bets_initial.py:1-93` — header format, `revision`, `down_revision`, `op.add_column` convention with `sa.DateTime(timezone=True)`:

```python
"""bets settled columns -- add settled_at + settled_via

Phase 5 / D-13: observability columns for bet settlement.
settled_at: when the bet was settled (PG func.now() filled by UPDATE).
settled_via: 'consumer' or 'reconciler' (Phase 6 reuses same interactor).

Revision ID: 0002_bets_settled_columns
Revises: 0001_bets_initial
Create Date: 2026-05-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_bets_settled_columns"
down_revision = "0001_bets_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bets", sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bets", sa.Column("settled_via", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("bets", "settled_via")
    op.drop_column("bets", "settled_at")
```

**Deviation from initial migration:** No ENUM creation. Pure `add_column` — simpler than initial migration. No `postgresql.ENUM` import needed. `sa.Text()` (not `sa.String`) matches idiomatic PG for short strings without schema-enforced length.

---

### `tests/contract/test_event_finished_message_schema.py` (contract test)

**Analog:** `tests/line_provider/test_schemas.py` (Pydantic schema verification pattern)

Test file style — `test_schemas.py` uses plain `assert` on model attributes (no async, no fixtures). Contract test pattern from RESEARCH.md §Testing §Contract test:

```python
from __future__ import annotations

import json

from bet_maker.schemas.messages import EventFinishedMessage as BMMessage
from line_provider.schemas.messages import EventFinishedMessage as LPMessage


def test_schemas_are_identical() -> None:
    lp_schema = json.dumps(LPMessage.model_json_schema(), sort_keys=True)
    bm_schema = json.dumps(BMMessage.model_json_schema(), sort_keys=True)
    assert lp_schema == bm_schema, (
        "EventFinishedMessage schema drift detected between services"
    )
```

**Deviation:** `sort_keys=True` to normalize field order (RESEARCH §Contract test pitfall). Synchronous test (no `@pytest.mark.asyncio`). Requires `tests/contract/__init__.py`.

---

### `tests/bet_maker/test_messaging.py` (unit test, TestRabbitBroker)

**Analog:** `tests/line_provider/test_set_event_state.py` (FakeEventBus, asyncio.gather, branch coverage style)

Test class/function structure from `test_set_event_state.py:44-80`:
```python
async def test_happy_path_new_to_finished_win_publishes() -> None:
    store = InMemoryEventStore()
    bus = FakeEventBus()
    ...
    assert len(bus.calls) == 1
```

TestRabbitBroker pattern from RESEARCH.md §7:
```python
from faststream.rabbit.testing import TestRabbitBroker
from bet_maker.entrypoints.messaging import router, on_event_finished

async def test_happy_path(session_factory) -> None:
    async with TestRabbitBroker(router.broker) as br:
        await br.publish(
            EventFinishedMessage(...),
            queue="bet_maker.events.finished",
            exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
        )
        on_event_finished.mock.assert_called_once()
```

Test class structure — mirror `test_set_event_state.py` convention (one function per branch, descriptive names):
- `test_happy_path_settles_bets_and_acks`
- `test_poison_validation_error_rejects_to_dlq`
- `test_poison_unsupported_schema_version_rejects_to_dlq`
- `test_poison_integrity_error_rejects_to_dlq`
- `test_transient_retry_success_acks`
- `test_transient_exhaustion_rejects_to_dlq`
- `test_noop_zero_pending_bets_acks_with_info_log`

**Deviation:** `TestRabbitBroker` is the mock infrastructure (no `FakeEventBus`). Tests must mock `settle_bets_for_event` via `unittest.mock.AsyncMock` to isolate handler logic. `session_factory` fixture from conftest (real PG not required for pure handler tests — mock the interactor).

---

### `tests/bet_maker/test_settle.py` (integration test, CRUD + concurrent)

**Analog:** `tests/bet_maker/test_repositories.py` (session_factory, real PG, multiple assertion patterns)

Existing test pattern `test_repositories.py:36-45`:
```python
@pytest.mark.asyncio(loop_scope="session")
class TestRuntime:
    async def test_add_stages_bet_in_session(
        self,
        session_factory: async_sessionmaker,
    ) -> None:
        async with session_factory() as session:
            repo = BetRepository(session)
            ...
```

Concurrent test pattern from `test_set_event_state.py:209-237` (asyncio.gather with suppress):
```python
async def test_concurrent_set_state_same_id_publishes_exactly_once() -> None:
    await asyncio.gather(
        do(EventState.FINISHED_WIN),
        do(EventState.FINISHED_LOSE),
    )
    assert len(bus.calls) == 1
```

Phase 5 concurrent settle test (D-12/D-15/D-16, RESEARCH §Concurrent consumer + reconciler recipe):
```python
@pytest.mark.asyncio(loop_scope="session")
class TestSettleConcurrent:
    async def test_concurrent_settle_no_double_update(
        self,
        session_factory: async_sessionmaker,
    ) -> None:
        # insert 3 PENDING bets same event_id
        # run settle_bets_for_event x2 via asyncio.gather
        # assert sum(settled_count) == 3, PENDING count == 0
```

**Deviation:** Requires real PG testcontainer (SQLite does not support `FOR UPDATE SKIP LOCKED` — explicitly noted in RESEARCH). Must use `session_factory` fixture from root `conftest.py`. `@pytest.mark.asyncio(loop_scope="session")` on test class (same as `test_repositories.py`).

---

### `tests/bet_maker/test_e2e_rabbitmq.py` (e2e test, testcontainers RabbitMQ)

**Analog:** `tests/bet_maker/conftest.py:47-68` (LifespanManager + os.environ injection + ASGITransport pattern)

Existing `app` fixture pattern `conftest.py:47-68`:
```python
@pytest_asyncio.fixture(scope="session")
async def app(pg_dsn: str) -> AsyncIterator[FastAPI]:
    os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
    try:
        application = build_app()
        async with LifespanManager(application):
            yield application
    finally:
        os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
```

RabbitMqContainer fixture pattern (RESEARCH §E2E test):
```python
@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[RabbitMqContainer]:
    with RabbitMqContainer("rabbitmq:4.2-management-alpine") as rmq:
        yield rmq

@pytest.fixture(scope="session")
def amqp_url(rabbitmq_container: RabbitMqContainer) -> str:
    host = rabbitmq_container.get_container_host_ip()
    port = rabbitmq_container.get_exposed_port(5672)
    return f"amqp://{rabbitmq_container.username}:{rabbitmq_container.password}@{host}:{port}/{rabbitmq_container.vhost}"
```

E2E test scenario (D-31): app fixtures set env vars (`BET_MAKER_RABBITMQ_URL`, `LINE_PROVIDER_RABBITMQ_URL`) + LifespanManager for both services, then HTTP sequence → poll GET /bets.

**Deviation:** `pika>=1.3,<2` must be in dev deps (RESEARCH §Environment Availability — required by `RabbitMqContainer.readiness_probe()`). `amqp_url` and `rabbitmq_container` fixtures go into root `tests/conftest.py` (session-scoped, shared with line_provider lifespan test).

---

### `tests/conftest.py` (modified — add RabbitMQ testcontainer fixtures)

**Analog:** Current `tests/conftest.py:24-41` (PostgresContainer session-scoped pattern)

Existing pattern `conftest.py:24-33`:
```python
@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg

@pytest.fixture(scope="session")
def pg_dsn(postgres_container: PostgresContainer) -> str:
    return str(postgres_container.get_connection_url())
```

New fixtures to add — same session-scoped pattern:
```python
from testcontainers.rabbitmq import RabbitMqContainer

@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[RabbitMqContainer]:
    with RabbitMqContainer("rabbitmq:4.2-management-alpine") as rmq:
        yield rmq

@pytest.fixture(scope="session")
def amqp_url(rabbitmq_container: RabbitMqContainer) -> str:
    host = rabbitmq_container.get_container_host_ip()
    port = rabbitmq_container.get_exposed_port(5672)
    user = rabbitmq_container.username
    password = rabbitmq_container.password
    vhost = rabbitmq_container.vhost
    return f"amqp://{user}:{password}@{host}:{port}/{vhost}"
```

**Deviation:** `RabbitMqContainer` requires `pika` for readiness probe. `pyproject.toml` change needed.

---

### `tests/bet_maker/test_health.py` (modified — add RMQ health assertions)

**Analog:** Current `tests/bet_maker/test_health.py:40-56` (patch + AsyncMock pattern)

Existing patch pattern `test_health.py:40-56`:
```python
async def test_health_returns_503_when_pg_down(self, app: FastAPI, client: AsyncClient) -> None:
    with patch(
        "bet_maker.entrypoints.api.health.ping_postgres",
        new=AsyncMock(return_value=False),
    ):
        response = await client.get("/health")
    assert response.status_code == 503
    assert body["checks"]["postgres"] == "down"
```

New tests to add (D-20):
- `test_health_returns_503_when_rmq_down` — patch `broker.ping` to return `False`
- `test_health_returns_503_when_no_subscribers` — patch `broker.subscribers` to return `[]`
- `test_health_returns_200_includes_rabbitmq_checks` — assert `body["checks"]["rabbitmq"] == "ok"`

**Deviation:** Must patch `router.broker.ping` from `bet_maker.entrypoints.messaging`. Test class already exists — add new methods.

---

### `tests/bet_maker/test_lifespan.py` (modified — add broker startup ordering)

**Analog:** Current `tests/bet_maker/test_lifespan.py:83-133` (TestShutdownOrder pattern with call_order list)

Existing call-order test `test_lifespan.py:83-133`:
```python
async def test_aclose_before_dispose(self, pg_dsn: str) -> None:
    call_order: list[str] = []
    ...
    assert call_order.index("aclose") < call_order.index("dispose")
```

New test: assert broker.close() is called before http_client.aclose() in shutdown. New test: assert `app.state` does not have broker-related state before lifespan (requires a separate fresh app fixture).

---

### `tests/line_provider/test_lifespan.py` (new)

**Analog:** `tests/bet_maker/test_lifespan.py` (mirror)

Copy `TestLifespanStatePins` + `TestShutdownOrder` patterns but for line-provider: assert `app.state.event_bus` is `RabbitEventBus` after startup (not `NoopEventBus`). line-provider has no PG, so no `pg_dsn` fixture needed — use `LifespanManager` with env var `LINE_PROVIDER_RABBITMQ_URL=amqp_url`.

---

### `tests/line_provider/test_event_bus.py` (new)

**Analog:** `tests/line_provider/test_set_event_state.py:165-184` (FakeEventBus, commit-before-publish pattern)

Test structure: unit tests for `RabbitEventBus.publish()` — verify `broker.publish()` is called with correct `routing_key`, `correlation_id`, `persist=True`. Use `TestRabbitBroker` from FastStream or a `MagicMock` on `RabbitBroker`.

---

## Cross-File Conventions

**1. structlog binding shape** — ALL handlers, interactors, and event bus methods use module-level `log = structlog.get_logger()` OR `log = structlog.get_logger()` inside the function body for request/message-scoped loggers. Keyword args are always explicit (no positional). `str(uuid)` for UUID values. Event keys follow `service.noun.verb` pattern (e.g., `settle.noop`, `settle.committed`, `line_provider.publish`).

**2. DI shape via `Annotated` + `Depends` + `app.state`** — ALL state-bound objects follow `def get_X(request: Request) -> T: return cast(T, request.app.state.X)` + `XDep = Annotated[T, Depends(get_X)]`. Never module-level singletons (except `router = RabbitRouter(...)` which is intentionally module-level per FastStream pattern). `RabbitBrokerDep` follows this convention.

**3. `from __future__ import annotations`** — ALL new files include this as first line. Codebase is 100% consistent on this.

**4. Pydantic schema `ConfigDict`** — Frozen DTOs use `ConfigDict(frozen=True, extra="forbid")`. ORM-to-schema DTOs use `ConfigDict(extra="forbid", from_attributes=True)`. Message schemas use `ConfigDict(frozen=True, extra="forbid")`. Never bare `model_config = {}`.

**5. Test file naming and scope** — Unit tests use plain `async def test_*() -> None` (no class, no fixtures needed for pure logic). Integration tests against real PG use `@pytest.mark.asyncio(loop_scope="session")` class. Handler tests use `TestRabbitBroker` context manager pattern (from RESEARCH). Test IDs follow `test_{noun}_{condition}_{expected_outcome}`.

**6. Schema duplication policy** — `EventFinishedMessage` exists in both `line_provider/schemas/messages.py` and `bet_maker/schemas/messages.py`. No cross-service imports. CI contract test enforces equality. New Phase 5 code in bet-maker must import from `bet_maker.schemas.messages`, never from `line_provider`.

**7. `async_sessionmaker` and UoW** — `AsyncUnitOfWork(sessionmaker)` constructed per-request/per-message. Never shared. In the consumer handler, `sessionmaker` is accessed via `request.app.state.sessionmaker` — but messaging.py has no `Request`. Options: (a) read `sessionmaker` from `app.state` via a module-level `app` reference (anti-pattern); (b) inject via a dependency using `app.state` after including the router; (c) pass `sessionmaker` to the handler via closure from lifespan. Recommended: pin `app.state.sessionmaker` in lifespan and access it inside the handler via the `router` reference: `app.state` is accessible as `router.broker._connection.app` (fragile) OR import the `app` object. Cleanest: handler calls a free function `settle_bets_for_event(uow=AsyncUnitOfWork(sessionmaker), ...)` where `sessionmaker` is obtained from a module-level reference that lifespan sets: `from bet_maker.entrypoints import _state; _state.sessionmaker`. Alternatively: use `Depends` on a background route — but subscriber handlers do not go through FastAPI DI. **Resolution: use FastStream's built-in `Depends` for subscribers** (FastStream supports `faststream.Depends` for subscriber handler injection, separate from FastAPI).

**8. Alembic migration naming** — `YYYYMMDD_NNNN_snake_description.py`. `revision` field is `NNNN_snake_description`. `down_revision` is the previous revision string. No `branch_labels`.

---

## Open Risks

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/bet_maker/entrypoints/messaging.py` | consumer entrypoint | event-driven | No existing FastStream consumer in codebase — pattern comes entirely from RESEARCH.md verified API + structlog middleware analog. `sessionmaker` injection in subscriber handler requires FastStream `Depends` or a module-level state reference; no prior art in repo. |
| `src/line_provider/entrypoints/messaging.py` | router holder | — | Needed for lifespan to `import router`. Currently no messaging.py in line-provider. Pattern: minimal file that only declares `router = RabbitRouter(str(settings.rabbitmq_url))` (no subscribers). This is a new pattern. |
| `tests/bet_maker/test_e2e_rabbitmq.py` | e2e test | event-driven + HTTP | Most complex test in Phase 5 — spans two LifespanManagers + real RabbitMQ container + real PG container. Polling loop pattern (asyncio.sleep + GET /bets) has no prior art in repo. No analog for multi-service e2e in current test suite. |
| `.planning/REQUIREMENTS.md` | documentation sync | — | Doc-only change; no code analog. |

---

## Metadata

**Analog search scope:** `src/line_provider/`, `src/bet_maker/`, `tests/`, `alembic/versions/`
**Files scanned:** 35 source files, 24 test files
**Pattern extraction date:** 2026-05-18

---

## PATTERN MAPPING COMPLETE
