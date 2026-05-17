---
phase: 05
plan: 04
type: execute
wave: 1
depends_on: [01, 02, 03]
files_modified:
  - src/bet_maker/interactors/settle_bets_for_event.py
  - tests/bet_maker/test_settle.py
autonomous: true
requirements: [BM-10]
must_haves:
  truths:
    - "settle_bets_for_event(uow, event_id, terminal_state, settled_via) returns SettleResult; idempotent on redelivery"
    - "Second call against the same event_id returns settled_count=0 (R3 / D-12 / D-15 / D-16)"
    - "Concurrent settle: two callers against the same event_id together settle the rows exactly once with no double-update and no deadlock"
    - "PG func.now() fills settled_at server-side in the UPDATE statement (D-14)"
    - "FOR UPDATE SKIP LOCKED is the only locking primitive; READ COMMITTED isolation untouched (D-18)"
  artifacts:
    - path: "src/bet_maker/interactors/settle_bets_for_event.py"
      provides: "settle interactor with keyword-only sig and SettleResult return"
      contains: "settle_bets_for_event"
  key_links:
    - from: "src/bet_maker/interactors/settle_bets_for_event.py"
      to: "src/bet_maker/repositories/bets.py::get_pending_locked"
      via: "async with uow"
      pattern: "uow.bets.get_pending_locked"
    - from: "src/bet_maker/interactors/settle_bets_for_event.py"
      to: "PG func.now()"
      via: "update().values(settled_at=func.now(), settled_via=settled_via, status=new_status)"
      pattern: "func.now()"
---

<objective>
Build the heart of Phase 5's Core Value: the idempotent settle interactor. Plan 05 consumer + Plan 06 publisher + Phase 6 reconciler all call this exact function. It is the SINGLE source of "ставка переходит из PENDING в WON/LOST".

Signature (D-17):
```python
async def settle_bets_for_event(
    uow: AsyncUnitOfWork,
    *,
    event_id: UUID,
    terminal_state: EventTerminalState,
    settled_via: Literal["consumer", "reconciler"],
) -> SettleResult: ...
```

Pitfalls guarded:
- **R3 (R/W race):** delegated to `get_pending_locked` (Plan 03).
- **R9/R12 / Anti-Pattern 2 (publish-before-commit):** no broker call inside this function — pure DB code.
- **A2 (session sharing across tasks):** each call gets its own `AsyncUnitOfWork` (caller responsibility); inside, one session, one transaction.
- **A1 (lazy-load after commit):** no ORM reads after `async with uow:` exits; bet ids captured before UPDATE.
- **Decimal precision:** untouched (status flip only, no amount math).

Integration test scenario (real PG, F6's predecessor):
1. Insert 3 PENDING bets with same event_id.
2. Run `asyncio.gather(settle_consumer(), settle_reconciler())` — both against same event_id.
3. Sum of `result.settled_count` across both = 3; PG row count of PENDING for this event = 0; row count of (WON or LOST) for this event = 3.

Output: 1 new interactor file; 1 fully-implemented test module (replacing Plan 01 stub).
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
@src/bet_maker/interactors/place_bet.py
@src/bet_maker/facades/uow.py
@src/bet_maker/models/bet.py
@src/bet_maker/schemas/bets.py
@src/bet_maker/schemas/messages.py
@src/bet_maker/schemas/settle.py
@src/bet_maker/repositories/bets.py

<interfaces>
<!-- Phase 5 contracts established in Plans 02 and 03 -->

From src/bet_maker/schemas/settle.py (created by Plan 02):
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

From src/bet_maker/schemas/messages.py (created by Plan 02):
```python
class EventTerminalState(str, Enum):
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"
```

From src/bet_maker/repositories/bets.py (extended by Plan 03):
```python
async def get_pending_locked(self, event_id: UUID) -> list[Bet]: ...
```

From src/bet_maker/facades/uow.py (Phase 3, unchanged):
```python
class AsyncUnitOfWork:
    bets: BetRepository
    session: AsyncSession
    async def __aenter__(self) -> Self: ...
    async def __aexit__(...) -> None: ...  # auto-commit or auto-rollback
```

From src/config/time.py (existing utility for utc_now) — confirm via grep before importing.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement settle_bets_for_event interactor</name>
  <read_first>
    - src/bet_maker/interactors/place_bet.py (UoW interactor pattern reference)
    - src/bet_maker/facades/uow.py
    - src/bet_maker/schemas/settle.py (created by Plan 02)
    - src/bet_maker/schemas/messages.py (created by Plan 02)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-12 through D-18
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/interactors/settle_bets_for_event.py`
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §Idempotency & SKIP LOCKED Pattern
  </read_first>
  <behavior>
    - Calling on a known event_id with 3 PENDING bets and `terminal_state=FINISHED_WIN, settled_via="consumer"`: returns `SettleResult(settled_count=3, settled_bet_ids=[...], settled_via="consumer", terminal_state=FINISHED_WIN)`; PG rows show 3 bets with status=WON, settled_at NOT NULL, settled_via='consumer'.
    - Calling on an event_id with no PENDING bets: returns `SettleResult(settled_count=0, settled_bet_ids=[], ...)`; structlog emits `settle.noop` info event with event_id + reason="no PENDING bets" + settled_via.
    - Calling on an event_id with only WON bets (already settled): returns `SettleResult(settled_count=0, settled_bet_ids=[], ...)` — same as no-PENDING path (D-15/D-16).
    - When `terminal_state=FINISHED_LOSE`: rows flip to `BetStatus.LOST` (not WON).
    - Second call on same event_id: returns `settled_count=0` because first call already flipped status (idempotency guarantee, R3).
  </behavior>
  <action>
    Create `src/bet_maker/interactors/settle_bets_for_event.py`. Use the EXACT pattern from PATTERNS.md §`src/bet_maker/interactors/settle_bets_for_event.py`.

    File contents:

    ```python
    """settle_bets_for_event — idempotent settle interactor for Phase 5/6 (D-17).

    Called by:
    - Plan 05 RabbitMQ consumer handler (settled_via='consumer')
    - Phase 6 reconciliation job (settled_via='reconciler')

    Idempotency (R3 / D-12 / D-15):
    - BetRepository.get_pending_locked() filters by status=PENDING + locks via
      FOR UPDATE SKIP LOCKED. Second caller on same event_id: 0 rows -> 0-row
      UPDATE -> structlog 'settle.noop' info -> SettleResult(settled_count=0).
    - No 'consumed_events' table — status filter is the single source of truth.

    Atomicity (R2 / F4):
    - Whole operation inside `async with uow:`; UoW commits on clean exit,
      rolls back on exception. Caller acks ONLY after this returns successfully.

    Server-side timestamp (D-14):
    - settled_at value in UPDATE statement is PG func.now() — same clock as
      created_at/updated_at. Python-side SettleResult.settled_at is a freshly
      taken utc_now() snapshot for logging/return purposes; the canonical
      timestamp lives in PG.

    Pitfalls guarded:
    - R9/R12 / Anti-Pattern 2: no broker.publish call here (publishing happens
      in line-provider; this is bet-maker side, settle only).
    - A1: bet_ids captured BEFORE the UPDATE; no lazy-load after UoW commit.
    """
    from __future__ import annotations

    from datetime import datetime, timezone
    from typing import Literal
    from uuid import UUID

    import structlog
    from sqlalchemy import func, update

    from bet_maker.facades.uow import AsyncUnitOfWork
    from bet_maker.models.bet import Bet
    from bet_maker.schemas.bets import BetStatus
    from bet_maker.schemas.messages import EventTerminalState
    from bet_maker.schemas.settle import SettleResult


    _TERMINAL_TO_STATUS: dict[EventTerminalState, BetStatus] = {
        EventTerminalState.FINISHED_WIN: BetStatus.WON,
        EventTerminalState.FINISHED_LOSE: BetStatus.LOST,
    }


    async def settle_bets_for_event(
        uow: AsyncUnitOfWork,
        *,
        event_id: UUID,
        terminal_state: EventTerminalState,
        settled_via: Literal["consumer", "reconciler"],
    ) -> SettleResult:
        log = structlog.get_logger()
        new_status = _TERMINAL_TO_STATUS[terminal_state]
        async with uow:
            bets = await uow.bets.get_pending_locked(event_id)
            settled_at = datetime.now(timezone.utc)
            if not bets:
                log.info(
                    "settle.noop",
                    event_id=str(event_id),
                    reason="no PENDING bets",
                    settled_via=settled_via,
                )
                return SettleResult(
                    event_id=event_id,
                    terminal_state=terminal_state,
                    settled_count=0,
                    settled_bet_ids=[],
                    settled_via=settled_via,
                    settled_at=settled_at,
                )

            bet_ids = [b.id for b in bets]
            await uow.session.execute(
                update(Bet)
                .where(Bet.id.in_(bet_ids))
                .values(
                    status=new_status,
                    settled_at=func.now(),
                    settled_via=settled_via,
                )
            )
            log.info(
                "settle.committed",
                event_id=str(event_id),
                settled_count=len(bet_ids),
                settled_bet_ids=[str(bid) for bid in bet_ids],
                settled_via=settled_via,
                new_status=new_status.value,
            )
            return SettleResult(
                event_id=event_id,
                terminal_state=terminal_state,
                settled_count=len(bet_ids),
                settled_bet_ids=bet_ids,
                settled_via=settled_via,
                settled_at=settled_at,
            )
    ```

    Do NOT add an early-return outside `async with uow:` (the lock must be acquired before deciding it's a no-op). Do NOT import `from sqlalchemy import select` — repository encapsulates SELECT. Do NOT call `await uow.session.flush()` between SELECT and UPDATE — they share the same session/transaction.
  </action>
  <verify>
    <automated>uv run python -c "import inspect; from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event; sig = inspect.signature(settle_bets_for_event); params = list(sig.parameters); assert params == ['uow', 'event_id', 'terminal_state', 'settled_via'], params; assert all(sig.parameters[p].kind.name == 'KEYWORD_ONLY' for p in ['event_id', 'terminal_state', 'settled_via']); print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/bet_maker/interactors/settle_bets_for_event.py`
    - `grep -q 'async def settle_bets_for_event' src/bet_maker/interactors/settle_bets_for_event.py`
    - `grep -q 'async with uow:' src/bet_maker/interactors/settle_bets_for_event.py`
    - `grep -q 'await uow.bets.get_pending_locked(event_id)' src/bet_maker/interactors/settle_bets_for_event.py`
    - `grep -q 'settled_at=func.now()' src/bet_maker/interactors/settle_bets_for_event.py`
    - `grep -q 'settled_via=settled_via' src/bet_maker/interactors/settle_bets_for_event.py`
    - `grep -q '"settle.noop"' src/bet_maker/interactors/settle_bets_for_event.py`
    - `grep -q '"settle.committed"' src/bet_maker/interactors/settle_bets_for_event.py`
    - `grep -c "broker\|publish" src/bet_maker/interactors/settle_bets_for_event.py | grep -v '^#'` returns 0 — Anti-Pattern 2 guarded (no publish in settle interactor)
    - `uv run mypy src/bet_maker/interactors/settle_bets_for_event.py` exits 0
    - `uv run ruff check src/bet_maker/interactors/settle_bets_for_event.py` exits 0
  </acceptance_criteria>
  <done>Interactor importable; mypy strict-clean; structure matches PATTERNS.md analog; no broker call inside.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Fully implement tests/bet_maker/test_settle.py (idempotency + concurrent settle race)</name>
  <read_first>
    - tests/bet_maker/test_settle.py (current Wave 0 stub)
    - tests/bet_maker/test_repositories.py (`TestRuntime` pattern reference)
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §Concurrent consumer + reconciler test recipe
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`tests/bet_maker/test_settle.py`
  </read_first>
  <behavior>
    Replace the Plan 01 stub with these test classes/methods:

    Class `TestSettleHappyPath`:
    - `test_settles_three_pending_bets_to_won_when_terminal_win`: insert 3 PENDING for event_id; call interactor with FINISHED_WIN, settled_via='consumer'; assert returned `settled_count == 3`, all 3 ids in `settled_bet_ids`; query DB confirms 3 rows status=WON, settled_at NOT NULL, settled_via='consumer'.
    - `test_settles_to_lost_when_terminal_lose`: same but `FINISHED_LOSE`; rows go to LOST.

    Class `TestSettleNoop`:
    - `test_idempotent_second_call_returns_zero`: insert 2 PENDING for event_id; first call returns settled_count=2; second call on same event_id returns settled_count=0 (rows already WON/LOST).
    - `test_noop_when_no_pending_for_event`: insert 1 WON bet for event_id; call settle; returns settled_count=0, empty settled_bet_ids.
    - `test_noop_when_event_has_only_other_events_bets`: insert 1 PENDING for event_A; call settle on event_B; settled_count=0; event_A still PENDING.

    Class `TestSettleConcurrent` (R3 — RESEARCH §recipe):
    - `test_concurrent_no_double_update`: insert 3 PENDING for event_id; build two `AsyncUnitOfWork` from same sessionmaker; `asyncio.gather(settle_consumer(), settle_reconciler())`; assert sum of settled_count across the two results == 3; PG row count of PENDING == 0; row count of WON == 3; settled_via column shows ONE pass for 'consumer' and ZERO or 'reconciler' (one task got all rows, other got none).
    - `test_concurrent_settled_via_attribution_is_single_pass`: same scenario, but additionally assert that exactly ONE of the two task results has `settled_count > 0`, the other has `settled_count == 0`. This is the strong R3 assertion.

    Class `TestSettleResultShape`:
    - `test_settle_result_is_frozen`: attempting to mutate `result.settled_count` raises `pydantic.ValidationError`.
    - `test_settle_result_settled_at_is_utc_aware`: `result.settled_at.tzinfo is not None`.
  </behavior>
  <action>
    Overwrite `tests/bet_maker/test_settle.py` with the full test suite. Use the EXACT fixture pattern from `tests/bet_maker/test_repositories.py` (session_factory + truncate_bets autouse).

    ```python
    """settle_bets_for_event interactor tests — Plan 05-04 (D-12 .. D-18).

    Covers (per VALIDATION.md task IDs 05-04-01, 05-04-02):
    - Happy path (settle_count == row count)
    - Idempotency (second call on same event_id is 0-row noop)
    - Concurrent settle (R3 / consumer-vs-reconciler race)
    - SettleResult shape (frozen, UTC-aware settled_at)

    All tests run against real PG testcontainer (QA-07). SQLite would not
    support FOR UPDATE SKIP LOCKED — this entire file's coverage would be
    fictional under SQLite.
    """
    from __future__ import annotations

    import asyncio
    from decimal import Decimal
    from uuid import uuid4

    import pytest
    from pydantic import ValidationError
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from bet_maker.facades.uow import AsyncUnitOfWork
    from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
    from bet_maker.models.bet import Bet
    from bet_maker.schemas.bets import BetStatus
    from bet_maker.schemas.messages import EventTerminalState


    @pytest.mark.asyncio(loop_scope="session")
    class TestSettleHappyPath:
        async def test_settles_three_pending_bets_to_won_when_terminal_win(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                for amt in ("10.00", "20.00", "30.00"):
                    session.add(Bet(event_id=event_id, amount=Decimal(amt)))
            result = await settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            )
            assert result.settled_count == 3
            assert len(result.settled_bet_ids) == 3
            assert result.settled_via == "consumer"

            async with session_factory() as session:
                rows = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalars().all()
            assert len(rows) == 3
            assert all(b.status == BetStatus.WON for b in rows)
            assert all(b.settled_at is not None for b in rows)
            assert all(b.settled_via == "consumer" for b in rows)

        async def test_settles_to_lost_when_terminal_lose(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
            result = await settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_LOSE,
                settled_via="consumer",
            )
            assert result.settled_count == 1
            async with session_factory() as session:
                bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
            assert bet.status == BetStatus.LOST


    @pytest.mark.asyncio(loop_scope="session")
    class TestSettleNoop:
        async def test_idempotent_second_call_returns_zero(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
                session.add(Bet(event_id=event_id, amount=Decimal("20.00")))

            first = await settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            )
            second = await settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            )
            assert first.settled_count == 2
            assert second.settled_count == 0
            assert second.settled_bet_ids == []

        async def test_noop_when_no_pending_for_event(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                session.add(Bet(event_id=event_id, amount=Decimal("10.00"), status=BetStatus.WON))
            result = await settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            )
            assert result.settled_count == 0
            assert result.settled_bet_ids == []

        async def test_noop_when_event_has_only_other_events_bets(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_a, event_b = uuid4(), uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                session.add(Bet(event_id=event_a, amount=Decimal("10.00")))
            result = await settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_b,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            )
            assert result.settled_count == 0
            async with session_factory() as session:
                bet = (await session.execute(select(Bet).where(Bet.event_id == event_a))).scalar_one()
            assert bet.status == BetStatus.PENDING  # Untouched.


    @pytest.mark.asyncio(loop_scope="session")
    class TestSettleConcurrent:
        async def test_concurrent_no_double_update(
            self, session_factory: async_sessionmaker
        ) -> None:
            """R3 / D-12: consumer + reconciler against same event_id together
            settle exactly once. SKIP LOCKED -> one task gets all rows, the
            other gets 0 rows."""
            event_id = uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                for amt in ("10.00", "20.00", "30.00"):
                    session.add(Bet(event_id=event_id, amount=Decimal(amt)))

            r1, r2 = await asyncio.gather(
                settle_bets_for_event(
                    AsyncUnitOfWork(session_factory),
                    event_id=event_id,
                    terminal_state=EventTerminalState.FINISHED_WIN,
                    settled_via="consumer",
                ),
                settle_bets_for_event(
                    AsyncUnitOfWork(session_factory),
                    event_id=event_id,
                    terminal_state=EventTerminalState.FINISHED_WIN,
                    settled_via="reconciler",
                ),
            )
            assert r1.settled_count + r2.settled_count == 3
            async with session_factory() as session:
                pending = (await session.execute(
                    select(Bet).where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
                )).scalars().all()
                settled = (await session.execute(
                    select(Bet).where(Bet.event_id == event_id, Bet.status == BetStatus.WON)
                )).scalars().all()
            assert len(pending) == 0
            assert len(settled) == 3

        async def test_concurrent_settled_via_attribution_is_single_pass(
            self, session_factory: async_sessionmaker
        ) -> None:
            """Strong R3 form: exactly ONE task settled rows, the other got 0."""
            event_id = uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                for amt in ("10.00", "20.00", "30.00"):
                    session.add(Bet(event_id=event_id, amount=Decimal(amt)))

            r1, r2 = await asyncio.gather(
                settle_bets_for_event(
                    AsyncUnitOfWork(session_factory),
                    event_id=event_id,
                    terminal_state=EventTerminalState.FINISHED_WIN,
                    settled_via="consumer",
                ),
                settle_bets_for_event(
                    AsyncUnitOfWork(session_factory),
                    event_id=event_id,
                    terminal_state=EventTerminalState.FINISHED_WIN,
                    settled_via="reconciler",
                ),
            )
            counts = sorted([r1.settled_count, r2.settled_count])
            assert counts == [0, 3], (
                f"expected exactly one task to settle all 3 rows, got {counts}"
            )


    @pytest.mark.asyncio(loop_scope="session")
    class TestSettleResultShape:
        async def test_settle_result_is_frozen(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_id = uuid4()
            result = await settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            )
            with pytest.raises(ValidationError):
                result.settled_count = 999  # type: ignore[misc]

        async def test_settle_result_settled_at_is_utc_aware(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_id = uuid4()
            result = await settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            )
            assert result.settled_at.tzinfo is not None
    ```
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker/test_settle.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/bet_maker/test_settle.py -x -q` exits 0 with 9 tests passed
    - `grep -q 'class TestSettleHappyPath' tests/bet_maker/test_settle.py`
    - `grep -q 'class TestSettleNoop' tests/bet_maker/test_settle.py`
    - `grep -q 'class TestSettleConcurrent' tests/bet_maker/test_settle.py`
    - `grep -q 'class TestSettleResultShape' tests/bet_maker/test_settle.py`
    - `grep -q 'test_concurrent_no_double_update' tests/bet_maker/test_settle.py`
    - `grep -q 'asyncio.gather' tests/bet_maker/test_settle.py`
    - `grep -q 'pytest.skip("Wave 0 stub' tests/bet_maker/test_settle.py` returns EMPTY (stub removed)
    - `uv run mypy tests/bet_maker/test_settle.py` exits 0
    - `uv run ruff check tests/bet_maker/test_settle.py` exits 0
  </acceptance_criteria>
  <done>9 settle tests pass against real PG testcontainer; idempotency + concurrent race proven; R3 closed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Concurrent settle paths | Consumer (Plan 05) and reconciler (Phase 6) may race against the same event_id |
| DB UPDATE statement | Sole write path for bet finalisation |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-04-01 | Tampering | Double-update via consumer + reconciler race | mitigate | `with_for_update(skip_locked=True) + WHERE status='PENDING'` (delegated to Plan 03 repo); Task 2 TestSettleConcurrent proves exactly-once attribution. |
| T-05-04-02 | Elevation of privilege | settled_via field could be arbitrary text in DB | mitigate | Function parameter typed `Literal["consumer", "reconciler"]`; mypy strict enforces at call site; only two known callers (Plan 05 + Phase 6). |
| T-05-04-03 | Denial of service | UPDATE on millions of rows holds locks too long | accept | Per-event_id UPDATE; cardinality bounded by number of bets on one match. Production-scale concerns out of scope for test task. |
| T-05-04-04 | Repudiation | settled_at not recorded; cannot audit | mitigate | `settled_at = func.now()` in UPDATE; column is non-NULL after settle; preserved in DB for audit. |
| T-05-04-05 | Information disclosure | structlog `settle.committed` log includes bet ids | accept | Bet ids are UUIDs (no PII); consistent with existing `place_bet.created` log convention. |
</threat_model>

<verification>
- `uv run pytest tests/bet_maker/test_settle.py -x -q` exits 0 with 9 passes
- `uv run pytest -q` exits 0 (no regressions in full suite — settle interactor not yet wired anywhere else)
- `uv run mypy src tests` exits 0
- `uv run ruff check src tests` exits 0
- `grep -c "broker\|publish" src/bet_maker/interactors/settle_bets_for_event.py | grep -v '^#'` returns 0 (Anti-Pattern 2)
</verification>

<success_criteria>
- Interactor returns `SettleResult` with correct count, ids, and timestamp
- Idempotent across re-invocations (second call returns settled_count=0)
- Concurrent invocations against same event_id produce exactly one settle pass (R3)
- 9 tests in test_settle.py pass against real PG testcontainer
- No regression in existing repository / migration / route tests
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-04-settle-interactor-SUMMARY.md` documenting: interactor file path, test counts (TestSettleHappyPath:2, TestSettleNoop:3, TestSettleConcurrent:2, TestSettleResultShape:2), and a one-paragraph proof of R3 closure (single-pass attribution in concurrent test).
</output>
