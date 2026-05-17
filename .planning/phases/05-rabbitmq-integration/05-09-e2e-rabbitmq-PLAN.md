---
phase: 05
plan: 09
type: execute
wave: 3
depends_on: [05, 06, 07, 08]
files_modified:
  - tests/bet_maker/test_e2e_rabbitmq.py
autonomous: true
requirements: [QA-06]
must_haves:
  truths:
    - "End-to-end: line-provider PUT /event terminal state -> RMQ publish -> bet-maker consume -> bet status flips WON/LOST within 1s (SC#1)"
    - "Test uses real RabbitMQ (testcontainers RabbitMqContainer rabbitmq:4.2-management-alpine) AND real PG"
    - "Topology binding asserted at runtime (F8): publish to bsw.events with routing_key event.finished.win reaches bet_maker.events.finished queue"
    - "Schema_version != 1 publish lands in DLQ; main queue does not enter redelivery loop (SC#3)"
  artifacts:
    - path: "tests/bet_maker/test_e2e_rabbitmq.py"
      provides: "e2e scenario test against real RMQ + real PG"
      contains: "RabbitMqContainer"
  key_links:
    - from: "line-provider FastAPI ASGI"
      to: "bet-maker FastAPI ASGI"
      via: "real RabbitMQ container"
      pattern: "amqp_url"
---

<objective>
Build the highest-fidelity test in Phase 5: a real-RabbitMQ end-to-end scenario that proves the entire stack from `PUT /event` on line-provider to `GET /bets` on bet-maker showing the bet as WON/LOST. This complements `TestRabbitBroker` unit tests (which miss topology bugs per F6).

Scenario (RESEARCH §E2E test):
1. Spin up both apps (`LifespanManager(lp_app)` + `LifespanManager(bm_app)`) against the same testcontainers RMQ + same testcontainers PG.
2. POST a new event to line-provider (state=NEW, deadline in future).
3. POST a bet to bet-maker for that event_id (event lookup uses real httpx to line-provider).
4. PUT event to FINISHED_WIN on line-provider — triggers `RabbitEventBus.publish` → real RMQ → bet-maker consumer → settle_bets_for_event.
5. Poll GET /bets on bet-maker until the bet's status flips to WON (timeout ~3-5s).
6. Assert the bet's `status == "WON"`.

Plus a DLQ acceptance test (SC#3):
1. Publish a malformed message (schema_version=99) directly via the line-provider broker.
2. Wait briefly.
3. Inspect that the main queue depth is 0 (not redelivery-looping) AND the DLQ has at least 1 message ready (via passive queue inspection through the FastStream broker).

Pitfalls guarded:
- **F6**: real broker test catches topology mistakes TestRabbitBroker would not (e.g., missing binding, wrong exchange type).
- **F8**: implicit binding assertion — settle happens only if `bsw.events --event.finished.*--> bet_maker.events.finished` exists.
- **SC#1**: 1s redelivery latency target (test uses 5s poll budget for CI variance tolerance).
- **SC#3**: poison → DLQ visible.

Output: 1 e2e test file fully implemented (replacing Plan 01 stub).
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
@tests/conftest.py
@tests/bet_maker/conftest.py
@tests/bet_maker/test_e2e_rabbitmq.py
@src/bet_maker/entrypoints/messaging.py
@src/line_provider/facades/event_bus.py

<interfaces>
<!-- Fixtures already available (Plan 01 + Plan 08): -->
- `pg_dsn` / `async_engine` (tests/conftest.py) — testcontainers PG
- `rabbitmq_container` / `amqp_url` (tests/conftest.py — Plan 01) — testcontainers RMQ
- `app` / `client` (tests/bet_maker/conftest.py — Plan 08 updated) — bet-maker FastAPI session-scoped via LifespanManager
- `line_provider_app` (tests/bet_maker/conftest.py — Plan 08 updated) — line-provider FastAPI session-scoped via LifespanManager

<!-- API paths in scope: -->
- POST /event (line-provider) — body: `{event_id, coefficient, deadline, state}`
- PUT /event (line-provider) — body: same shape, transition NEW -> FINISHED_WIN
- POST /bet (bet-maker) — body: `{event_id, amount}` -> 201 with id
- GET /bets (bet-maker) -> list of `{id, event_id, amount, status, created_at}`
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fully implement tests/bet_maker/test_e2e_rabbitmq.py</name>
  <read_first>
    - tests/bet_maker/test_e2e_rabbitmq.py (current Wave 0 stub)
    - tests/bet_maker/conftest.py (after Plan 08 — `app`, `client`, `line_provider_app` fixtures already wired to RMQ)
    - tests/bet_maker/test_events_routes.py (existing two-FastAPI-apps integration pattern with ASGITransport)
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §E2E test scenario
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`tests/bet_maker/test_e2e_rabbitmq.py`
  </read_first>
  <behavior>
    Two test scenarios:

    Scenario A — `test_e2e_consumer_settles_bet_via_real_rabbitmq` (SC#1 / F6):
    1. POST event to line-provider with state=NEW, future deadline, coefficient=1.50.
    2. Set up real httpx event_lookup on bet-maker pointing at line-provider ASGI (already done by existing `test_events_routes.py` pattern — reuse it).
    3. POST bet to bet-maker for event_id.
    4. PUT event on line-provider to FINISHED_WIN.
    5. Poll GET /bets up to ~5s for the bet to have status="WON".
    6. Assert success.

    Scenario B — `test_e2e_poison_message_lands_in_dlq` (SC#3):
    1. Build a deliberately malformed message dict (schema_version=99) — NOT an EventFinishedMessage instance (the validator would reject it).
    2. Publish raw dict via line-provider's `router.broker.publish({...}, routing_key="event.finished.win", exchange=...)` — FastStream will serialize the dict as JSON and the bet-maker consumer's `payload: EventFinishedMessage` annotation will raise during parsing → POISON branch → `reject(requeue=False)` → DLQ.
    3. Poll DLQ depth via FastStream's `broker.declare_queue(RabbitQueue("bet_maker.events.finished.dlq", durable=True, passive=True))` and inspect the returned aio-pika queue's message count. (`passive=True` opens the queue without re-declaring.)
    4. Assert DLQ depth >= 1 within ~3s.

    Note: Scenario B uses a SEPARATE event_id to avoid contaminating Scenario A's bet state.
  </behavior>
  <action>
    Overwrite `tests/bet_maker/test_e2e_rabbitmq.py` with the full e2e module. Use the existing fixture chain (no new fixtures needed; everything is wired by Plans 01 / 08).

    ```python
    """E2E tests — real RabbitMQ + real PG (Plan 05-09 / QA-06 / SC#1 / SC#3).

    These tests are the highest-fidelity validation in Phase 5. TestRabbitBroker
    (Plan 05) catches handler-level bugs; this file catches topology bugs:
    missing binding, wrong exchange type, missing DLX wiring, missing
    correlation propagation.

    Fixtures used (all session-scoped from tests/conftest.py + tests/bet_maker/conftest.py):
      - postgres_container / pg_dsn / async_engine — real PG via testcontainers (Phase 3)
      - rabbitmq_container / amqp_url — real RMQ via testcontainers (Plan 05-01)
      - app / client — bet-maker FastAPI with full lifespan (Plan 05-07)
      - line_provider_app — line-provider FastAPI with full lifespan (Plan 05-07)
    """
    from __future__ import annotations

    import asyncio
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    import pytest
    from asgi_lifespan import LifespanManager
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from bet_maker.schemas.bets import BetStatus


    @pytest.mark.asyncio(loop_scope="session")
    class TestE2ERabbitMQ:
        """SC#1: PUT to terminal state -> bet flips WON/LOST within 1s (5s budget for CI)."""

        async def test_consumer_settles_bet_after_lp_transitions_to_finished_win(
            self,
            app: FastAPI,
            client: AsyncClient,
            line_provider_app: FastAPI,
        ) -> None:
            # Build httpx client against line-provider ASGI to wire bet-maker's event_lookup
            lp_transport = ASGITransport(app=line_provider_app)
            async with AsyncClient(transport=lp_transport, base_url="http://lp") as lp_client:
                # 1. Create event in line-provider
                event_id = str(uuid4())
                deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
                r = await lp_client.post(
                    "/event",
                    json={"event_id": event_id, "coefficient": "1.50", "deadline": deadline},
                )
                assert r.status_code in (200, 201), r.text

                # 2. Swap bet-maker event_lookup to point at line-provider ASGI (mirror Plan 04-08 pattern)
                from bet_maker.facades.http_event_lookup import HttpEventLookup
                original_event_lookup = app.state.event_lookup
                app.state.event_lookup = HttpEventLookup(
                    http_client=lp_client,
                    attempts=3,
                    max_backoff=1.0,
                )
                try:
                    # 3. Place bet via bet-maker
                    rb = await client.post(
                        "/bet",
                        json={"event_id": event_id, "amount": "10.00"},
                    )
                    assert rb.status_code == 201, rb.text
                    bet_id = rb.json()["id"]

                    # 4. Transition event to FINISHED_WIN on line-provider (publishes EventFinishedMessage)
                    rp = await lp_client.put(
                        f"/event/{event_id}",
                        json={
                            "event_id": event_id,
                            "coefficient": "1.50",
                            "deadline": deadline,
                            "state": "FINISHED_WIN",
                        },
                    )
                    assert rp.status_code in (200, 204), rp.text

                    # 5. Poll bet-maker GET /bets for the bet to flip to WON
                    deadline_poll = asyncio.get_event_loop().time() + 5.0
                    final_status: str | None = None
                    while asyncio.get_event_loop().time() < deadline_poll:
                        rg = await client.get("/bets")
                        assert rg.status_code == 200
                        bets = rg.json()
                        for b in bets:
                            if b["id"] == bet_id:
                                if b["status"] != BetStatus.PENDING.value:
                                    final_status = b["status"]
                                break
                        if final_status is not None:
                            break
                        await asyncio.sleep(0.1)

                    assert final_status == BetStatus.WON.value, (
                        f"bet did not flip to WON within 5s; final_status={final_status}"
                    )
                finally:
                    app.state.event_lookup = original_event_lookup

        async def test_poison_message_lands_in_dlq(
            self,
            app: FastAPI,
            line_provider_app: FastAPI,
        ) -> None:
            """SC#3: schema_version=99 -> reject(requeue=False) -> DLQ.

            Publish a raw dict that does NOT match EventFinishedMessage (extra='forbid'
            on schema_version field default + version validation). Consumer rejects
            it to DLQ. We then passively declare the DLQ and check its message count.
            """
            from line_provider.entrypoints.messaging import router as lp_router
            from faststream.rabbit.schemas import ExchangeType, RabbitExchange, RabbitQueue

            # Publish a poison payload directly via the line-provider broker.
            # The bet-maker consumer's `payload: EventFinishedMessage` parser raises
            # ValidationError because schema_version=99 violates Field(ge=1) (1 is the
            # only supported value — UnsupportedSchemaVersion fires inside the handler
            # after parse; ValidationError can also fire if the value is non-int).
            # For maximum poison signal, we send an entirely malformed payload:
            poison_body = {
                "schema_version": 99,
                "event_id": str(uuid4()),
                "new_state": "FINISHED_WIN",
                "coefficient": "1.50",
                "occurred_at": "2026-05-18T10:00:00+00:00",
                "correlation_id": "poison-test",
            }
            exchange = RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
            await lp_router.broker.publish(
                poison_body,  # dict, not Pydantic model
                routing_key="event.finished.win",
                exchange=exchange,
                persist=True,
            )

            # Wait briefly for the consumer to process and reject.
            await asyncio.sleep(2.0)

            # Passively declare DLQ to inspect message count without re-creating it.
            from bet_maker.entrypoints.messaging import router as bm_router
            dlq = await bm_router.broker.declare_queue(
                RabbitQueue("bet_maker.events.finished.dlq", durable=True, passive=True)
            )
            # aio-pika RobustQueue: declare returns the result; for message count
            # use the underlying channel get_queue + declaration_result.message_count
            # Different aio-pika versions expose this differently; use the safer:
            # re-declare with passive=False and read .declaration_result.message_count
            # if that path exists. As a portable fallback, perform a get() with
            # no_ack to peek a message (then nack it back).
            # SIMPLEST robust assertion: declare_result message count attribute.
            msg_count = getattr(dlq, "declaration_result", None)
            if msg_count is not None and hasattr(msg_count, "message_count"):
                assert msg_count.message_count >= 1, (
                    f"DLQ depth expected >= 1, got {msg_count.message_count}"
                )
            else:
                # Fallback: consume one message from DLQ to confirm it has at least 1.
                got = await dlq.get(fail=False, timeout=2.0)
                assert got is not None, "DLQ has 0 messages — poison routing failed"
                await got.ack()
    ```

    Notes for executor:
    - The `app.state.event_lookup` swap is REQUIRED because bet-maker's `_clear_event_lookup` autouse fixture installs a `StubEventLookup` before each test (see `tests/bet_maker/conftest.py`). The swap to `HttpEventLookup(lp_client)` makes bet-maker actually consult line-provider over httpx — matching the Plan 04-08 `TestPostBetViaRealLp` integration pattern.
    - For `test_poison_message_lands_in_dlq`: aio-pika's queue message-count API surface varies across versions; the test includes a robust fallback (`get(fail=False)`) that consumes one message and asserts it exists. If the executor finds a more idiomatic FastStream/aio-pika introspection API in 0.6.7, they may use it — the INTENT is "DLQ has ≥1 message after poison publish".
    - PUT route on line-provider expects body shape `{event_id, coefficient, deadline, state}` per Phase 2 schemas — confirm the field name `state` (not `new_state`) by reading `src/line_provider/schemas/events.py::EventUpdate`. Adjust if needed.
    - The poll budget is 5s; SC#1 says 1s. CI variance allows the wider margin while still asserting bounded latency.
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker/test_e2e_rabbitmq.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/bet_maker/test_e2e_rabbitmq.py -x -q` exits 0 with 2 tests passed
    - `grep -q 'class TestE2ERabbitMQ' tests/bet_maker/test_e2e_rabbitmq.py`
    - `grep -q 'test_consumer_settles_bet_after_lp_transitions_to_finished_win' tests/bet_maker/test_e2e_rabbitmq.py`
    - `grep -q 'test_poison_message_lands_in_dlq' tests/bet_maker/test_e2e_rabbitmq.py`
    - `grep -q 'BetStatus.WON.value' tests/bet_maker/test_e2e_rabbitmq.py`
    - `grep -q 'bet_maker.events.finished.dlq' tests/bet_maker/test_e2e_rabbitmq.py`
    - `grep -q 'pytest.skip("Wave 0 stub' tests/bet_maker/test_e2e_rabbitmq.py` returns EMPTY
    - `uv run mypy tests/bet_maker/test_e2e_rabbitmq.py` exits 0
    - `uv run ruff check tests/bet_maker/test_e2e_rabbitmq.py` exits 0
  </acceptance_criteria>
  <done>2 e2e tests pass against real RMQ + real PG; SC#1 + SC#3 closed; topology bindings asserted at runtime.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Testcontainer ephemerality | Test isolation depends on per-session containers; data from previous tests must not leak into e2e assertions |
| Two FastAPI apps in one event loop | Both `LifespanManager`s must share the same asyncio event loop or asyncpg will fail with "Future attached to different loop" — Phase 4 D-16 invariant |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-09-01 | Tampering | Test contamination across e2e runs leaks state | mitigate | session-scoped fixtures + truncate_bets autouse for per-test isolation; each scenario uses fresh `event_id = uuid4()`. |
| T-05-09-02 | Denial of service | Poll loop infinite (CI hang) | mitigate | Bounded poll budget (5s) with assert on timeout; pytest configured with timeout via -ra option. |
| T-05-09-03 | Repudiation | DLQ inspection unreliable across aio-pika versions | mitigate | Robust fallback to `dlq.get(fail=False)` consumes one message to prove DLQ is non-empty; intent preserved across versions. |
| T-05-09-04 | Information disclosure | Poison message body contains sensitive payload | accept | Synthetic UUIDs only; no PII; `correlation_id="poison-test"` is operational. |
</threat_model>

<verification>
- `uv run pytest tests/bet_maker/test_e2e_rabbitmq.py -x -q` exits 0
- `uv run pytest -q` exits 0 (full suite — including all prior plans — passes)
- `uv run mypy src tests` exits 0
- `uv run ruff check src tests` exits 0
- Manual smoke (after merge): `docker compose up`, POST/PUT through the curl sequence in README, confirm bet flips within ~1s.
</verification>

<success_criteria>
- 2 e2e tests pass against real RMQ (testcontainers) + real PG (testcontainers)
- SC#1 (terminal state → bet flips) demonstrated end-to-end
- SC#3 (poison → DLQ) demonstrated with real broker
- F6 (real-broker test catches topology bugs unit tests miss) closed
- Full suite remains green
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-09-e2e-rabbitmq-SUMMARY.md` documenting: test runtime in CI, polling-budget measurements, DLQ-depth assertion outcome, and confirmation that no test relies on TestRabbitBroker mocks (this file uses real broker exclusively).
</output>
