from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, status

from bet_maker.facades.deps import EventLookupDep, SessionDep, UoWDep
from bet_maker.facades.line_provider_client import LineProviderUnavailable
from bet_maker.interactors.place_bet import EventNotBettable, place_bet
from bet_maker.schemas.bets import BetCreate, BetRead
from bet_maker.schemas.errors import ErrorDetail
from bet_maker.selectors.get_bet import get_bet_by_id
from bet_maker.selectors.list_bets import list_bets

router = APIRouter(tags=["bets"])


@router.post(
    "/bet",
    status_code=status.HTTP_201_CREATED,
    response_model=BetRead,
    summary="Place a bet on a bettable event",
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorDetail,
            "description": (
                "Event is not bettable: event not found, "
                "deadline passed, or event not active. "
                "Pydantic body validation 422 (extra fields, bad Decimal) "
                "is also possible and uses FastAPI's HTTPValidationError shape."
            ),
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorDetail,
            "description": "line-provider unreachable after retries.",
        },
    },
)
async def post_bet(
    uow: UoWDep,
    event_lookup: EventLookupDep,
    body: Annotated[
        BetCreate,
        Body(
            openapi_examples={
                "happy": {
                    "summary": "Place a valid bet on a NEW non-expired event",
                    "value": {
                        "event_id": "00000000-0000-0000-0000-000000000001",
                        "amount": "10.00",
                    },
                },
                "bad_decimal": {
                    "summary": "Invalid amount — too many decimal places (returns 422)",
                    "value": {
                        "event_id": "00000000-0000-0000-0000-000000000001",
                        "amount": "10.123",
                    },
                },
            },
        ),
    ],
) -> BetRead:
    """POST /bet — place a bet on a bettable event.

    BM-05: 201 + BetRead on success.
    BM-06: 422 with detail='event {id} is not bettable: {reason}'
    when EventNotBettable raised by place_bet interactor.
    D-06: three exact reason strings ("event not found", "deadline passed",
    "event not active") surfaced in the detail message.
    D-08: LineProviderUnavailable (upstream unreachable after retry) ->
    503 with static detail. Ladder order MUST be LineProviderUnavailable
    first, EventNotBettable second — sibling exceptions, but D-08 fixes
    the order for explicit reading clarity. Pitfall 7 (RESEARCH line
    646): place_bet must NOT catch LineProviderUnavailable internally;
    it propagates here.
    """
    try:
        return await place_bet(
            uow,
            event_id=body.event_id,
            amount=body.amount,
            event_lookup=event_lookup,
        )
    except LineProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="event validation unavailable: line-provider unreachable",
        ) from exc
    except EventNotBettable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event {body.event_id} is not bettable: {exc.reason}",
        ) from exc


@router.get(
    "/bets",
    response_model=list[BetRead],
    summary="List all bets (newest first)",
)
async def get_bets(session: SessionDep) -> list[BetRead]:
    """GET /bets — list all bets, newest first.

    BM-07: returns list[BetRead] ordered by created_at DESC.
    D-25: pure read — session injected directly (no UoW).
    """
    return await list_bets(session)


@router.get(
    "/bet/{bet_id}",
    response_model=BetRead,
    summary="Fetch single bet by id",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorDetail,
            "description": "Bet with this bet_id does not exist.",
        },
    },
)
async def get_bet(bet_id: UUID, session: SessionDep) -> BetRead:
    """GET /bet/{bet_id} — fetch single bet by id.

    BM-13: 200 + BetRead on hit; 404 with detail='bet {id} not found' on miss.
    D-25: pure read — session injected directly (no UoW).
    """
    bet = await get_bet_by_id(session, bet_id)
    if bet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"bet {bet_id} not found",
        )
    return bet
