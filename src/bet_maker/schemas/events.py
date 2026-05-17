"""EventState (and EventRead, per D-13) duplicated from line_provider.schemas.events
-- intentional service-boundary isolation per D-12 (mirror of P2 D-13
EventFinishedMessage intentional duplication). Value-parity test in
test_schemas.py prevents drift.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventState(str, Enum):
    NEW = "NEW"
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"


class EventRead(BaseModel):
    """LP GET /events payload item, observed at bet-maker boundary.

    D-13: intentionally duplicated from line_provider.schemas.events.EventRead
    (service-boundary discipline, mirror of EventState duplication per
    P3 D-12). bet-maker uses plain Decimal (not LP's `Coefficient`
    Annotated alias) -- we only deserialise, never construct/normalise.
    frozen=True because the bet-maker side only reads these -- they
    should never be mutated mid-pipeline (Pattern D in PATTERNS.md).
    extra='forbid' guards against LP schema drift -- adding a new field
    in line-provider would fail loud in bet-maker tests rather than
    silently dropping data.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    coefficient: Decimal
    deadline: datetime
    state: EventState
