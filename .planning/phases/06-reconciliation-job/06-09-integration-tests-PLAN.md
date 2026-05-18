---
phase: 06-reconciliation-job
plan: 09
type: execute
wave: 4
depends_on: [08]
files_modified:
  - tests/bet_maker/integration/test_reconciler_consumer_race.py
  - tests/bet_maker/integration/test_reconciler_drop_publish.py
autonomous: true
requirements: [BM-12]
tags: [integration, respx, testcontainers-pg, race, drop-publish]

must_haves:
  truths:
    - "Concurrent settle+reconcile against same event_id produces exactly one settled status per bet (no double-update, no deadlock)"
    - "Reconciler observes terminal state via respx-mocked LP and settles bets within one interval"
    - "Reconciler observes 404 via respx-mocked LP and cancels bets within one interval"
    - "Reconciler skips events still in NEW state (no false settle)"
    - "All tests use real PG via testcontainers (not SQLite) — FOR UPDATE SKIP LOCKED is exercised"
  artifacts:
    - path: "tests/bet_maker/integration/test_reconciler_consumer_race.py"
      provides: "2 real tests on the FOR UPDATE SKIP LOCKED guarantee (SC#4)"
      contains: "FOR UPDATE SKIP LOCKED"
    - path: "tests/bet_maker/integration/test_reconciler_drop_publish.py"
      provides: "3 real tests on respx-mocked LP drop-publish recovery (SC#1)"
      contains: "respx"
  key_links:
    - from: "tests/bet_maker/integration/test_reconciler_consumer_race.py"
      to: "src/bet_maker/repositories/bets.py::get_pending_locked"
      via: "tests exercise the SKIP LOCKED + status filter contract under asyncio.gather"
      pattern: "FOR UPDATE SKIP LOCKED|get_pending_locked"
    - from: "tests/bet_maker/integration/test_reconciler_drop_publish.py"
      to: "src/bet_maker/facades/http_event_lookup.py"
      via: "respx mocks the HTTP layer; HttpEventLookup is the production class under test"
      pattern: "respx"
---

<objective>
Lock in two of the four ROADMAP success criteria for Phase 6 via medium-fidelity integration tests:

- **SC#4 (Reconciler-consumer race)**: Run `settle_bets_for_event` and `cancel_bets_for_event` (and `_reconcile_event` → settle) concurrently against the same event_id. Assert exactly one winner; the other observes 0 rows. This is the FOR UPDATE SKIP LOCKED guarantee, end-to-end on real PG (not SQLite — SQLite would silently pass without ever exercising the lock).

- **SC#1 (Drop-publish recovery — fast path)**: Use `respx` to mock line-provider's HTTP surface. Drive the production `HttpEventLookup` (the same class lifespan wires) through `_reconcile_event`. Verify three branches:
  - LP returns 200 with `state=FINISHED_WIN` → bet flips to WON (`settled_via='reconciler'`).
  - LP returns 404 → bet flips to CANCELLED (`settled_via='reconciler'`).
  - LP returns 200 with `state=NEW` → bet stays PENDING.

  This is the "fast path" version of QA-08 / SC#5 — we mock LP because real-RMQ + real-LP e2e takes ~5s per scenario; this respx-based version runs in <1s.

Purpose: Plan 06-07 unit tests use a duck-typed `_FakeLookup` (CONTEXT.md D-08). That proves the decision tree is correct but does NOT prove the production HttpEventLookup wires correctly to a mocked HTTP transport. This plan closes that gap before Plan 06-10 spends testcontainers minutes on the real-RMQ e2e.

Output: 5 real test assertions across 2 files (replacing 5 Wave-0 stubs).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@src/bet_maker/jobs/reconciler.py
@src/bet_maker/facades/http_event_lookup.py
@src/bet_maker/interactors/settle_bets_for_event.py
@src/bet_maker/interactors/cancel_bets_for_event.py
@tests/bet_maker/test_settle.py
@tests/bet_maker/test_http_event_lookup.py
@tests/bet_maker/integration/test_reconciler_consumer_race.py
@tests/bet_maker/integration/test_reconciler_drop_publish.py
</context>

<interfaces>
Existing test fixtures available:
- `session_factory: async_sessionmaker[AsyncSession]` (session-scoped, testcontainers PG).
- `app: FastAPI` (session-scoped, lifespan-driven — exposes `app.state.line_provider_http_client` already mocked-friendly).
- `_auto_truncate` (autouse — per-test bets cleanup).

respx pattern (verified in `tests/bet_maker/test_http_event_lookup.py`):
```python
import respx
from httpx import Response

with respx.mock(base_url="http://line-provider:8000", assert_all_called=False) as router:
    router.get(f"/event/{event_id}").mock(
        return_value=Response(200, json={
            "event_id": str(event_id),
            "coefficient": "1.50",
            "deadline": "2030-01-01T00:00:00+00:00",
            "state": "FINISHED_WIN",
        })
    )
    # ... drive HttpEventLookup.get_event(event_id) ...
```

Note: `HttpEventLookup` uses the lifespan-pinned httpx.AsyncClient whose `base_url = settings.line_provider_base_url`. The test must use the SAME base_url for respx.mock, otherwise respx returns ConnectionError. In Phase 4 tests, base_url was `http://test` for the test client and `http://line-provider:8000` for the real settings. respx works against the http_client's effective URL — `http_client.base_url + path`.

Reconciler test pattern:
- Build a `_reconcile_event` invocation by reusing the `app.state.line_provider_http_client` and instantiating `HttpEventLookup` directly with reconciler params, OR by reading `app.state.reconciler_event_lookup` (already wired by Plan 06-08).
- Seed Bet rows via `session_factory.begin()` (same pattern as `tests/bet_maker/test_settle.py`).
- After `_reconcile_event` returns, query Bet rows to assert state transitions.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace consumer-race stub with 2 real tests (SC#4 — FOR UPDATE SKIP LOCKED)</name>
  <files>tests/bet_maker/integration/test_reconciler_consumer_race.py</files>
  <read_first>
    - tests/bet_maker/test_settle.py (existing pattern: `TestSettleConcurrent::test_concurrent_no_double_update` — direct template)
    - tests/bet_maker/interactors/test_cancel_bets_for_event.py (Plan 06-06 / `TestCancelConcurrent`)
    - src/bet_maker/jobs/reconciler.py (Plan 06-07 — confirm `_reconcile_event` signature)
    - tests/bet_maker/integration/test_reconciler_consumer_race.py (Wave-0 stub — 2 method names locked)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Testing D-22
  </read_first>
  <behavior>
    Two tests inside class `TestReconcilerConsumerRace`:

    - `test_concurrent_settle_consumer_and_reconciler_no_double_update`: Seed 3 PENDING bets on event_id A. Wrap `settle_bets_for_event(uow, event_id=A, terminal_state=FINISHED_WIN, settled_via='consumer')` (consumer path) and `_reconcile_event(sessionmaker, fake_lookup_returning_finished_win, A)` (reconciler path) in `asyncio.gather`. After the gather, assert all 3 bets are in BetStatus.WON; assert there are zero PENDING and zero double-rows. This is the SC#4 — concurrent settle path.

    - `test_for_update_skip_locked_one_winner_one_noop`: Seed 3 PENDING bets on event_id B. Wrap `settle_bets_for_event(... 'consumer')` and `cancel_bets_for_event(... 'reconciler')` in `asyncio.gather`. Assert exactly one interactor returned count=3 and the other count=0 (the strong form of R3 from `TestSettleConcurrent::test_concurrent_settled_via_attribution_is_single_pass`).

    Both tests use `session_factory` (testcontainers PG). The reconciler test seeds a custom `_FakeLookup` (duck-typed) so we do NOT need a running line-provider; the SC#4 contract is about PG concurrency, not HTTP.
  </behavior>
  <action>
    Replace `tests/bet_maker/integration/test_reconciler_consumer_race.py`:

    ```python
    """Integration: reconciler + consumer concurrent settle (Plan 06-09 / SC#4 / D-22)."""

    from __future__ import annotations

    import asyncio
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from uuid import UUID, uuid4

    import pytest
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from bet_maker.facades.event_lookup import EventSnapshot
    from bet_maker.facades.uow import AsyncUnitOfWork
    from bet_maker.interactors.cancel_bets_for_event import cancel_bets_for_event
    from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
    from bet_maker.jobs.reconciler import _reconcile_event
    from bet_maker.models.bet import Bet
    from bet_maker.schemas.bets import BetStatus
    from bet_maker.schemas.events import EventState
    from bet_maker.schemas.messages import EventTerminalState


    class _FakeLookup:
        def __init__(self, snapshot: EventSnapshot | None) -> None:
            self._snapshot = snapshot

        async def get_event(self, event_id: UUID) -> EventSnapshot | None:
            return self._snapshot


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerConsumerRace:
        async def test_concurrent_settle_consumer_and_reconciler_no_double_update(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            """SC#4: consumer settle + reconciler tick on same event_id ->
            exactly 3 bets in WON, zero PENDING."""
            event_id = uuid4()
            async with session_factory.begin() as session:
                for amt in ("10.00", "20.00", "30.00"):
                    session.add(Bet(event_id=event_id, amount=Decimal(amt)))

            lookup = _FakeLookup(
                EventSnapshot(
                    event_id=event_id,
                    deadline=datetime.now(timezone.utc) + timedelta(hours=1),
                    state=EventState.FINISHED_WIN,
                )
            )

            await asyncio.gather(
                settle_bets_for_event(
                    AsyncUnitOfWork(session_factory),
                    event_id=event_id,
                    terminal_state=EventTerminalState.FINISHED_WIN,
                    settled_via="consumer",
                ),
                _reconcile_event(session_factory, lookup, event_id),  # type: ignore[arg-type]
            )

            async with session_factory() as session:
                rows = (
                    (await session.execute(select(Bet).where(Bet.event_id == event_id)))
                    .scalars().all()
                )
            assert len(rows) == 3
            assert all(b.status == BetStatus.WON for b in rows)
            assert all(b.settled_at is not None for b in rows)

        async def test_for_update_skip_locked_one_winner_one_noop(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            """R3: settle vs cancel on same event_id -> exactly one returns
            count=3, the other count=0 (SKIP LOCKED + status filter)."""
            event_id = uuid4()
            async with session_factory.begin() as session:
                for amt in ("10.00", "20.00", "30.00"):
                    session.add(Bet(event_id=event_id, amount=Decimal(amt)))

            settle_r, cancel_r = await asyncio.gather(
                settle_bets_for_event(
                    AsyncUnitOfWork(session_factory),
                    event_id=event_id,
                    terminal_state=EventTerminalState.FINISHED_WIN,
                    settled_via="consumer",
                ),
                cancel_bets_for_event(
                    AsyncUnitOfWork(session_factory),
                    event_id=event_id,
                    cancelled_via="reconciler",
                ),
            )

            counts = sorted([settle_r.settled_count, cancel_r.cancelled_count])
            assert counts == [0, 3], (
                f"expected exactly one of settle/cancel to take all 3 rows, got {counts}"
            )
    ```

    Notes:
    - `_reconcile_event` is called with a duck-typed `_FakeLookup`; the cast `# type: ignore[arg-type]` is acceptable for tests (HttpEventLookup is the parameter type, FakeLookup has a structural-compatible `get_event` method).
    - The test does NOT depend on Plan 06-08 (lifespan wiring) — it uses `session_factory` directly.
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/integration/test_reconciler_consumer_race.py</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest -x -q tests/bet_maker/integration/test_reconciler_consumer_race.py` reports 2 passed
    - `grep -c "asyncio.gather" tests/bet_maker/integration/test_reconciler_consumer_race.py` >= 2
    - `grep -c "_reconcile_event" tests/bet_maker/integration/test_reconciler_consumer_race.py` >= 1
    - `grep -c "Wave-0 stub" tests/bet_maker/integration/test_reconciler_consumer_race.py` == 0
    - `uv run mypy tests/bet_maker/integration/` exits 0
    - `uv run ruff check tests/bet_maker/integration/` exits 0
  </acceptance_criteria>
  <done>2 SC#4 tests green; SKIP LOCKED contract proven under real PG concurrency.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Replace drop-publish stub with 3 real respx-mocked tests (SC#1 — drop publish recovery)</name>
  <files>tests/bet_maker/integration/test_reconciler_drop_publish.py</files>
  <read_first>
    - tests/bet_maker/test_http_event_lookup.py (existing respx patterns — direct template; e.g., `TestHttpEventLookupGetEvent` uses `respx.mock(base_url=...)` context manager)
    - src/bet_maker/facades/http_event_lookup.py (production HttpEventLookup — same class under test here)
    - src/bet_maker/jobs/reconciler.py (Plan 06-07 — `_reconcile_event` invocation shape)
    - tests/bet_maker/integration/test_reconciler_drop_publish.py (Wave-0 stub — 3 method names locked)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-02 + §Testing D-23 Scenario 2
  </read_first>
  <behavior>
    Three tests in class `TestReconcilerDropPublish`. All three use `respx.mock` to substitute LP's HTTP surface and drive a real `HttpEventLookup` through `_reconcile_event`. Real PG, fake LP. Each test:
    1. Seeds a PENDING bet for a fresh event_id.
    2. Configures respx to return the right response for `GET /event/{event_id}`.
    3. Instantiates `HttpEventLookup` against an httpx.AsyncClient bound to the same base_url.
    4. Calls `await _reconcile_event(session_factory, lookup, event_id)`.
    5. Asserts the final Bet status.

    - `test_respx_mocked_lp_terminal_state_triggers_reconciler_settle`: LP returns 200 + state=FINISHED_WIN → Bet → WON.
    - `test_respx_mocked_lp_404_triggers_reconciler_cancel`: LP returns 404 → Bet → CANCELLED.
    - `test_reconciler_skip_when_lp_still_returns_new`: LP returns 200 + state=NEW → Bet stays PENDING.
  </behavior>
  <action>
    Replace `tests/bet_maker/integration/test_reconciler_drop_publish.py`:

    ```python
    """Integration: respx-mocked LP drives reconciler decision branches
    (Plan 06-09 / SC#1 / D-02 / D-23 Scenario 2)."""

    from __future__ import annotations

    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from uuid import uuid4

    import httpx
    import pytest
    import respx
    from httpx import Response
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from bet_maker.facades.http_event_lookup import HttpEventLookup
    from bet_maker.jobs.reconciler import _reconcile_event
    from bet_maker.models.bet import Bet
    from bet_maker.schemas.bets import BetStatus

    _LP_BASE_URL = "http://line-provider:8000"


    def _make_lookup(http_client: httpx.AsyncClient) -> HttpEventLookup:
        return HttpEventLookup(
            http_client=http_client,
            attempts=2,
            max_backoff=0.1,
        )


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerDropPublish:
        async def test_respx_mocked_lp_terminal_state_triggers_reconciler_settle(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))

            with respx.mock(base_url=_LP_BASE_URL, assert_all_called=False) as mock_router:
                mock_router.get(f"/event/{event_id}").mock(
                    return_value=Response(
                        200,
                        json={
                            "event_id": str(event_id),
                            "coefficient": "1.50",
                            "deadline": (
                                datetime.now(timezone.utc) + timedelta(hours=1)
                            ).isoformat(),
                            "state": "FINISHED_WIN",
                        },
                    )
                )
                async with httpx.AsyncClient(
                    base_url=_LP_BASE_URL, timeout=5.0
                ) as http_client:
                    await _reconcile_event(session_factory, _make_lookup(http_client), event_id)

            async with session_factory() as session:
                bet = (
                    await session.execute(select(Bet).where(Bet.event_id == event_id))
                ).scalar_one()
            assert bet.status == BetStatus.WON
            assert bet.settled_via == "reconciler"

        async def test_respx_mocked_lp_404_triggers_reconciler_cancel(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))

            with respx.mock(base_url=_LP_BASE_URL, assert_all_called=False) as mock_router:
                mock_router.get(f"/event/{event_id}").mock(return_value=Response(404))
                async with httpx.AsyncClient(
                    base_url=_LP_BASE_URL, timeout=5.0
                ) as http_client:
                    await _reconcile_event(session_factory, _make_lookup(http_client), event_id)

            async with session_factory() as session:
                bet = (
                    await session.execute(select(Bet).where(Bet.event_id == event_id))
                ).scalar_one()
            assert bet.status == BetStatus.CANCELLED
            assert bet.settled_via == "reconciler"

        async def test_reconciler_skip_when_lp_still_returns_new(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))

            with respx.mock(base_url=_LP_BASE_URL, assert_all_called=False) as mock_router:
                mock_router.get(f"/event/{event_id}").mock(
                    return_value=Response(
                        200,
                        json={
                            "event_id": str(event_id),
                            "coefficient": "1.50",
                            "deadline": (
                                datetime.now(timezone.utc) + timedelta(hours=1)
                            ).isoformat(),
                            "state": "NEW",
                        },
                    )
                )
                async with httpx.AsyncClient(
                    base_url=_LP_BASE_URL, timeout=5.0
                ) as http_client:
                    await _reconcile_event(session_factory, _make_lookup(http_client), event_id)

            async with session_factory() as session:
                bet = (
                    await session.execute(select(Bet).where(Bet.event_id == event_id))
                ).scalar_one()
            assert bet.status == BetStatus.PENDING  # unchanged
            assert bet.settled_via is None
    ```

    Notes:
    - Each test uses its own throwaway `httpx.AsyncClient` + `HttpEventLookup` — does NOT use the lifespan-pinned singleton (which would have respx interference issues since other tests run against the same `app` session).
    - `assert_all_called=False` allows respx not to fail if retries cause additional calls.
    - The base_url string matches `HttpEventLookup.get_event` issuing relative `/event/{id}`; respx's `base_url` filter must match exactly.
    - `attempts=2, max_backoff=0.1` keeps these tests fast.
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/integration/test_reconciler_drop_publish.py</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest -x -q tests/bet_maker/integration/test_reconciler_drop_publish.py` reports 3 passed
    - `grep -c "respx.mock" tests/bet_maker/integration/test_reconciler_drop_publish.py` == 3
    - `grep -c "_reconcile_event" tests/bet_maker/integration/test_reconciler_drop_publish.py` == 3
    - `grep -c "Wave-0 stub" tests/bet_maker/integration/test_reconciler_drop_publish.py` == 0
    - `uv run mypy tests/bet_maker/integration/` exits 0
    - `uv run ruff check tests/bet_maker/integration/` exits 0
    - Combined integration run: `uv run pytest -x -q tests/bet_maker/integration/` reports 5 passed (2 from race + 3 from drop-publish).
  </acceptance_criteria>
  <done>3 respx-mocked tests green; reconciler decision tree exercised through production HttpEventLookup.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| respx mock → HttpEventLookup → reconciler | Outbound HTTP under test; mock fidelity determines whether the real path is exercised |
| concurrent asyncio.gather → PG row locks | Real concurrency on real PG; mistake in lock semantics would silently pass under SQLite |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-09-01 | Tampering (false-pass on SQLite) | concurrent race tests | mitigate | Real PG via testcontainers — SC#4 cannot pass under SQLite (no SKIP LOCKED) |
| T-06-09-02 | Tampering (respx mocking the wrong path) | drop-publish tests | mitigate | base_url + relative path are explicit constants; test 2 asserts CANCELLED only if 404 is actually delivered to the production class |
| T-06-09-03 | Information Disclosure | event_id in respx logs | accept | event_id is non-secret |
</threat_model>

<verification>
- `uv run pytest -x -q tests/bet_maker/integration/` exits 0 (5 tests).
- `uv run mypy tests/` exits 0.
- `uv run ruff check tests/` exits 0.
</verification>

<success_criteria>
- SC#4 (consumer-vs-reconciler race) has 2 passing tests.
- SC#1 fast-path (respx drop-publish recovery) has 3 passing tests.
- All tests use real PG; no SQLite shortcuts.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-09-SUMMARY.md` with the 5 test outcomes and a one-line confirmation that real PG was exercised.
</output>

## Decision Coverage

- D-22: Concurrent integration test `tests/bet_maker/integration/test_reconciler_consumer_race.py` against testcontainers PG — reconciler + consumer racing the same `event_id` produce exactly one settled status (FOR UPDATE SKIP LOCKED).
