"""Unit tests for bet_maker schemas + helpers/money.

BM-05 / D-04: BetCreate.amount = Annotated[Decimal, Field(gt=0, max_digits=12,
decimal_places=2), AfterValidator(quantize_amount)].
BM-05 / D-19: Decimal serialization as string "10.00" (Pydantic v2 default,
Pitfall A4 mitigation: tests compare strings, never floats).
BM-06 / D-12: EventState duplicated from line_provider (value-parity).
D-20 / P2 D-13: BetStatus is (str, Enum), not StrEnum (Python 3.10).
D-30: helpers/status.event_state_to_bet_status is a P5 stub.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from bet_maker.helpers.money import quantize_amount
from bet_maker.helpers.status import event_state_to_bet_status
from bet_maker.schemas.bets import BetCreate, BetRead, BetStatus
from bet_maker.schemas.events import EventRead, EventState
from line_provider.schemas.events import EventState as LpEventState


class TestQuantize:
    """D-04 / D-19: quantize_amount normalises amounts to 2dp ROUND_HALF_UP."""

    def test_pad_zeros(self) -> None:
        """`Decimal('10')` -> `Decimal('10.00')`."""
        assert quantize_amount(Decimal("10")) == Decimal("10.00")
        assert str(quantize_amount(Decimal("10"))) == "10.00"

    def test_keep_two_places(self) -> None:
        """Already-2dp value passes through unchanged."""
        assert quantize_amount(Decimal("10.42")) == Decimal("10.42")

    def test_round_half_up(self) -> None:
        """ROUND_HALF_UP, not banker's: `10.005` -> `10.01`, `10.125` -> `10.13`."""
        assert quantize_amount(Decimal("10.005")) == Decimal("10.01")
        assert quantize_amount(Decimal("10.125")) == Decimal("10.13")


class TestBetCreate:
    """BM-05 / D-04: BetCreate validates amount and forbids extra fields."""

    def test_happy_path_quantizes(self) -> None:
        """BM-05: `amount='10'` is accepted and quantized to `Decimal('10.00')`."""
        body = BetCreate(event_id=uuid4(), amount=Decimal("10"))
        assert body.amount == Decimal("10.00")

    def test_string_input_quantizes(self) -> None:
        """BM-05: JSON-like `amount='10'` (string) coerces to Decimal then quantizes."""
        body = BetCreate.model_validate({"event_id": str(uuid4()), "amount": "10"})
        assert body.amount == Decimal("10.00")

    def test_three_decimal_places_rejected(self) -> None:
        """D-04: `amount='10.123'` -> ValidationError type=decimal_max_places."""
        with pytest.raises(ValidationError) as exc:
            BetCreate.model_validate({"event_id": str(uuid4()), "amount": "10.123"})
        assert "decimal_max_places" in str(exc.value)

    def test_zero_rejected(self) -> None:
        """D-04: `amount='0'` -> ValidationError type=greater_than (gt=0, not ge)."""
        with pytest.raises(ValidationError) as exc:
            BetCreate.model_validate({"event_id": str(uuid4()), "amount": "0"})
        assert "greater_than" in str(exc.value)

    def test_negative_rejected(self) -> None:
        """D-04: `amount='-5'` -> ValidationError type=greater_than."""
        with pytest.raises(ValidationError) as exc:
            BetCreate.model_validate({"event_id": str(uuid4()), "amount": "-5"})
        assert "greater_than" in str(exc.value)

    def test_invalid_uuid_rejected(self) -> None:
        """T-03-3: malformed event_id rejected before reaching SQL layer."""
        with pytest.raises(ValidationError):
            BetCreate.model_validate({"event_id": "not-a-uuid", "amount": "10"})

    def test_extra_field_rejected(self) -> None:
        """D-01: coefficient is NOT a field on BetCreate; extra='forbid' rejects it."""
        with pytest.raises(ValidationError) as exc:
            BetCreate.model_validate(
                {
                    "event_id": str(uuid4()),
                    "amount": "10",
                    "coefficient": "1.5",
                }
            )
        error_str = str(exc.value)
        assert "Extra inputs are not permitted" in error_str or "extra_forbidden" in error_str

    def test_missing_amount_rejected(self) -> None:
        """D-04: amount is required."""
        with pytest.raises(ValidationError):
            BetCreate.model_validate({"event_id": str(uuid4())})

    def test_oversized_amount_rejected(self) -> None:
        """T-03-1 / D-04: max_digits=12 caps at 999_999_999_999.99."""
        with pytest.raises(ValidationError) as exc:
            BetCreate.model_validate({"event_id": str(uuid4()), "amount": "1000000000000.00"})
        assert "decimal" in str(exc.value).lower() or "max_digits" in str(exc.value).lower()


class TestBetRead:
    """BM-05 / D-19 / D-05: BetRead from_attributes + Decimal as JSON string."""

    def test_from_attributes_accepts_orm_like(self) -> None:
        """D-14: BetRead.model_validate(orm_obj, from_attributes=True) works."""
        orm_like = SimpleNamespace(
            id=uuid4(),
            event_id=uuid4(),
            amount=Decimal("10.00"),
            status=BetStatus.PENDING,
            created_at=datetime.now(),
        )
        read = BetRead.model_validate(orm_like, from_attributes=True)
        assert isinstance(read.id, UUID)
        assert read.status == BetStatus.PENDING
        assert read.amount == Decimal("10.00")

    def test_decimal_serializes_as_string(self) -> None:
        """D-19 / Pitfall A4: amount serialises as string '10.00', not float."""
        orm_like = SimpleNamespace(
            id=uuid4(),
            event_id=uuid4(),
            amount=Decimal("10.00"),
            status=BetStatus.PENDING,
            created_at=datetime.now(),
        )
        read = BetRead.model_validate(orm_like, from_attributes=True)
        payload = json.loads(read.model_dump_json())
        assert payload["amount"] == "10.00", f"expected string '10.00', got {payload['amount']!r}"
        assert isinstance(payload["amount"], str)


class TestEventRead:
    """BM-04 / D-13: EventRead is the bet-maker-side mirror of LP GET /events item shape."""

    def test_event_read_parses_lp_payload(self) -> None:
        """D-13: EventRead.model_validate accepts the canonical LP payload shape."""
        payload = {
            "event_id": "11111111-1111-1111-1111-111111111111",
            "coefficient": "2.50",
            "deadline": "2026-12-01T12:00:00+00:00",
            "state": "NEW",
        }
        read = EventRead.model_validate(payload)
        assert isinstance(read.event_id, UUID)
        assert read.event_id == UUID("11111111-1111-1111-1111-111111111111")
        assert read.coefficient == Decimal("2.50")
        assert isinstance(read.coefficient, Decimal)
        assert read.deadline.tzinfo is not None
        assert read.state == EventState.NEW

    def test_event_read_extra_forbid(self) -> None:
        """D-13 / Pattern D: extra fields rejected to surface LP schema drift loud."""
        payload = {
            "event_id": str(uuid4()),
            "coefficient": "1.50",
            "deadline": "2026-12-01T12:00:00+00:00",
            "state": "NEW",
            "unknown": "x",
        }
        with pytest.raises(ValidationError):
            EventRead.model_validate(payload)

    def test_event_read_frozen(self) -> None:
        """D-13: EventRead is frozen -- mutations rejected post-construction."""
        read = EventRead.model_validate(
            {
                "event_id": str(uuid4()),
                "coefficient": "2.00",
                "deadline": "2026-12-01T12:00:00+00:00",
                "state": "NEW",
            }
        )
        with pytest.raises(ValidationError):
            read.event_id = uuid4()  # type: ignore[misc]

    def test_event_read_decimal_serializes_as_string(self) -> None:
        """D-13 / Pitfall A4: coefficient serialises as JSON string '2.50' (not float)."""
        read = EventRead.model_validate(
            {
                "event_id": str(uuid4()),
                "coefficient": "2.50",
                "deadline": "2026-12-01T12:00:00+00:00",
                "state": "NEW",
            }
        )
        payload = json.loads(read.model_dump_json())
        assert payload["coefficient"] == "2.50"
        assert isinstance(payload["coefficient"], str)


class TestEnums:
    """D-12 / D-20: EventState (duplicated) and BetStatus enum invariants."""

    def test_eventstate_has_three_members(self) -> None:
        """D-12: EventState parity with line_provider -- 3 members, exact names."""
        members = {m.name: m.value for m in EventState}
        assert members == {
            "NEW": "NEW",
            "FINISHED_WIN": "FINISHED_WIN",
            "FINISHED_LOSE": "FINISHED_LOSE",
        }

    def test_eventstate_value_parity_with_line_provider(self) -> None:
        """D-12: bet_maker EventState values match line_provider exactly.

        P5 e2e tests assert byte-for-byte parity in EventFinishedMessage.
        Here we only assert the same string values exist on both sides.
        """
        assert {m.value for m in EventState} == {m.value for m in LpEventState}

    def test_betstatus_has_four_members(self) -> None:
        members = {m.name: m.value for m in BetStatus}
        assert members == {
            "PENDING": "PENDING",
            "WON": "WON",
            "LOST": "LOST",
            "CANCELLED": "CANCELLED",
        }
        assert all(isinstance(m.value, str) for m in BetStatus)


class TestStatusStub:
    """D-30: helpers/status.event_state_to_bet_status raises NotImplementedError."""

    def test_raises_for_p5(self) -> None:
        """D-30: P3 stub; P5 fills in real mapping."""
        with pytest.raises(NotImplementedError) as exc:
            event_state_to_bet_status(EventState.FINISHED_WIN)
        assert "P5" in str(exc.value)


class TestExtraForbid:
    """Schema-wide invariant: BetCreate AND BetRead both forbid extras (T-03-3)."""

    def test_betcreate_extra_forbid(self) -> None:
        """T-03-3: BetCreate.model_config extra='forbid'."""
        assert BetCreate.model_config.get("extra") == "forbid"

    def test_betread_extra_forbid(self) -> None:
        """T-03-3: BetRead.model_config extra='forbid'."""
        assert BetRead.model_config.get("extra") == "forbid"

    def test_eventread_extra_forbid(self) -> None:
        """T-03-3 / D-13: EventRead.model_config extra='forbid'."""
        assert EventRead.model_config.get("extra") == "forbid"
