from __future__ import annotations

from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.events import EventState


def event_state_to_bet_status(state: EventState) -> BetStatus:
    """Map terminal event state to bet outcome status.

    Stub: when the consumer settles bets after EventFinished arrives, it
    maps EventState.FINISHED_WIN -> BetStatus.WON and FINISHED_LOSE -> LOST.
    Calling this raises -- the settlement path lives in
    settle_bets_for_event interactor.
    """
    raise NotImplementedError("Implemented in P5 (settle_bets_for_event interactor)")
