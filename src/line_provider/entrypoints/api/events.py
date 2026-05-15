from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from line_provider.facades.deps import EventBusDep, StoreDep
from line_provider.helpers.state_machine import TransitionForbiddenError
from line_provider.infrastructure.store.in_memory import (
    EventAlreadyExistsError,
    EventNotFoundError,
)
from line_provider.interactors.create_event import create_event
from line_provider.interactors.set_event_state import set_event_state
from line_provider.schemas.events import EventCreate, EventRead, EventUpdate
from line_provider.selectors.get_event_by_id import get_event_by_id
from line_provider.selectors.list_active_events import list_active_events

router = APIRouter(tags=["events"])


@router.post(
    "/event",
    status_code=status.HTTP_201_CREATED,
    response_model=EventRead,
)
async def post_event(body: EventCreate, store: StoreDep) -> EventRead:
    try:
        event = await create_event(store, body=body)
    except EventAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return EventRead.model_validate(event.model_dump())


@router.put(
    "/event/{event_id}",
    status_code=status.HTTP_200_OK,
    response_model=EventRead,
)
async def put_event(
    event_id: UUID,
    body: EventUpdate,
    request: Request,
    store: StoreDep,
    event_bus: EventBusDep,
) -> EventRead:
    correlation_id = request.headers.get("X-Request-ID", "no-request-id")
    try:
        event = await set_event_state(
            store,
            event_bus,
            event_id=event_id,
            coefficient=body.coefficient,
            deadline=body.deadline,
            new_state=body.state,
            correlation_id=correlation_id,
        )
    except EventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    except TransitionForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"state transition {exc.current.value}->{exc.new.value} not allowed",
        ) from exc
    return EventRead.model_validate(event.model_dump())


@router.get(
    "/event/{event_id}",
    response_model=EventRead,
)
async def get_event(event_id: UUID, store: StoreDep) -> EventRead:
    event = await get_event_by_id(store, event_id=event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return EventRead.model_validate(event.model_dump())


@router.get(
    "/events",
    response_model=list[EventRead],
)
async def list_events(store: StoreDep) -> list[EventRead]:
    events = await list_active_events(store)
    return [EventRead.model_validate(e.model_dump()) for e in events]
