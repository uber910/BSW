"""SettleResult — return DTO of settle_bets_for_event interactor (D-17).

Phase 5 / D-17 / D-13: shape returned by settle_bets_for_event so callers
(consumer handler in Plan 05, reconciler in Phase 6) get a typed snapshot
of which bets were settled and via which path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bet_maker.schemas.messages import EventTerminalState


class SettleResult(BaseModel):
    """Immutable result of one settle_bets_for_event invocation.

    settled_count: number of rows flipped from PENDING to WON/LOST in this call.
                   0 = idempotent no-op (D-15/D-16).
    settled_bet_ids: list of bet ids that were settled in this call.
    settled_via: 'consumer' (Phase 5) or 'reconciler' (Phase 6).
    settled_at: Python-side timestamp filled by caller (PG fills the column
                server-side via func.now() in the UPDATE statement — D-14).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    terminal_state: EventTerminalState
    settled_count: int
    settled_bet_ids: list[UUID]
    settled_via: Literal["consumer", "reconciler"]
    settled_at: datetime
