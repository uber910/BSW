from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Request, status

from line_provider.facades.deps import EventBusDep, StoreDep
from line_provider.helpers.state_machine import TransitionForbiddenError
from line_provider.infrastructure.store.in_memory import (
    EventAlreadyExistsError,
    EventNotFoundError,
)
from line_provider.interactors.create_event import create_event
from line_provider.interactors.set_event_state import set_event_state
from line_provider.schemas.errors import ErrorDetail
from line_provider.schemas.events import EventCreate, EventRead, EventUpdate
from line_provider.selectors.get_event_by_id import get_event_by_id
from line_provider.selectors.list_active_events import list_active_events

router = APIRouter(tags=["events"])


@router.post(
    "/event",
    status_code=status.HTTP_201_CREATED,
    response_model=EventRead,
    summary="Create new event in NEW state",
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorDetail,
            "description": "Event with this event_id already exists.",
        },
    },
)
async def post_event(
    store: StoreDep,
    body: Annotated[
        EventCreate,
        Body(
            openapi_examples={
                "happy": {
                    "summary": "Create new bettable event",
                    "description": "Successful creation of a NEW event in the future.",
                    "value": {
                        "event_id": "00000000-0000-0000-0000-000000000001",
                        "coefficient": "1.50",
                        "deadline": "2030-01-01T00:00:00+00:00",
                    },
                },
            },
        ),
    ],
) -> EventRead:
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
    summary="Update event (state transition NEW -> FINISHED_WIN/LOSE)",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorDetail,
            "description": "Event with this event_id does not exist.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorDetail,
            "description": "State transition not allowed (e.g. FINISHED -> NEW).",
        },
    },
)
async def put_event(
    event_id: UUID,
    request: Request,
    store: StoreDep,
    event_bus: EventBusDep,
    body: Annotated[
        EventUpdate,
        Body(
            openapi_examples={
                "finish_win": {
                    "summary": "Transition NEW event to FINISHED_WIN",
                    "value": {
                        "coefficient": "1.50",
                        "deadline": "2030-01-01T00:00:00+00:00",
                        "state": "FINISHED_WIN",
                    },
                },
                "finish_lose": {
                    "summary": "Transition NEW event to FINISHED_LOSE",
                    "value": {
                        "coefficient": "1.50",
                        "deadline": "2030-01-01T00:00:00+00:00",
                        "state": "FINISHED_LOSE",
                    },
                },
            },
        ),
    ],
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
    summary="Fetch event by id",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorDetail,
            "description": "Event with this event_id does not exist.",
        },
    },
)
async def get_event(event_id: UUID, store: StoreDep) -> EventRead:
    event = await get_event_by_id(store, event_id=event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return EventRead.model_validate(event.model_dump())


@router.get(
    "/events",
    response_model=list[EventRead],
    summary="List active events (deadline in future, state == NEW)",
)
async def list_events(store: StoreDep) -> list[EventRead]:
    events = await list_active_events(store)
    return [EventRead.model_validate(e.model_dump()) for e in events]
