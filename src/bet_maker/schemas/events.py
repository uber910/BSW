"""EventState duplicated from line_provider.schemas.events -- intentional
service-boundary isolation per D-12 (mirror of P2 D-13 EventFinishedMessage
intentional duplication). Value-parity test in test_schemas.py prevents drift.
"""

from __future__ import annotations

from enum import Enum


class EventState(str, Enum):
    NEW = "NEW"
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"
