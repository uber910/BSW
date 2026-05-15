from __future__ import annotations

from line_provider.schemas.events import EventState

ALLOWED_TRANSITIONS: frozenset[tuple[EventState, EventState]] = frozenset(
    {
        (EventState.NEW, EventState.FINISHED_WIN),
        (EventState.NEW, EventState.FINISHED_LOSE),
    }
)


class TransitionForbiddenError(Exception):
    def __init__(self, current: EventState, new: EventState) -> None:
        self.current = current
        self.new = new
        super().__init__(f"state transition {current.value}->{new.value} not allowed")


def is_transition_allowed(current: EventState, new: EventState) -> bool:
    if current == new:
        return True
    return (current, new) in ALLOWED_TRANSITIONS
