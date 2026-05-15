"""Wave 0 stub — implemented in plan 03-03.

BM-05 / BM-06 / D-04: BetCreate (Annotated Decimal with max_digits=12,
decimal_places=2, AfterValidator quantize) + BetRead (extra='forbid',
from_attributes=True). BetStatus (str, Enum: PENDING/WON/LOST).
EventState duplicate (D-12) — kept in sync with line_provider.
helpers/money.quantize_amount ROUND_HALF_UP to 2dp.
helpers/status.event_state_to_bet_status — NotImplementedError stub (P5).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-03")
