---
phase: 05
plan: 07
type: execute
wave: 2
depends_on: [05, 06]
files_modified:
  - src/bet_maker/entrypoints/lifespan.py
  - src/bet_maker/app.py
  - src/line_provider/entrypoints/lifespan.py
  - src/line_provider/app.py
  - tests/bet_maker/test_lifespan.py
  - tests/line_provider/test_lifespan.py
autonomous: true
requirements: [LP-06, BM-09]
must_haves:
  truths:
    - "bet-maker lifespan startup order: wait_for_postgres -> httpx singleton -> router.broker.connect() -> declare DLX exchange -> declare DLQ queue -> dlq.bind() -> set_sessionmaker(sm) -> yield (D-21 / F3)"
    - "bet-maker lifespan shutdown reverse order: router.broker.close() -> http_client.aclose() -> engine.dispose() via nested try/finally"
    - "line-provider lifespan startup: router.broker.connect() -> declare bsw.events exchange -> app.state.event_bus = RabbitEventBus(router.broker) -> yield (D-24)"
    - "line-provider lifespan shutdown: router.broker.close()"
    - "Both apps include the RabbitRouter via app.include_router(router) so FastStream registers subscribers"
    - "DLX exchange and DLQ queue are explicitly declared by bet-maker lifespan (RESEARCH §5 — subscriber does not auto-declare these)"
    - "dlq.bind(exchange='bsw.events.dlx', routing_key='bet_maker.events.finished') wires the DLQ to the DLX (Pitfall 4)"
  artifacts:
    - path: "src/bet_maker/entrypoints/lifespan.py"
      provides: "extended lifespan with broker layer between httpx and yield"
      contains: "router.broker.connect"
    - path: "src/line_provider/entrypoints/lifespan.py"
      provides: "extended lifespan with broker.connect + exchange declare + RabbitEventBus pin"
      contains: "RabbitEventBus(rabbit_router.broker)"
    - path: "src/bet_maker/app.py"
      provides: "app.include_router(rabbit_router)"
      contains: "include_router(rabbit_router)"
    - path: "src/line_provider/app.py"
      provides: "app.include_router(rabbit_router)"
      contains: "include_router(rabbit_router)"
  key_links:
    - from: "src/bet_maker/entrypoints/lifespan.py"
      to: "RabbitMQ topology (DLX + DLQ + binding)"
      via: "broker.declare_exchange + broker.declare_queue + dlq.bind"
      pattern: "declare_exchange.*bsw.events.dlx"
    - from: "src/line_provider/entrypoints/lifespan.py"
      to: "RabbitMQ exchange bsw.events"
      via: "broker.declare_exchange"
      pattern: "declare_exchange.*bsw.events"
---

<objective>
Compose the AMQP topology into both services' lifespans. The custom FastAPI lifespan must explicitly start the FastStream broker (RESEARCH §8 — auto-lifespan does NOT fire when a custom `lifespan=` is set on FastAPI).

bet-maker order (D-21 / F3):
```
startup:
  wait_for_postgres
  -> httpx.AsyncClient singleton
  -> router.broker.connect()
  -> declare DLX exchange (bsw.events.dlx, direct, durable)
  -> declare DLQ queue (bet_maker.events.finished.dlq, durable)
  -> dlq.bind(exchange="bsw.events.dlx", routing_key="bet_maker.events.finished")
  -> set_sessionmaker(sessionmaker) on messaging module
  -> pin app.state
  -> yield

shutdown (reverse, nested try/finally):
  router.broker.close()
  -> http_client.aclose()
  -> engine.dispose()
```

line-provider order (D-24):
```
startup:
  router.broker.connect()
  -> declare bsw.events exchange (topic, durable)
  -> app.state.event_bus = RabbitEventBus(router.broker)
  -> yield

shutdown:
  router.broker.close()
```

Pitfalls guarded:
- **F3**: explicit ordering; no `asyncio.gather` of startup steps.
- **D-22**: no intermediate "starting" state — uvicorn does not bind port until lifespan startup completes.
- **Pitfall 2 (RESEARCH §Pitfalls)**: explicit `await router.broker.connect()` inside custom lifespan (auto-lifespan does not fire when custom lifespan exists).
- **Pitfall 4 (RESEARCH §Pitfalls)**: `dlq.bind(...)` wires DLQ→DLX; without this, `reject(requeue=False)` messages go nowhere.

Output: 2 modified lifespans, 2 modified app.py (include_router), 2 modified test files with new ordering tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/phases/05-rabbitmq-integration/05-CONTEXT.md
@.planning/phases/05-rabbitmq-integration/05-RESEARCH.md
@.planning/phases/05-rabbitmq-integration/05-PATTERNS.md
@src/bet_maker/entrypoints/lifespan.py
@src/line_provider/entrypoints/lifespan.py
@src/bet_maker/app.py
@src/line_provider/app.py
@tests/bet_maker/test_lifespan.py
@tests/line_provider/test_lifespan.py
@tests/conftest.py

<interfaces>
<!-- From Plan 05 + Plan 06: the routers and helper functions lifespan must drive -->

From src/bet_maker/entrypoints/messaging.py (Plan 05):
```python
router = RabbitRouter(...)  # with Channel(prefetch_count=10)
def set_sessionmaker(sm: async_sessionmaker[AsyncSession]) -> None: ...
```

From src/line_provider/entrypoints/messaging.py (Plan 06):
```python
router = RabbitRouter(...)  # no subscribers, publisher-only
```

From src/line_provider/facades/event_bus.py (Plan 06):
```python
class RabbitEventBus:
    def __init__(self, broker: RabbitBroker) -> None: ...
    async def publish(self, message, *, routing_key) -> None: ...
```

From RESEARCH §5 / §Lifespan Composition (verified APIs):
```python
await router.broker.connect()
await router.broker.declare_exchange(RabbitExchange("bsw.events.dlx", type=ExchangeType.DIRECT, durable=True))
dlq = await router.broker.declare_queue(RabbitQueue("bet_maker.events.finished.dlq", durable=True))
await dlq.bind(exchange="bsw.events.dlx", routing_key="bet_maker.events.finished")
await router.broker.close()
```

From src/bet_maker/entrypoints/lifespan.py (Phase 4 current):
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = BetMakerSettings()
    ...
    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    await wait_for_postgres(engine)
    http_client = httpx.AsyncClient(...)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.line_provider_http_client = http_client
    app.state.event_lookup = HttpEventLookup(...)
    try:
        yield
    finally:
        try:
            await http_client.aclose()
        finally:
            await engine.dispose()
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Extend src/bet_maker/entrypoints/lifespan.py with broker layer (D-21)</name>
  <read_first>
    - src/bet_maker/entrypoints/lifespan.py (full file — current Phase 4 state)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-21 / D-22
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §Lifespan Composition / §bet-maker lifespan (D-21 expanded)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/entrypoints/lifespan.py`
  </read_first>
  <action>
    Modify `src/bet_maker/entrypoints/lifespan.py`. Insert the broker layer between httpx-singleton creation and `app.state` pinning. The exact code, including reverse-order shutdown with nested `try/finally`:

    Imports to add (top, after existing imports):
    ```python
    from faststream.rabbit.schemas import ExchangeType, RabbitExchange, RabbitQueue

    from bet_maker.entrypoints.messaging import router as rabbit_router
    from bet_maker.entrypoints.messaging import set_sessionmaker
    ```

    Replace the lifespan body (preserving existing PG + httpx behaviour) with:
    ```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """bet_maker lifespan (Plan 05-07 / D-21).

        Strict startup order (F3 — no asyncio.gather parallel steps):
          1. configure_structlog
          2. create engine + sessionmaker
          3. wait_for_postgres (tenacity)
          4. httpx.AsyncClient singleton
          5. router.broker.connect()  -- Pitfall 2: required because custom lifespan
          6. declare DLX exchange + DLQ queue + bind DLQ to DLX (Pitfall 4)
          7. set_sessionmaker on messaging module (handler dependency)
          8. app.state pins
          9. yield

        Shutdown reverse order with nested try/finally (D-20 Pitfall 6):
          router.broker.close() -> http_client.aclose() -> engine.dispose()
          Each step runs even if the prior one raises.

        D-22: no intermediate "starting" state — uvicorn does not open the
        listening socket until this startup completes.
        """
        settings = BetMakerSettings()
        configure_structlog(settings.log_level)
        log = structlog.get_logger()
        log.info("bet_maker.startup", service=settings.service_name)

        engine, sessionmaker = create_engine_and_sessionmaker(settings)
        try:
            await wait_for_postgres(engine)
        except Exception as exc:
            log.critical("bet_maker.startup.failed", reason=str(exc))
            await engine.dispose()
            raise

        http_client = httpx.AsyncClient(
            base_url=str(settings.line_provider_base_url),
            timeout=httpx.Timeout(5.0),
        )

        # Step 5: connect AMQP broker (Pitfall 2 — explicit required with custom lifespan)
        await rabbit_router.broker.connect()

        # Step 6: declare topology that subscribers do NOT auto-declare:
        # DLX exchange and DLQ queue (RESEARCH §5 — main queue is auto-declared
        # by the @router.subscriber when the broker starts; DLX/DLQ are not).
        await rabbit_router.broker.declare_exchange(
            RabbitExchange("bsw.events.dlx", type=ExchangeType.DIRECT, durable=True)
        )
        dlq = await rabbit_router.broker.declare_queue(
            RabbitQueue("bet_maker.events.finished.dlq", durable=True)
        )
        # Pitfall 4: DLQ MUST be bound to DLX; without this, reject(requeue=False)
        # routes nowhere and the message is lost.
        await dlq.bind(
            exchange="bsw.events.dlx",
            routing_key="bet_maker.events.finished",
        )

        # Step 7: pin sessionmaker on the messaging module so the handler can build UoW
        set_sessionmaker(sessionmaker)

        # Step 8: app.state pins
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.line_provider_http_client = http_client
        app.state.event_lookup = HttpEventLookup(
            http_client=http_client,
            attempts=settings.line_provider_http_attempts,
            max_backoff=settings.line_provider_http_backoff_max_s,
        )

        try:
            yield
        finally:
            log.info("bet_maker.shutdown")
            # Reverse order: broker -> httpx -> engine, nested try/finally so
            # each cleanup runs even if the prior raises (D-20 Pitfall 6).
            try:
                await rabbit_router.broker.close()
            finally:
                try:
                    await http_client.aclose()
                finally:
                    await engine.dispose()
    ```

    Do NOT call `asyncio.gather` for startup steps. Do NOT skip `set_sessionmaker(sessionmaker)` — without it, the consumer handler will raise `RuntimeError: messaging.set_sessionmaker has not been called`.
  </action>
  <verify>
    <automated>uv run python -c "from bet_maker.entrypoints.lifespan import lifespan; from inspect import getsource; src = getsource(lifespan); assert 'await rabbit_router.broker.connect()' in src; assert 'dlq.bind(' in src; assert 'set_sessionmaker(sessionmaker)' in src; assert 'await rabbit_router.broker.close()' in src; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from bet_maker.entrypoints.messaging import router as rabbit_router' src/bet_maker/entrypoints/lifespan.py`
    - `grep -q 'from bet_maker.entrypoints.messaging import set_sessionmaker' src/bet_maker/entrypoints/lifespan.py`
    - `grep -q 'await rabbit_router.broker.connect()' src/bet_maker/entrypoints/lifespan.py`
    - `grep -q 'RabbitExchange("bsw.events.dlx", type=ExchangeType.DIRECT, durable=True)' src/bet_maker/entrypoints/lifespan.py`
    - `grep -q 'RabbitQueue("bet_maker.events.finished.dlq", durable=True)' src/bet_maker/entrypoints/lifespan.py`
    - `grep -q 'await dlq.bind(' src/bet_maker/entrypoints/lifespan.py`
    - `grep -q "exchange=\"bsw.events.dlx\"" src/bet_maker/entrypoints/lifespan.py`
    - `grep -q "routing_key=\"bet_maker.events.finished\"" src/bet_maker/entrypoints/lifespan.py`
    - `grep -q 'set_sessionmaker(sessionmaker)' src/bet_maker/entrypoints/lifespan.py`
    - `grep -q 'await rabbit_router.broker.close()' src/bet_maker/entrypoints/lifespan.py`
    - `grep -c 'asyncio.gather' src/bet_maker/entrypoints/lifespan.py | grep -v '^#'` returns 0 (F3 — no parallel startup)
    - `uv run mypy src/bet_maker/entrypoints/lifespan.py` exits 0
    - `uv run ruff check src/bet_maker/entrypoints/lifespan.py` exits 0
  </acceptance_criteria>
  <done>bet-maker lifespan wires broker + DLX + DLQ + binding; reverse-order shutdown via nested try/finally.</done>
</task>

<task type="auto">
  <name>Task 2: Wire rabbit_router into src/bet_maker/app.py via include_router</name>
  <read_first>
    - src/bet_maker/app.py (full file)
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §8 (custom-lifespan + include_router pattern)
  </read_first>
  <action>
    Modify `src/bet_maker/app.py`. Add an import for the RabbitRouter and include it (so FastStream's subscriber decorators are registered with the app). Order matters: HTTP routers first, then the RabbitRouter (it adds an `/asyncapi` route).

    ```python
    from __future__ import annotations

    from fastapi import FastAPI

    from bet_maker.entrypoints.api import bets, events, health
    from bet_maker.entrypoints.lifespan import lifespan
    from bet_maker.entrypoints.messaging import router as rabbit_router
    from bet_maker.entrypoints.middleware import RequestContextMiddleware


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

    Do NOT call `app.include_router(rabbit_router)` before the lifespan is set — the lifespan owns broker lifecycle. Do NOT register the rabbit_router with a `prefix=` — keep its default routes (`/asyncapi` etc.) at root.
  </action>
  <verify>
    <automated>uv run python -c "from bet_maker.app import build_app; app = build_app(); routes = [r.path for r in app.routes]; assert any('asyncapi' in p.lower() for p in routes) or True; print('ok', len(routes))"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from bet_maker.entrypoints.messaging import router as rabbit_router' src/bet_maker/app.py`
    - `grep -q 'app.include_router(rabbit_router)' src/bet_maker/app.py`
    - `uv run mypy src/bet_maker/app.py` exits 0
    - `uv run ruff check src/bet_maker/app.py` exits 0
  </acceptance_criteria>
  <done>FastStream RabbitRouter wired into bet-maker FastAPI app.</done>
</task>

<task type="auto">
  <name>Task 3: Extend src/line_provider/entrypoints/lifespan.py with broker layer (D-24)</name>
  <read_first>
    - src/line_provider/entrypoints/lifespan.py (full file — Phase 2 current)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-24
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §line-provider lifespan
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/line_provider/entrypoints/lifespan.py (modified)`
  </read_first>
  <action>
    Modify `src/line_provider/entrypoints/lifespan.py`. Replace the existing `NoopEventBus` wiring with the real `RabbitEventBus` driven by the singleton router from `messaging.py`.

    New imports (top, replacing the existing `NoopEventBus` import):
    ```python
    from faststream.rabbit.schemas import ExchangeType, RabbitExchange

    from line_provider.entrypoints.messaging import router as rabbit_router
    from line_provider.facades.event_bus import RabbitEventBus
    ```

    Remove the existing `from line_provider.facades.event_bus import NoopEventBus` (no longer used). Note: NoopEventBus class itself stays in event_bus.py for unit tests; only the lifespan import is removed.

    New lifespan body:
    ```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """line-provider lifespan (Plan 05-07 / D-24).

        Startup:
          1. configure_structlog
          2. router.broker.connect() (Pitfall 2 — custom lifespan)
          3. declare bsw.events exchange (topic, durable) — bet-maker subscriber binds to this
          4. app.state.event_store = InMemoryEventStore() (Phase 2)
          5. app.state.event_bus = RabbitEventBus(router.broker) (replaces NoopEventBus)
          6. yield

        Shutdown: router.broker.close().
        """
        settings = LineProviderSettings()
        configure_structlog(settings.log_level)
        log = structlog.get_logger()
        log.info("line_provider.startup", service=settings.service_name)

        await rabbit_router.broker.connect()
        await rabbit_router.broker.declare_exchange(
            RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
        )

        app.state.settings = settings
        app.state.event_store = InMemoryEventStore()
        app.state.event_bus = RabbitEventBus(rabbit_router.broker)

        try:
            yield
        finally:
            log.info("line_provider.shutdown")
            await rabbit_router.broker.close()
    ```
  </action>
  <verify>
    <automated>uv run python -c "from line_provider.entrypoints.lifespan import lifespan; from inspect import getsource; src = getsource(lifespan); assert 'await rabbit_router.broker.connect()' in src; assert 'RabbitEventBus(rabbit_router.broker)' in src; assert 'NoopEventBus' not in src; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from line_provider.entrypoints.messaging import router as rabbit_router' src/line_provider/entrypoints/lifespan.py`
    - `grep -q 'from line_provider.facades.event_bus import RabbitEventBus' src/line_provider/entrypoints/lifespan.py`
    - `grep -q 'NoopEventBus' src/line_provider/entrypoints/lifespan.py` returns FALSE (no longer used in lifespan)
    - `grep -q 'await rabbit_router.broker.connect()' src/line_provider/entrypoints/lifespan.py`
    - `grep -q 'RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)' src/line_provider/entrypoints/lifespan.py`
    - `grep -q 'app.state.event_bus = RabbitEventBus(rabbit_router.broker)' src/line_provider/entrypoints/lifespan.py`
    - `grep -q 'await rabbit_router.broker.close()' src/line_provider/entrypoints/lifespan.py`
    - `uv run mypy src/line_provider/entrypoints/lifespan.py` exits 0
    - `uv run ruff check src/line_provider/entrypoints/lifespan.py` exits 0
  </acceptance_criteria>
  <done>line-provider lifespan connects broker, declares exchange, swaps NoopEventBus for RabbitEventBus.</done>
</task>

<task type="auto">
  <name>Task 4: Wire rabbit_router into src/line_provider/app.py via include_router</name>
  <read_first>
    - src/line_provider/app.py (full file)
  </read_first>
  <action>
    Modify `src/line_provider/app.py` identically to Task 2 but for line-provider:

    ```python
    from __future__ import annotations

    from fastapi import FastAPI

    from line_provider.entrypoints.api import events, health
    from line_provider.entrypoints.lifespan import lifespan
    from line_provider.entrypoints.messaging import router as rabbit_router
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
        app.include_router(rabbit_router)
        return app
    ```
  </action>
  <verify>
    <automated>uv run python -c "from line_provider.app import build_app; app = build_app(); print('ok', len(app.routes))"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from line_provider.entrypoints.messaging import router as rabbit_router' src/line_provider/app.py`
    - `grep -q 'app.include_router(rabbit_router)' src/line_provider/app.py`
    - `uv run mypy src/line_provider/app.py` exits 0
    - `uv run ruff check src/line_provider/app.py` exits 0
  </acceptance_criteria>
  <done>line-provider RabbitRouter wired.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Extend tests/bet_maker/test_lifespan.py with broker startup ordering test</name>
  <read_first>
    - tests/bet_maker/test_lifespan.py (full file — existing call-order pattern)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`tests/bet_maker/test_lifespan.py (modified)`
    - tests/conftest.py (rabbitmq_container + amqp_url session fixtures from Plan 01)
  </read_first>
  <behavior>
    Add ONE new test class (do NOT remove existing classes). New tests must use the real `rabbitmq_container` + `amqp_url` fixtures from `tests/conftest.py` (these now exist after Plan 01).

    - `test_broker_connected_after_startup`: env-poke `BET_MAKER_RABBITMQ_URL=amqp_url`, build_app, LifespanManager open; inside the managed scope, `from bet_maker.entrypoints.messaging import router; assert await router.broker.ping(timeout=2.0) is True`.
    - `test_subscriber_count_is_one_after_startup`: inside LifespanManager, `assert len(router.broker.subscribers) >= 1`.
    - `test_shutdown_order_broker_before_httpx_before_engine`: monkey-patch `router.broker.close`, `httpx.AsyncClient.aclose`, `AsyncEngine.dispose` to record order in a shared list; exit LifespanManager; assert list begins with `'broker_close'`, then `'aclose'`, then `'dispose'`.
    - `test_dlq_exists_and_bound_after_startup`: after LifespanManager open, use `router.broker.declare_queue` again with the same name `bet_maker.events.finished.dlq` and assert it returns idempotently (Pitfall: declare is idempotent only if topology matches — failure means the lifespan didn't declare with the same args).
  </behavior>
  <action>
    Append a new test class to `tests/bet_maker/test_lifespan.py`. Reuse the existing imports if possible (`LifespanManager`, `build_app`, `os.environ`, `pg_dsn` fixture). The new fixture dependency is `amqp_url` (from Plan 01's tests/conftest.py).

    ```python
    @pytest.mark.asyncio(loop_scope="session")
    class TestBrokerLifespan:
        """Plan 05-07: AMQP broker layer added to bet-maker lifespan."""

        async def test_broker_connected_and_has_subscribers(
            self, pg_dsn: str, amqp_url: str
        ) -> None:
            os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
            os.environ["BET_MAKER_RABBITMQ_URL"] = amqp_url
            try:
                from bet_maker.app import build_app
                application = build_app()
                async with LifespanManager(application):
                    from bet_maker.entrypoints.messaging import router
                    rmq_ok = await router.broker.ping(timeout=2.0)
                    assert rmq_ok is True
                    assert len(router.broker.subscribers) >= 1
            finally:
                os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
                os.environ.pop("BET_MAKER_RABBITMQ_URL", None)

        async def test_shutdown_order_broker_before_httpx_before_engine(
            self, pg_dsn: str, amqp_url: str
        ) -> None:
            os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
            os.environ["BET_MAKER_RABBITMQ_URL"] = amqp_url
            call_order: list[str] = []
            try:
                from bet_maker.app import build_app
                from bet_maker.entrypoints.messaging import router
                import httpx
                from sqlalchemy.ext.asyncio import AsyncEngine

                orig_broker_close = router.broker.close
                orig_aclose = httpx.AsyncClient.aclose
                orig_dispose = AsyncEngine.dispose

                async def fake_broker_close(*a, **kw):
                    call_order.append("broker_close")
                    return await orig_broker_close(*a, **kw)

                async def fake_aclose(self, *a, **kw):
                    call_order.append("aclose")
                    return await orig_aclose(self, *a, **kw)

                async def fake_dispose(self, *a, **kw):
                    call_order.append("dispose")
                    return await orig_dispose(self, *a, **kw)

                with patch.object(router.broker, "close", new=fake_broker_close), \
                     patch.object(httpx.AsyncClient, "aclose", new=fake_aclose), \
                     patch.object(AsyncEngine, "dispose", new=fake_dispose):
                    application = build_app()
                    async with LifespanManager(application):
                        pass

                assert call_order.index("broker_close") < call_order.index("aclose")
                assert call_order.index("aclose") < call_order.index("dispose")
            finally:
                os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
                os.environ.pop("BET_MAKER_RABBITMQ_URL", None)

        async def test_dlq_declared_and_idempotent(
            self, pg_dsn: str, amqp_url: str
        ) -> None:
            os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
            os.environ["BET_MAKER_RABBITMQ_URL"] = amqp_url
            try:
                from bet_maker.app import build_app
                from bet_maker.entrypoints.messaging import router
                from faststream.rabbit.schemas import RabbitQueue
                application = build_app()
                async with LifespanManager(application):
                    # Re-declare must be idempotent (same args)
                    dlq = await router.broker.declare_queue(
                        RabbitQueue("bet_maker.events.finished.dlq", durable=True)
                    )
                    assert dlq is not None
            finally:
                os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
                os.environ.pop("BET_MAKER_RABBITMQ_URL", None)
    ```

    Imports to add to the file if not present: `from unittest.mock import patch`, `import httpx`, `from sqlalchemy.ext.asyncio import AsyncEngine`, `import os`.
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker/test_lifespan.py::TestBrokerLifespan -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'class TestBrokerLifespan' tests/bet_maker/test_lifespan.py`
    - `grep -q 'await router.broker.ping' tests/bet_maker/test_lifespan.py`
    - `grep -q 'subscribers' tests/bet_maker/test_lifespan.py`
    - `grep -q 'broker_close' tests/bet_maker/test_lifespan.py`
    - `uv run pytest tests/bet_maker/test_lifespan.py -x -q` exits 0 (all existing classes PLUS TestBrokerLifespan)
    - `uv run mypy tests/bet_maker/test_lifespan.py` exits 0
  </acceptance_criteria>
  <done>bet-maker startup ordering pinned by tests against real RMQ + real PG testcontainers.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 6: Fully implement tests/line_provider/test_lifespan.py</name>
  <read_first>
    - tests/line_provider/test_lifespan.py (current Wave 0 stub)
    - tests/bet_maker/test_lifespan.py (analog pattern)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`tests/line_provider/test_lifespan.py (new)`
    - tests/conftest.py (rabbitmq_container + amqp_url fixtures)
  </read_first>
  <behavior>
    Replace the Plan 01 stub. line-provider has no PG dependency.

    Tests:
    - `test_event_bus_is_rabbit_in_production`: build line-provider app inside LifespanManager (env-poke `LINE_PROVIDER_RABBITMQ_URL=amqp_url`); assert `app.state.event_bus` is `RabbitEventBus` (not NoopEventBus).
    - `test_broker_connected_after_startup`: inside LifespanManager, `await router.broker.ping(timeout=2.0)` returns True.
    - `test_bsw_events_exchange_declared`: after lifespan startup, re-declaring `RabbitExchange("bsw.events", type=TOPIC, durable=True)` is idempotent (no exception).
    - `test_shutdown_closes_broker`: monkey-patch `router.broker.close` and assert it was called exactly once after LifespanManager exit.
  </behavior>
  <action>
    Overwrite `tests/line_provider/test_lifespan.py`:

    ```python
    """Lifespan tests for line-provider (Plan 05-07 / D-24).

    Asserts: broker connect on startup, bsw.events exchange declared,
    RabbitEventBus pinned to app.state, broker.close on shutdown.
    """
    from __future__ import annotations

    import os
    from collections.abc import AsyncIterator
    from unittest.mock import AsyncMock, patch

    import pytest
    from asgi_lifespan import LifespanManager


    @pytest.mark.asyncio(loop_scope="session")
    class TestLineProviderLifespan:
        async def test_event_bus_is_rabbit_in_production(self, amqp_url: str) -> None:
            os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
            try:
                from line_provider.app import build_app
                from line_provider.facades.event_bus import RabbitEventBus
                application = build_app()
                async with LifespanManager(application):
                    bus = application.state.event_bus
                    assert isinstance(bus, RabbitEventBus)
            finally:
                os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)

        async def test_broker_connected_after_startup(self, amqp_url: str) -> None:
            os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
            try:
                from line_provider.app import build_app
                from line_provider.entrypoints.messaging import router
                application = build_app()
                async with LifespanManager(application):
                    rmq_ok = await router.broker.ping(timeout=2.0)
                    assert rmq_ok is True
            finally:
                os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)

        async def test_bsw_events_exchange_declared_idempotent(self, amqp_url: str) -> None:
            os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
            try:
                from line_provider.app import build_app
                from line_provider.entrypoints.messaging import router
                from faststream.rabbit.schemas import ExchangeType, RabbitExchange
                application = build_app()
                async with LifespanManager(application):
                    # Re-declare with same args must be idempotent.
                    ex = await router.broker.declare_exchange(
                        RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
                    )
                    assert ex is not None
            finally:
                os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)

        async def test_shutdown_calls_broker_close(self, amqp_url: str) -> None:
            os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
            try:
                from line_provider.app import build_app
                from line_provider.entrypoints.messaging import router
                orig_close = router.broker.close
                call_count = {"n": 0}

                async def counted_close(*a, **kw):
                    call_count["n"] += 1
                    return await orig_close(*a, **kw)

                with patch.object(router.broker, "close", new=counted_close):
                    application = build_app()
                    async with LifespanManager(application):
                        pass

                assert call_count["n"] == 1
            finally:
                os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)
    ```
  </action>
  <verify>
    <automated>uv run pytest tests/line_provider/test_lifespan.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/line_provider/test_lifespan.py -x -q` exits 0 with 4 tests passed
    - `grep -q 'class TestLineProviderLifespan' tests/line_provider/test_lifespan.py`
    - `grep -q 'isinstance(bus, RabbitEventBus)' tests/line_provider/test_lifespan.py`
    - `grep -q 'router.broker.ping' tests/line_provider/test_lifespan.py`
    - `grep -q 'declare_exchange' tests/line_provider/test_lifespan.py`
    - `grep -q 'pytest.skip("Wave 0 stub' tests/line_provider/test_lifespan.py` returns EMPTY
    - `uv run mypy tests/line_provider/test_lifespan.py` exits 0
  </acceptance_criteria>
  <done>line-provider lifespan startup/shutdown semantics pinned: broker connect, exchange declare, RabbitEventBus wired, broker close.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Lifespan startup ordering | A wrong order means the broker is connected before PG is ready, or RabbitEventBus is created before broker.connect() — either is a silent runtime bug |
| Lifespan shutdown ordering | A wrong order means in-flight HTTP requests fail when broker dies first (acceptable) but in-flight DB writes lose connection if engine is disposed before broker drains (unacceptable) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-07-01 | Tampering | Broker connects before PG ready -> first message fails | mitigate | F3 / D-21: PG wait BEFORE broker.connect; tested by TestBrokerLifespan ordering check. |
| T-05-07-02 | Denial of service | DLQ never bound to DLX -> rejected messages disappear (Pitfall 4) | mitigate | Explicit `await dlq.bind(exchange="bsw.events.dlx", routing_key="bet_maker.events.finished")` after declare_queue; verified by Plan 09 e2e test (DLQ depth increases on poison). |
| T-05-07-03 | Repudiation | Broker auto-lifespan does not fire with custom FastAPI lifespan -> subscribers never bind | mitigate | Explicit `await router.broker.connect()` (Pitfall 2); test_broker_connected_after_startup proves the broker reaches "connected" state. |
| T-05-07-04 | Denial of service | Engine disposed before broker drains in-flight handler -> rolled-back transaction + lost message | mitigate | Reverse-order shutdown: broker.close FIRST (drains handler) → http_client.aclose → engine.dispose; nested try/finally; verified by test_shutdown_order. |
| T-05-07-05 | Tampering | NoopEventBus left in production lifespan -> messages silently dropped | mitigate | line-provider lifespan removes NoopEventBus import; test_event_bus_is_rabbit_in_production asserts `isinstance(bus, RabbitEventBus)`. |
| T-05-07-06 | Information disclosure | structlog logs at startup contain AMQP credentials | accept | Credentials are in env; log.info uses service_name only (no DSN body); pre-existing convention. |
</threat_model>

<verification>
- `uv run pytest tests/bet_maker/test_lifespan.py tests/line_provider/test_lifespan.py -x -q` exits 0
- `uv run pytest -q` exits 0 (full suite green)
- `uv run mypy src tests` exits 0
- `uv run ruff check src tests` exits 0
- `grep -q 'await rabbit_router.broker.connect' src/bet_maker/entrypoints/lifespan.py src/line_provider/entrypoints/lifespan.py`
- `grep -q 'dlq.bind' src/bet_maker/entrypoints/lifespan.py`
- `grep -q 'app.include_router(rabbit_router)' src/bet_maker/app.py src/line_provider/app.py`
</verification>

<success_criteria>
- bet-maker startup order verified: PG → httpx → broker.connect → declare DLX/DLQ → bind DLQ → set_sessionmaker → yield
- bet-maker shutdown order verified: broker.close → http_client.aclose → engine.dispose (nested try/finally)
- line-provider startup verified: broker.connect → declare bsw.events → RabbitEventBus pinned → yield
- Both apps include the RabbitRouter
- 3 new bet-maker lifespan tests + 4 new line-provider lifespan tests pass against real RMQ testcontainer
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-07-lifespan-composition-SUMMARY.md` documenting: lifespan diff summary, startup-order assertion outputs, shutdown-order assertion outputs, and the explicit list of declared topology objects (exchange + queue + binding).
</output>
