"""Reconciliation background task.

Composition module — no new business rules; it merely dispatches
PENDING bets to existing interactors based on what line-provider
reports for each event_id:

| LP response                          | reconciler action                               |
|--------------------------------------|-------------------------------------------------|
| EventSnapshot(state=FINISHED_WIN)    | settle_bets_for_event(... WON,  via=reconciler) |
| EventSnapshot(state=FINISHED_LOSE)   | settle_bets_for_event(... LOST, via=reconciler) |
| None (404 from LP)                   | cancel_bets_for_event(... CANCELLED, via=reconciler) |
| EventSnapshot(state=NEW)             | skip (LP has not transitioned yet — try again)  |

Defence-in-depth: even if every consumer dispatch fails silently, this
loop sweeps every PENDING bet within `RECONCILIATION_INTERVAL_S`
seconds. Idempotent by construction because the underlying interactors
are idempotent (FOR UPDATE SKIP LOCKED + status filter).

Error model:
- The outer while-True body has TWO except blocks:
    1. asyncio.CancelledError -> log and re-raise (clean shutdown).
    2. Exception                 -> log.exception and continue.
  BaseException other than CancelledError is NEVER caught.
- Per-event try/except inside _run_tick isolates failures so one bad
  event_id does not abort the whole tick.

Sleep ordering: `await asyncio.sleep(interval_s)` is the FIRST awaited
operation in each iteration — no cold-start noise, predictable cadence.

Task name: `asyncio.create_task(..., name="reconciliation")` set by
lifespan; grep-able in logs and asyncio debug output.
"""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import UUID

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.contextvars import bound_contextvars

from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.interactors.cancel_bets_for_event import cancel_bets_for_event
from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
from bet_maker.schemas.events import EventState
from bet_maker.schemas.messages import EventTerminalState
from bet_maker.selectors.get_pending_event_ids import get_pending_event_ids
from bet_maker.uow.postgres import PostgresUnitOfWork

_log = structlog.get_logger().bind(task="reconciliation")


async def reconciliation_loop(app: FastAPI, *, interval_s: float) -> None:
    """Outer infinite loop. Sleep first, then tick.

    Two-tier try/except: CancelledError is caught explicitly BEFORE
    Exception so a future refactor that adds a `try` deeper in the call
    stack cannot accidentally swallow it.
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

    Read-only session for the work-list — no UoW wrapper because
    ``get_pending_event_ids`` is a single SELECT DISTINCT with no
    ``FOR UPDATE`` (D-05 selectors take ``AsyncSession`` directly). A bare
    ``sessionmaker()`` context avoids the empty COMMIT that
    ``async_sessionmaker.begin()`` would send every tick.

    Per-event UoW happens inside ``_reconcile_event`` so a long-running event
    lookup does not hold an open DB transaction.
    """
    sessionmaker = cast("async_sessionmaker[AsyncSession]", app.state.sessionmaker)
    lookup = cast(HttpEventLookup, app.state.reconciler_event_lookup)
    async with sessionmaker() as session:
        event_ids = await get_pending_event_ids(session)

    if not event_ids:
        _log.debug("reconciler.tick.noop")
        return

    for event_id in event_ids:
        # Bind event_id into structlog contextvars for the whole reconciliation
        # of this event_id so child logs (selectors, interactors, HTTP client)
        # inherit it. Mirrors the consumer handler pattern in
        # api/messaging.py:154-194.
        with bound_contextvars(event_id=str(event_id)):
            try:
                await _reconcile_event(sessionmaker, lookup, event_id)
            except Exception:
                _log.exception("reconciler.event.failed")
                continue


async def _reconcile_event(
    sessionmaker: async_sessionmaker[AsyncSession],
    lookup: HttpEventLookup,
    event_id: UUID,
) -> None:
    """Decision tree for one event_id.

    FINISHED_WIN | FINISHED_LOSE -> settle
    None (LP 404)                -> cancel
    NEW                           -> skip
    other (future LP state)       -> log + skip (NOT raise -- avoids ValueError
                                    noise from ``EventTerminalState(...)`` if
                                    ``EventState`` gains additional non-terminal
                                    states in v2).
    """
    snapshot = await lookup.get_event(event_id)

    if snapshot is None:
        uow = PostgresUnitOfWork(sessionmaker)
        await cancel_bets_for_event(uow, event_id=event_id, cancelled_via="reconciler")
        _log.info("reconciler.event.cancelled", event_id=str(event_id))
        return

    # Explicit whitelist of terminal states. Non-terminal states (NEW today;
    # future CANCELLED_BY_LP / POSTPONED / etc.) skip rather than raise
    # ``ValueError`` from ``EventTerminalState(snapshot.state.value)``, which
    # would otherwise log as ``reconciler.event.failed`` every tick until LP
    # transitions to a terminal state and confuse it with real DB/HTTP errors.
    match snapshot.state:
        case EventState.FINISHED_WIN:
            terminal_state = EventTerminalState.FINISHED_WIN
        case EventState.FINISHED_LOSE:
            terminal_state = EventTerminalState.FINISHED_LOSE
        case EventState.NEW:
            _log.debug("reconciler.event.still_new", event_id=str(event_id))
            return
        case _:
            _log.warning(
                "reconciler.event.unexpected_state",
                event_id=str(event_id),
                state=snapshot.state.value,
            )
            return

    uow = PostgresUnitOfWork(sessionmaker)
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
