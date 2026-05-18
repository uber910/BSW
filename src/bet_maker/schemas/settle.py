"""SettleResult — return DTO of settle_bets_for_event interactor.

Shape returned by settle_bets_for_event so callers (consumer handler,
reconciler) get a typed snapshot of which bets were settled and via
which path.
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
                   0 = idempotent no-op.
    settled_bet_ids: list of bet ids that were settled in this call.
    settled_via: 'consumer' or 'reconciler'.
    settled_at: Python-side timestamp filled by caller (PG fills the column
                server-side via func.now() in the UPDATE statement).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    terminal_state: EventTerminalState
    settled_count: int
    settled_bet_ids: list[UUID]
    settled_via: Literal["consumer", "reconciler"]
    settled_at: datetime


class CancelResult(BaseModel):
    """Immutable result of one cancel_bets_for_event invocation.

    Mirror of SettleResult but for the 404-branch of the reconciler:
    bets are flipped to CANCELLED when line-provider returns 404 for
    the event_id (event deleted / LP recreated). No terminal_state
    field — cancellation has no outcome.

    cancelled_count: number of rows flipped from PENDING to CANCELLED
                     in this call. 0 = idempotent no-op (same status
                     filter + FOR UPDATE SKIP LOCKED mechanism as
                     settle, see SettleResult docstring).
    cancelled_bet_ids: list of bet ids that were cancelled.
    cancelled_via: 'reconciler' only — no other call site exists.
                   Literal kept narrow to make future extension
                   (manual admin cancel, deadline fallback) an
                   intentional widening.
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
