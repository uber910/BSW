---
phase: 06-reconciliation-job
plan: 07
type: execute
wave: 2
depends_on: [03, 04, 05, 06]
files_modified:
  - src/bet_maker/jobs/__init__.py
  - src/bet_maker/jobs/reconciler.py
  - tests/bet_maker/jobs/test_reconciler_tick.py
  - tests/bet_maker/jobs/test_reconciler_cancellation.py
autonomous: true
requirements: [BM-12]
tags: [reconciler, asyncio-task, cancellable, structlog, error-isolation]

must_haves:
  truths:
    - "src/bet_maker/jobs/reconciler.py defines reconciliation_loop(app, *, interval_s) → coroutine"
    - "Inner reconcile_event(sessionmaker, lookup, event_id) handles the 3-branch decision: FINISHED_* → settle, None → cancel, NEW → skip"
    - "_run_tick(app) does ONE read-only UoW for get_pending_event_ids + per-event try/except"
    - "Outer try/except in loop: except asyncio.CancelledError BEFORE except Exception (re-raise CancelledError, log+continue Exception)"
    - "asyncio.sleep(interval_s) is called BEFORE the first _run_tick (no cold-start noise)"
    - "Per-event Exception is logged with reconciler.event.failed and the loop continues to the next event_id"
    - "Per-tick Exception (raised by get_pending_event_ids) is logged reconciler.tick.failed and the loop continues to the next iteration"
    - "Task name is 'reconciliation' (asyncio.Task.get_name())"
  artifacts:
    - path: "src/bet_maker/jobs/__init__.py"
      provides: "Empty package marker"
      contains: "package"
    - path: "src/bet_maker/jobs/reconciler.py"
      provides: "reconciliation_loop, _run_tick, _reconcile_event (~80 lines)"
      contains: "reconciliation_loop"
    - path: "tests/bet_maker/jobs/test_reconciler_tick.py"
      provides: "Real assertions across TestReconcilerTick + TestReconcilerErrorIsolation (8 tests)"
      contains: "TestReconcilerTick"
    - path: "tests/bet_maker/jobs/test_reconciler_cancellation.py"
      provides: "Real assertions for TestReconcilerCancellation (3 tests)"
      contains: "CancelledError"
  key_links:
    - from: "src/bet_maker/jobs/reconciler.py"
      to: "src/bet_maker/entrypoints/lifespan.py (Plan 06-08)"
      via: "lifespan does `asyncio.create_task(reconciliation_loop(app, interval_s=...), name='reconciliation')`"
      pattern: "create_task\\(.*reconciliation_loop"
    - from: "src/bet_maker/jobs/reconciler.py"
      to: "src/bet_maker/interactors/settle_bets_for_event.py + cancel_bets_for_event.py"
      via: "reconciler branches dispatch to existing interactors"
      pattern: "(settle|cancel)_bets_for_event"
    - from: "src/bet_maker/jobs/reconciler.py"
      to: "src/bet_maker/repositories/bets.py::get_pending_event_ids"
      via: "tick reads work-list via uow.bets.get_pending_event_ids()"
      pattern: "get_pending_event_ids"
---

<objective>
Implement the heart of Phase 6: `src/bet_maker/jobs/reconciler.py` — the asyncio background task that polls line-provider for terminal-state events and settles or cancels stuck PENDING bets. This is a pure-composition module: it dispatches to `settle_bets_for_event` (Phase 5) and `cancel_bets_for_event` (Plan 06-06) over a work-list returned by `BetRepository.get_pending_event_ids` (Plan 06-05).

The module exposes three callables:

1. **`reconciliation_loop(app: FastAPI, *, interval_s: float) -> None`** — the infinite outer loop. Sleeps first (D-17), then runs `_run_tick`. Catches `asyncio.CancelledError` and re-raises (for clean lifespan shutdown). Catches `Exception` and logs `reconciler.tick.failed` then continues (R8 — never silently exit).

2. **`_run_tick(app: FastAPI) -> None`** — one iteration. Opens a short read-only UoW, calls `get_pending_event_ids`, then iterates per event_id calling `_reconcile_event`. Per-event try/except isolates failures so one bad event_id does not poison the rest of the tick (D-11).

3. **`_reconcile_event(sessionmaker, lookup, event_id) -> None`** — one event. Calls `lookup.get_event(event_id)`. Branches on the result: `FINISHED_WIN|FINISHED_LOSE` → settle, `None` → cancel, `NEW` → skip with debug log. Each branch opens its own short-lived UoW so per-event row-lock contention with the consumer is minimal.

Purpose: This is the **lifeblood** of the Phase 6 Core Value guarantee. Without this loop, the only path from PENDING to terminal is the AMQP consumer (Phase 5); if a message is dropped, bets stay PENDING forever. The reconciler closes that hole.

Output: ~80 production lines + 11 real tests (8 in tick file + 3 in cancellation file). Designed to be testable without testcontainers RMQ — the tests substitute a fake EventLookup (duck-typed, not Protocol) and a real PG via session_factory (CONTEXT.md D-08).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@.planning/phases/06-reconciliation-job/06-RESEARCH.md
@src/bet_maker/interactors/settle_bets_for_event.py
@src/bet_maker/interactors/cancel_bets_for_event.py
@src/bet_maker/facades/event_lookup.py
@src/bet_maker/facades/uow.py
@src/bet_maker/schemas/messages.py
@src/bet_maker/schemas/events.py
@tests/bet_maker/test_settle.py
@tests/bet_maker/jobs/test_reconciler_tick.py
@tests/bet_maker/jobs/test_reconciler_cancellation.py
</context>

<interfaces>
Existing interfaces the reconciler depends on:

```python
# src/bet_maker/facades/event_lookup.py
class EventSnapshot(BaseModel):
    event_id: UUID
    deadline: datetime
    state: EventState  # NEW / FINISHED_WIN / FINISHED_LOSE — line_provider terms
    # frozen=True, extra=forbid

# src/bet_maker/facades/http_event_lookup.py — duck-typed in reconciler
class HttpEventLookup:
    async def get_event(self, event_id: UUID) -> EventSnapshot | None: ...

# src/bet_maker/schemas/events.py
class EventState(str, Enum):
    NEW = "NEW"
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"

# src/bet_maker/schemas/messages.py
class EventTerminalState(str, Enum):
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"

# src/bet_maker/facades/uow.py
class AsyncUnitOfWork:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None: ...
    bets: BetRepository  # set in __aenter__
    session: AsyncSession  # set in __aenter__

# src/bet_maker/repositories/bets.py (Plan 06-05)
class BetRepository:
    async def get_pending_event_ids(self) -> list[UUID]: ...

# src/bet_maker/interactors/settle_bets_for_event.py (Phase 5)
async def settle_bets_for_event(
    uow: AsyncUnitOfWork,
    *, event_id: UUID, terminal_state: EventTerminalState,
    settled_via: Literal["consumer", "reconciler"],
) -> SettleResult: ...

# src/bet_maker/interactors/cancel_bets_for_event.py (Plan 06-06)
async def cancel_bets_for_event(
    uow: AsyncUnitOfWork,
    *, event_id: UUID, cancelled_via: Literal["reconciler"],
) -> CancelResult: ...
```

Reconciler API to build:
```python
async def reconciliation_loop(app: FastAPI, *, interval_s: float) -> None:
    """Outer loop. Sleep first, then tick. Survives any tick-level error."""
    ...

async def _run_tick(app: FastAPI) -> None:
    """One iteration of the loop."""
    ...

async def _reconcile_event(
    sessionmaker: async_sessionmaker[AsyncSession],
    lookup: HttpEventLookup,
    event_id: UUID,
) -> None:
    """Decision for one event_id."""
    ...
```

The lookup parameter is intentionally typed as the concrete `HttpEventLookup`, NOT the `EventLookup` Protocol, per CONTEXT.md D-08. Tests pass a duck-typed fake; no Protocol implementation gymnastics.

EventState → EventTerminalState mapping for settle: `EventState.FINISHED_WIN` → `EventTerminalState.FINISHED_WIN`. They share the same string values; safe `EventTerminalState(event.state.value)` cast inside the FINISHED branch.

Reading from app.state inside reconciler (D-11): `app.state.sessionmaker` and `app.state.reconciler_event_lookup`. (The latter is pinned in Plan 06-08.) For testability, `_run_tick` reads from `app.state` but `_reconcile_event` takes sessionmaker + lookup as explicit params.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create src/bet_maker/jobs/ package and implement reconciler.py (loop + _run_tick + _reconcile_event)</name>
  <files>src/bet_maker/jobs/__init__.py, src/bet_maker/jobs/reconciler.py</files>
  <read_first>
    - src/bet_maker/interactors/settle_bets_for_event.py (template for short interactor with UoW + structlog)
    - src/bet_maker/interactors/cancel_bets_for_event.py (just shipped — sibling shape)
    - src/bet_maker/facades/event_lookup.py (EventSnapshot shape)
    - src/bet_maker/schemas/events.py (EventState enum values)
    - src/bet_maker/schemas/messages.py (EventTerminalState enum values)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-02, D-08, D-10, D-11, D-12
    - .planning/phases/06-reconciliation-job/06-RESEARCH.md §Architecture Patterns (Patterns 2 + 3)
  </read_first>
  <behavior>
    - `reconciliation_loop` is a coroutine that runs forever (until cancelled). Each iteration sleeps `interval_s` seconds FIRST (no first-iteration cold-start noise — D-17), then calls `_run_tick(app)`.
    - When `asyncio.CancelledError` is raised inside the loop (typically inside `asyncio.sleep`), the loop logs `reconciler.cancelled` and re-raises so the awaiter in lifespan sees a clean cancellation.
    - When any other `Exception` is raised inside `_run_tick`, the loop logs `reconciler.tick.failed` via `log.exception(...)` and continues to the next iteration. The loop does NOT die.
    - `BaseException` other than `CancelledError` (e.g., `KeyboardInterrupt`, `SystemExit`) is NOT caught — propagates as the runtime expects.
    - `_run_tick` opens ONE read-only UoW to read the work-list:
      ```python
      async with AsyncUnitOfWork(sessionmaker) as uow:
          event_ids = await uow.bets.get_pending_event_ids()
      ```
      Then iterates `event_ids`, calling `_reconcile_event` in a per-event try/except so one bad event_id does not abort the tick.
    - When `event_ids == []`, `_run_tick` logs `reconciler.tick.noop` at debug level and returns. Goal: cheap when the system is idle.
    - `_reconcile_event` calls `lookup.get_event(event_id)`:
      - Returns `EventSnapshot` with `state ∈ {EventState.FINISHED_WIN, EventState.FINISHED_LOSE}` → invoke `settle_bets_for_event(uow, event_id=..., terminal_state=EventTerminalState(snapshot.state.value), settled_via="reconciler")` inside its own fresh UoW (own AsyncUnitOfWork instance).
      - Returns `None` → 404 from LP → invoke `cancel_bets_for_event(uow, event_id=..., cancelled_via="reconciler")` inside its own fresh UoW.
      - Returns snapshot with `state == EventState.NEW` → log `reconciler.event.still_new` at debug level and return.
    - Log namespace `reconciler.*` is the single source of truth for grep observability:
      `reconciler.tick.start`, `reconciler.tick.noop`, `reconciler.tick.failed`, `reconciler.event.settled`, `reconciler.event.cancelled`, `reconciler.event.still_new`, `reconciler.event.failed`, `reconciler.cancelled`.
    - The structlog logger is bound with `task="reconciliation"` at module level so every log line carries the marker.
    - mypy strict: `app.state.sessionmaker` and `app.state.reconciler_event_lookup` are accessed via `cast(async_sessionmaker[AsyncSession], app.state.sessionmaker)` and `cast(HttpEventLookup, app.state.reconciler_event_lookup)` to keep the loop type-clean.
  </behavior>
  <action>
    Step A — Create the package marker `src/bet_maker/jobs/__init__.py`:
    ```python
    """Long-running asyncio background jobs (Phase 6 onwards).

    Distinct from `entrypoints/` (HTTP routes + AMQP subscribers): a job
    is started by lifespan, lives for the duration of the process, and
    yields to the loop only via `await`. The reconciler is the first
    inhabitant; future health-watchdogs / outbox-drainers would also land
    here.
    """
    ```

    Step B — Write `src/bet_maker/jobs/reconciler.py`. Approximate target size 90-110 lines including docstrings. Skeleton:

    ```python
    """Reconciliation background task (Phase 6 / BM-12).

    Composition module — no new business rules; it merely dispatches
    PENDING bets to existing interactors based on what line-provider
    reports for each event_id:

    | LP response                          | reconciler action                              |
    |--------------------------------------|------------------------------------------------|
    | EventSnapshot(state=FINISHED_WIN)    | settle_bets_for_event(... WON,  via=reconciler) |
    | EventSnapshot(state=FINISHED_LOSE)   | settle_bets_for_event(... LOST, via=reconciler) |
    | None (404 from LP)                   | cancel_bets_for_event(... CANCELLED, via=reconciler) |
    | EventSnapshot(state=NEW)             | skip (LP has not transitioned yet — try again)   |

    Defence-in-depth: even if every consumer dispatch in Phase 5 fails
    silently, this loop sweeps every PENDING bet within
    `RECONCILIATION_INTERVAL_S` seconds. Idempotent by construction
    because the underlying interactors are idempotent (FOR UPDATE SKIP
    LOCKED + status filter, Phase 5 / Plan 06-06).

    Error model (CONTEXT.md D-10 / D-11 / D-12, RESEARCH §Pattern 3):
    - The outer while-True body has TWO except blocks:
        1. asyncio.CancelledError -> log and re-raise (clean shutdown).
        2. Exception                 -> log.exception and continue (R8 invariant).
      BaseException other than CancelledError is NEVER caught.
    - Per-event try/except inside _run_tick isolates failures so one bad
      event_id does not abort the whole tick.

    Sleep ordering (D-17): `await asyncio.sleep(interval_s)` is the FIRST
    awaited operation in each iteration — no cold-start noise, predictable
    cadence.

    Task name (D-18): `asyncio.create_task(..., name="reconciliation")`
    set by lifespan; grep-able in logs and asyncio debug output.
    """

    from __future__ import annotations

    import asyncio
    from typing import cast
    from uuid import UUID

    import structlog
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from bet_maker.facades.http_event_lookup import HttpEventLookup
    from bet_maker.facades.uow import AsyncUnitOfWork
    from bet_maker.interactors.cancel_bets_for_event import cancel_bets_for_event
    from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
    from bet_maker.schemas.events import EventState
    from bet_maker.schemas.messages import EventTerminalState

    _log = structlog.get_logger().bind(task="reconciliation")


    async def reconciliation_loop(app: FastAPI, *, interval_s: float) -> None:
        """Outer infinite loop. Sleep first (D-17), then tick. R8-compliant.

        Two-tier try/except (D-10 / RESEARCH Pattern 3): CancelledError is
        caught explicitly BEFORE Exception so a future refactor that adds a
        `try` deeper in the call stack cannot accidentally swallow it.
        """
        while True:
            try:
                await asyncio.sleep(interval_s)
                _log.debug("reconciler.tick.start")
                await _run_tick(app)
            except asyncio.CancelledError:
                _log.info("reconciler.cancelled")
                raise  # propagate up to lifespan await
            except Exception:
                _log.exception("reconciler.tick.failed")
                # loop continues — R8


    async def _run_tick(app: FastAPI) -> None:
        """One tick of the loop. Read work-list, then process each event_id.

        Read-only UoW for the work-list (D-11): short transaction, minimal
        lock contention with the consumer (Phase 5). Per-event UoW happens
        inside _reconcile_event so a long-running event lookup does not
        hold an open DB transaction.
        """
        sessionmaker = cast(
            "async_sessionmaker[AsyncSession]", app.state.sessionmaker
        )
        lookup = cast(HttpEventLookup, app.state.reconciler_event_lookup)
        async with AsyncUnitOfWork(sessionmaker) as uow:
            event_ids = await uow.bets.get_pending_event_ids()

        if not event_ids:
            _log.debug("reconciler.tick.noop")
            return

        for event_id in event_ids:
            try:
                await _reconcile_event(sessionmaker, lookup, event_id)
            except Exception:
                _log.exception(
                    "reconciler.event.failed", event_id=str(event_id)
                )
                continue  # isolate per-event failure


    async def _reconcile_event(
        sessionmaker: "async_sessionmaker[AsyncSession]",
        lookup: HttpEventLookup,
        event_id: UUID,
    ) -> None:
        """Decision tree for one event_id (CONTEXT.md D-02).

        FINISHED_WIN | FINISHED_LOSE -> settle
        None (LP 404)                -> cancel
        NEW                           -> skip
        """
        snapshot = await lookup.get_event(event_id)

        if snapshot is None:
            uow = AsyncUnitOfWork(sessionmaker)
            await cancel_bets_for_event(
                uow, event_id=event_id, cancelled_via="reconciler"
            )
            _log.info("reconciler.event.cancelled", event_id=str(event_id))
            return

        if snapshot.state == EventState.NEW:
            _log.debug(
                "reconciler.event.still_new", event_id=str(event_id)
            )
            return

        # snapshot.state in {EventState.FINISHED_WIN, EventState.FINISHED_LOSE}
        uow = AsyncUnitOfWork(sessionmaker)
        terminal_state = EventTerminalState(snapshot.state.value)
        await settle_bets_for_event(
            uow,
            event_id=event_id,
            terminal_state=terminal_state,
            settled_via="reconciler",
        )
        _log.info(
            "reconciler.event.settled",
            event_id=str(event_id),
            terminal_state=terminal_state.value,
        )
    ```

    Notes:
    - `from __future__ import annotations` allows `"async_sessionmaker[AsyncSession]"` string forward-references which Python 3.10 mypy strict requires for generic types in cast targets.
    - The `cast` calls bridge mypy's view of `app.state` (which is `State`/`Any`) to the concrete types pinned by lifespan; without them, every read of `app.state.sessionmaker` would be `Any` and propagate.
    - `EventTerminalState(snapshot.state.value)` is safe: we only reach this line when `state in {FINISHED_WIN, FINISHED_LOSE}`, both of which exist as EventTerminalState members with identical string values.
  </action>
  <verify>
    <automated>uv run mypy src/bet_maker/jobs/ && uv run ruff check src/bet_maker/jobs/ && uv run python -c "from bet_maker.jobs.reconciler import reconciliation_loop, _run_tick, _reconcile_event; print('imports ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -d src/bet_maker/jobs && test -f src/bet_maker/jobs/__init__.py && test -f src/bet_maker/jobs/reconciler.py`
    - `grep -c "async def reconciliation_loop" src/bet_maker/jobs/reconciler.py` == 1
    - `grep -c "async def _run_tick" src/bet_maker/jobs/reconciler.py` == 1
    - `grep -c "async def _reconcile_event" src/bet_maker/jobs/reconciler.py` == 1
    - `grep -c "except asyncio.CancelledError" src/bet_maker/jobs/reconciler.py` == 1
    - `grep -c "except Exception" src/bet_maker/jobs/reconciler.py` >= 2 (loop + per-event)
    - `grep -c "raise  # propagate" src/bet_maker/jobs/reconciler.py` == 1 (re-raise CancelledError)
    - `grep -c "except BaseException" src/bet_maker/jobs/reconciler.py` == 0 (must NOT catch BaseException)
    - The sleep-before-tick ordering: in the source of `reconciliation_loop`, the first `await` inside the `try` block is `asyncio.sleep`. Verify with: `python -c "import inspect; from bet_maker.jobs.reconciler import reconciliation_loop; src = inspect.getsource(reconciliation_loop); idx_sleep = src.find('asyncio.sleep'); idx_tick = src.find('_run_tick'); assert 0 < idx_sleep < idx_tick"` exits 0
    - `uv run mypy src/bet_maker/` exits 0
    - `uv run ruff check src/bet_maker/` exits 0
  </acceptance_criteria>
  <done>Reconciler module exists with correct decision tree, two-tier exception handling, sleep-first ordering, and the right structlog namespace.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Replace Wave-0 stubs with real reconciler tick + cancellation tests</name>
  <files>tests/bet_maker/jobs/test_reconciler_tick.py, tests/bet_maker/jobs/test_reconciler_cancellation.py</files>
  <read_first>
    - src/bet_maker/jobs/reconciler.py (just shipped)
    - tests/bet_maker/jobs/test_reconciler_tick.py (Wave-0 stub — class + method names locked)
    - tests/bet_maker/jobs/test_reconciler_cancellation.py (Wave-0 stub)
    - tests/bet_maker/test_settle.py (template for session_factory + Bet seeding)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Testing D-20
  </read_first>
  <behavior>
    Per-tick assertions (TestReconcilerTick — 6 tests):
    - With a fake lookup that returns FINISHED_WIN for event A, FINISHED_LOSE for event B, NEW for event C, None for event D, and a seeded bets table with 1 PENDING bet per event_id → after `_run_tick`, A is WON, B is LOST, C is still PENDING (NEW skip), D is CANCELLED.
    - With 0 PENDING bets → `_run_tick` is a noop (does not call the lookup at all).
    - Per-event exception isolation: fake lookup raises on event A, returns FINISHED_WIN for event B → `_run_tick` completes; B is settled, A is left PENDING (no crash).
    - `reconciliation_loop` calls `asyncio.sleep(interval_s)` BEFORE the first `_run_tick`: build a stub `_run_tick` that counts how many times it was called; cancel the task after `interval_s + buffer` — assert `_run_tick` was called exactly once (or zero times if cancelled mid-sleep).

    Error isolation (TestReconcilerErrorIsolation — 2 tests):
    - When `_run_tick` raises `RuntimeError`, the loop logs `reconciler.tick.failed` and continues — set up: monkeypatch `_run_tick` to raise on the first call and succeed on the second; cancel after two iterations; assert the second call ran (loop survived).
    - `except Exception` does NOT catch `SystemExit`: monkeypatch `_run_tick` to raise `SystemExit`; assert the awaited task ends with `SystemExit` (BaseException propagates).

    Cancellation (TestReconcilerCancellation — 3 tests):
    - `task.cancel()` while in `asyncio.sleep` causes the loop to log `reconciler.cancelled` and re-raise. `await task` (with `suppress(CancelledError)`) returns cleanly within a bounded timeout (e.g., 2s).
    - The CancelledError is re-raised (not swallowed) — verify `task.cancelled() is True` or `isinstance(task.exception(), asyncio.CancelledError)` after `with suppress(CancelledError): await task`.
    - The log message `reconciler.cancelled` is emitted (use structlog `capture_logs` from `structlog.testing`).

    Tests use **a real `app` fixture WITH session_factory** but **a fake `app.state.reconciler_event_lookup`** (a tiny class with a `get_event` method). We do not require Plan 06-08 (which wires the real lookup in lifespan); we manually set `app.state.reconciler_event_lookup = FakeLookup(...)` per-test.
  </behavior>
  <action>
    Step A — Replace `tests/bet_maker/jobs/test_reconciler_tick.py`:

    ```python
    """reconciler tick + error-isolation tests (Plan 06-07 / BM-12 / D-10..D-11)."""

    from __future__ import annotations

    import asyncio
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from uuid import UUID, uuid4

    import pytest
    from fastapi import FastAPI
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from bet_maker.facades.event_lookup import EventSnapshot
    from bet_maker.jobs import reconciler as reconciler_module
    from bet_maker.jobs.reconciler import _run_tick, reconciliation_loop
    from bet_maker.models.bet import Bet
    from bet_maker.schemas.bets import BetStatus
    from bet_maker.schemas.events import EventState


    class _FakeLookup:
        """Duck-typed EventLookup (CONTEXT.md D-08 — no Protocol gymnastics).

        seed(event_id, snapshot_or_none_or_raise) registers a behaviour for
        get_event. raise = sentinel callable.
        """

        def __init__(self) -> None:
            self._table: dict[UUID, EventSnapshot | None | Exception] = {}
            self.calls: list[UUID] = []

        def seed(self, event_id: UUID, val: EventSnapshot | None | Exception) -> None:
            self._table[event_id] = val

        async def get_event(self, event_id: UUID) -> EventSnapshot | None:
            self.calls.append(event_id)
            v = self._table.get(event_id)
            if isinstance(v, Exception):
                raise v
            return v


    def _snapshot(event_id: UUID, state: EventState) -> EventSnapshot:
        return EventSnapshot(
            event_id=event_id,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
            state=state,
        )


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerTick:
        async def test_run_tick_settles_finished_win_events(
            self,
            app: FastAPI,
            session_factory: async_sessionmaker,  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
            lookup = _FakeLookup()
            lookup.seed(event_id, _snapshot(event_id, EventState.FINISHED_WIN))
            app.state.reconciler_event_lookup = lookup
            await _run_tick(app)
            async with session_factory() as session:
                bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
            assert bet.status == BetStatus.WON
            assert bet.settled_via == "reconciler"

        async def test_run_tick_cancels_404_events(
            self,
            app: FastAPI,
            session_factory: async_sessionmaker,  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
            lookup = _FakeLookup()
            lookup.seed(event_id, None)  # 404 -> None
            app.state.reconciler_event_lookup = lookup
            await _run_tick(app)
            async with session_factory() as session:
                bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
            assert bet.status == BetStatus.CANCELLED
            assert bet.settled_via == "reconciler"

        async def test_run_tick_skips_new_state_events(
            self,
            app: FastAPI,
            session_factory: async_sessionmaker,  # type: ignore[type-arg]
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
            lookup = _FakeLookup()
            lookup.seed(event_id, _snapshot(event_id, EventState.NEW))
            app.state.reconciler_event_lookup = lookup
            await _run_tick(app)
            async with session_factory() as session:
                bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
            assert bet.status == BetStatus.PENDING  # unchanged

        async def test_run_tick_noop_when_no_pending(
            self, app: FastAPI
        ) -> None:
            lookup = _FakeLookup()
            app.state.reconciler_event_lookup = lookup
            await _run_tick(app)
            assert lookup.calls == []  # no HTTP calls made

        async def test_per_event_exception_isolation(
            self,
            app: FastAPI,
            session_factory: async_sessionmaker,  # type: ignore[type-arg]
        ) -> None:
            event_a, event_b = uuid4(), uuid4()
            async with session_factory.begin() as session:
                session.add(Bet(event_id=event_a, amount=Decimal("10.00")))
                session.add(Bet(event_id=event_b, amount=Decimal("10.00")))
            lookup = _FakeLookup()
            lookup.seed(event_a, RuntimeError("boom"))
            lookup.seed(event_b, _snapshot(event_b, EventState.FINISHED_WIN))
            app.state.reconciler_event_lookup = lookup
            await _run_tick(app)  # must not raise
            async with session_factory() as session:
                bet_a = (await session.execute(select(Bet).where(Bet.event_id == event_a))).scalar_one()
                bet_b = (await session.execute(select(Bet).where(Bet.event_id == event_b))).scalar_one()
            assert bet_a.status == BetStatus.PENDING  # failure isolated
            assert bet_b.status == BetStatus.WON      # other event still processed

        async def test_sleep_before_first_tick(
            self,
            app: FastAPI,
            monkeypatch: pytest.MonkeyPatch,
        ) -> None:
            """D-17: asyncio.sleep MUST run before the first _run_tick call.

            Replace _run_tick with a counter; replace asyncio.sleep with a
            counter that records its argument; run reconciliation_loop for
            a brief moment then cancel. Assert sleep was called BEFORE the
            first tick (i.e. tick_calls == 1 when sleep_calls == 1).
            """
            tick_calls: list[int] = []
            sleep_args: list[float] = []

            async def fake_tick(_app: FastAPI) -> None:
                tick_calls.append(len(sleep_args))

            real_sleep = asyncio.sleep

            async def fake_sleep(s: float) -> None:
                sleep_args.append(s)
                await real_sleep(0)  # actually yield to the event loop

            monkeypatch.setattr(reconciler_module, "_run_tick", fake_tick)
            monkeypatch.setattr(reconciler_module.asyncio, "sleep", fake_sleep)

            task = asyncio.create_task(
                reconciliation_loop(app, interval_s=0.01), name="reconciliation"
            )
            await real_sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Assert sleep was called at least once, and the first tick
            # observed >= 1 sleep already recorded.
            assert sleep_args, "asyncio.sleep was never called before first tick"
            if tick_calls:
                assert tick_calls[0] >= 1, (
                    "first tick ran before any sleep -- D-17 violated"
                )


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerErrorIsolation:
        async def test_loop_continues_after_tick_exception(
            self,
            app: FastAPI,
            monkeypatch: pytest.MonkeyPatch,
        ) -> None:
            calls = {"n": 0}

            async def flaky_tick(_app: FastAPI) -> None:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("first tick fails")

            monkeypatch.setattr(reconciler_module, "_run_tick", flaky_tick)
            task = asyncio.create_task(
                reconciliation_loop(app, interval_s=0.01), name="reconciliation"
            )
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert calls["n"] >= 2, f"loop died after first tick exception (calls={calls['n']})"

        async def test_loop_does_not_catch_basesystem_exits(
            self,
            app: FastAPI,
            monkeypatch: pytest.MonkeyPatch,
        ) -> None:
            async def raise_systemexit(_app: FastAPI) -> None:
                raise SystemExit(1)

            monkeypatch.setattr(reconciler_module, "_run_tick", raise_systemexit)
            task = asyncio.create_task(
                reconciliation_loop(app, interval_s=0.01), name="reconciliation"
            )
            with pytest.raises(SystemExit):
                await task
    ```

    Step B — Replace `tests/bet_maker/jobs/test_reconciler_cancellation.py`:

    ```python
    """reconciler CancelledError propagation (Plan 06-07 / BM-12 / D-10)."""

    from __future__ import annotations

    import asyncio
    from contextlib import suppress

    import pytest
    import structlog
    from fastapi import FastAPI

    from bet_maker.jobs.reconciler import reconciliation_loop


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerCancellation:
        async def test_cancelled_error_propagates_out_of_loop(
            self, app: FastAPI
        ) -> None:
            """task.cancel() while loop awaits sleep -> CancelledError propagates."""
            task = asyncio.create_task(
                reconciliation_loop(app, interval_s=10.0), name="reconciliation"
            )
            await asyncio.sleep(0.01)  # let the loop reach `await asyncio.sleep(interval_s)`
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        async def test_task_cancel_then_await_terminates_cleanly(
            self, app: FastAPI
        ) -> None:
            """The shutdown idiom (lifespan): cancel then `with suppress(CancelledError): await`."""
            task = asyncio.create_task(
                reconciliation_loop(app, interval_s=10.0), name="reconciliation"
            )
            await asyncio.sleep(0.01)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2.0)
            assert task.done()
            assert task.cancelled() or isinstance(task.exception(), asyncio.CancelledError)

        async def test_cancelled_error_logged_then_reraised(
            self, app: FastAPI
        ) -> None:
            """The 'reconciler.cancelled' log line is emitted before re-raise."""
            with structlog.testing.capture_logs() as captured:
                task = asyncio.create_task(
                    reconciliation_loop(app, interval_s=10.0), name="reconciliation"
                )
                await asyncio.sleep(0.01)
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=2.0)

            events = [record.get("event") for record in captured]
            assert "reconciler.cancelled" in events
    ```

    Notes:
    - `tests/bet_maker/conftest.py` already supplies a session-scoped `app` fixture with engine + sessionmaker pinned to testcontainers PG. We re-purpose it by overriding `app.state.reconciler_event_lookup` per-test (no autouse fixture for reconciler_event_lookup exists yet — Plan 06-08 will optionally add one).
    - The `_clear_event_lookup` autouse swaps the route-layer `event_lookup` to a Stub — it does NOT touch `reconciler_event_lookup`, so we are safe.
    - `monkeypatch.setattr(reconciler_module, "_run_tick", ...)` replaces the module attribute; the loop reads it as a closure variable (resolved at call time), so the patch takes effect for new invocations.
    - The cancellation tests use `await asyncio.sleep(0.01)` to ensure the loop has entered its first `await asyncio.sleep(interval_s)` before we call `task.cancel()`.
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/jobs/</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest -x -q tests/bet_maker/jobs/test_reconciler_tick.py` reports 8 passed (6 in TestReconcilerTick + 2 in TestReconcilerErrorIsolation)
    - `uv run pytest -x -q tests/bet_maker/jobs/test_reconciler_cancellation.py` reports 3 passed
    - `grep -c "Wave-0 stub" tests/bet_maker/jobs/test_reconciler_tick.py tests/bet_maker/jobs/test_reconciler_cancellation.py` == 0
    - `uv run mypy src/bet_maker/ tests/bet_maker/jobs/` exits 0
    - `uv run ruff check src/bet_maker/jobs/ tests/bet_maker/jobs/` exits 0
    - Full bet_maker suite green: `uv run pytest -x -q tests/bet_maker/ --ignore=tests/bet_maker/e2e --ignore=tests/bet_maker/integration --ignore=tests/bet_maker/test_lifespan_reconciler.py --ignore=tests/bet_maker/test_health_reconciler.py` exits 0 (lifespan/health/integration/e2e stubs still fail — they are Plan 06-08/09/10 territory).
  </acceptance_criteria>
  <done>Reconciler tick + cancellation tests green; full module behaves per CONTEXT.md D-02/D-10/D-11/D-17.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| reconciler tick → DB (read PENDING list) | Read-only — minimal lock contention |
| reconciler per-event → DB (UPDATE via settle/cancel) | Mutating; concurrent with consumer thread; idempotency from underlying interactors |
| reconciler → line-provider HTTP | Outbound HTTP; LineProviderUnavailable bubbles up via per-event try/except |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-07-01 | DoS (loop dies silently) | reconciliation_loop | mitigate | `except Exception: log.exception + continue`; test_loop_continues_after_tick_exception asserts |
| T-06-07-02 | DoS (BaseException swallowed) | loop except blocks | mitigate | `except Exception` is narrower than `BaseException`; test_loop_does_not_catch_basesystem_exits asserts SystemExit propagates |
| T-06-07-03 | DoS (cold-start spike) | first tick timing | mitigate | `await asyncio.sleep(interval_s)` FIRST; test_sleep_before_first_tick asserts |
| T-06-07-04 | Tampering (per-event poison stops tick) | per-event try/except | mitigate | Per-event try/except isolates failures; test_per_event_exception_isolation asserts |
| T-06-07-05 | Information Disclosure | structlog log content | accept | event_id and bet_ids are non-secret; no PII |
| T-06-07-06 | Repudiation (untraceable settle) | settled_via column | mitigate | `settled_via='reconciler'` propagates through both branches; DB persists attribution |
</threat_model>

<verification>
- `uv run pytest -x -q tests/bet_maker/jobs/` exits 0 (11 tests).
- `uv run mypy src/` exits 0.
- `uv run ruff check src/ tests/` exits 0.
- `uv run pytest -x -q tests/bet_maker/test_settle.py tests/bet_maker/interactors/test_cancel_bets_for_event.py tests/bet_maker/repositories/test_get_pending_event_ids.py` exits 0 — no regression on dependencies.
</verification>

<success_criteria>
- `src/bet_maker/jobs/reconciler.py` ships with `reconciliation_loop` + `_run_tick` + `_reconcile_event` satisfying CONTEXT.md D-02/D-10/D-11/D-17/D-18.
- 11 reconciler tests pass (8 tick + 3 cancellation).
- mypy strict + ruff clean.
- No regressions on prior plans.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-07-SUMMARY.md` with the reconciler.py LOC count and the pytest pass count.
</output>

## Decision Coverage

- D-02: Per `event_id` decision branch table — `FINISHED_*` → settle, `None` → cancel, `NEW` → skip.
- D-05: Reconciler does NOT special-case `LineProviderUnavailable`; per-event `try/except Exception` captures it identically to any transient error → log + continue, next tick retries.
- D-08: No `EventLookup` Protocol abstraction — duck-typed concrete `HttpEventLookup` (or test fake) is passed in; symmetry with request-scope interactors is intentionally NOT mirrored for background tasks.
- D-10: Two-level `try/except`: outer `except asyncio.CancelledError: raise` BEFORE `except Exception: log+continue` — R8 + liveness guarantee.
- D-11: `_run_tick(app)` body: one read-only UoW for `get_pending_event_ids`, then per-event try/except wrapping `_reconcile_event(sessionmaker, lookup, event_id)`.
- D-12: PG `OperationalError` raised inside `get_pending_event_ids` propagates out of inner UoW into outer except → loop continues, next tick retries (no separate handler).
- D-17: `await asyncio.sleep(interval_s)` runs BEFORE the first `_run_tick` (no cold-start noise; gives lifespan time to finish wiring).
- D-18: `asyncio.create_task(..., name="reconciliation")` — fixed task name for grep/observability.
- D-20: Unit tests `tests/bet_maker/jobs/test_reconciler_tick.py` + `test_reconciler_cancellation.py` cover loop, tick, error isolation, `CancelledError` re-raise.
