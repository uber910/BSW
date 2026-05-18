"""Reconciliation background task (Phase 6 / BM-12).

Composition module — no new business rules; it merely dispatches
PENDING bets to existing interactors based on what line-provider
reports for each event_id:

| LP response                          | reconciler action                               |
|--------------------------------------|-------------------------------------------------|
| EventSnapshot(state=FINISHED_WIN)    | settle_bets_for_event(... WON,  via=reconciler) |
| EventSnapshot(state=FINISHED_LOSE)   | settle_bets_for_event(... LOST, via=reconciler) |
| None (404 from LP)                   | cancel_bets_for_event(... CANCELLED, via=reconciler) |
| EventSnapshot(state=NEW)             | skip (LP has not transitioned yet — try again)  |

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
            raise
        except Exception:
            _log.exception("reconciler.tick.failed")


async def _run_tick(app: FastAPI) -> None:
    """One tick of the loop. Read work-list, then process each event_id.

    Read-only UoW for the work-list (D-11): short transaction, minimal
    lock contention with the consumer (Phase 5). Per-event UoW happens
    inside _reconcile_event so a long-running event lookup does not
    hold an open DB transaction.
    """
    sessionmaker = cast("async_sessionmaker[AsyncSession]", app.state.sessionmaker)
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
            _log.exception("reconciler.event.failed", event_id=str(event_id))
            continue


async def _reconcile_event(
    sessionmaker: async_sessionmaker[AsyncSession],
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
        await cancel_bets_for_event(uow, event_id=event_id, cancelled_via="reconciler")
        _log.info("reconciler.event.cancelled", event_id=str(event_id))
        return

    if snapshot.state == EventState.NEW:
        _log.debug("reconciler.event.still_new", event_id=str(event_id))
        return

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
