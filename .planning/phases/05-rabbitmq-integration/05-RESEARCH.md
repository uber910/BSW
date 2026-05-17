# Phase 5: RabbitMQ integration — Research

**Researched:** 2026-05-18
**Domain:** FastStream 0.6.x / RabbitMQ / SQLAlchemy 2.0 async / testcontainers
**Confidence:** HIGH (all critical APIs verified against installed package 0.6.7 via uv run python)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Topic exchange `bsw.events` (durable, auto_delete=False)
- D-02: Main queue `bet_maker.events.finished` — classic durable
- D-03: Split ownership: line-provider declares exchange; bet-maker declares queue + DLX + DLQ + bindings
- D-04: DLX `bsw.events.dlx` (direct, durable) + DLQ `bet_maker.events.finished.dlq`; main queue args `x-dead-letter-exchange` + `x-dead-letter-routing-key`
- D-05: Routing key constants in `messaging/routing.py` per service; `Final[str]`
- D-06: Wildcard subscriber `event.finished.*` — one queue catches both terminal states
- D-07: `ack_policy=AckPolicy.MANUAL` mandatory on every `@router.subscriber`
- D-08: In-handler retry: tenacity 3 attempts, exp backoff multiplier=0.2 min=0.2 max=2; only around `settle_bets_for_event` DB call
- D-09: Exception classification — POISON → reject(requeue=False); TRANSIENT → tenacity retry
- D-10: Default: unknown Exception → reject(requeue=False); retry exhaustion → reject(requeue=False)
- D-11: ack() only after UoW commit; nack(requeue=True) not used; broker-cycling avoided
- D-12: Idempotency via `get_pending_locked(event_id)` with `with_for_update(skip_locked=True)` + `WHERE status=PENDING`
- D-13: Alembic migration adding `settled_at` (nullable TIMESTAMPTZ) and `settled_via` (nullable VARCHAR/TEXT)
- D-14: `settled_at` sourced from PG `func.now()` in UPDATE statement
- D-15: No `consumed_events` table; status-filter + idempotent UPDATE is the single source of truth
- D-16: 0 PENDING bets → `structlog.info("settle.noop")` + ack
- D-17: `settle_bets_for_event` interactor signature with `SettleResult` DTO
- D-18: Transaction isolation READ COMMITTED (PG default)
- D-19: Single process bet-maker: HTTP + subscriber via RabbitRouter + `app.include_router(router)`
- D-20: `/health` checks: broker.ping(timeout=1.0) + len(broker.subscribers) > 0 + PG ping; 503 on any failure
- D-21: Lifespan strict sequence: wait_for_postgres → httpx singleton → broker.connect() → declare topology → yield; shutdown reverse with try/finally
- D-22: No intermediate "starting" state; uvicorn waits for startup to complete
- D-23: `RabbitEventBus` in `src/line_provider/facades/event_bus.py`
- D-24: line-provider lifespan: broker.connect() → declare exchange → set app.state.event_bus → yield
- D-25: `src/bet_maker/entrypoints/messaging.py` with `RabbitRouter` + `@router.subscriber`
- D-26: `prefetch_count=10` — researcher to confirm exact API
- D-27: structlog binding in handler: clear_contextvars() → bind_contextvars → try: ... finally: clear_contextvars()
- D-28: `EventFinishedMessage` duplicated byte-for-byte in `bet_maker/schemas/messages.py`
- D-29: Contract test `tests/contract/test_event_finished_message_schema.py` via `model_json_schema()`
- D-30: Unit tests via `TestRabbitBroker(router.broker)`
- D-31: One e2e test via `testcontainers.rabbitmq.RabbitMqContainer`

### Claude's Discretion
- Exact `prefetch_count` API: broker-level via `Channel(prefetch_count=N)` vs subscriber QoS
- DLQ wiring: `RabbitQueue.arguments` dict vs FastStream `dlq` shortcut
- Placement of `messaging/routing.py` (new sub-package vs inside `entrypoints/`)
- Tenacity wrapping shape: reuse `make_retry_decorator` factory from Phase 4 or inline `AsyncRetrying`

### Deferred Ideas (OUT OF SCOPE)
- Reconciliation job — Phase 6
- DLQ replay/inspection endpoints
- Publisher confirms
- Quorum queues/cluster
- Schema migration v2
- Outbox pattern
- Prometheus metrics
- k8s readiness/liveness split
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LP-06 | line-provider publishes `EventFinishedMessage` to RabbitMQ on NEW→FINISHED transition | RabbitEventBus wraps `router.broker.publish()`; call site already exists in `set_event_state.py` |
| BM-09 | FastStream RabbitRouter consumer on `bet_maker.events.finished` with AckPolicy.MANUAL, prefetch=10 (REQUIREMENTS says 20 — drift noted), durable | Verified: `RabbitRouter(default_channel=Channel(prefetch_count=10))` + subscriber with `ack_policy=AckPolicy.MANUAL` |
| BM-10 | `settle_bets_for_event` idempotent via `SELECT FOR UPDATE SKIP LOCKED` | Verified via SQLAlchemy 2.0 `with_for_update(skip_locked=True)` |
| BM-11 | DLX + DLQ with bounded retries via `x-death` header (REQUIREMENTS text) — Phase 5 uses tenacity in-handler (D-08/D-09), not `x-death` header counting; `x-death` is a deferred hardening approach | `RabbitQueue(arguments={"x-dead-letter-exchange": ..., "x-dead-letter-routing-key": ...})` — verified API |
| QA-06 | Consumer tests via `TestRabbitBroker`; one e2e via testcontainers RabbitMQ | `from faststream.rabbit.testing import TestRabbitBroker`; `RabbitMqContainer` API verified |
</phase_requirements>

---

## Executive Summary

- **prefetch_count is set at broker level via `Channel(prefetch_count=10)`** passed as `default_channel=` to `RabbitRouter(...)`. There is no subscriber-level QoS kwarg. The `Channel` dataclass lives in `faststream.rabbit.schemas`. [VERIFIED: uv run python]
- **routing_key for topic binding goes on `RabbitQueue`, NOT on `@router.subscriber()`**. `RabbitRouter.subscriber()` has no `routing_key` parameter. Use `RabbitQueue(name=..., routing_key="event.finished.*", durable=True, arguments={...})`. [VERIFIED: uv run python — `routing_key` on subscriber raises `TypeError`]
- **DLQ wiring must use `RabbitQueue.arguments` dict** — FastStream 0.6.x has no `dlq` shortcut on the subscriber decorator for RabbitMQ. `x-dead-letter-exchange` and `x-dead-letter-routing-key` are set directly in `arguments={}`. [VERIFIED: uv run python]
- **`broker.subscribers` is a `list` attribute** (not `_subscribers` weakset) — use `len(router.broker.subscribers) > 0` for health check. Both `broker.subscribers` (list) and `broker._subscribers` (WeakSet) exist; only the list is public API. [VERIFIED: uv run python]
- **Auto-lifespan via `app.include_router(router)` is confirmed** for `fastapi>=0.112.2`. With our pin `>=0.115`, no manual `lifespan=router.lifespan_context` needed. However, the custom `lifespan` function in `entrypoints/lifespan.py` must explicitly call `await router.broker.connect()` before declares — auto-lifespan only handles broker start/stop when there is NO custom lifespan. When a custom lifespan exists in FastAPI, `router.lifespan_context` must be composed inside it. [VERIFIED: FastStream docs, confirmed pattern below]

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Event state change publish | line-provider API tier | — | Call site in `set_event_state.py` interactor; broker is DI-injected via `EventBus` Protocol |
| AMQP consumer loop | bet-maker AMQP tier (messaging.py) | — | Separate from HTTP entrypoints; same process |
| Bet settlement (settle_bets_for_event) | bet-maker interactor tier | DB tier (FOR UPDATE SKIP LOCKED) | Pure business logic; DB owns the idempotency lock |
| DLQ routing | AMQP broker tier (RabbitMQ) | bet-maker consumer (reject call) | Broker routes on reject; consumer initiates via `msg.reject(requeue=False)` |
| Topology declaration | lifespan tier per service | — | line-provider owns exchange; bet-maker owns queues+DLX+DLQ+bindings |
| Health checks | bet-maker API tier (/health) | — | Extends existing health.py handler |
| Schema contract | Both services (duplicated schemas) | CI (contract test) | No cross-service imports; enforced by pytest |

---

## FastStream 0.6.x API Reference

### 1. RabbitRouter construction with prefetch_count (D-26 RESOLVED)

**Verdict: broker-level via `Channel(prefetch_count=N)` in `default_channel=` kwarg.**

```python
from faststream.rabbit.fastapi import RabbitRouter
from faststream.rabbit.schemas import Channel

router = RabbitRouter(
    str(settings.rabbitmq_url),
    default_channel=Channel(prefetch_count=10),
)
```

`Channel` is a dataclass: `Channel(prefetch_count=10, global_qos=False, channel_number=None, publisher_confirms=True, on_return_raises=False)`. Import: `from faststream.rabbit.schemas import Channel`. [VERIFIED: `faststream/rabbit/schemas/channel.py` in 0.6.7]

There is no `prefetch_count` kwarg on `RabbitBroker.__init__` or on subscriber. The `Channel` path is the only stable API. `global_qos=False` (default) means per-consumer QoS, which is correct for our pattern.

### 2. Subscriber decoration with DLQ wiring (D-09/D-25 RESOLVED)

**Verdict: `RabbitQueue.arguments` dict is the only stable API for DLX headers. No `dlq` shortcut exists in FastStream 0.6.x.**

**Critical discovery: `routing_key` is a parameter of `RabbitQueue`, NOT of `@router.subscriber()`.**

```python
from faststream.rabbit.fastapi import RabbitRouter
from faststream.rabbit.schemas import RabbitQueue, RabbitExchange, ExchangeType, Channel
from faststream.rabbit.annotations import RabbitMessage
from faststream import AckPolicy

router = RabbitRouter(
    str(settings.rabbitmq_url),
    default_channel=Channel(prefetch_count=10),
)

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

Import paths (all verified against 0.6.7):
- `from faststream.rabbit.fastapi import RabbitRouter`
- `from faststream.rabbit.schemas import RabbitQueue, RabbitExchange, ExchangeType, Channel`
- `from faststream.rabbit.annotations import RabbitMessage`
- `from faststream import AckPolicy`
- `from faststream.rabbit.testing import TestRabbitBroker`

`AckPolicy.MANUAL` enum value: `"manual"`. [VERIFIED: uv run python `AckPolicy.__members__`]

`RabbitRouter.subscriber()` accepted kwargs (verified): `queue`, `exchange`, `channel`, `consume_args`, `dependencies`, `parser`, `decoder`, `middlewares`, `no_ack`, `ack_policy`, `no_reply`, `title`, `description`, `include_in_schema`, `response_model_*`. **No `routing_key` kwarg — it belongs to `RabbitQueue`.**

### 3. Manual ack / nack / reject inside handler

```python
from faststream.rabbit.message import RabbitMessage

async def on_event_finished(payload: EventFinishedMessage, msg: RabbitMessage) -> None:
    await msg.ack()
    await msg.nack(multiple=False, requeue=True)   # not used per D-11
    await msg.reject(requeue=False)                 # → DLQ
```

`RabbitMessage` exposes `correlation_id: str` and `message_id: str` as attributes inherited from `StreamMessage`. [VERIFIED: `faststream/message/message.py` — `self.correlation_id` and `self.message_id` are set in `__init__`]

`msg.correlation_id` reads the AMQP correlation_id property from the incoming message. This is the canonical source for structlog binding (D-27). Do NOT read from payload — AMQP header is set by FastStream automatically when publishing a Pydantic model.

### 4. router.broker.publish() for Pydantic payloads

```python
await router.broker.publish(
    message,                        # EventFinishedMessage Pydantic model → auto-serialized to JSON
    routing_key="event.finished.win",
    exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
    persist=True,                   # survive broker restart
    correlation_id=correlation_id,  # propagate from HTTP request context
)
```

Signature (verified): `publish(self, message, queue, exchange, routing_key, mandatory, immediate, timeout, persist, reply_to, correlation_id, headers, content_type, content_encoding, expiration, message_id, timestamp, message_type, user_id, priority)`. Pydantic v2 models are serialized to JSON automatically by FastStream. Content-type is set to `application/json`. [VERIFIED: uv run python inspect + Context7]

### 5. Topology declaration — broker.declare_exchange / declare_queue

```python
# Returns aio-pika RobustExchange/RobustQueue — idempotent
exchange = await router.broker.declare_exchange(
    RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
)
queue = await router.broker.declare_queue(
    RabbitQueue("bet_maker.events.finished", durable=True, routing_key="event.finished.*", arguments={...})
)
```

`broker.declare_exchange(RabbitExchange)` and `broker.declare_queue(RabbitQueue)` both exist in 0.6.7 and return aio-pika robust objects. [VERIFIED: uv run python — both methods listed in `dir(RabbitBroker)`]

FastStream subscribers automatically declare their queues and exchanges when the broker starts — explicit `declare_*` calls in lifespan are needed ONLY for objects that are NOT declared by a subscriber (e.g., the DLX exchange and DLQ queue in bet-maker, and the main exchange in line-provider which has no subscriber).

### 6. broker.ping() and broker.subscribers for /health (D-20)

```python
# Returns bool
rmq_ok = await router.broker.ping(timeout=1.0)

# Returns list (public API, NOT _subscribers WeakSet)
sub_count = len(router.broker.subscribers)
```

`broker.ping(timeout: float | None) -> bool` — signature verified. `broker.subscribers` is a `list` of subscriber objects. `broker._subscribers` is a private `WeakSet`. Use `broker.subscribers` (the public list). [VERIFIED: uv run python — both attributes exist; `broker.subscribers` is the public list]

### 7. TestRabbitBroker (D-30)

```python
from faststream.rabbit.testing import TestRabbitBroker
from bet_maker.entrypoints.messaging import router

async def test_happy_path():
    async with TestRabbitBroker(router.broker) as br:
        await br.publish(
            EventFinishedMessage(event_id=..., new_state=..., ...),
            queue="bet_maker.events.finished",
            exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
        )
        on_event_finished.mock.assert_called_once()
```

`TestRabbitBroker(broker, with_real=False)` — async context manager. In-memory: no real broker needed. Subscribers are invoked synchronously inside `asyncio`. [VERIFIED: uv run python — `__aenter__`/`__aexit__` present]

### 8. Auto-lifespan composition with custom lifespan

When `app.include_router(router)` is used with FastAPI `>=0.112.2` AND there is a **custom lifespan** on the FastAPI app, FastStream does NOT auto-start the broker. The custom lifespan must explicitly start/stop it.

**Correct pattern for our case** (custom lifespan already exists in `entrypoints/lifespan.py`):

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 1. wait_for_postgres (existing)
    # 2. httpx singleton (existing)
    # 3. start FastStream broker explicitly
    await router.broker.connect()
    try:
        # 4. declare extra topology (DLX, DLQ, bindings)
        yield
    finally:
        await router.broker.close()  # or stop()
        # ...existing reverse shutdown...

app = FastAPI(lifespan=lifespan)
app.include_router(router)
```

`app.include_router(router)` registers HTTP routes AND subscriber decorators from the RabbitRouter. Broker lifecycle is owned by the custom lifespan. `router.broker.connect()` establishes the AMQP connection; `router.broker.close()` disconnects. [CITED: faststream docs lifespan section; pattern confirmed by FastStream ASGI integration examples]

**For line-provider** (simpler, no custom lifespan for broker):
```python
# Since line_provider lifespan is custom, same pattern applies:
await router.broker.connect()
# declare exchange
app.state.event_bus = RabbitEventBus(router.broker)
yield
# finally: await router.broker.close()
```

---

## Topology & DLQ Semantics

### Exchange/Queue Architecture

```
line-provider declares:
  bsw.events (topic, durable)

bet-maker declares (in lifespan, after broker.connect()):
  bsw.events.dlx         (direct, durable)       — DLX
  bet_maker.events.finished.dlq (durable)         — DLQ
  bet_maker.events.finished (durable, args={x-dead-letter-exchange, x-dead-letter-routing-key})
    + binding: bsw.events --event.finished.*--> bet_maker.events.finished
    + binding: bsw.events.dlx --bet_maker.events.finished--> bet_maker.events.finished.dlq
```

Note: `@router.subscriber` auto-declares `bet_maker.events.finished` queue and its binding to `bsw.events`. The DLX exchange and DLQ queue are NOT declared by any subscriber — they must be declared explicitly in lifespan via `broker.declare_exchange` and `broker.declare_queue` AFTER `broker.connect()`.

### DLX trigger conditions

Messages route to DLX (`bsw.events.dlx`) only when:
- `await msg.reject(requeue=False)` — consumer explicit reject
- `await msg.nack(requeue=False)` — consumer explicit nack without requeue
- Message TTL expires (if `x-message-ttl` set on queue)
- Queue length overflow (if `x-max-length` set)

Messages do NOT route to DLX when:
- AMQP channel exception (message becomes unacknowledged, will be redelivered)
- Broker restart (durable queue replays unacked messages)
- Consumer process crash (unacked messages return to queue)

This means our POISON path (explicit `reject(requeue=False)`) correctly triggers DLX routing. TRANSIENT errors that exhaust tenacity also hit `reject(requeue=False)` per D-10 — correct, reconciler picks them up in Phase 6.

### Topic exchange + wildcard binding

FastStream 0.6.x supports topic exchange + wildcard routing key via `RabbitQueue(routing_key="event.finished.*")`. The binding is created automatically when the subscriber starts. The `*` wildcard matches exactly one word-segment (e.g., `event.finished.win`, `event.finished.lose`). [VERIFIED: Context7 topic exchange example; FastStream path variable docs]

### Publisher confirms (deferred decision)

`Channel(publisher_confirms=True)` is the default in FastStream 0.6.x. This means basic publisher confirm mode is ALREADY active by default — broker will ACK/NACK publish calls. The `on_return_raises=False` default means a mandatory-flag return does NOT raise an exception. For Phase 5 we keep defaults. No opt-in needed. [VERIFIED: `Channel` dataclass defaults]

Recommendation: **do not add explicit `mandatory=True` to publish calls**. The bet-maker queue will exist before line-provider publishes (both declared at startup). If they race at startup, the message would be lost without mandatory — but `depends_on: service_healthy` in docker-compose prevents this race. Adding `mandatory=True` adds complexity without value for a single-node test task.

---

## Manual-Ack Ladder & Error Classification

```python
import asyncio
from uuid import UUID

import structlog
from faststream import AckPolicy
from faststream.rabbit.annotations import RabbitMessage
from faststream.rabbit.fastapi import RabbitRouter
from faststream.rabbit.schemas import Channel, ExchangeType, RabbitExchange, RabbitQueue
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from structlog.contextvars import bind_contextvars, clear_contextvars
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.schemas.messages import EventFinishedMessage

router = RabbitRouter(
    str(settings.rabbitmq_url),
    default_channel=Channel(prefetch_count=10),
)


class UnsupportedSchemaVersion(ValueError):
    pass


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, Exception) and getattr(exc, "connection_invalidated", False):
        return True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    return False


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
) -> None:
    log = structlog.get_logger()
    clear_contextvars()
    try:
        bind_contextvars(
            message_id=msg.message_id,
            correlation_id=msg.correlation_id,
            event_id=str(payload.event_id),
        )

        if payload.schema_version != 1:
            raise UnsupportedSchemaVersion(f"schema_version={payload.schema_version}")

        settle = retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
            retry=retry_if_exception(_is_transient),
            reraise=True,
        )(settle_bets_for_event)

        async with AsyncUnitOfWork(sessionmaker) as uow:
            result = await settle(uow, event_id=payload.event_id, ...)

        if result.settled_count == 0:
            log.info("settle.noop", event_id=str(payload.event_id), reason="no PENDING bets")
        else:
            log.info("settle.committed", settled_count=result.settled_count, ...)

        await msg.ack()

    except (ValidationError, UnsupportedSchemaVersion, IntegrityError) as exc:
        log.warning("settle.poison_to_dlq", exc_type=type(exc).__name__, exc=str(exc))
        await msg.reject(requeue=False)

    except Exception as exc:
        log.error("settle.transient_exhausted", exc_type=type(exc).__name__, exc=str(exc))
        await msg.reject(requeue=False)

    finally:
        clear_contextvars()
```

**Exception classification table:**

| Exception | Class | Action |
|-----------|-------|--------|
| `pydantic.ValidationError` | POISON | `reject(requeue=False)` → DLQ |
| `faststream.exceptions.DecodeError` | POISON | `reject(requeue=False)` → DLQ |
| `UnsupportedSchemaVersion` (custom ValueError) | POISON | `reject(requeue=False)` → DLQ |
| `sqlalchemy.exc.IntegrityError` | POISON | `reject(requeue=False)` → DLQ |
| `sqlalchemy.exc.OperationalError` | TRANSIENT | tenacity retry 3x → on exhaust: `reject(requeue=False)` |
| `sqlalchemy.exc.DBAPIError` (connection_invalidated=True) | TRANSIENT | tenacity retry 3x → on exhaust: `reject(requeue=False)` |
| `asyncio.TimeoutError` | TRANSIENT | tenacity retry 3x → on exhaust: `reject(requeue=False)` |
| Any other `Exception` | DEFAULT | `reject(requeue=False)` → DLQ |

Note: `ValidationError` from Pydantic is raised by FastStream's parser BEFORE the handler body executes when `payload: EventFinishedMessage` type annotation is used. FastStream wraps it as `DecodeError` in some versions. To catch both, add `from faststream.exceptions import DecodeError` to the except clause. [ASSUMED — verify exact exception type in handler context with TestRabbitBroker]

---

## Lifespan Composition

### bet-maker lifespan (D-21 expanded)

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = BetMakerSettings()
    configure_structlog(settings.log_level)
    log = structlog.get_logger()

    # Step 1: DB (existing)
    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    try:
        await wait_for_postgres(engine)
    except Exception as exc:
        log.critical("bet_maker.startup.failed", reason=str(exc))
        await engine.dispose()
        raise

    # Step 2: httpx singleton (existing)
    http_client = httpx.AsyncClient(
        base_url=str(settings.line_provider_base_url),
        timeout=httpx.Timeout(5.0),
    )

    # Step 3: RabbitMQ broker connect
    await router.broker.connect()

    # Step 4: declare DLX + DLQ + bindings (NOT declared by subscriber)
    await router.broker.declare_exchange(
        RabbitExchange("bsw.events.dlx", type=ExchangeType.DIRECT, durable=True)
    )
    dlq = await router.broker.declare_queue(
        RabbitQueue("bet_maker.events.finished.dlq", durable=True)
    )
    # bind DLQ to DLX
    await dlq.bind(exchange="bsw.events.dlx", routing_key="bet_maker.events.finished")

    # Step 5: pin state
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.line_provider_http_client = http_client
    app.state.event_lookup = HttpEventLookup(...)

    try:
        yield
    finally:
        log.info("bet_maker.shutdown")
        try:
            await router.broker.close()
        finally:
            try:
                await http_client.aclose()
            finally:
                await engine.dispose()
```

**Key: dlq.bind()** uses the aio-pika RobustQueue object returned by `declare_queue`. This is the idiomatic way to bind to DLX without duplicating topology config. [CITED: FastStream declare docs — "methods return low-level aio-pika objects"]

### line-provider lifespan (D-24 expanded)

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = LineProviderSettings()
    configure_structlog(settings.log_level)

    await router.broker.connect()
    # Declare topic exchange (bet-maker subscriber auto-binds to it)
    await router.broker.declare_exchange(
        RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
    )

    app.state.settings = settings
    app.state.event_store = InMemoryEventStore()
    app.state.event_bus = RabbitEventBus(router.broker)

    try:
        yield
    finally:
        log.info("line_provider.shutdown")
        await router.broker.close()
```

### Auto-lifespan clarification

When a FastAPI app has a custom `lifespan=` parameter, `app.include_router(router)` from FastStream does NOT invoke broker start/stop automatically. The pattern above is required. If there were NO custom lifespan, `app.include_router(router)` would trigger auto-lifespan for `fastapi>=0.112.2`. Since we have custom lifespans in both services, explicit `await router.broker.connect()` + `close()` is mandatory. [CITED: FastStream ASGI integration docs + release notes]

---

## Open Questions Resolved

| Decision | Chosen Answer | Rationale | Source |
|----------|--------------|-----------|--------|
| D-26: prefetch_count API | `RabbitRouter(default_channel=Channel(prefetch_count=10))` — broker-level via `Channel` dataclass | Only stable API in 0.6.7; no `prefetch_count` on broker `__init__` or subscriber kwarg | VERIFIED: uv run python `inspect.signature(RabbitBroker.__init__)` + `Channel` class |
| D-09/D-25: DLQ wiring | `RabbitQueue(arguments={"x-dead-letter-exchange": ..., "x-dead-letter-routing-key": ...})` — no FastStream `dlq` shortcut | `dlq` shortcut does not exist in 0.6.7 FastStream RabbitMQ API surface | VERIFIED: uv run python — no `dlq` kwarg on subscriber |
| routing.py placement | New `messaging/` sub-package: `src/line_provider/messaging/routing.py` and `src/bet_maker/messaging/routing.py` | Consistent with D-05 naming; `entrypoints/messaging.py` is already the consumer module name; routing constants are a separate concern from the entrypoint handler | [ASSUMED based on D-05 and existing `entrypoints/messaging.py` name in D-25] |
| D-08: tenacity wrapping shape | Inline `retry(...)` decorator applied to a local reference of `settle_bets_for_event` inside the handler; NOT reusing `make_retry_decorator` from Phase 4 | Phase 4 factory is HTTP-specific (`httpx.TransportError`, `httpx.HTTPStatusError`); Phase 5 retry predicate is DB-specific (`OperationalError`, `asyncio.TimeoutError`). Creating a second factory or adapting Phase 4's `_is_retryable` would add cross-concern coupling. An inline `retry(...)` applied as a decorator at call time is the cleanest shape for a different predicate set. Phase 4 factory can be kept as-is for HTTP. | [ASSUMED — recommended based on separation of concerns; both Phase 4 factory and inline retry use same tenacity API] |

---

## Idempotency & SKIP LOCKED Pattern

### BetRepository.get_pending_locked()

```python
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus

async def get_pending_locked(self, event_id: UUID) -> list[Bet]:
    result = await self._session.execute(
        select(Bet)
        .where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())
```

SQLAlchemy 2.0: `select(Bet).where(...).with_for_update(skip_locked=True)` generates `SELECT ... FOR UPDATE SKIP LOCKED`. The row-lock is released at UoW commit (when `async with uow:` exits cleanly). [VERIFIED: SQLAlchemy 2.0 docs via Context7 — `with_for_update(skip_locked=True)` confirmed]

**Idempotency guarantee:** If a message is redelivered (consumer crash before ack), the second `get_pending_locked()` call returns 0 rows because status is already `WON`/`LOST` from the first settlement. No row-lock contention, no UPDATE issued.

**Concurrency guarantee:** If consumer and reconciler run concurrently against same `event_id`, `SKIP LOCKED` ensures exactly one of them acquires the rows. The other gets 0 rows and takes the `settle.noop` path.

### settle_bets_for_event interactor shape

```python
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, update

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.messages import EventTerminalState


class SettleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    terminal_state: EventTerminalState
    settled_count: int
    settled_bet_ids: list[UUID]
    settled_via: Literal["consumer", "reconciler"]
    settled_at: datetime


async def settle_bets_for_event(
    uow: AsyncUnitOfWork,
    *,
    event_id: UUID,
    terminal_state: EventTerminalState,
    settled_via: Literal["consumer", "reconciler"],
) -> SettleResult:
    async with uow:
        bets = await uow.bets.get_pending_locked(event_id)
        if not bets:
            return SettleResult(
                event_id=event_id,
                terminal_state=terminal_state,
                settled_count=0,
                settled_bet_ids=[],
                settled_via=settled_via,
                settled_at=...,  # use utc_now() from config
            )

        new_status = BetStatus.WON if terminal_state == EventTerminalState.FINISHED_WIN else BetStatus.LOST
        bet_ids = [b.id for b in bets]

        await uow.session.execute(
            update(Bet)
            .where(Bet.id.in_(bet_ids))
            .values(status=new_status, settled_at=func.now(), settled_via=settled_via)
        )
        # UoW auto-commits on exit
```

Note: The `settled_at` column value comes from PG `func.now()` in the UPDATE statement (D-14). This matches `created_at`/`updated_at` convention from Phase 3 (server-side clock).

### Concurrent consumer + reconciler test recipe

To provoke and verify the race in pytest:
1. Insert 3 PENDING bets with same `event_id` against real PG testcontainer.
2. Launch two `asyncio.Task` concurrently: both call `settle_bets_for_event` for the same `event_id`.
3. `await asyncio.gather(task_consumer, task_reconciler)` — gather results.
4. Assert: sum of `settled_count` across both results = 3 (one task got all 3, other got 0).
5. `SELECT COUNT(*) FROM bets WHERE event_id=:id AND status='PENDING'` = 0.
6. `SELECT COUNT(*) FROM bets WHERE event_id=:id AND (status='WON' OR status='LOST')` = 3.

This test requires real PostgreSQL (testcontainer) — SQLite does not support `FOR UPDATE SKIP LOCKED`.

---

## Alembic Migration (D-13)

**File location:** `alembic/versions/20260518_0002_bets_settled_columns.py` (next revision after `0001_bets_initial`).

**Naming convention:** `YYYYMMDD_NNNN_snake_description.py` — matches existing `20260515_0001_bets_initial.py`.

```python
revision = "0002_bets_settled_columns"
down_revision = "0001_bets_initial"

def upgrade() -> None:
    op.add_column(
        "bets",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bets",
        sa.Column("settled_via", sa.Text(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("bets", "settled_via")
    op.drop_column("bets", "settled_at")
```

**Column types:** `DateTime(timezone=True)` matches existing `created_at`/`updated_at` pattern (not `TIMESTAMPTZ` literal — SQLAlchemy maps it automatically for PG). `Text()` for `settled_via` — avoids ENUM for a 2-value field that Phase 6 reconciler also writes; avoids migration for ENUM extension if reconciler adds values. [ASSUMED — TEXT vs VARCHAR convention; TEXT is consistent with PG idiomatic style for short strings without schema-enforced enums]

**ORM update:** Bet model gains:
```python
settled_at: Mapped[datetime | None] = mapped_column(
    sa.DateTime(timezone=True), nullable=True
)
settled_via: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
```

---

## Testing Strategy

### Unit tests (D-30): TestRabbitBroker

**Import path (verified):** `from faststream.rabbit.testing import TestRabbitBroker`

```python
import pytest
from faststream.rabbit.testing import TestRabbitBroker
from bet_maker.entrypoints.messaging import router, on_event_finished
from bet_maker.schemas.messages import EventFinishedMessage
from faststream.rabbit.schemas import RabbitExchange, ExchangeType

@pytest.mark.asyncio
async def test_happy_path(sessionmaker):
    async with TestRabbitBroker(router.broker) as br:
        await br.publish(
            EventFinishedMessage(event_id=..., new_state="FINISHED_WIN", ...),
            queue="bet_maker.events.finished",
            exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
        )
        on_event_finished.mock.assert_called_once()

@pytest.mark.asyncio
async def test_poison_schema_version():
    async with TestRabbitBroker(router.broker) as br:
        msg = {"schema_version": 99, "event_id": str(uuid4()), ...}
        await br.publish(msg, queue="bet_maker.events.finished", ...)
        # assert msg.reject was called — check via mock on msg.reject
```

Branches to cover per D-30:
1. Happy path → ack after UoW commit
2. ValidationError (malformed payload) → reject(requeue=False)
3. UnsupportedSchemaVersion (schema_version != 1) → reject(requeue=False)
4. IntegrityError → reject(requeue=False)
5. OperationalError → tenacity retry → success on retry → ack
6. OperationalError → tenacity exhaustion → reject(requeue=False)
7. 0 PENDING bets → settle.noop log + ack

### Integration test: concurrent settle (F3/R3)

```python
@pytest.mark.asyncio
async def test_concurrent_settle(session_factory):
    # Insert 3 PENDING bets same event_id
    # Run settle_bets_for_event twice concurrently via asyncio.gather
    # Assert exactly 3 bets settled, 0 PENDING, no double-update
```

Uses real PG testcontainer (already in `tests/conftest.py`).

### E2E test (D-31): testcontainers RabbitMQ

**RabbitMqContainer API (verified from source):**

```python
import pytest
from testcontainers.rabbitmq import RabbitMqContainer

@pytest.fixture(scope="session")
def rabbitmq_container():
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

**Wait-for-ready:** `RabbitMqContainer` uses `pika.BlockingConnection` in its `readiness_probe()` — it retries until AMQP port accepts connections. This is the built-in wait strategy. No manual `sleep` needed. [VERIFIED: testcontainers source read]

**Critical:** `RabbitMqContainer` requires `pika` at runtime for its readiness probe. `pika` is NOT in our dependencies (we avoid it per CLAUDE.md). Must add `pika` as a **dev-only dependency** (`pika>=1.3,<2`) or use an alternative wait strategy.

**Alternative wait strategy** (to avoid pika):
```python
import time
import socket

@pytest.fixture(scope="session")
def rabbitmq_container():
    with RabbitMqContainer("rabbitmq:4.2-management-alpine") as rmq:
        # Wait for port to be open (alternative to pika-based readiness probe)
        yield rmq
```

OR: Override the readiness probe by subclassing, or use `testcontainers.core.waiting_utils.wait_container_is_ready` with a TCP check. The simplest path: **add `pika>=1.3,<2` to `[dependency-groups.dev]`** — it's only used for test container readiness, never in production code.

**E2E test scenario:**
```python
@pytest.mark.asyncio
async def test_e2e_consumer_settles_bet(
    lp_app,     # line-provider FastAPI app with RabbitEventBus wired to real RMQ
    bm_app,     # bet-maker FastAPI app with consumer wired to real RMQ
    lp_client,  # httpx AsyncClient for line-provider
    bm_client,  # httpx AsyncClient for bet-maker
):
    # 1. Create event in LP
    event_id = str(uuid4())
    await lp_client.post("/event", json={"event_id": event_id, ...})
    # 2. Place bet in BM
    r = await bm_client.post("/bet", json={"event_id": event_id, "amount": "10.00"})
    bet_id = r.json()["id"]
    # 3. Finish event in LP (triggers publish)
    await lp_client.put(f"/event/{event_id}", json={..., "state": "FINISHED_WIN"})
    # 4. Poll GET /bets until status != PENDING (with timeout)
    for _ in range(20):
        await asyncio.sleep(0.1)
        bets = (await bm_client.get("/bets")).json()
        if any(b["id"] == bet_id and b["status"] == "WON" for b in bets):
            break
    else:
        pytest.fail("Bet not settled within timeout")
```

### Contract test (D-29)

```python
# tests/contract/test_event_finished_message_schema.py
import json
from line_provider.schemas.messages import EventFinishedMessage as LPMessage
from bet_maker.schemas.messages import EventFinishedMessage as BMMessage

def test_schemas_are_identical():
    lp_schema = json.dumps(LPMessage.model_json_schema(), sort_keys=True)
    bm_schema = json.dumps(BMMessage.model_json_schema(), sort_keys=True)
    assert lp_schema == bm_schema, (
        "EventFinishedMessage schema drift detected between services"
    )
```

**Gotcha:** `model_json_schema()` output is deterministic within a single Python session but field order in `properties` may vary across Pydantic versions. Using `json.dumps(..., sort_keys=True)` normalizes this. `$defs` key ordering is also normalized by `sort_keys=True`. [VERIFIED: ran `model_json_schema()` on existing LP schema — output is stable with sort_keys]

---

## Pitfall × Defense Matrix

| Pitfall | Guard |
|---------|-------|
| **R1 / F1** — Missing MANUAL ack policy | `ack_policy=AckPolicy.MANUAL` hardcoded in `@router.subscriber`; CI unit test with `TestRabbitBroker` verifies handler calls `ack()`/`reject()` |
| **R2 / F4** — ack before UoW commit | `await msg.ack()` is the LAST statement after `async with uow:` exits; tenacity wraps only the settle call, not the ack |
| **R3** — Consumer/reconciler race double-update | `with_for_update(skip_locked=True)` + `WHERE status=PENDING` — second caller gets 0 rows; integration test with `asyncio.gather` proves this |
| **R5** — Editing existing exchange/queue arguments | Exchange/queue names and `arguments` dict are `Final[str]`/immutable constants in `messaging/routing.py`; CONTEXT.md D-01 prohibits editing args of declared objects |
| **R7** — Unbounded requeue loop | `nack(requeue=True)` never used per D-11; transient retry is in-handler via tenacity; after 3 attempts → `reject(requeue=False)` |
| **R9 / R12 / Anti-Pattern 2** — Publish before store commit | Existing Phase 2 D-12 invariant: `store.update()` completes before `event_bus.publish()`; broker connection established in lifespan, not in transaction |
| **F2** — Unlimited prefetch | `Channel(prefetch_count=10)` on `RabbitRouter` constructor |
| **F3** — Wrong startup order | Lifespan sequence: PG wait → httpx → `broker.connect()` → declare → yield; no `asyncio.gather` in startup |
| **F5 / Anti-Pattern 5** — Multiple broker instances | One `RabbitRouter` per service; `EventBus` facade wraps `router.broker.publish()`; no second `RabbitBroker` instantiation |
| **F6** — TestRabbitBroker only, no real broker test | D-31 e2e test uses `RabbitMqContainer` against real `rabbitmq:4.2-management-alpine` |
| **F7** — No schema_version check | `if payload.schema_version != 1: raise UnsupportedSchemaVersion(...)` in handler preamble; `extra="forbid"` on both copies of `EventFinishedMessage` |
| **F8** — Binding not asserted | Integration test publishes to `bsw.events` with routing key `event.finished.win` and asserts bet-maker consumer receives it — proves binding exists at runtime |
| **A7** — structlog contextvars cross-task contamination | `clear_contextvars()` at handler entry + `finally: clear_contextvars()` mirrors Phase 1 `RequestContextMiddleware` A7 double-clear pattern |
| **Anti-Pattern 2** — Publish inside lock/transaction | `RabbitEventBus.publish()` is called AFTER `store.update()` exits the asyncio.Lock context; no broker call inside any DB transaction |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.1.0 |
| Config | `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"` |
| Quick run | `uv run pytest tests/bet_maker/test_messaging.py -x -q` |
| Full suite | `uv run pytest -q --cov=src --cov-report=term-missing` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LP-06 | line-provider publishes EventFinishedMessage on state change | unit + e2e | `pytest tests/line_provider/test_interactors.py -x` | ❌ Wave 0 (new test in existing file) |
| BM-09 | Consumer with AckPolicy.MANUAL, prefetch=10, durable | unit (TestRabbitBroker) | `pytest tests/bet_maker/test_messaging.py -x` | ❌ Wave 0 |
| BM-10 | settle_bets_for_event idempotent via FOR UPDATE SKIP LOCKED | integration (real PG) | `pytest tests/bet_maker/test_settle.py -x` | ❌ Wave 0 |
| BM-11 | Poison messages → DLQ via reject(requeue=False) | unit (TestRabbitBroker per branch) | `pytest tests/bet_maker/test_messaging.py::TestPoison -x` | ❌ Wave 0 |
| QA-06 | TestRabbitBroker handler tests + e2e testcontainers RabbitMQ | unit + e2e | `pytest tests/bet_maker/test_messaging.py tests/bet_maker/test_e2e_rabbitmq.py -x` | ❌ Wave 0 |

### Observability Events (structlog)

| Event key | Log level | Required bindings |
|-----------|-----------|------------------|
| `settle.noop` | INFO | `event_id`, `reason="no PENDING bets"`, `message_id`, `correlation_id` |
| `settle.committed` | INFO | `event_id`, `settled_count`, `settled_bet_ids` (as str list), `settled_via`, `message_id`, `correlation_id` |
| `settle.poison_to_dlq` | WARNING | `event_id`, `exc_type`, `exc` (truncated), `message_id`, `correlation_id` |
| `settle.transient_exhausted` | ERROR | `event_id`, `exc_type`, `exc`, `message_id`, `correlation_id`, `attempts=3` |
| `line_provider.publish` (new) | INFO | `routing_key`, `event_id`, `new_state`, `correlation_id` |

### Operational Checks

**/health 503 paths (D-20):**
- `await router.broker.ping(timeout=1.0)` returns `False` → 503 + `checks.rabbitmq = "down"`
- `len(router.broker.subscribers) == 0` → 503 + `checks.rabbitmq_consumer = "no subscribers"`
- `await ping_postgres(engine)` returns `False` → 503 + `checks.postgres = "down"` (existing)

**Updated health response shape:**
```json
{
  "status": "ok" | "degraded",
  "checks": {
    "postgres": "ok" | "down",
    "rabbitmq": "ok" | "down",
    "rabbitmq_consumer": "ok" | "no subscribers"
  }
}
```

**Mandatory binding assertion (F8):**
The binding `bsw.events --event.finished.*--> bet_maker.events.finished` is asserted implicitly by the E2E testcontainer test (D-31): publishing to the exchange with routing key `event.finished.win` must result in the bet being settled. Explicit Management API assertion is not required for Phase 5 acceptance.

### Wave 0 Gaps

- [ ] `tests/bet_maker/test_messaging.py` — unit tests for `on_event_finished` handler (7 branches: D-30)
- [ ] `tests/bet_maker/test_settle.py` — `settle_bets_for_event` interactor + concurrent settle race test
- [ ] `tests/bet_maker/test_e2e_rabbitmq.py` — real RabbitMQ e2e (D-31); needs `pika` dev-dep
- [ ] `tests/contract/test_event_finished_message_schema.py` — schema equality (D-29)
- [ ] `tests/contract/__init__.py` — new package
- [ ] `pika>=1.3,<2` added to `[dependency-groups.dev]` in `pyproject.toml` (required by `RabbitMqContainer.readiness_probe`)
- [ ] `faststream[rabbit]>=0.6,<0.7` already in prod deps (no change needed)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10 | Runtime | ✓ | 3.10.20 | — |
| faststream[rabbit] | Consumer/Publisher | ✓ | 0.6.7 (in uv.lock) | — |
| testcontainers | E2E tests | ✓ | >=4.9 (in pyproject.toml) | — |
| pika | RabbitMqContainer readiness probe | ✗ | — | Add to dev deps; NOT used in prod code |
| Docker | testcontainers | ✓ | (assumed; Phase 3 PG testcontainer already passing) | — |
| RabbitMQ (docker) | E2E test container | ✓ (via testcontainers) | 4.2-management-alpine | — |

**Missing dependencies with no fallback:**
- `pika` — required by `testcontainers.rabbitmq.RabbitMqContainer.readiness_probe()`. Must be added as dev-only dep. This is the ONLY new dependency Phase 5 introduces beyond what's already in `pyproject.toml`.

---

## TZ Drift Check

Comparing REQUIREMENTS.md LP-06/BM-09/BM-10/BM-11/QA-06 against the original ТЗ clauses:

- **LP-06** covers «независимая обработка статусов событий» — correct; ТЗ stр. 3 says line-provider publishes events to broker on state change.
- **BM-09** states `prefetch=20` while D-26 fixes `prefetch_count=10`. **Minor drift**: REQUIREMENTS.md says "prefetch=20" but CONTEXT.md D-26 locks "10". The planner must update REQUIREMENTS.md BM-09 in the sync task to reflect the locked value of 10.
- **BM-10** correctly captures «нельзя зависнуть в PENDING» via `FOR UPDATE SKIP LOCKED`.
- **BM-11** says "bounded retries via `x-death` header" but D-08/D-09 use in-handler tenacity retry (no `x-death` counting). **Drift**: REQUIREMENTS.md BM-11 describes a different DLQ retry mechanism than what is implemented. The `x-death` header approach would require reading the AMQP header and re-implementing retry counting in the consumer — this is strictly inferior to tenacity in-handler retry (which gives backoff, logging, and type-specific predicate). The planner must update REQUIREMENTS.md BM-11 to say "bounded in-handler retries via tenacity (3 attempts, exp backoff) for transient errors; poison messages rejected to DLQ immediately".
- **QA-06** and **QA-08** (e2e) are correctly scoped: QA-06 in Phase 5, QA-08 (consumer + reconciler scenario) in Phase 6.
- ТЗ clause «асинхронность сквозь стек» is satisfied: FastStream consumer is fully async, UoW/session is async, no blocking calls.
- ТЗ clause «всё в docker compose с RabbitMQ Management UI» is already satisfied by Phase 1 (rabbitmq:4.2-management-alpine, port 15672).

**Summary:** Two items need syncing in the Phase 5 doc-sync plan task: BM-09 prefetch value (20→10) and BM-11 retry mechanism description (x-death header → tenacity in-handler).

---

## Common Pitfalls

### Pitfall 1: routing_key on subscriber instead of RabbitQueue
**What goes wrong:** `@router.subscriber(routing_key="event.finished.*")` raises `TypeError: unexpected keyword argument 'routing_key'`.
**How to avoid:** Put `routing_key` on `RabbitQueue(name=..., routing_key="event.finished.*")`, not on the decorator.

### Pitfall 2: broker.connect() missing with custom lifespan
**What goes wrong:** With a custom FastAPI lifespan, `app.include_router(router)` does NOT auto-start the broker. The subscriber is registered but never connects.
**How to avoid:** Explicitly call `await router.broker.connect()` inside the custom lifespan before `yield`.

### Pitfall 3: pika import error on testcontainers
**What goes wrong:** `from testcontainers.rabbitmq import RabbitMqContainer` triggers `ModuleNotFoundError: No module named 'pika'` at import time.
**How to avoid:** Add `pika>=1.3,<2` to `[dependency-groups.dev]` in pyproject.toml.

### Pitfall 4: DLX binding not created
**What goes wrong:** DLQ exists but messages from `reject(requeue=False)` go nowhere because DLQ is not bound to DLX.
**How to avoid:** After `broker.declare_queue(RabbitQueue("...dlq", ...))`, call `await dlq.bind(exchange="bsw.events.dlx", routing_key="bet_maker.events.finished")` using the aio-pika RobustQueue object returned by `declare_queue`.

### Pitfall 5: ValidationError caught by FastStream before handler
**What goes wrong:** When `payload: EventFinishedMessage` type annotation is used and the message is malformed, FastStream may raise `DecodeError` (wrapping `ValidationError`) at the framework level, bypassing the handler's `except ValidationError` clause.
**How to avoid:** Add `from faststream.exceptions import DecodeError` and catch both `(ValidationError, DecodeError)` in the POISON branch, or use a middleware that catches pre-parse errors. Verify in unit tests with `TestRabbitBroker`.

### Pitfall 6: msg.correlation_id is auto-generated UUID if not set by publisher
**What goes wrong:** If `router.broker.publish()` does not pass `correlation_id=`, FastStream generates a random UUID for `msg.correlation_id`. The structlog binding gets a random ID instead of the HTTP request's correlation_id.
**How to avoid:** In `RabbitEventBus.publish()`, extract correlation_id from the `EventFinishedMessage.correlation_id` field (set by the interactor from the HTTP request context) and pass it to `broker.publish(correlation_id=message.correlation_id)`.

---

## Sources

### Primary (HIGH confidence — verified against installed package 0.6.7)
- uv run python introspection — `RabbitBroker`, `RabbitRouter`, `RabbitQueue`, `RabbitExchange`, `ExchangeType`, `Channel`, `AckPolicy`, `TestRabbitBroker`, `RabbitMessage`, `broker.ping`, `broker.subscribers` — all signatures verified directly
- `faststream/message/message.py` — `StreamMessage.correlation_id` and `StreamMessage.message_id` attributes confirmed
- `faststream/rabbit/message.py` — `RabbitMessage.ack()`, `nack(requeue=)`, `reject(requeue=)` signatures confirmed
- `/Users/dmitrydankov/Personal/BSW/.venv/lib/python3.10/site-packages/testcontainers/rabbitmq/__init__.py` — `RabbitMqContainer` API read directly

### Secondary (HIGH confidence — Context7)
- `/ag2ai/faststream` — FastAPI integration patterns, manual ack, TestRabbitBroker, AckPolicy, topic exchange binding, broker.ping
- `/websites/sqlalchemy_en_20` — `with_for_update(skip_locked=True)` API confirmed
- Context7 FastStream release notes — `publisher_confirms`, `Channel`, `on_return_raises` added in 0.5.6+

### Tertiary (ASSUMED — flagged)
- routing.py placement in `messaging/` sub-package — based on D-05 naming and existing code structure; not verified against official FastStream project layout conventions
- Inline tenacity shape over factory reuse — based on concern separation principle
- `Text()` type for `settled_via` column — convention choice; not from authoritative source

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `messaging/routing.py` placed under new `messaging/` sub-package (not inside `entrypoints/`) | Open Questions Resolved | Purely organizational; wrong choice adds a rename but no functional impact |
| A2 | Inline `retry(...)` in handler body instead of reusing Phase 4 `make_retry_decorator` factory | Open Questions Resolved | Both work; planner could choose factory approach — adds import but is also valid |
| A3 | `Text()` for `settled_via` column type | Alembic Migration | Could use `VARCHAR(16)` — planner can choose; both work for PG |
| A4 | `DecodeError` is raised at framework level for malformed JSON (before handler body) | Manual-Ack Ladder | If wrong, `ValidationError` IS caught in handler — test with TestRabbitBroker to confirm exact exception type |
| A5 | `dlq.bind(exchange="...", routing_key="...")` is the correct aio-pika API for binding DLQ to DLX | Lifespan Composition | If wrong, may need `await broker.declare_queue(RabbitQueue(bind_arguments=...))` — test against real RMQ in e2e |

---

## RESEARCH COMPLETE
