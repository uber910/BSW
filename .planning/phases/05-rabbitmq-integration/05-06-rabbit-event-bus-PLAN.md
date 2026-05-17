---
phase: 05
plan: 06
type: execute
wave: 2
depends_on: [02]
files_modified:
  - src/line_provider/facades/event_bus.py
  - src/line_provider/entrypoints/messaging.py
  - src/line_provider/interactors/set_event_state.py
  - tests/line_provider/test_event_bus.py
  - tests/line_provider/test_set_event_state.py
autonomous: true
requirements: [LP-06]
must_haves:
  truths:
    - "RabbitEventBus implements EventBus Protocol and publishes via router.broker.publish (D-23)"
    - "EventFinishedMessage.correlation_id is propagated to broker.publish(correlation_id=...) — Pitfall 6 fixed"
    - "Publish goes to exchange bsw.events with routing key from messaging/routing.py constants (D-01 / D-05)"
    - "persist=True on every publish — message survives broker restart"
    - "set_event_state.py imports routing constants from line_provider/messaging/routing.py (D-05) — no inline dict"
    - "Store mutation completes BEFORE publish — R9/R12/Anti-Pattern 2 preserved (Phase 2 D-12 invariant unchanged)"
  artifacts:
    - path: "src/line_provider/facades/event_bus.py"
      provides: "RabbitEventBus class implementing EventBus Protocol"
      contains: "class RabbitEventBus"
    - path: "src/line_provider/entrypoints/messaging.py"
      provides: "router = RabbitRouter(...) for lifespan import"
      contains: "RabbitRouter"
    - path: "src/line_provider/interactors/set_event_state.py"
      provides: "rewired to use messaging/routing.py constants"
      contains: "EVENT_FINISHED_WIN"
  key_links:
    - from: "src/line_provider/facades/event_bus.py"
      to: "RabbitMQ exchange bsw.events"
      via: "router.broker.publish(message, routing_key, exchange, persist=True, correlation_id=message.correlation_id)"
      pattern: "broker.publish"
    - from: "src/line_provider/interactors/set_event_state.py"
      to: "src/line_provider/messaging/routing.py"
      via: "import EVENT_FINISHED_WIN/LOSE constants"
      pattern: "from line_provider.messaging.routing import"
---

<objective>
Build the line-provider publisher side:

1. **`RabbitEventBus(broker)`** in `facades/event_bus.py`: implements existing `EventBus` Protocol. Its `publish()` calls `router.broker.publish(message, routing_key=..., exchange=RabbitExchange("bsw.events", type=TOPIC, durable=True), persist=True, correlation_id=message.correlation_id)`. The `NoopEventBus` stays alongside for unit tests (Phase 2 conftest still uses it).

2. **`messaging.py` module** in line-provider: declares `router = RabbitRouter(str(settings.rabbitmq_url))` so lifespan (Plan 07) can `await router.broker.connect()` and `app.state.event_bus = RabbitEventBus(router.broker)`. No subscribers — line-provider only publishes. No `Channel(prefetch_count=...)` either — that is consumer-side concern.

3. **Rewire `set_event_state.py`** to import `EVENT_FINISHED_WIN` / `EVENT_FINISHED_LOSE` from the new `line_provider/messaging/routing.py` (created in Plan 02). The existing inline `_TERMINAL_TO_ROUTING` dict is replaced by `{EventState.FINISHED_WIN: EVENT_FINISHED_WIN, EventState.FINISHED_LOSE: EVENT_FINISHED_LOSE}`. Commit-before-publish ordering (Phase 2 D-12) is untouched.

Pitfalls guarded:
- **R9/R12/Anti-Pattern 2**: Phase 2 D-12 already guarantees `store.update()` exits BEFORE `event_bus.publish()`. We do NOT relax this; we only swap the bus implementation.
- **F5 / Anti-Pattern 5**: one `RabbitRouter` for line-provider; module-level singleton in `messaging.py`. `RabbitEventBus` wraps `router.broker.publish` — no second broker.
- **Pitfall 6 (correlation_id default UUID)**: `broker.publish(correlation_id=message.correlation_id)` propagates the HTTP request's correlation_id (set by middleware → set in `EventFinishedMessage.correlation_id` by interactor); no random UUIDs.
- **D-28 (no cross-service imports)**: `EventFinishedMessage` comes from `line_provider.schemas.messages` ONLY.

Output: 1 modified facade, 1 new entrypoint, 1 modified interactor, 1 new test file fully implemented, 1 modified test file with new assertions.
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
@src/line_provider/facades/event_bus.py
@src/line_provider/interactors/set_event_state.py
@src/line_provider/schemas/messages.py
@src/line_provider/messaging/routing.py
@src/line_provider/settings/config.py
@tests/line_provider/test_set_event_state.py

<interfaces>
<!-- Existing contracts that this plan extends (NOT rewrites) -->

From src/line_provider/facades/event_bus.py (extend, don't replace):
```python
class EventBus(Protocol):
    async def publish(self, message: EventFinishedMessage, *, routing_key: str) -> None: ...

class NoopEventBus:
    async def publish(self, message, *, routing_key): ...  # keep for tests
```

From src/line_provider/interactors/set_event_state.py (current — Phase 2 D-12 commit-before-publish):
```python
new_event, previous_state = await store.update(...)  # mutate first

if previous_state == EventState.NEW and new_state in _TERMINAL_TO_ROUTING:  # <-- swap dict to constants
    await event_bus.publish(EventFinishedMessage(...), routing_key=_TERMINAL_TO_ROUTING[new_state])
```

From RESEARCH §4 (verified API):
```python
await router.broker.publish(
    message,
    routing_key="event.finished.win",
    exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
    persist=True,
    correlation_id=correlation_id,  # <-- propagate (Pitfall 6)
)
```

From src/line_provider/messaging/routing.py (Plan 02):
```python
EVENT_FINISHED_WIN: Final[str] = "event.finished.win"
EVENT_FINISHED_LOSE: Final[str] = "event.finished.lose"
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add RabbitEventBus to src/line_provider/facades/event_bus.py</name>
  <read_first>
    - src/line_provider/facades/event_bus.py (full file — NoopEventBus pattern)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-23 / D-24
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/line_provider/facades/event_bus.py`
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §4 (publish API) + §Pitfall 6 (correlation_id propagation)
  </read_first>
  <behavior>
    - `RabbitEventBus.publish(message, routing_key)` calls `broker.publish(message, routing_key=routing_key, exchange=RabbitExchange("bsw.events", type=TOPIC, durable=True), persist=True, correlation_id=message.correlation_id)`.
    - After publish, emits structlog `line_provider.publish` info event with routing_key + event_id + new_state + correlation_id.
    - NoopEventBus stays — Phase 2 conftest still uses it. `EventBus` Protocol unchanged.
  </behavior>
  <action>
    Extend `src/line_provider/facades/event_bus.py`. Keep all existing content. Append the new class and necessary imports.

    Imports to add at the top (after existing `import structlog`):
    ```python
    from faststream.rabbit import RabbitBroker
    from faststream.rabbit.schemas import ExchangeType, RabbitExchange
    ```

    New class to append at the end of the file:
    ```python
    class RabbitEventBus:
        """D-23: publishes EventFinishedMessage to the bsw.events topic exchange.

        Implements the EventBus Protocol structurally — no inheritance.
        Constructed in lifespan (Plan 07) with the FastStream RabbitBroker
        from line_provider.entrypoints.messaging.router.broker.

        Pitfall 6 (RESEARCH.md): correlation_id is propagated from
        EventFinishedMessage.correlation_id (set by the interactor from
        the HTTP request's request_id middleware binding) to
        broker.publish(correlation_id=...) so the AMQP property carries
        the same id end-to-end. Without this, FastStream would generate
        a random UUID for msg.correlation_id and structlog binding in
        the consumer would lose request traceability.

        persist=True ensures the message survives a broker restart
        (combined with durable=True on the queue declared by bet-maker).
        """

        def __init__(self, broker: RabbitBroker) -> None:
            self._broker = broker
            self._exchange = RabbitExchange(
                "bsw.events", type=ExchangeType.TOPIC, durable=True
            )

        async def publish(
            self,
            message: EventFinishedMessage,
            *,
            routing_key: str,
        ) -> None:
            await self._broker.publish(
                message,
                routing_key=routing_key,
                exchange=self._exchange,
                persist=True,
                correlation_id=message.correlation_id,
            )
            structlog.get_logger().info(
                "line_provider.publish",
                routing_key=routing_key,
                event_id=str(message.event_id),
                new_state=message.new_state.value,
                schema_version=message.schema_version,
                correlation_id=message.correlation_id,
            )
    ```

    Do NOT modify `NoopEventBus` (Phase 2 tests depend on it). Do NOT change the `EventBus` Protocol.
  </action>
  <verify>
    <automated>uv run python -c "from line_provider.facades.event_bus import RabbitEventBus, NoopEventBus, EventBus; from faststream.rabbit import RabbitBroker; import inspect; sig = inspect.signature(RabbitEventBus.publish); params = list(sig.parameters); assert params == ['self', 'message', 'routing_key'], params; assert sig.parameters['routing_key'].kind.name == 'KEYWORD_ONLY'; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'class RabbitEventBus' src/line_provider/facades/event_bus.py`
    - `grep -q 'class NoopEventBus' src/line_provider/facades/event_bus.py` (preserved)
    - `grep -q 'class EventBus(Protocol)' src/line_provider/facades/event_bus.py` (preserved)
    - `grep -q 'await self._broker.publish' src/line_provider/facades/event_bus.py`
    - `grep -q 'persist=True' src/line_provider/facades/event_bus.py`
    - `grep -q 'correlation_id=message.correlation_id' src/line_provider/facades/event_bus.py`
    - `grep -q 'RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)' src/line_provider/facades/event_bus.py`
    - `grep -q '"line_provider.publish"' src/line_provider/facades/event_bus.py`
    - `uv run mypy src/line_provider/facades/event_bus.py` exits 0
    - `uv run ruff check src/line_provider/facades/event_bus.py` exits 0
  </acceptance_criteria>
  <done>RabbitEventBus class exists, mypy strict-clean, NoopEventBus preserved, correlation propagation in source.</done>
</task>

<task type="auto">
  <name>Task 2: Create src/line_provider/entrypoints/messaging.py declaring the RabbitRouter</name>
  <read_first>
    - src/line_provider/settings/config.py (LineProviderSettings — confirm rabbitmq_url field)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-23 / D-24
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/line_provider/entrypoints/lifespan.py (modified)` notes about messaging.py
  </read_first>
  <action>
    Create `src/line_provider/entrypoints/messaging.py`. line-provider has NO subscribers — this module only declares the `RabbitRouter` instance so lifespan (Plan 07) can `await router.broker.connect()` and instantiate `RabbitEventBus(router.broker)`.

    ```python
    """line-provider AMQP entrypoint (publisher-only) (D-24).

    line-provider does NOT consume any AMQP messages — Phase 5 publishes
    EventFinishedMessage on store-state transitions. This module exists
    solely to own the singleton RabbitRouter instance (F5 / Anti-Pattern 5).
    Lifespan calls router.broker.connect() and wires
    `app.state.event_bus = RabbitEventBus(router.broker)`.

    No subscriber decorators. No Channel(prefetch_count=...) — that is a
    consumer-side concern (bet-maker). No exchange declarations here —
    lifespan does the explicit declare (D-24 / RESEARCH §5).
    """
    from __future__ import annotations

    from faststream.rabbit.fastapi import RabbitRouter

    from line_provider.settings.config import LineProviderSettings

    _settings = LineProviderSettings()

    router = RabbitRouter(str(_settings.rabbitmq_url))
    ```

    Do NOT add subscribers. Do NOT add a `Channel(prefetch_count=...)` — line-provider does not consume. Do NOT import from `line_provider.facades.event_bus` (circular import — `event_bus.py` does not import this module).
  </action>
  <verify>
    <automated>uv run python -c "from line_provider.entrypoints.messaging import router; from faststream.rabbit.fastapi import RabbitRouter; assert isinstance(router, RabbitRouter); assert len(router.broker.subscribers) == 0; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/line_provider/entrypoints/messaging.py`
    - `grep -q 'router = RabbitRouter(str(_settings.rabbitmq_url))' src/line_provider/entrypoints/messaging.py`
    - `grep -c '@router.subscriber' src/line_provider/entrypoints/messaging.py | grep -v '^#'` returns 0 (publisher-only)
    - `grep -c 'Channel(prefetch' src/line_provider/entrypoints/messaging.py | grep -v '^#'` returns 0 (consumer-only concern)
    - `uv run mypy src/line_provider/entrypoints/messaging.py` exits 0
    - `uv run ruff check src/line_provider/entrypoints/messaging.py` exits 0
  </acceptance_criteria>
  <done>line-provider has its singleton RabbitRouter ready for lifespan to consume.</done>
</task>

<task type="auto">
  <name>Task 3: Rewire set_event_state.py to import routing constants from messaging/routing.py</name>
  <read_first>
    - src/line_provider/interactors/set_event_state.py (full file)
    - src/line_provider/messaging/routing.py (created by Plan 02)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-05
  </read_first>
  <action>
    Modify `src/line_provider/interactors/set_event_state.py`. Two changes ONLY — do NOT touch the commit-before-publish ordering (Phase 2 D-12 invariant must remain).

    Change 1 — replace the inline `_TERMINAL_TO_ROUTING` dict (lines 19-22) with a dict built from the new constants:
    ```python
    from line_provider.messaging.routing import EVENT_FINISHED_LOSE, EVENT_FINISHED_WIN

    _TERMINAL_TO_ROUTING: dict[EventState, str] = {
        EventState.FINISHED_WIN: EVENT_FINISHED_WIN,
        EventState.FINISHED_LOSE: EVENT_FINISHED_LOSE,
    }
    ```

    Change 2 — leave the rest of the file (the `set_event_state` function body) UNCHANGED. The existing `if previous_state == EventState.NEW and new_state in _TERMINAL_TO_ROUTING: await event_bus.publish(..., routing_key=_TERMINAL_TO_ROUTING[new_state])` works as-is because the dict shape (`{EventState: str}`) is preserved.

    Do NOT inline the routing constants into the publish call (`routing_key=EVENT_FINISHED_WIN` instead of dict lookup) — the dict gives compile-time guarantee that both terminal states map to known constants and keeps the code one-place-of-truth.
  </action>
  <verify>
    <automated>uv run pytest tests/line_provider/test_set_event_state.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from line_provider.messaging.routing import' src/line_provider/interactors/set_event_state.py`
    - `grep -q 'EVENT_FINISHED_WIN' src/line_provider/interactors/set_event_state.py`
    - `grep -q 'EVENT_FINISHED_LOSE' src/line_provider/interactors/set_event_state.py`
    - `grep -q '"event.finished.win"' src/line_provider/interactors/set_event_state.py` returns FALSE (literal removed — constant used)
    - `grep -q '"event.finished.lose"' src/line_provider/interactors/set_event_state.py` returns FALSE
    - `uv run pytest tests/line_provider/test_set_event_state.py -x -q` exits 0 (existing tests still green)
    - `uv run mypy src/line_provider/interactors/set_event_state.py` exits 0
  </acceptance_criteria>
  <done>Constants single-sourced; existing Phase 2 publish behaviour unchanged; tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Fully implement tests/line_provider/test_event_bus.py</name>
  <read_first>
    - tests/line_provider/test_event_bus.py (current Wave 0 stub)
    - tests/line_provider/_fakes.py (existing FakeEventBus reference)
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §Pitfall 6 (correlation propagation)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`tests/line_provider/test_event_bus.py`
  </read_first>
  <behavior>
    Replace the Plan 01 stub with real tests. `RabbitEventBus` interacts with a `RabbitBroker` — test by passing a `MagicMock(spec=RabbitBroker)` (or `AsyncMock`) and asserting `broker.publish` was called with the right kwargs.

    Tests:
    - `test_publish_calls_broker_publish_with_correct_kwargs`: build a sample `EventFinishedMessage(correlation_id="abc-123", ...)`, call `bus.publish(message, routing_key="event.finished.win")`, assert `broker.publish` was awaited once with `routing_key="event.finished.win"`, `exchange.name == "bsw.events"`, `persist=True`, `correlation_id="abc-123"`.
    - `test_publish_propagates_correlation_id_from_message` (Pitfall 6 explicit guard): two messages with different correlation_ids → two publish calls with matching correlation_id kwargs.
    - `test_exchange_is_topic_and_durable`: inspect the exchange the bus constructs — it should be `ExchangeType.TOPIC` + `durable=True`.
    - `test_persist_is_always_true`: assert `persist=True` is always passed (no path that omits it).
  </behavior>
  <action>
    Overwrite `tests/line_provider/test_event_bus.py`:

    ```python
    """Unit tests for RabbitEventBus.publish (Plan 05-06 / LP-06).

    Pitfall 6: correlation_id propagation from message into broker.publish kwarg.
    Tests use AsyncMock(spec=RabbitBroker) — no real broker required for unit-level
    assertion of "broker received the right call".
    """
    from __future__ import annotations

    from datetime import datetime, timezone
    from decimal import Decimal
    from unittest.mock import AsyncMock
    from uuid import uuid4

    import pytest
    from faststream.rabbit import RabbitBroker
    from faststream.rabbit.schemas import ExchangeType

    from line_provider.facades.event_bus import RabbitEventBus
    from line_provider.schemas.messages import EventFinishedMessage, EventTerminalState


    def _message(correlation_id: str = "test-corr") -> EventFinishedMessage:
        return EventFinishedMessage(
            schema_version=1,
            event_id=uuid4(),
            new_state=EventTerminalState.FINISHED_WIN,
            coefficient=Decimal("1.50"),
            occurred_at=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
            correlation_id=correlation_id,
        )


    @pytest.mark.asyncio(loop_scope="session")
    class TestPublish:
        async def test_publish_calls_broker_publish_with_correct_kwargs(self) -> None:
            broker = AsyncMock(spec=RabbitBroker)
            bus = RabbitEventBus(broker)
            msg = _message("abc-123")

            await bus.publish(msg, routing_key="event.finished.win")

            broker.publish.assert_awaited_once()
            args, kwargs = broker.publish.call_args
            # message is positional or kwarg depending on FastStream signature — assert via args[0] or kwargs
            assert args[0] is msg or kwargs.get("message") is msg
            assert kwargs.get("routing_key") == "event.finished.win"
            assert kwargs.get("persist") is True
            assert kwargs.get("correlation_id") == "abc-123"
            exchange = kwargs.get("exchange")
            assert exchange is not None
            assert exchange.name == "bsw.events"
            assert exchange.type == ExchangeType.TOPIC
            assert exchange.durable is True

        async def test_publish_propagates_correlation_id_from_message(self) -> None:
            """Pitfall 6: two messages, two correlation_ids — both forwarded as-is."""
            broker = AsyncMock(spec=RabbitBroker)
            bus = RabbitEventBus(broker)

            await bus.publish(_message("corr-1"), routing_key="event.finished.win")
            await bus.publish(_message("corr-2"), routing_key="event.finished.lose")

            assert broker.publish.await_count == 2
            corrs = [c.kwargs.get("correlation_id") for c in broker.publish.call_args_list]
            assert corrs == ["corr-1", "corr-2"]

        async def test_persist_is_always_true(self) -> None:
            broker = AsyncMock(spec=RabbitBroker)
            bus = RabbitEventBus(broker)
            await bus.publish(_message(), routing_key="event.finished.win")
            assert broker.publish.call_args.kwargs.get("persist") is True
    ```

    Notes for executor: FastStream's `broker.publish` signature (RESEARCH §4) is `publish(self, message, queue, exchange, routing_key, mandatory, immediate, timeout, persist, reply_to, correlation_id, ...)`. The `message` is the first positional. `AsyncMock(spec=RabbitBroker)` will create `publish` as an `AsyncMock` that records call_args. If the spec causes attribute resolution issues, fall back to `AsyncMock()` without spec.
  </action>
  <verify>
    <automated>uv run pytest tests/line_provider/test_event_bus.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/line_provider/test_event_bus.py -x -q` exits 0 with 3 passed
    - `grep -q 'AsyncMock(spec=RabbitBroker)' tests/line_provider/test_event_bus.py`
    - `grep -q 'correlation_id="corr-1"' tests/line_provider/test_event_bus.py` AND `grep -q 'correlation_id="corr-2"' tests/line_provider/test_event_bus.py`
    - `grep -q 'persist.*True' tests/line_provider/test_event_bus.py`
    - `grep -q 'pytest.skip("Wave 0 stub' tests/line_provider/test_event_bus.py` returns EMPTY
    - `uv run mypy tests/line_provider/test_event_bus.py` exits 0
  </acceptance_criteria>
  <done>RabbitEventBus.publish behaviour pinned: correct kwargs, correlation propagation, persist=True invariant.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Extend tests/line_provider/test_set_event_state.py with routing-constant import assertion + commit-before-publish re-verification</name>
  <read_first>
    - tests/line_provider/test_set_event_state.py (existing test file — preserve all existing tests)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-05 (routing key single-source) and the Phase 2 D-12 invariant (commit-before-publish)
  </read_first>
  <behavior>
    Add ONE test class to the existing file (do NOT rewrite the file). The class re-verifies the two invariants this plan touches:

    - `test_publish_uses_routing_constants_from_messaging_module`: build the existing FakeEventBus scenario; transition NEW→FINISHED_WIN; assert the `routing_key` argument equals `EVENT_FINISHED_WIN` constant (proves the dict swap landed) — NOT the literal string `"event.finished.win"` (the constant IS that string but the import guards against accidental literal use).
    - `test_publish_uses_routing_constants_for_finished_lose`: same but for FINISHED_LOSE / EVENT_FINISHED_LOSE.
    - `test_existing_commit_before_publish_invariant_preserved`: this is a documentation-style test that asserts the existing call-order property of `set_event_state` — the FakeEventBus publish only fires AFTER the store update completes (Phase 2 D-12). Use the existing test pattern in the file as a reference.
  </behavior>
  <action>
    Append a new test class to `tests/line_provider/test_set_event_state.py` (do NOT remove or modify existing tests; this plan strictly extends).

    Step A — read the existing file to identify the existing fixture/import shape (`FakeEventBus`, `InMemoryEventStore`, `set_event_state`, etc.). Reuse them.

    Step B — append:

    ```python
    from line_provider.messaging.routing import EVENT_FINISHED_LOSE, EVENT_FINISHED_WIN


    @pytest.mark.asyncio(loop_scope="session")
    class TestRoutingConstantsWiring:
        """D-05: set_event_state.py must use messaging/routing.py constants,
        not inline string literals."""

        async def test_publish_uses_event_finished_win_constant(self) -> None:
            # Existing helper pattern from the file: build store + FakeEventBus
            # then transition NEW -> FINISHED_WIN and assert the call.
            # The executor adapts to the actual fixture names in this file.
            from line_provider.infrastructure.store.in_memory import InMemoryEventStore
            from line_provider.interactors.set_event_state import set_event_state
            from line_provider.schemas.events import Event, EventState
            from tests.line_provider._fakes import FakeEventBus

            from datetime import datetime, timedelta, timezone
            from decimal import Decimal
            from uuid import uuid4

            store = InMemoryEventStore()
            bus = FakeEventBus()
            evt_id = uuid4()
            deadline = datetime.now(timezone.utc) + timedelta(hours=1)
            initial = Event(event_id=evt_id, coefficient=Decimal("1.50"), deadline=deadline, state=EventState.NEW)
            await store.create(initial)

            await set_event_state(
                store, bus,
                event_id=evt_id,
                coefficient=Decimal("1.50"),
                deadline=deadline,
                new_state=EventState.FINISHED_WIN,
                correlation_id="cid-1",
            )

            assert len(bus.calls) == 1
            assert bus.calls[0].routing_key == EVENT_FINISHED_WIN

        async def test_publish_uses_event_finished_lose_constant(self) -> None:
            from line_provider.infrastructure.store.in_memory import InMemoryEventStore
            from line_provider.interactors.set_event_state import set_event_state
            from line_provider.schemas.events import Event, EventState
            from tests.line_provider._fakes import FakeEventBus

            from datetime import datetime, timedelta, timezone
            from decimal import Decimal
            from uuid import uuid4

            store = InMemoryEventStore()
            bus = FakeEventBus()
            evt_id = uuid4()
            deadline = datetime.now(timezone.utc) + timedelta(hours=1)
            initial = Event(event_id=evt_id, coefficient=Decimal("1.50"), deadline=deadline, state=EventState.NEW)
            await store.create(initial)

            await set_event_state(
                store, bus,
                event_id=evt_id,
                coefficient=Decimal("1.50"),
                deadline=deadline,
                new_state=EventState.FINISHED_LOSE,
                correlation_id="cid-2",
            )

            assert len(bus.calls) == 1
            assert bus.calls[0].routing_key == EVENT_FINISHED_LOSE
    ```

    Notes:
    - Verify the actual `FakeEventBus.calls[i].routing_key` attribute by reading `tests/line_provider/_fakes.py`. The fake records publish calls with at least `message`, `routing_key`. If the field is named `route_key` or stored differently, adapt accordingly. The test's INTENT is: assert the constants flowed through.
    - If `InMemoryEventStore.create(initial)` does not exist by that name in the existing code, use whatever creation helper the existing tests use (read the surrounding tests in the file).
  </action>
  <verify>
    <automated>uv run pytest tests/line_provider/test_set_event_state.py::TestRoutingConstantsWiring -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'class TestRoutingConstantsWiring' tests/line_provider/test_set_event_state.py`
    - `grep -q 'EVENT_FINISHED_WIN' tests/line_provider/test_set_event_state.py`
    - `grep -q 'EVENT_FINISHED_LOSE' tests/line_provider/test_set_event_state.py`
    - `uv run pytest tests/line_provider/test_set_event_state.py -x -q` exits 0 (all existing PLUS new tests green)
    - `uv run mypy tests/line_provider/test_set_event_state.py` exits 0
  </acceptance_criteria>
  <done>Constants verified at the call site via Phase 2's existing fake; commit-before-publish invariant unchanged.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Outbound AMQP publish | line-provider broadcasts state changes; downstream consumers (bet-maker + future) trust this stream |
| correlation_id propagation | Required for end-to-end traceability; failure means observability gap |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-06-01 | Spoofing | A publish with wrong/missing correlation_id | mitigate | `broker.publish(correlation_id=message.correlation_id)` always set; Pitfall 6 fix; test_event_bus_propagates_correlation_id_from_message proves this. |
| T-05-06-02 | Tampering | Publish before store mutation (publishing on stale data) | mitigate | Phase 2 D-12 invariant preserved (store.update returns before event_bus.publish call); existing test_set_event_state tests untouched; new TestRoutingConstantsWiring re-validates this implicitly. |
| T-05-06-03 | Repudiation | Message lost during broker restart | mitigate | `persist=True` on every publish; `durable=True` on exchange and queue (Plan 07 lifespan); test_persist_is_always_true asserts persist invariant. |
| T-05-06-04 | Denial of service | Multiple RabbitBroker instances exhausting connections | mitigate | F5 / Anti-Pattern 5: single `RabbitRouter` in `line_provider/entrypoints/messaging.py`; `RabbitEventBus` wraps `router.broker.publish`; no second broker instantiated anywhere. |
| T-05-06-05 | Information disclosure | structlog log includes full message body | accept | message body is event_id (UUID, no PII), new_state, routing_key — operational metadata, not user data. |
</threat_model>

<verification>
- `uv run pytest tests/line_provider/test_event_bus.py tests/line_provider/test_set_event_state.py -x -q` exits 0
- `uv run pytest -q` exits 0 (full suite green; no regression in Phase 2 tests)
- `uv run mypy src tests` exits 0
- `uv run ruff check src tests` exits 0
- `grep -q 'class RabbitEventBus' src/line_provider/facades/event_bus.py`
- `grep -q 'persist=True' src/line_provider/facades/event_bus.py`
- `grep -q 'correlation_id=message.correlation_id' src/line_provider/facades/event_bus.py`
- `grep -q 'router = RabbitRouter' src/line_provider/entrypoints/messaging.py`
- `grep -q 'EVENT_FINISHED_WIN' src/line_provider/interactors/set_event_state.py`
</verification>

<success_criteria>
- `RabbitEventBus` implements `EventBus` Protocol structurally; publishes with persist=True and correlation_id propagation
- `line_provider/entrypoints/messaging.py` declares the singleton `router` (no subscribers)
- `set_event_state.py` imports routing constants — no inline string literals
- Phase 2 D-12 invariant preserved (commit-before-publish)
- New test_event_bus.py (3 tests) green; existing test_set_event_state.py PLUS new TestRoutingConstantsWiring (2 tests) all green
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-06-rabbit-event-bus-SUMMARY.md` documenting: RabbitEventBus class signature, line-provider router presence, set_event_state.py diff (dict literal → constants), test counts, and explicit confirmation that NoopEventBus is preserved.
</output>
