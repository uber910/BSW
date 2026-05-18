---
phase: 06-reconciliation-job
plan: 06
type: execute
wave: 2
depends_on: [03, 05]
files_modified:
  - src/bet_maker/schemas/settle.py
  - src/bet_maker/interactors/cancel_bets_for_event.py
  - tests/bet_maker/interactors/test_cancel_bets_for_event.py
autonomous: true
requirements: [BM-12]
tags: [interactor, cancel, idempotent, uow, for-update-skip-locked]

must_haves:
  truths:
    - "CancelResult Pydantic DTO exists, frozen, extra=forbid, no terminal_state field"
    - "cancel_bets_for_event(uow, *, event_id, cancelled_via) returns CancelResult"
    - "Happy path: PENDING bets → CANCELLED with settled_at=func.now(), settled_via='reconciler'"
    - "Idempotent: second call returns cancelled_count=0 (status filter + SKIP LOCKED)"
    - "Concurrent with settle: exactly one of the two interactors flips the rows"
    - "Uses get_pending_locked (FOR UPDATE SKIP LOCKED + status='PENDING')"
    - "Interactor body is async with uow: ... — no manual commit"
  artifacts:
    - path: "src/bet_maker/schemas/settle.py"
      provides: "CancelResult DTO sibling to SettleResult"
      contains: "class CancelResult"
    - path: "src/bet_maker/interactors/cancel_bets_for_event.py"
      provides: "Idempotent cancel interactor"
      contains: "cancel_bets_for_event"
    - path: "tests/bet_maker/interactors/test_cancel_bets_for_event.py"
      provides: "9 real test assertions replacing the Wave-0 stub"
      contains: "TestCancelHappyPath"
  key_links:
    - from: "src/bet_maker/interactors/cancel_bets_for_event.py"
      to: "src/bet_maker/repositories/bets.py::get_pending_locked"
      via: "interactor calls uow.bets.get_pending_locked(event_id) inside async with uow"
      pattern: "uow\\.bets\\.get_pending_locked"
    - from: "src/bet_maker/interactors/cancel_bets_for_event.py"
      to: "src/bet_maker/jobs/reconciler.py (Plan 06-07)"
      via: "reconciler calls cancel_bets_for_event on the 404 branch"
      pattern: "cancel_bets_for_event"
---

<objective>
Implement the cancel-interactor — the 404 branch of the reconciler decision tree (CONTEXT.md D-02/D-04). When line-provider returns 404 for an event_id, the event was deleted or LP was recreated and the bet cannot be settled normally; the reconciler flips the affected PENDING bets to `BetStatus.CANCELLED` with `settled_at` / `settled_via='reconciler'`.

The interactor is the byte-for-byte sibling of `settle_bets_for_event` (Phase 5), differing only in:
- Output DTO is `CancelResult` (no `terminal_state` — cancellation has no outcome).
- New status is `BetStatus.CANCELLED` (not WON/LOST).
- `cancelled_via` is `Literal["reconciler"]` (one value today, extensible).
- Logging namespace: `cancel.committed` / `cancel.noop` (mirrors settle.committed / settle.noop).

Idempotency mechanism is identical to settle: `BetRepository.get_pending_locked(event_id)` returns `[]` when called twice in a row, so the second call short-circuits to a 0-row no-op. Concurrent settle vs cancel against the same event_id is also safe — `FOR UPDATE SKIP LOCKED` + `WHERE status='PENDING'` guarantees one of the two interactors gets all the rows and the other gets `[]`.

Output: One new DTO class, one new interactor module (~50 lines), 9 real test assertions replacing the Wave-0 stub.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@.planning/phases/06-reconciliation-job/06-RESEARCH.md
@src/bet_maker/interactors/settle_bets_for_event.py
@src/bet_maker/schemas/settle.py
@src/bet_maker/repositories/bets.py
@src/bet_maker/models/bet.py
@src/bet_maker/schemas/bets.py
@src/bet_maker/facades/uow.py
@tests/bet_maker/test_settle.py
@tests/bet_maker/interactors/test_cancel_bets_for_event.py
</context>

<interfaces>
Existing `src/bet_maker/schemas/settle.py` shape (do NOT delete `SettleResult`):
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

Reference implementation pattern (`src/bet_maker/interactors/settle_bets_for_event.py`):
- `async with uow:` wraps the entire mutation.
- `bets = await uow.bets.get_pending_locked(event_id)` (SELECT ... FOR UPDATE SKIP LOCKED).
- Noop branch returns DTO with count=0.
- Mutation via `uow.session.execute(update(Bet).where(Bet.id.in_(bet_ids)).values(...))`.
- `settled_at=func.now()` server-side; Python-side `datetime.now(timezone.utc)` for DTO.
- Logs `settle.committed` / `settle.noop` via structlog at info level.

New `CancelResult` shape (CONTEXT.md D-04 verbatim, no `terminal_state`):
```python
class CancelResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: UUID
    cancelled_count: int
    cancelled_bet_ids: list[UUID]
    cancelled_via: Literal["reconciler"]
    cancelled_at: datetime
```

Interactor signature (CONTEXT.md D-04):
```python
async def cancel_bets_for_event(
    uow: AsyncUnitOfWork,
    *,
    event_id: UUID,
    cancelled_via: Literal["reconciler"],
) -> CancelResult:
```
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add CancelResult DTO to schemas/settle.py</name>
  <files>src/bet_maker/schemas/settle.py</files>
  <read_first>
    - src/bet_maker/schemas/settle.py (existing SettleResult — copy the model_config, frozen, extra=forbid)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-04 (DTO shape verbatim)
    - .planning/phases/06-reconciliation-job/06-RESEARCH.md §Pattern 5 (CancelResult template)
  </read_first>
  <behavior>
    - `CancelResult` is importable from `bet_maker.schemas.settle`.
    - `CancelResult` is frozen (mutation raises `ValidationError`).
    - `CancelResult` uses `extra="forbid"` (unknown field on construction raises `ValidationError`).
    - `cancelled_via: Literal["reconciler"]` — only "reconciler" accepted; other strings raise `ValidationError`.
    - `cancelled_at: datetime` — must be tz-aware when set from the interactor (Python `datetime.now(timezone.utc)`).
    - `SettleResult` is UNCHANGED.
  </behavior>
  <action>
    Edit `src/bet_maker/schemas/settle.py`. After the existing `SettleResult` class, add a new sibling class `CancelResult`:

    ```python
    class CancelResult(BaseModel):
        """Immutable result of one cancel_bets_for_event invocation (D-04).

        Mirror of SettleResult but for the 404-branch of the reconciler:
        bets are flipped to CANCELLED when line-provider returns 404 for
        the event_id (event deleted / LP recreated). No terminal_state
        field — cancellation has no outcome.

        cancelled_count: number of rows flipped from PENDING to CANCELLED
                         in this call. 0 = idempotent no-op (same status
                         filter + FOR UPDATE SKIP LOCKED mechanism as
                         settle, see SettleResult docstring).
        cancelled_bet_ids: list of bet ids that were cancelled.
        cancelled_via: 'reconciler' only — Phase 6 introduces no other
                       call site. Literal kept narrow to make future
                       extension (manual admin cancel, deadline fallback)
                       an intentional widening.
        cancelled_at: Python-side timestamp filled by the interactor.
                      PG-side settled_at column filled server-side via
                      func.now() in the UPDATE statement (same column as
                      settle uses — observability semantics shared).
        """

        model_config = ConfigDict(frozen=True, extra="forbid")

        event_id: UUID
        cancelled_count: int
        cancelled_bet_ids: list[UUID]
        cancelled_via: Literal["reconciler"]
        cancelled_at: datetime
    ```

    The imports `Literal`, `UUID`, `datetime`, `BaseModel`, `ConfigDict` are already at the top of the file. No new imports required.

    Do NOT modify the SettleResult class or its docstring.
  </action>
  <verify>
    <automated>uv run python -c "from bet_maker.schemas.settle import CancelResult, SettleResult; from datetime import datetime, timezone; from uuid import uuid4; c = CancelResult(event_id=uuid4(), cancelled_count=0, cancelled_bet_ids=[], cancelled_via='reconciler', cancelled_at=datetime.now(timezone.utc)); print('ok')" && uv run mypy src/bet_maker/schemas/settle.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "class CancelResult" src/bet_maker/schemas/settle.py` == 1
    - `grep -c "class SettleResult" src/bet_maker/schemas/settle.py` == 1 (unchanged)
    - `grep -c "cancelled_via: Literal\\[\"reconciler\"\\]" src/bet_maker/schemas/settle.py` == 1
    - `grep -c "terminal_state" src/bet_maker/schemas/settle.py` == 1 (still ONE — only in SettleResult, not in CancelResult)
    - `uv run python -c "from bet_maker.schemas.settle import CancelResult"` exits 0
    - `uv run python -c "from bet_maker.schemas.settle import CancelResult; from datetime import datetime, timezone; from uuid import uuid4; CancelResult(event_id=uuid4(), cancelled_count=0, cancelled_bet_ids=[], cancelled_via='consumer', cancelled_at=datetime.now(timezone.utc))"` exits NON-zero (cancelled_via='consumer' is invalid — Literal restricts to 'reconciler')
    - `uv run mypy src/bet_maker/` exits 0
    - `uv run ruff check src/bet_maker/schemas/` exits 0
    - Phase 5 tests unaffected: `uv run pytest -x -q tests/bet_maker/test_settle.py` exits 0
  </acceptance_criteria>
  <done>CancelResult class added; SettleResult untouched; mypy + ruff clean; Phase 5 settle tests still green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement cancel_bets_for_event interactor + replace Wave-0 stub with 9 real tests</name>
  <files>src/bet_maker/interactors/cancel_bets_for_event.py, tests/bet_maker/interactors/test_cancel_bets_for_event.py</files>
  <read_first>
    - src/bet_maker/interactors/settle_bets_for_event.py (full file — direct template)
    - src/bet_maker/schemas/settle.py (after Task 1 — confirm CancelResult is importable)
    - src/bet_maker/schemas/bets.py (after Plan 06-03 — confirm BetStatus.CANCELLED exists)
    - src/bet_maker/repositories/bets.py (after Plan 06-05 — get_pending_locked unchanged)
    - tests/bet_maker/test_settle.py (test file template — class-per-scenario, session_factory fixture)
    - tests/bet_maker/interactors/test_cancel_bets_for_event.py (Wave-0 stub with 9 locked method names + 4 class names)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-04, D-05
    - .planning/phases/06-reconciliation-job/06-RESEARCH.md §Code Examples cancel_bets_for_event implementation
  </read_first>
  <behavior>
    Happy path (TestCancelHappyPath):
    - 2 PENDING bets on event A → `cancel_bets_for_event(uow, event_id=A, cancelled_via="reconciler")` → all flipped to CANCELLED, `cancelled_count==2`.
    - Post-cancel: `bet.settled_via == "reconciler"` for all flipped rows.
    - Post-cancel: `bet.settled_at IS NOT NULL` for all flipped rows (server-side func.now()).

    Noop (TestCancelNoop):
    - Second call on already-cancelled event → 0 rows → `cancelled_count==0`, `cancelled_bet_ids==[]`.
    - No PENDING bets for event → noop.
    - Only CANCELLED/WON/LOST bets exist for event → noop.

    Concurrent (TestCancelConcurrent):
    - `asyncio.gather(settle_bets_for_event(..., FINISHED_WIN, settled_via='consumer'), cancel_bets_for_event(..., cancelled_via='reconciler'))` → exactly one succeeds with count==3, other returns 0 (FOR UPDATE SKIP LOCKED + status filter).

    DTO shape (TestCancelResultShape):
    - `CancelResult` is frozen — setting attribute raises ValidationError.
    - `cancelled_at` is timezone-aware UTC.
  </behavior>
  <action>
    Step A — Write `src/bet_maker/interactors/cancel_bets_for_event.py`. Copy the structure of `settle_bets_for_event.py` and adapt:

    ```python
    """cancel_bets_for_event — idempotent cancel interactor for Phase 6 (D-04).

    Called by:
    - Phase 6 reconciliation job, 404-branch (cancelled_via='reconciler').

    Trigger:
    - Reconciler observes that line-provider returned 404 for event_id —
      event deleted / LP recreated. Bet cannot be settled because the
      event no longer exists; CANCELLED is the recovery sink (D-02 / D-04).

    Idempotency (mirrors settle_bets_for_event):
    - BetRepository.get_pending_locked() filters status='PENDING' and locks
      via FOR UPDATE SKIP LOCKED. Second caller on same event_id: 0 rows ->
      0-row UPDATE -> structlog 'cancel.noop' info -> CancelResult(count=0).

    Concurrent with settle (R3):
    - cancel vs settle on the same event_id: SKIP LOCKED + status filter
      guarantee exactly one of the two interactors gets all rows; the
      other observes 0 rows. Verified by test_concurrent_with_settle_no_double_update.

    Server-side timestamp (D-14 reuse):
    - settled_at column filled with func.now() in the UPDATE — same column
      and clock as settle_bets_for_event. settled_via='reconciler' is the
      attribution.

    Pitfalls guarded:
    - A1 / Anti-Pattern 1: bet_ids captured BEFORE the UPDATE; no lazy-load
      after UoW commit.
    - The interactor never calls uow.session.commit() — UoW owns the
      transaction (D-17 settle pattern).
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
    from bet_maker.schemas.settle import CancelResult


    async def cancel_bets_for_event(
        uow: AsyncUnitOfWork,
        *,
        event_id: UUID,
        cancelled_via: Literal["reconciler"],
    ) -> CancelResult:
        log = structlog.get_logger()
        cancelled_at = datetime.now(timezone.utc)
        async with uow:
            bets = await uow.bets.get_pending_locked(event_id)
            if not bets:
                log.info(
                    "cancel.noop",
                    event_id=str(event_id),
                    reason="no PENDING bets",
                    cancelled_via=cancelled_via,
                )
                return CancelResult(
                    event_id=event_id,
                    cancelled_count=0,
                    cancelled_bet_ids=[],
                    cancelled_via=cancelled_via,
                    cancelled_at=cancelled_at,
                )

            bet_ids = [b.id for b in bets]
            await uow.session.execute(
                update(Bet)
                .where(Bet.id.in_(bet_ids))
                .values(
                    status=BetStatus.CANCELLED,
                    settled_at=func.now(),
                    settled_via=cancelled_via,
                )
            )
            log.info(
                "cancel.committed",
                event_id=str(event_id),
                cancelled_count=len(bet_ids),
                cancelled_bet_ids=[str(bid) for bid in bet_ids],
                cancelled_via=cancelled_via,
                reason="line_provider_404",
            )
            return CancelResult(
                event_id=event_id,
                cancelled_count=len(bet_ids),
                cancelled_bet_ids=bet_ids,
                cancelled_via=cancelled_via,
                cancelled_at=cancelled_at,
            )
    ```

    Step B — Replace the Wave-0 stub `tests/bet_maker/interactors/test_cancel_bets_for_event.py` with 9 real tests across 4 classes. Method names and class names locked by Plan 06-02. Use `session_factory` fixture from root conftest.

    ```python
    """cancel_bets_for_event interactor tests (Plan 06-06 / BM-12 / D-04..D-05)."""

    from __future__ import annotations

    import asyncio
    from decimal import Decimal
    from uuid import uuid4

    import pytest
    from pydantic import ValidationError
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from bet_maker.facades.uow import AsyncUnitOfWork
    from bet_maker.interactors.cancel_bets_for_event import cancel_bets_for_event
    from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
    from bet_maker.models.bet import Bet
    from bet_maker.schemas.bets import BetStatus
    from bet_maker.schemas.messages import EventTerminalState


    @pytest.mark.asyncio(loop_scope="session")
    class TestCancelHappyPath:
        async def test_cancels_two_pending_bets_to_cancelled_status(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                for amt in ("10.00", "20.00"):
                    session.add(Bet(event_id=event_id, amount=Decimal(amt)))
            result = await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                cancelled_via="reconciler",
            )
            assert result.cancelled_count == 2
            async with session_factory() as session:
                rows = (
                    (await session.execute(select(Bet).where(Bet.event_id == event_id)))
                    .scalars().all()
                )
            assert all(b.status == BetStatus.CANCELLED for b in rows)

        async def test_settled_via_is_reconciler(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
            await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                cancelled_via="reconciler",
            )
            async with session_factory() as session:
                bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
            assert bet.settled_via == "reconciler"

        async def test_settled_at_is_filled(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
            await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                cancelled_via="reconciler",
            )
            async with session_factory() as session:
                bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
            assert bet.settled_at is not None


    @pytest.mark.asyncio(loop_scope="session")
    class TestCancelNoop:
        async def test_idempotent_second_call_returns_zero(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
            first = await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory), event_id=event_id, cancelled_via="reconciler"
            )
            second = await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory), event_id=event_id, cancelled_via="reconciler"
            )
            assert first.cancelled_count == 1
            assert second.cancelled_count == 0
            assert second.cancelled_bet_ids == []

        async def test_noop_when_no_pending_for_event(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            result = await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory), event_id=uuid4(), cancelled_via="reconciler"
            )
            assert result.cancelled_count == 0

        async def test_noop_when_only_already_cancelled_exist(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(
                    Bet(event_id=event_id, amount=Decimal("10.00"), status=BetStatus.CANCELLED)
                )
            result = await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory), event_id=event_id, cancelled_via="reconciler"
            )
            assert result.cancelled_count == 0


    @pytest.mark.asyncio(loop_scope="session")
    class TestCancelConcurrent:
        async def test_concurrent_with_settle_no_double_update(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            """R3 / D-05: settle vs cancel on same event_id — exactly one wins."""
            event_id = uuid4()
            async with session_factory.begin() as session:
                for amt in ("10.00", "20.00", "30.00"):
                    session.add(Bet(event_id=event_id, amount=Decimal(amt)))
            r_settle, r_cancel = await asyncio.gather(
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
            counts = sorted([r_settle.settled_count, r_cancel.cancelled_count])
            assert counts == [0, 3], f"expected exactly one winner, got {counts}"


    @pytest.mark.asyncio(loop_scope="session")
    class TestCancelResultShape:
        async def test_cancel_result_is_frozen(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            result = await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory), event_id=uuid4(), cancelled_via="reconciler"
            )
            with pytest.raises(ValidationError):
                result.cancelled_count = 999  # type: ignore[misc]

        async def test_cancel_result_cancelled_at_is_utc_aware(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            result = await cancel_bets_for_event(
                AsyncUnitOfWork(session_factory), event_id=uuid4(), cancelled_via="reconciler"
            )
            assert result.cancelled_at.tzinfo is not None
    ```
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/interactors/test_cancel_bets_for_event.py</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/bet_maker/interactors/cancel_bets_for_event.py`
    - `grep -c "async def cancel_bets_for_event" src/bet_maker/interactors/cancel_bets_for_event.py` == 1
    - `grep -c "get_pending_locked" src/bet_maker/interactors/cancel_bets_for_event.py` == 1
    - `grep -c "BetStatus.CANCELLED" src/bet_maker/interactors/cancel_bets_for_event.py` == 1
    - `grep -c "settled_via=cancelled_via" src/bet_maker/interactors/cancel_bets_for_event.py` == 1
    - `grep -c "settled_at=func.now()" src/bet_maker/interactors/cancel_bets_for_event.py` == 1
    - `grep -c "session.commit\|session.rollback" src/bet_maker/interactors/cancel_bets_for_event.py` == 0 (UoW owns transactions)
    - `uv run pytest -x -q tests/bet_maker/interactors/test_cancel_bets_for_event.py` reports 9 passed
    - `uv run pytest -x -q tests/bet_maker/test_settle.py` reports zero regressions
    - `uv run mypy src/bet_maker/` exits 0
    - `uv run ruff check src/bet_maker/interactors/ tests/bet_maker/interactors/` exits 0
    - Stub replaced: `grep -c "Wave-0 stub" tests/bet_maker/interactors/test_cancel_bets_for_event.py` == 0
  </acceptance_criteria>
  <done>cancel_bets_for_event implemented and idempotent; 9 tests green; settle suite untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| reconciler → cancel_bets_for_event → PG UPDATE | Mutation crossing trust boundary; race with consumer thread; must be idempotent |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-06-01 | Tampering (double-update race) | concurrent settle vs cancel | mitigate | Reuse `get_pending_locked` — FOR UPDATE SKIP LOCKED + status filter; test_concurrent_with_settle_no_double_update asserts exactly one winner |
| T-06-06-02 | Tampering (cancelled bet revived) | cancel idempotency | mitigate | Status filter `WHERE status='PENDING'` excludes already-CANCELLED bets; test_idempotent_second_call_returns_zero asserts |
| T-06-06-03 | Repudiation (no audit trail) | observability | mitigate | structlog `cancel.committed` includes event_id + cancelled_bet_ids + cancelled_via + reason="line_provider_404"; DB columns settled_at/settled_via persist the audit |
| T-06-06-04 | Information Disclosure | log output | accept | event_id and bet_ids are non-secret; no PII in cancel path |
</threat_model>

<verification>
- `uv run pytest -x -q tests/bet_maker/interactors/test_cancel_bets_for_event.py tests/bet_maker/test_settle.py` exits 0.
- `uv run mypy src/` exits 0.
- `uv run ruff check src/ tests/` exits 0.
</verification>

<success_criteria>
- `CancelResult` DTO + `cancel_bets_for_event` interactor exist with the locked CONTEXT.md signatures.
- 9 unit tests pass (happy, noop, concurrent vs settle, DTO shape).
- Zero regression on Phase 5 settle suite.
- `cancel_bets_for_event` body satisfies R3 (SKIP LOCKED + status filter) for free by reusing `get_pending_locked`.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-06-SUMMARY.md` summarising the DTO additions and the 9 test outcomes.
</output>

## Decision Coverage

- D-04: New interactor `cancel_bets_for_event(uow, *, event_id, cancelled_via="reconciler") -> CancelResult` (separate from `settle_bets_for_event` — distinct semantics, separate DTO).
- D-19: Unit tests `tests/bet_maker/interactors/test_cancel_bets_for_event.py` against testcontainers PG — 9 cases including idempotency + concurrent settle race.
