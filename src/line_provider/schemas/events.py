from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

from config.time import utc_now
from line_provider.helpers.money import quantize_coefficient


class EventState(str, Enum):
    NEW = "NEW"
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"


def _quantize(value: Decimal) -> Decimal:
    return quantize_coefficient(value)


def _deadline_in_future(value: datetime) -> datetime:
    if value <= utc_now():
        raise ValueError("deadline must be in the future")
    return value


Coefficient = Annotated[
    Decimal,
    Field(gt=Decimal("0"), max_digits=8, decimal_places=2),
    AfterValidator(_quantize),
]

FutureDeadline = Annotated[AwareDatetime, AfterValidator(_deadline_in_future)]


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    coefficient: Coefficient
    deadline: FutureDeadline


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coefficient: Coefficient
    deadline: AwareDatetime
    state: EventState


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    coefficient: Coefficient
    deadline: AwareDatetime
    state: EventState


class EventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    coefficient: Coefficient
    deadline: AwareDatetime
    state: EventState
