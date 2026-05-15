from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from bet_maker.facades.deps import EventLookupDep, SessionDep, UoWDep
from bet_maker.interactors.place_bet import EventNotBettable, place_bet
from bet_maker.schemas.bets import BetCreate, BetRead
from bet_maker.selectors.get_bet import get_bet_by_id
from bet_maker.selectors.list_bets import list_bets

router = APIRouter(tags=["bets"])


@router.post(
    "/bet",
    status_code=status.HTTP_201_CREATED,
    response_model=BetRead,
)
async def post_bet(
    body: BetCreate,
    uow: UoWDep,
    event_lookup: EventLookupDep,
) -> BetRead:
    """POST /bet — place a bet on a bettable event.

    BM-05: 201 + BetRead on success.
    BM-06: 422 with detail='event {id} is not bettable: {reason}'
    when EventNotBettable raised by place_bet interactor.
    D-06: three exact reason strings ("event not found", "deadline passed",
    "event not active") surfaced in the detail message.
    """
    try:
        return await place_bet(
            uow,
            event_id=body.event_id,
            amount=body.amount,
            event_lookup=event_lookup,
        )
    except EventNotBettable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event {body.event_id} is not bettable: {exc.reason}",
        ) from exc


@router.get(
    "/bets",
    response_model=list[BetRead],
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
