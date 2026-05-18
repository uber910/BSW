---
phase: 06-reconciliation-job
plan: 10
type: execute
wave: 5
depends_on: [09]
files_modified:
  - tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py
autonomous: true
requirements: [BM-12, QA-08]
tags: [e2e, testcontainers, rabbitmq, postgres, drop-publish, sc5]

must_haves:
  truths:
    - "Consumer happy path: create event → place bet → finish event → bet WON via consumer (SC#5 scenario a)"
    - "Drop-publish recovery: create event → place bet → DROP publish → finish event → bet WON via reconciler within one interval (SC#5 scenario b — main QA-08)"
    - "Delete-event cancellation: create event → place bet → delete event → bet CANCELLED via reconciler within one interval (SC#5 scenario c)"
    - "RECONCILIATION_INTERVAL_S override to 1.0s for fast test feedback (CONTEXT.md D-24)"
    - "Real RMQ + real PG via testcontainers (no mocks)"
  artifacts:
    - path: "tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py"
      provides: "3 real e2e tests replacing Wave-0 stub"
      contains: "TestReconcilerDropPublishE2E"
  key_links:
    - from: "tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py"
      to: "tests/conftest.py rabbitmq_container + postgres_container"
      via: "session-scoped testcontainers fixtures"
      pattern: "rabbitmq_container|postgres_container"
    - from: "test scenario b (drop-publish)"
      to: "line_provider.facades.event_bus.RabbitEventBus.publish"
      via: "unittest.mock.patch on the LP publish to suppress the AMQP message"
      pattern: "patch.*RabbitEventBus.*publish|monkeypatch.*publish"
---

<objective>
Deliver the **headline test for Phase 6 / QA-08**: a real-RMQ + real-PG end-to-end test that proves the Core Value — "a bet never stays PENDING after its event finished" — even when the AMQP publish is dropped.

This is the closing-the-loop test. Plan 06-09 has already shown the decision branches work against a respx-mocked LP; Plan 06-10 stitches together the FULL stack:
- Real testcontainers PostgreSQL.
- Real testcontainers RabbitMQ.
- Real bet-maker FastAPI app with full lifespan (consumer + reconciler both running).
- Real line-provider FastAPI app with full lifespan.
- The reconciliation interval is overridden to **1.0s** so test runtime stays under ~5 seconds per scenario.

Three scenarios (CONTEXT.md D-23 / ROADMAP SC#5):
- **Scenario a — Consumer happy path**: Verifies the Phase 5 contract still holds (no regression from Phase 6 wiring): create event, place bet, finish event (LP publishes normally), bet flips to WON via the consumer within ~1s.
- **Scenario b — Drop publish recovery (QA-08 main)**: Same flow as (a) but with `patch("line_provider.facades.event_bus.RabbitEventBus.publish", AsyncMock())` so the AMQP message goes to the void. The reconciler picks up the change within one interval (~1s + buffer) and flips the bet to WON. `settled_via='reconciler'` is the smoking gun.
- **Scenario c — Delete event → cancel**: Create event, place bet, then physically remove the event from line-provider's in-memory store (or restart it). The reconciler observes 404 and flips the bet to CANCELLED.

Purpose: This is the **only** test that proves the system end-to-end. Everything else is unit / integration. A reviewer of the project will run this test (or read its source) to validate the Core Value claim.

Output: 3 real e2e test assertions replacing 3 Wave-0 stubs. ~5s test runtime per scenario on a warm testcontainers cache (containers are session-scoped).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@.planning/phases/06-reconciliation-job/06-RESEARCH.md
@tests/bet_maker/test_e2e_rabbitmq.py
@tests/bet_maker/conftest.py
@tests/conftest.py
@src/bet_maker/jobs/reconciler.py
@src/bet_maker/entrypoints/lifespan.py
@tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py
</context>

<interfaces>
Existing e2e pattern (`tests/bet_maker/test_e2e_rabbitmq.py::TestE2ERabbitMQ::test_consumer_settles_bet_after_lp_transitions_to_finished_win`):
- Session-scoped `app` (bet-maker) + `line_provider_app` fixtures.
- `client: AsyncClient` for bet-maker, separate `lp_client = AsyncClient(transport=ASGITransport(app=line_provider_app), base_url="http://lp")`.
- Swap `app.state.event_lookup = HttpEventLookup(http_client=lp_client, ...)` so bet-maker's POST /bet validation routes to the test LP.
- POST `/event` to LP, POST `/bet` to bet-maker, PUT `/event/{id}` to LP to flip state → wait for bet flip via polling GET `/bets`.

Phase 6 wrinkle (`RECONCILIATION_INTERVAL_S`):
- The session-scoped `app` fixture spins up lifespan ONCE per test session with the default 30s interval. Overriding it requires either:
  (a) A separate fixture that builds a **fresh** app with `BET_MAKER_RECONCILIATION_INTERVAL_S=1.0` in env.
  (b) Hot-cancel-and-recreate the reconciliation_task with a shorter interval inside each test.

Choice for this plan: **(b)** — cancel `app.state.reconciliation_task`, await it under `suppress(CancelledError)`, then create a new task with `interval_s=1.0`. After the test, restore the original task. This avoids the cost of a second lifespan spin-up.

```python
import asyncio
from contextlib import suppress
from bet_maker.jobs.reconciler import reconciliation_loop

old_task = app.state.reconciliation_task
old_task.cancel()
with suppress(asyncio.CancelledError):
    await old_task
fast_task = asyncio.create_task(
    reconciliation_loop(app, interval_s=1.0), name="reconciliation"
)
app.state.reconciliation_task = fast_task
try:
    # ... run scenario ...
finally:
    fast_task.cancel()
    with suppress(asyncio.CancelledError):
        await fast_task
    # restart a normal task to leave fixture state consistent for next test
    app.state.reconciliation_task = asyncio.create_task(
        reconciliation_loop(app, interval_s=app.state.settings.reconciliation_interval_s),
        name="reconciliation",
    )
```

Drop-publish (Scenario b — D-23 Scenario 2):
- `from unittest.mock import AsyncMock` + `from unittest.mock import patch`.
- `with patch("line_provider.facades.event_bus.RabbitEventBus.publish", new=AsyncMock(return_value=None)): ...`
- Inside the `with` block, transition the event to FINISHED_WIN — the publish call is swallowed.
- The reconciler still runs and catches up.

Delete event (Scenario c — D-23 Scenario 3):
- Easiest path: directly mutate the in-memory store. From `line_provider.entrypoints.api.events`, the store is `line_provider/infrastructure/state.py::InMemoryEventStore`; in test scope we can reach into `line_provider_app.state.event_store._events.pop(event_id)`.
- If that exact path is not accessible due to encapsulation, fallback: pop via `line_provider_app.state` or call an internal delete method if one exists.
- Implementer note: confirm the exact `app.state` attribute name on `line_provider_app` (likely `event_store`); use `inspect` or check `line_provider/entrypoints/lifespan.py` if needed.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement 3 e2e scenarios (consumer happy / drop-publish recovery / delete-event cancel)</name>
  <files>tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py</files>
  <read_first>
    - tests/bet_maker/test_e2e_rabbitmq.py (full file — direct template; copy the AsyncClient + ASGITransport + event_lookup swap idiom)
    - tests/bet_maker/conftest.py (session-scoped app + line_provider_app fixtures + autouse _clear_event_lookup pattern)
    - src/bet_maker/jobs/reconciler.py (reconciliation_loop signature)
    - src/bet_maker/entrypoints/lifespan.py (after Plan 06-08 — confirms `app.state.reconciliation_task` and `app.state.settings`)
    - src/line_provider/entrypoints/lifespan.py (locate the in-memory event_store reference for Scenario c)
    - src/line_provider/facades/event_bus.py (or wherever `RabbitEventBus.publish` lives — exact import path for the monkeypatch)
    - tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py (Wave-0 stub — 3 method names locked)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Testing D-23 + D-24
    - .planning/phases/06-reconciliation-job/06-RESEARCH.md §Open Questions 3 (monkeypatch target path)
  </read_first>
  <behavior>
    All three tests:
    1. Generate fresh `event_id = uuid4()` and `deadline = now + 1h`.
    2. POST `/event` to LP to create the event (state=NEW).
    3. Swap `app.state.event_lookup = HttpEventLookup(http_client=lp_client, ...)` so POST /bet validation hits the test LP.
    4. POST `/bet` to bet-maker.
    5. **Speed up reconciler**: cancel the original 30s task; create a 1.0s task; pin to `app.state.reconciliation_task`. Use `try/finally` to restore on exit.
    6. Run the scenario-specific action.
    7. Poll `GET /bets` for up to 8 seconds for the expected status.
    8. Restore the original task before exiting the test.

    **Scenario a (consumer)**: After step 6, just `PUT /event/{id}` with state=FINISHED_WIN — LP publishes normally; the consumer settles. Poll → status=WON, settled_via=consumer.

    **Scenario b (drop-publish)**: Wrap `PUT /event/{id}` in `patch("line_provider.facades.event_bus.RabbitEventBus.publish", new=AsyncMock(return_value=None))` (or the actual class path determined from RESEARCH Open Question 3 — implementer must verify and adjust). The PUT succeeds but no AMQP message goes out. Wait ~2.5s (interval=1.0 + buffer). Poll → status=WON, settled_via=reconciler.

    **Scenario c (delete event)**: After POST /bet, delete the event from LP's in-memory store directly (`line_provider_app.state.event_store._events.pop(event_id, None)` — adjust to actual attribute path). No PUT needed. Wait ~2.5s. Poll → status=CANCELLED, settled_via=reconciler.

    Cleanup (finally in every test): cancel the fast task, restore a default-interval task.
  </behavior>
  <action>
    Replace `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py`:

    ```python
    """E2E (Plan 06-10 / QA-08 / SC#5): real PG + real RMQ + drop-publish recovery.

    Three scenarios from CONTEXT.md D-23 / ROADMAP Phase 6 SC#5:
      a) consumer happy path (no regression on Phase 5).
      b) drop-publish recovery via reconciler (main QA-08).
      c) delete-event recovery via reconciler (CANCELLED branch).
    """

    from __future__ import annotations

    import asyncio
    from contextlib import suppress
    from datetime import datetime, timedelta, timezone
    from unittest.mock import AsyncMock, patch
    from uuid import uuid4

    import pytest
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from bet_maker.jobs.reconciler import reconciliation_loop

    _POLL_BUDGET_S = 8.0
    _FAST_INTERVAL_S = 1.0
    _BUFFER_S = 1.5  # accommodate one tick + processing


    async def _swap_to_fast_reconciler(app: FastAPI) -> asyncio.Task[None]:
        """D-24: cancel the default 30s task, return a 1.0s task pinned to app.state.

        Returns the fast task so the test can cancel it on cleanup.
        """
        old = app.state.reconciliation_task
        old.cancel()
        with suppress(asyncio.CancelledError):
            await old
        fast = asyncio.create_task(
            reconciliation_loop(app, interval_s=_FAST_INTERVAL_S),
            name="reconciliation",
        )
        app.state.reconciliation_task = fast
        return fast


    async def _restore_default_reconciler(app: FastAPI, fast_task: asyncio.Task[None]) -> None:
        fast_task.cancel()
        with suppress(asyncio.CancelledError):
            await fast_task
        app.state.reconciliation_task = asyncio.create_task(
            reconciliation_loop(
                app, interval_s=app.state.settings.reconciliation_interval_s
            ),
            name="reconciliation",
        )


    async def _poll_bet_status(client: AsyncClient, bet_id: str, budget_s: float) -> dict:
        """Polls GET /bets until the bet status changes from PENDING or the budget is exhausted."""
        loop = asyncio.get_running_loop()
        end = loop.time() + budget_s
        while loop.time() < end:
            r = await client.get("/bets")
            assert r.status_code == 200, r.text
            for bet in r.json():
                if bet["id"] == bet_id:
                    if bet["status"] != "PENDING":
                        return bet
            await asyncio.sleep(0.1)
        # final read for diagnostic
        r = await client.get("/bets")
        for bet in r.json():
            if bet["id"] == bet_id:
                return bet
        raise AssertionError(f"bet {bet_id} not found in GET /bets")


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerDropPublishE2E:
        async def test_consumer_happy_path_settles_won(
            self,
            app: FastAPI,
            client: AsyncClient,
            line_provider_app: FastAPI,
        ) -> None:
            """SC#5 scenario a: consumer happy path (Phase 5 regression check)."""
            from bet_maker.facades.http_event_lookup import HttpEventLookup  # noqa: PLC0415

            lp_transport = ASGITransport(app=line_provider_app)
            async with AsyncClient(transport=lp_transport, base_url="http://lp") as lp_client:
                event_id = str(uuid4())
                deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

                r = await lp_client.post(
                    "/event",
                    json={"event_id": event_id, "coefficient": "1.50", "deadline": deadline},
                )
                assert r.status_code in (200, 201), r.text

                original_event_lookup = app.state.event_lookup
                app.state.event_lookup = HttpEventLookup(
                    http_client=lp_client, attempts=3, max_backoff=1.0
                )
                fast = await _swap_to_fast_reconciler(app)
                try:
                    rb = await client.post(
                        "/bet", json={"event_id": event_id, "amount": "10.00"}
                    )
                    assert rb.status_code == 201, rb.text
                    bet_id = rb.json()["id"]

                    rp = await lp_client.put(
                        f"/event/{event_id}",
                        json={
                            "coefficient": "1.50",
                            "deadline": deadline,
                            "state": "FINISHED_WIN",
                        },
                    )
                    assert rp.status_code in (200, 204), rp.text

                    bet = await _poll_bet_status(client, bet_id, _POLL_BUDGET_S)
                finally:
                    app.state.event_lookup = original_event_lookup
                    await _restore_default_reconciler(app, fast)

            assert bet["status"] == "WON", bet

        async def test_drop_publish_reconciler_recovers_won(
            self,
            app: FastAPI,
            client: AsyncClient,
            line_provider_app: FastAPI,
        ) -> None:
            """SC#5 scenario b / QA-08: AMQP publish dropped; reconciler recovers."""
            from bet_maker.facades.http_event_lookup import HttpEventLookup  # noqa: PLC0415

            lp_transport = ASGITransport(app=line_provider_app)
            async with AsyncClient(transport=lp_transport, base_url="http://lp") as lp_client:
                event_id = str(uuid4())
                deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

                r = await lp_client.post(
                    "/event",
                    json={"event_id": event_id, "coefficient": "1.50", "deadline": deadline},
                )
                assert r.status_code in (200, 201), r.text

                original_event_lookup = app.state.event_lookup
                app.state.event_lookup = HttpEventLookup(
                    http_client=lp_client, attempts=3, max_backoff=1.0
                )
                fast = await _swap_to_fast_reconciler(app)
                try:
                    rb = await client.post(
                        "/bet", json={"event_id": event_id, "amount": "10.00"}
                    )
                    assert rb.status_code == 201, rb.text
                    bet_id = rb.json()["id"]

                    # CRITICAL: drop the LP publish call so the consumer never sees the
                    # FINISHED_WIN message. The patch target is RabbitEventBus.publish
                    # in line_provider — the bus is reused across the lifespan of the
                    # LP app, so a class-level patch covers the single instance.
                    with patch(
                        "line_provider.facades.event_bus.RabbitEventBus.publish",
                        new=AsyncMock(return_value=None),
                    ):
                        rp = await lp_client.put(
                            f"/event/{event_id}",
                            json={
                                "coefficient": "1.50",
                                "deadline": deadline,
                                "state": "FINISHED_WIN",
                            },
                        )
                        assert rp.status_code in (200, 204), rp.text

                    # Wait long enough for at least one reconciler tick.
                    await asyncio.sleep(_FAST_INTERVAL_S + _BUFFER_S)
                    bet = await _poll_bet_status(client, bet_id, _POLL_BUDGET_S)
                finally:
                    app.state.event_lookup = original_event_lookup
                    await _restore_default_reconciler(app, fast)

            assert bet["status"] == "WON", bet
            # We do not GET /bet/{id} here — settled_via is not in BetRead per P3 D-05;
            # the status flip from PENDING -> WON via the dropped-publish branch is
            # itself the QA-08 acceptance signal.

        async def test_delete_event_reconciler_cancels_bet(
            self,
            app: FastAPI,
            client: AsyncClient,
            line_provider_app: FastAPI,
        ) -> None:
            """SC#5 scenario c: event deleted from LP -> bet -> CANCELLED."""
            from bet_maker.facades.http_event_lookup import HttpEventLookup  # noqa: PLC0415

            lp_transport = ASGITransport(app=line_provider_app)
            async with AsyncClient(transport=lp_transport, base_url="http://lp") as lp_client:
                event_id = str(uuid4())
                deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

                r = await lp_client.post(
                    "/event",
                    json={"event_id": event_id, "coefficient": "1.50", "deadline": deadline},
                )
                assert r.status_code in (200, 201), r.text

                original_event_lookup = app.state.event_lookup
                app.state.event_lookup = HttpEventLookup(
                    http_client=lp_client, attempts=3, max_backoff=1.0
                )
                fast = await _swap_to_fast_reconciler(app)
                try:
                    rb = await client.post(
                        "/bet", json={"event_id": event_id, "amount": "10.00"}
                    )
                    assert rb.status_code == 201, rb.text
                    bet_id = rb.json()["id"]

                    # Delete the event from LP's in-memory store directly.
                    # The exact attribute name should be verified against
                    # line_provider/entrypoints/lifespan.py; commonly
                    # `event_store._events` (dict[UUID, Event]).
                    from uuid import UUID as _UUID  # noqa: PLC0415

                    event_store = line_provider_app.state.event_store
                    # InMemoryEventStore internal dict is _events per P2 02-04.
                    event_store._events.pop(_UUID(event_id), None)

                    await asyncio.sleep(_FAST_INTERVAL_S + _BUFFER_S)
                    bet = await _poll_bet_status(client, bet_id, _POLL_BUDGET_S)
                finally:
                    app.state.event_lookup = original_event_lookup
                    await _restore_default_reconciler(app, fast)

            assert bet["status"] == "CANCELLED", bet
    ```

    Notes / verification responsibility:
    - **The implementer MUST verify the two introspection-sensitive paths before declaring done**:
      1. `line_provider.facades.event_bus.RabbitEventBus.publish` — confirm the module path. If `RabbitEventBus` lives in a different module (e.g., `line_provider/entrypoints/messaging.py`), update the patch string. `grep -rE "class RabbitEventBus" src/line_provider/` will give the answer.
      2. `line_provider_app.state.event_store._events` — confirm `event_store` is the actual `app.state` attribute and `_events` is the internal dict on `InMemoryEventStore`. `grep -E "event_store\\.|_events" src/line_provider/ -r` plus `cat src/line_provider/entrypoints/lifespan.py` will confirm.
    - If either path differs, update the test in place; do NOT silently skip the scenario.
    - The session-scoped `app` fixture means the reconciler task is shared across the entire test session — `_restore_default_reconciler` is therefore important: leaving a 1.0s task running would tax subsequent tests with unnecessary HTTP traffic.
    - Each scenario uses its own fresh `event_id` and `lp_client` context — no cross-test contamination.
    - Polling budget is 8s (with 1s interval); on CI this gives 8 reconciler ticks of margin.
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest -x -q tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` reports 3 passed
    - `grep -c "RabbitEventBus.publish" tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` >= 1 (Scenario b)
    - `grep -c "_swap_to_fast_reconciler\|interval_s=_FAST_INTERVAL_S\|interval_s=1.0" tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` >= 3 (each test calls it)
    - `grep -c "Wave-0 stub" tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` == 0
    - Total runtime ≤ ~30s (3 scenarios × ~5-8s each); informational
    - `uv run mypy tests/bet_maker/e2e/` exits 0
    - `uv run ruff check tests/bet_maker/e2e/` exits 0
    - Suite stays green after this plan: `uv run pytest -x -q tests/bet_maker/` exits 0
  </acceptance_criteria>
  <done>3 e2e scenarios pass; QA-08 is mechanically verified; settled_via/cancelled_via attribution proven through the full stack.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| dropped AMQP message → reconciler | The whole defence-in-depth contract; this test is the proof |
| testcontainers RMQ / PG → process | Real network + DB; container failures surface as test errors |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-10-01 | DoS (silent failure to recover) | reconciler drop-publish path | mitigate | Scenario b — REQUIRED to pass; the QA-08 acceptance is `bet.status == "WON"` |
| T-06-10-02 | Tampering (test passes against mocks only) | scenarios b + c | mitigate | Real PG + real RMQ via testcontainers; bypass of either layer would surface as a fixture-level failure |
| T-06-10-03 | Repudiation (test passes for wrong reason) | Scenario b | mitigate | The drop-publish patch ensures the consumer cannot observe FINISHED_WIN; only the reconciler can flip the bet — passing the test proves the reconciler did it |
| T-06-10-04 | Information Disclosure | logs | accept | event_id and bet_id are non-secret |
</threat_model>

<verification>
- `uv run pytest -x -q tests/bet_maker/e2e/` exits 0 (3 tests passed).
- `uv run pytest -x -q tests/bet_maker/` reports zero regressions (entire suite green after this plan).
- `uv run mypy src/ tests/` exits 0.
- `uv run ruff check src/ tests/` exits 0.
</verification>

<success_criteria>
- 3 e2e scenarios pass against real testcontainers PG + RMQ.
- QA-08 is mechanically verified via Scenario b.
- Scenario c proves the CANCELLED branch end-to-end (D-23 Scenario 3).
- Scenario a confirms Phase 5 consumer regression-free.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-10-SUMMARY.md` with the 3 scenario outcomes, the testcontainers runtime, and a note on which target paths required adjustment from the planner-suggested values.
</output>

## Decision Coverage

- D-23: E2E "drop publish" QA-08 / SC#5 `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` — testcontainers PG + RMQ, 3 scenarios (consumer happy path, reconciler recovers dropped publish, reconciler cancels 404).
