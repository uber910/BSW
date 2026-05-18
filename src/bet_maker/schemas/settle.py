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


class CancelResult(BaseModel):
    """Immutable result of one cancel_bets_for_event invocation (D-04).

    Mirror of SettleResult but for the 404-branch of the reconciler:
    bets are flipped to CANCELLED when line-provider returns 404 for
    the event_id (event deleted / LP recreated). No terminal_state
    field — cancellation has no outcome.

    cancelled_count: number of rows flipped from PENDING to CANCELLED
                     in this call. 0 = idempotent no-op (same status
                     filter + FOR UPDATE SKIP LOCKED mechanism as
                     settle, see SettleResult docstring).
    cancelled_bet_ids: list of bet ids that were cancelled.
    cancelled_via: 'reconciler' only — Phase 6 introduces no other
                   call site. Literal kept narrow to make future
                   extension (manual admin cancel, deadline fallback)
                   an intentional widening.
    cancelled_at: Python-side timestamp filled by the interactor.
                  PG-side settled_at column filled server-side via
                  func.now() in the UPDATE statement (same column as
                  settle uses — observability semantics shared).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    cancelled_count: int
    cancelled_bet_ids: list[UUID]
    cancelled_via: Literal["reconciler"]
    cancelled_at: datetime
