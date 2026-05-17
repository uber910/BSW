"""AMQP routing-key constants — bet-maker consumer side (D-05).

F8: single source of truth for routing keys; CI integration test
asserts the binding bsw.events --event.finished.*--> bet_maker.events.finished
exists at runtime. R5: rename, never edit — keep stability across deploys.
"""

from __future__ import annotations

from typing import Final

EVENT_FINISHED_WIN: Final[str] = "event.finished.win"
EVENT_FINISHED_LOSE: Final[str] = "event.finished.lose"
EVENT_FINISHED_WILDCARD: Final[str] = "event.finished.*"
