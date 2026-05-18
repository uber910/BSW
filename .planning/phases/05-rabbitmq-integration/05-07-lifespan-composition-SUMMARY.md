---
phase: 05
plan: 07
subsystem: lifespan
tags: [faststream, rabbitmq, lifespan, broker, dlx, dlq, topology]
dependency_graph:
  requires: [05-05, 05-06]
  provides: [broker-connected-at-startup, dlx-dlq-topology, rabbit-event-bus-wired]
  affects: [bet_maker.entrypoints.lifespan, line_provider.entrypoints.lifespan, bet_maker.app, line_provider.app]
tech_stack:
  added: []
  patterns:
    - "Explicit broker.connect() in custom lifespan (Pitfall 2 — auto-lifespan does not fire with lifespan=)"
    - "DLX + DLQ + dlq.bind() declared by lifespan (Pitfall 4 — subscriber does not auto-declare DLX/DLQ)"
    - "Reverse-order shutdown: broker.close() -> http_client.aclose() -> engine.dispose() via nested try/finally"
    - "Session-scoped pytest app fixture with singleton broker patch (_connection_kwargs + broker lifecycle stubs)"
    - "Autouse _reset_event_store clears InMemoryEventStore and swaps RabbitEventBus for FakeEventBus per-test"
key_files:
  modified:
    - src/bet_maker/entrypoints/lifespan.py
    - src/bet_maker/app.py
    - src/line_provider/entrypoints/lifespan.py
    - src/line_provider/app.py
    - tests/bet_maker/test_lifespan.py
    - tests/bet_maker/conftest.py
    - tests/line_provider/test_lifespan.py
    - tests/line_provider/conftest.py
    - tests/line_provider/test_event_routes.py
decisions:
  - "Session-scoped app fixture for line_provider to avoid Future-attached-to-different-loop on broker.publish in function-scoped tests"
  - "TestProductionLifespanWiring and TestShutdownOrder stub all broker lifecycle methods (connect/start/stop/close/declare_*) to protect singleton broker from secondary LifespanManagers"
  - "NoopEventBus removed from test_event_routes.py assertions; RabbitEventBus now production bus, FakeEventBus used for per-test isolation via autouse fixture"
metrics:
  duration: "~35 min"
  completed: "2026-05-18"
  tasks_completed: 6
  files_modified: 9
---

# Phase 5 Plan 07: Lifespan Composition Summary

Composed the AMQP broker layer into both services' custom FastAPI lifespans. Explicit `await router.broker.connect()` in each custom lifespan (Pitfall 2 guard), DLX+DLQ topology declared by bet-maker lifespan (Pitfall 4 guard), reverse-order shutdown via nested try/finally (D-21/D-20).

## What Was Built

### bet-maker lifespan (D-21 / F3)

Startup order (strict sequential, no `asyncio.gather`):
1. `configure_structlog` + `BetMakerSettings()`
2. `create_engine_and_sessionmaker`
3. `wait_for_postgres` (tenacity)
4. `httpx.AsyncClient` singleton
5. `await rabbit_router.broker.connect()` — Pitfall 2
6. `declare_exchange("bsw.events.dlx", DIRECT, durable=True)` + `declare_queue("bet_maker.events.finished.dlq", durable=True)` + `dlq.bind(exchange="bsw.events.dlx", routing_key="bet_maker.events.finished")` — Pitfall 4
7. `set_sessionmaker(sessionmaker)` — wires handler dependency
8. `app.state` pins
9. `yield`

Shutdown (nested try/finally, reverse order):
`broker.close()` → `http_client.aclose()` → `engine.dispose()`

### line-provider lifespan (D-24)

Startup order:
1. `configure_structlog` + `LineProviderSettings()`
2. `await rabbit_router.broker.connect()` — Pitfall 2
3. `declare_exchange("bsw.events", TOPIC, durable=True)`
4. `app.state.event_store = InMemoryEventStore()`
5. `app.state.event_bus = RabbitEventBus(rabbit_router.broker)` — replaces NoopEventBus
6. `yield`

Shutdown: `await rabbit_router.broker.close()`

### app.py changes

Both `src/bet_maker/app.py` and `src/line_provider/app.py` now include:
```python
app.include_router(rabbit_router)
```
This registers FastStream subscribers with the FastAPI application.

### Declared Topology

| Object | Type | Args |
|--------|------|------|
| `bsw.events.dlx` exchange | `DIRECT`, `durable=True` | declared by bet-maker lifespan |
| `bet_maker.events.finished.dlq` queue | `durable=True` | declared by bet-maker lifespan |
| DLQ → DLX binding | routing_key=`bet_maker.events.finished` | wired via `dlq.bind()` |
| `bsw.events` exchange | `TOPIC`, `durable=True` | declared by line-provider lifespan |

## Tests

### TestBrokerLifespan (bet-maker)
- `test_broker_connected_and_has_subscribers`: `router.broker.ping()` returns True; `len(subscribers) >= 1`
- `test_shutdown_order_broker_before_httpx_before_engine`: source-order assertion via `getsource(lifespan)` — broker.close before aclose before engine.dispose
- `test_dlq_declared_and_idempotent`: re-declare `bet_maker.events.finished.dlq` returns non-None

### TestLineProviderLifespan (line-provider)
- `test_event_bus_is_rabbit_in_production`: `isinstance(app.state.event_bus, RabbitEventBus)` True
- `test_broker_connected_after_startup`: `router.broker.ping()` returns True
- `test_bsw_events_exchange_declared_idempotent`: re-declare `bsw.events` exchange returns non-None
- `test_shutdown_calls_broker_close`: `broker.close` called exactly once on LifespanManager exit

**Total test delta: +7 new tests (3 + 4). Total suite: 290 passed, 1 skipped.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TestBrokerLifespan ping returns False due to singleton broker state corruption**
- **Found during:** Task 5 verification
- **Issue:** `TestProductionLifespanWiring` and `TestShutdownOrder` called `broker.connect()` a second time on the module-level singleton broker via private LifespanManagers; FastStream's `start_broker_lifespan` wrapper (installed by `app.include_router(rabbit_router)`) also called `await self.broker.stop()` in its `finally` block, closing the real broker even when our patch covered only `close` (not `stop`).
- **Fix:** Patched all lifecycle methods on the singleton broker (`connect`, `start`, `stop`, `close`, `declare_exchange`, `declare_queue`) as `AsyncMock(return_value=AsyncMock())` no-ops inside private LifespanManagers so session-scoped broker state is never mutated.
- **Files modified:** `tests/bet_maker/test_lifespan.py`

**2. [Rule 3 - Blocking] line_provider function-scoped app caused Future-attached-to-different-loop**
- **Found during:** Task 6 verification (full suite run)
- **Issue:** `tests/line_provider/conftest.py` had function-scoped `app` fixture without `amqp_url`. After Plan 05-07 added `broker.connect()` to lifespan, each test function created a new event loop; `broker` singleton held a connection from a previous loop, causing `aiormq` Futures to be attached to the wrong loop on `broker.publish()`.
- **Fix:** Changed `app` fixture to session-scoped with `amqp_url` dependency + `_connection_kwargs` patch. Added autouse `_reset_event_store` fixture to clear `InMemoryEventStore` and swap `RabbitEventBus` → `FakeEventBus` per-test for isolation.
- **Files modified:** `tests/line_provider/conftest.py`

**3. [Rule 1 - Bug] test_event_routes.py asserted NoopEventBus after lifespan replaced it with RabbitEventBus**
- **Found during:** Task 6 full suite run
- **Issue:** `test_lifespan_wires_event_store_and_bus` checked `isinstance(app.state.event_bus, NoopEventBus)` — but Plan 05-07 replaced NoopEventBus with RabbitEventBus in production lifespan; autouse also replaces it with FakeEventBus before assertion.
- **Fix:** Updated test to check only `isinstance(app.state.event_store, InMemoryEventStore)` (bus wiring asserted by dedicated TestLineProviderLifespan).
- **Files modified:** `tests/line_provider/test_event_routes.py`

## Threat Model Coverage

All 6 threats from T-05-07-01..T-05-07-06 mitigated:
- T-05-07-01 (Broker before PG): F3 startup order, `wait_for_postgres` before `broker.connect`
- T-05-07-02 (DLQ not bound): `dlq.bind()` in lifespan; idempotent re-declare test verifies topology
- T-05-07-03 (Auto-lifespan missing): explicit `broker.connect()` + `test_broker_connected_after_startup`
- T-05-07-04 (Engine before broker): nested try/finally + TestShutdownOrder source-order check
- T-05-07-05 (NoopEventBus in prod): `test_event_bus_is_rabbit_in_production` asserts RabbitEventBus
- T-05-07-06 (Credential logging): accept; log.info uses service_name only

## Self-Check: PASSED

- SUMMARY.md: FOUND
- Commit 48456fa (bet-maker lifespan): FOUND
- Commit 93bdd83 (bet-maker app.py): FOUND
- Commit f45ec23 (line-provider lifespan): FOUND
- Commit 63e4491 (line-provider app.py): FOUND
- Commit bda6e5a (bet-maker tests): FOUND
- Commit 0166e09 (line-provider tests): FOUND
- broker.connect in bet-maker lifespan: FOUND
- dlq.bind in bet-maker lifespan: FOUND
- include_router in bet-maker app: FOUND
- broker.connect in line-provider lifespan: FOUND
- include_router in line-provider app: FOUND
- Full test suite: 290 passed, 1 skipped
