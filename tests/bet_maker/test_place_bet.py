"""Wave 0 stub — implemented in plan 03-07.

BM-05: place_bet interactor — happy path produces BetRead with status=PENDING.
BM-06: EventNotBettable on (a) event_lookup returns None, (b) deadline <= now,
(c) state != NEW. D-14: model_validate inside session (A1 mitigation —
no MissingGreenlet on amount/created_at access after commit).
amount quantization round-trip: '10' → '10.00' in BetRead.amount.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-07")
