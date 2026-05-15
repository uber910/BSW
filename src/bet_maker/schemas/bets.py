from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from bet_maker.helpers.money import quantize_amount


class BetStatus(str, Enum):
    """Bet lifecycle status.

    PENDING -- bet placed, event not yet finished.
    WON -- event finished with the outcome the user bet on.
    LOST -- event finished with the opposite outcome.

    Settled by the RabbitMQ consumer (P5) or reconciliation job (P6).
    Python 3.10: `(str, Enum)` instead of `StrEnum` (3.11+); P2 D-20 locked.
    """

    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"


Amount = Annotated[
    Decimal,
    Field(gt=Decimal("0"), max_digits=12, decimal_places=2),
    AfterValidator(quantize_amount),
]
"""Validated bet amount.

D-04: gt=0, max_digits=12 (caps at 999,999,999,999.99 -- Pitfall A4 mitigation
for oversized payloads), decimal_places=2. AfterValidator normalises `"10"` ->
`Decimal("10.00")` so BetRead serialises consistently (D-19).
"""


class BetCreate(BaseModel):
    """POST /bet body. D-04: event_id + amount only; no coefficient (D-01)."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    amount: Amount


class BetRead(BaseModel):
    """Response shape for POST /bet 201, GET /bets items, GET /bet/{id} 200.

    D-05: superset of TZ-minimum (TZ requires only id + status; we include
    event_id + amount + created_at for curl-demo UX in README).
    from_attributes=True enables model_validate(orm_bet, from_attributes=True)
    inside the session (A1 / Anti-Pattern 5 mitigation: never return raw ORM).
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    event_id: UUID
    amount: Decimal
    status: BetStatus
    created_at: datetime
