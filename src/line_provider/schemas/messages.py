from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class EventTerminalState(str, Enum):
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"


class EventFinishedMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    event_id: UUID
    new_state: EventTerminalState
    coefficient: Annotated[Decimal, Field(gt=Decimal("0"), max_digits=8, decimal_places=2)]
    occurred_at: AwareDatetime
    correlation_id: str
