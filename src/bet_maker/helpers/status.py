from __future__ import annotations

from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.events import EventState


def event_state_to_bet_status(state: EventState) -> BetStatus:
    """Map terminal event state to bet outcome status.

    Stub for P5: when the consumer settles bets after EventFinished arrives,
    it maps EventState.FINISHED_WIN -> BetStatus.WON and FINISHED_LOSE -> LOST.
    Calling this in P3 raises -- there is no settlement path yet.

    D-30: helpers/status.py created here so P5 can fill it in without an
    SOC violation (single file ownership, no cross-phase edits to other
    modules).
    """
    raise NotImplementedError("Implemented in P5 (settle_bets_for_event interactor)")
