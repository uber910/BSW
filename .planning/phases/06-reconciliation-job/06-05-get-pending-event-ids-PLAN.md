---
phase: 06-reconciliation-job
plan: 05
type: execute
wave: 1
depends_on: [01, 02]
files_modified:
  - src/bet_maker/repositories/bets.py
  - tests/bet_maker/repositories/test_get_pending_event_ids.py
autonomous: true
requirements: [BM-12]
tags: [repository, sqlalchemy, select-distinct]

must_haves:
  truths:
    - "BetRepository.get_pending_event_ids() returns list[UUID]"
    - "Query is SELECT DISTINCT event_id FROM bets WHERE status='PENDING'"
    - "Repository does NOT commit or flush (Anti-Pattern 1 preserved)"
    - "Returns [] when no PENDING bets exist"
    - "Returns DISTINCT event_ids (no duplicates even with multiple bets per event)"
    - "Excludes WON/LOST/CANCELLED bets"
  artifacts:
    - path: "src/bet_maker/repositories/bets.py"
      provides: "New async method get_pending_event_ids on BetRepository"
      contains: "get_pending_event_ids"
    - path: "tests/bet_maker/repositories/test_get_pending_event_ids.py"
      provides: "4 real assertions replacing the Wave-0 stub"
      contains: "DISTINCT"
  key_links:
    - from: "BetRepository.get_pending_event_ids"
      to: "src/bet_maker/jobs/reconciler.py (Plan 06-07 _run_tick)"
      via: "reconciler calls this through `await uow.bets.get_pending_event_ids()` (D-01 / D-11)"
      pattern: "uow\\.bets\\.get_pending_event_ids"
---

<objective>
Add a new read-only method `get_pending_event_ids() -> list[UUID]` to `BetRepository` returning the distinct set of event_ids that have at least one PENDING bet (CONTEXT.md D-01 / D-11).

Purpose: The reconciler tick (Plan 06-07) starts by asking "which events still have unsettled bets?" — that work-list query is this single repository method. Separating it into Wave 1 keeps it independent of the cancel-interactor (Wave 2).

Implementation is a one-shot SELECT — no FOR UPDATE, no SKIP LOCKED — because:
- We do not need to lock the rows; we just need their event_ids.
- The downstream settle/cancel interactor (per event_id) takes its own short-lived UoW with row-level locks. Holding a long lock across all PENDING events would maximally contend with the consumer.

Output: ~12 lines of new repository code + 4 real test assertions replacing the Wave-0 stub.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@.planning/phases/06-reconciliation-job/06-RESEARCH.md
@src/bet_maker/repositories/bets.py
@src/bet_maker/models/bet.py
@tests/bet_maker/test_repositories.py
@tests/bet_maker/repositories/test_get_pending_event_ids.py
</context>

<interfaces>
Existing `src/bet_maker/repositories/bets.py` shape (DO NOT delete or modify existing methods):
```python
class BetRepository:
    def __init__(self, session: AsyncSession) -> None: ...
    def add(self, bet: Bet) -> None: ...
    async def get_by_id(self, bet_id: UUID) -> Bet | None: ...
    async def get_pending_locked(self, event_id: UUID) -> list[Bet]: ...
```

Pattern (RESEARCH.md §Pattern 1, VERIFIED via Context7 /websites/sqlalchemy_en_20):
```python
result = await self._session.execute(
    select(Bet.event_id)
    .where(Bet.status == BetStatus.PENDING)
    .distinct()
)
return list(result.scalars().all())
```

Pitfall 4 (RESEARCH.md) — use `.scalars().all()` for a single-column SELECT, NOT `.all()` (the latter returns `Row` objects, not raw UUIDs).
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add BetRepository.get_pending_event_ids method + replace Wave-0 stub with 4 real assertions</name>
  <files>src/bet_maker/repositories/bets.py, tests/bet_maker/repositories/test_get_pending_event_ids.py</files>
  <read_first>
    - src/bet_maker/repositories/bets.py (full file)
    - src/bet_maker/models/bet.py (Bet.event_id type + Bet.status column)
    - tests/bet_maker/test_repositories.py (existing pattern: session_factory fixture + Bet seeding)
    - tests/bet_maker/repositories/test_get_pending_event_ids.py (Wave-0 stub with 4 locked method names)
    - .planning/phases/06-reconciliation-job/06-RESEARCH.md §Pattern 1 + Pitfall 4
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-01 + D-11
  </read_first>
  <behavior>
    - With 3 PENDING bets on event A, 2 PENDING on event B, no other bets — `get_pending_event_ids()` returns a list whose set is `{A, B}` (DISTINCT).
    - With only WON / LOST / CANCELLED bets — returns `[]`.
    - With no bets at all — returns `[]`.
    - Mixed: 1 PENDING on A, 1 WON on B — returns `[A]`.
    - The method does NOT call `session.commit()` / `session.flush()` / `session.rollback()` — Anti-Pattern 1 preserved (verified via source-introspection).
    - Each element of the returned list is `uuid.UUID`, not `str` or `Row` (Pitfall 4).
  </behavior>
  <action>
    Step A — Edit `src/bet_maker/repositories/bets.py`. Add the new method to the `BetRepository` class, IMMEDIATELY AFTER `get_pending_locked`. Imports stay as-is.

    Method body:
    ```python
    async def get_pending_event_ids(self) -> list[UUID]:
        """D-01 / Plan 06-05: distinct event_ids with at least one PENDING bet.

        SELECT DISTINCT event_id FROM bets WHERE status = 'PENDING'

        Used by the reconciler tick (Plan 06-07 _run_tick) to discover
        which events still need a state poll from line-provider. Read-only
        — no FOR UPDATE, no commit, no flush. Anti-Pattern 1 preserved.

        Pitfall 4 (RESEARCH.md): `.scalars().all()` returns the raw UUID
        column values; plain `.all()` would return SQLAlchemy `Row` objects.
        """
        result = await self._session.execute(
            select(Bet.event_id)
            .where(Bet.status == BetStatus.PENDING)
            .distinct()
        )
        return list(result.scalars().all())
    ```

    Do NOT modify `__init__`, `add`, `get_by_id`, or `get_pending_locked`.

    Step B — Replace the Wave-0 stub `tests/bet_maker/repositories/test_get_pending_event_ids.py` with four real assertions. Method names already locked by Plan 06-02 — DO NOT rename. Class name: `TestGetPendingEventIds`.

    ```python
    """BetRepository.get_pending_event_ids assertions (Plan 06-05 / BM-12 / D-01)."""
    from __future__ import annotations

    import inspect
    from decimal import Decimal
    from uuid import uuid4

    import pytest
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from bet_maker.facades.uow import AsyncUnitOfWork
    from bet_maker.models.bet import Bet
    from bet_maker.repositories.bets import BetRepository
    from bet_maker.schemas.bets import BetStatus


    @pytest.mark.asyncio(loop_scope="session")
    class TestGetPendingEventIds:
        async def test_returns_distinct_event_ids_for_pending_bets(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            event_a, event_b = uuid4(), uuid4()
            async with session_factory.begin() as session:
                for amt in ("10.00", "20.00", "30.00"):
                    session.add(Bet(event_id=event_a, amount=Decimal(amt)))
                for amt in ("5.00", "15.00"):
                    session.add(Bet(event_id=event_b, amount=Decimal(amt)))
            async with AsyncUnitOfWork(session_factory) as uow:
                event_ids = await uow.bets.get_pending_event_ids()
            assert set(event_ids) == {event_a, event_b}
            assert len(event_ids) == 2

        async def test_excludes_won_lost_cancelled_bets(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            ev_pending, ev_won, ev_lost, ev_cancelled = uuid4(), uuid4(), uuid4(), uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=ev_pending, amount=Decimal("10.00"), status=BetStatus.PENDING))
                session.add(Bet(event_id=ev_won, amount=Decimal("10.00"), status=BetStatus.WON))
                session.add(Bet(event_id=ev_lost, amount=Decimal("10.00"), status=BetStatus.LOST))
                session.add(Bet(event_id=ev_cancelled, amount=Decimal("10.00"), status=BetStatus.CANCELLED))
            async with AsyncUnitOfWork(session_factory) as uow:
                event_ids = await uow.bets.get_pending_event_ids()
            assert event_ids == [ev_pending]

        async def test_returns_empty_list_when_no_pending(
            self, session_factory: async_sessionmaker  # type: ignore[type-arg]
        ) -> None:
            async with AsyncUnitOfWork(session_factory) as uow:
                event_ids = await uow.bets.get_pending_event_ids()
            assert event_ids == []

        async def test_no_commit_no_flush(self) -> None:
            """Anti-Pattern 1: repository must not own transactions."""
            source = inspect.getsource(BetRepository.get_pending_event_ids)
            assert ".commit(" not in source
            assert ".flush(" not in source
            assert ".rollback(" not in source
            assert "select(" in source
            assert ".distinct()" in source
    ```

    Notes:
    - `session_factory` is session-scoped from `tests/conftest.py`.
    - `truncate_bets` is autouse via `tests/bet_maker/conftest.py::_auto_truncate` — fresh state per test.
    - mypy: `async_sessionmaker[AsyncSession]` is annotated as `async_sessionmaker  # type: ignore[type-arg]` (same pattern as `tests/bet_maker/test_settle.py`).
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/repositories/test_get_pending_event_ids.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "async def get_pending_event_ids" src/bet_maker/repositories/bets.py` == 1
    - `grep -c "select(Bet.event_id)" src/bet_maker/repositories/bets.py` == 1
    - `grep -c ".distinct()" src/bet_maker/repositories/bets.py` == 1
    - `grep -c "scalars().all()" src/bet_maker/repositories/bets.py` >= 2 (existing + new)
    - `uv run pytest -x -q tests/bet_maker/repositories/test_get_pending_event_ids.py` reports 4 passed
    - `uv run pytest -x -q tests/bet_maker/test_repositories.py tests/bet_maker/test_settle.py` reports zero regressions
    - `uv run mypy src/bet_maker/` exits 0
    - `uv run ruff check src/bet_maker/ tests/bet_maker/repositories/` exits 0
    - Stub replaced: `grep -c "Wave-0 stub" tests/bet_maker/repositories/test_get_pending_event_ids.py` == 0
    - The method has no commit/flush/rollback: `grep -A 12 "async def get_pending_event_ids" src/bet_maker/repositories/bets.py | grep -E "(commit|flush|rollback)\(" | wc -l` == 0
  </acceptance_criteria>
  <done>New method added; 4 tests green; existing repository / settle tests unaffected; mypy + ruff clean.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| DB read → reconciler | DB returns potentially huge list of event_ids; reconciler iterates serially |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-05-01 | Denial of Service (large workload) | get_pending_event_ids | accept | For a test task with sub-1000 events the DISTINCT scan is trivial; multi-thousand-event hardening (pagination, semaphore) deferred per CONTEXT.md deferred-ideas |
| T-06-05-02 | Tampering (status enum drift) | WHERE clause | mitigate | Filter compares to BetStatus.PENDING (Python enum) — SQLAlchemy emits the canonical PG label; test 2 asserts the WON/LOST/CANCELLED exclusion |
</threat_model>

<verification>
- `uv run pytest -x -q tests/bet_maker/repositories/ tests/bet_maker/test_repositories.py tests/bet_maker/test_settle.py` exits 0.
- `uv run mypy src/bet_maker/ tests/bet_maker/repositories/` exits 0.
</verification>

<success_criteria>
- New `get_pending_event_ids` method exists on `BetRepository`.
- 4 new repository tests pass.
- No regression on Phase 3-5 tests.
- mypy + ruff clean.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-05-SUMMARY.md` summarising the one new method and the 4 new tests.
</output>

## Decision Coverage

- D-01: `BetRepository.get_pending_event_ids()` — `SELECT DISTINCT event_id FROM bets WHERE status='PENDING'` (no FOR UPDATE — reconciler is read-only here, settle path uses existing `get_pending_locked`).
