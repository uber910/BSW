from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from line_provider.facades.event_bus import EventBus
from line_provider.helpers.state_machine import (
    TransitionForbiddenError,
    is_transition_allowed,
)
from line_provider.infrastructure.store.in_memory import (
    EventNotFoundError,
    InMemoryEventStore,
)
from line_provider.messaging.routing import EVENT_FINISHED_LOSE, EVENT_FINISHED_WIN
from line_provider.schemas.events import Event, EventState
from line_provider.schemas.messages import EventFinishedMessage, EventTerminalState

_TERMINAL_TO_ROUTING: dict[EventState, str] = {
    EventState.FINISHED_WIN: EVENT_FINISHED_WIN,
    EventState.FINISHED_LOSE: EVENT_FINISHED_LOSE,
}


async def set_event_state(
    store: InMemoryEventStore,
    event_bus: EventBus,
    *,
    event_id: UUID,
    coefficient: Decimal,
    deadline: datetime,
    new_state: EventState,
    correlation_id: str,
) -> Event:
    current = await store.get_by_id(event_id)
    if current is None:
        raise EventNotFoundError(str(event_id))
    if not is_transition_allowed(current.state, new_state):
        raise TransitionForbiddenError(current.state, new_state)

    new_event, previous_state = await store.update(
        event_id,
        coefficient=coefficient,
        deadline=deadline,
        state=new_state,
    )

    if previous_state == EventState.NEW and new_state in _TERMINAL_TO_ROUTING:
        await event_bus.publish(
            EventFinishedMessage(
                event_id=new_event.event_id,
                new_state=EventTerminalState(new_state.value),
                coefficient=new_event.coefficient,
                occurred_at=new_event.deadline,
                correlation_id=correlation_id,
            ),
            routing_key=_TERMINAL_TO_ROUTING[new_state],
        )
    return new_event
