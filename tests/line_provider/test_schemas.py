"""Unit tests for line_provider.schemas.*.

Event domain model (``event_id=UUID4``, ``coefficient=Decimal`` 2dp >0,
``deadline`` tz-aware, ``state``) and HTTP schemas (``EventCreate``,
``EventUpdate``, ``EventRead``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from line_provider.helpers.money import quantize_coefficient
from line_provider.schemas.events import (
    Event,
    EventCreate,
    EventRead,
    EventState,
    EventUpdate,
)
from line_provider.schemas.messages import EventFinishedMessage, EventTerminalState


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


def _past() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=1)


class TestQuantize:
    def test_quantize_pads_to_two_places(self) -> None:
        """quantize_coefficient('10') -> '10.00'."""
        assert quantize_coefficient(Decimal("10")) == Decimal("10.00")
        assert quantize_coefficient(Decimal("10")).as_tuple().exponent == -2

    def test_quantize_keeps_two_places(self) -> None:
        """quantize_coefficient('1.50') stays '1.50'."""
        assert quantize_coefficient(Decimal("1.50")) == Decimal("1.50")

    def test_quantize_rounds_half_up(self) -> None:
        """quantize_coefficient rounds to 2dp using ROUND_HALF_UP."""
        assert quantize_coefficient(Decimal("1.235")) == Decimal("1.24")
        assert quantize_coefficient(Decimal("1.234")) == Decimal("1.23")


class TestEventCreate:
    def test_happy_path(self) -> None:
        """EventCreate accepts UUID4 + Decimal('10.50') + future deadline."""
        ec = EventCreate(
            event_id=uuid4(),
            coefficient=Decimal("10.50"),
            deadline=_future(),
        )
        assert isinstance(ec.event_id, UUID)
        assert ec.coefficient == Decimal("10.50")

    def test_quantizes_int_string_input(self) -> None:
        """'10' string input quantized to Decimal('10.00')."""
        ec = EventCreate(
            event_id=uuid4(),
            coefficient=Decimal("10"),
            deadline=_future(),
        )
        assert ec.coefficient == Decimal("10.00")
        assert ec.coefficient.as_tuple().exponent == -2

    def test_rejects_non_uuid(self) -> None:
        """event_id must be a UUID, not arbitrary str."""
        with pytest.raises(ValidationError):
            EventCreate.model_validate(
                {
                    "event_id": "not-a-uuid",
                    "coefficient": "10.50",
                    "deadline": _future().isoformat(),
                }
            )

    def test_rejects_zero_coefficient(self) -> None:
        """coefficient must be > 0."""
        with pytest.raises(ValidationError):
            EventCreate(event_id=uuid4(), coefficient=Decimal("0"), deadline=_future())

    def test_rejects_negative_coefficient(self) -> None:
        """coefficient must be > 0."""
        with pytest.raises(ValidationError):
            EventCreate(event_id=uuid4(), coefficient=Decimal("-1.00"), deadline=_future())

    def test_rejects_more_than_two_decimal_places(self) -> None:
        """coefficient must have <= 2 decimal places (rejected before quantize)."""
        with pytest.raises(ValidationError):
            EventCreate(event_id=uuid4(), coefficient=Decimal("10.123"), deadline=_future())

    def test_rejects_naive_deadline(self) -> None:
        """deadline must be tz-aware."""
        naive = datetime.now() + timedelta(hours=1)
        with pytest.raises(ValidationError):
            EventCreate(event_id=uuid4(), coefficient=Decimal("1.00"), deadline=naive)

    def test_rejects_past_deadline(self) -> None:
        """deadline > now required on CREATE."""
        with pytest.raises(ValidationError):
            EventCreate(event_id=uuid4(), coefficient=Decimal("1.00"), deadline=_past())

    def test_rejects_extra_field(self) -> None:
        """EventCreate forbids extra fields."""
        with pytest.raises(ValidationError):
            EventCreate.model_validate(
                {
                    "event_id": str(uuid4()),
                    "coefficient": "1.00",
                    "deadline": _future().isoformat(),
                    "state": "NEW",
                }
            )


class TestEventUpdate:
    def test_happy_path(self) -> None:
        """EventUpdate accepts coefficient/deadline/state."""
        eu = EventUpdate(
            coefficient=Decimal("2.00"),
            deadline=_future(),
            state=EventState.FINISHED_WIN,
        )
        assert eu.state == EventState.FINISHED_WIN

    def test_accepts_past_deadline(self) -> None:
        """PUT does NOT validate deadline > now (pinned once, no clock drift)."""
        past = _past()
        eu = EventUpdate(coefficient=Decimal("2.00"), deadline=past, state=EventState.FINISHED_WIN)
        assert eu.deadline == past

    def test_rejects_event_id_in_body(self) -> None:
        """event_id in PUT body forbidden (extra='forbid')."""
        with pytest.raises(ValidationError):
            EventUpdate.model_validate(
                {
                    "event_id": str(uuid4()),
                    "coefficient": "1.00",
                    "deadline": _future().isoformat(),
                    "state": "NEW",
                }
            )


class TestEvent:
    def test_frozen(self) -> None:
        """Event is frozen — setattr raises ValidationError."""
        event = Event(
            event_id=uuid4(),
            coefficient=Decimal("1.50"),
            deadline=_future(),
            state=EventState.NEW,
        )
        with pytest.raises(ValidationError):
            event.coefficient = Decimal("2.50")  # type: ignore[misc]


class TestEventRead:
    def test_from_event(self) -> None:
        """EventRead.model_validate(event) cross-model conversion."""
        event = Event(
            event_id=uuid4(),
            coefficient=Decimal("1.50"),
            deadline=_future(),
            state=EventState.NEW,
        )
        read = EventRead.model_validate(event.model_dump())
        assert read.event_id == event.event_id
        assert read.state == EventState.NEW


class TestEventFinishedMessage:
    def test_happy_path(self) -> None:
        """EventFinishedMessage accepts all fields, default schema_version=1."""
        msg = EventFinishedMessage(
            event_id=uuid4(),
            new_state=EventTerminalState.FINISHED_WIN,
            coefficient=Decimal("2.00"),
            occurred_at=_future(),
            correlation_id="req-abc",
        )
        assert msg.schema_version == 1

    def test_frozen(self) -> None:
        """EventFinishedMessage is frozen."""
        msg = EventFinishedMessage(
            event_id=uuid4(),
            new_state=EventTerminalState.FINISHED_WIN,
            coefficient=Decimal("2.00"),
            occurred_at=_future(),
            correlation_id="req-abc",
        )
        with pytest.raises(ValidationError):
            msg.schema_version = 2  # type: ignore[misc]

    def test_rejects_schema_version_zero(self) -> None:
        """schema_version must be >= 1."""
        with pytest.raises(ValidationError):
            EventFinishedMessage(
                schema_version=0,
                event_id=uuid4(),
                new_state=EventTerminalState.FINISHED_WIN,
                coefficient=Decimal("2.00"),
                occurred_at=_future(),
                correlation_id="req-abc",
            )

    def test_rejects_extra_field(self) -> None:
        """extra='forbid'."""
        with pytest.raises(ValidationError):
            EventFinishedMessage.model_validate(
                {
                    "event_id": str(uuid4()),
                    "new_state": "FINISHED_WIN",
                    "coefficient": "2.00",
                    "occurred_at": _future().isoformat(),
                    "correlation_id": "req-abc",
                    "extra_field": "evil",
                }
            )

    def test_terminal_state_values_match_event_state(self) -> None:
        """EventTerminalState values are a subset of EventState values."""
        assert EventTerminalState.FINISHED_WIN.value == EventState.FINISHED_WIN.value
        assert EventTerminalState.FINISHED_LOSE.value == EventState.FINISHED_LOSE.value
