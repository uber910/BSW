"""Unit tests for line_provider.helpers.state_machine.

The state machine forbids reverse transitions ``FINISHED_* -> NEW`` and
cross-FINISHED transitions; allowed: ``NEW -> FINISHED_WIN |
FINISHED_LOSE`` plus the no-op (``current == new``). The 422 wording
carries "state transition X->Y not allowed". The no-op state is allowed
(publish is skipped at the interactor level).
"""

from __future__ import annotations

import pytest

from line_provider.helpers.state_machine import (
    ALLOWED_TRANSITIONS,
    TransitionForbiddenError,
    is_transition_allowed,
)
from line_provider.schemas.events import EventState


@pytest.mark.parametrize(
    ("current", "new", "allowed"),
    [
        (EventState.NEW, EventState.NEW, True),
        (EventState.NEW, EventState.FINISHED_WIN, True),
        (EventState.NEW, EventState.FINISHED_LOSE, True),
        (EventState.FINISHED_WIN, EventState.FINISHED_WIN, True),
        (EventState.FINISHED_WIN, EventState.NEW, False),
        (EventState.FINISHED_WIN, EventState.FINISHED_LOSE, False),
        (EventState.FINISHED_LOSE, EventState.FINISHED_LOSE, True),
        (EventState.FINISHED_LOSE, EventState.NEW, False),
        (EventState.FINISHED_LOSE, EventState.FINISHED_WIN, False),
    ],
)
def test_is_transition_allowed_table(current: EventState, new: EventState, allowed: bool) -> None:
    """State-machine 3x3 truth table."""
    assert is_transition_allowed(current, new) is allowed


def test_allowed_transitions_is_frozenset_with_two_entries() -> None:
    """ALLOWED_TRANSITIONS is immutable and has exactly two forward transitions."""
    assert isinstance(ALLOWED_TRANSITIONS, frozenset)
    assert len(ALLOWED_TRANSITIONS) == 2
    assert (EventState.NEW, EventState.FINISHED_WIN) in ALLOWED_TRANSITIONS
    assert (EventState.NEW, EventState.FINISHED_LOSE) in ALLOWED_TRANSITIONS


def test_transition_forbidden_error_carries_states_and_message() -> None:
    """TransitionForbiddenError preserves current/new + human-readable message."""
    err = TransitionForbiddenError(EventState.FINISHED_WIN, EventState.NEW)
    assert err.current == EventState.FINISHED_WIN
    assert err.new == EventState.NEW
    message = str(err)
    assert "FINISHED_WIN" in message
    assert "NEW" in message
    assert "not allowed" in message


def test_transition_forbidden_error_is_exception_subclass() -> None:
    """TransitionForbiddenError must be a plain Exception subclass (raisable, catchable)."""
    with pytest.raises(TransitionForbiddenError):
        raise TransitionForbiddenError(EventState.FINISHED_WIN, EventState.NEW)
