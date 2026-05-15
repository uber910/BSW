"""Wave 0 stub — implemented in plan 03-08.

BM-05: POST /bet 201 + BetRead happy path; 422 on (a) amount > 2dp,
(b) amount <= 0, (c) extra field (extra='forbid'), (d) missing amount.
BM-06: POST /bet 422 on EventNotBettable (event_lookup miss / deadline /
state). BM-07: GET /bets 200 + ordering. BM-13: GET /bet/{id} 200 + 404.
SC-6 (ROADMAP P3): Decimal round-trip "10.00" → body["amount"] == "10.00"
(string compare per D-19, NOT float).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-08")
