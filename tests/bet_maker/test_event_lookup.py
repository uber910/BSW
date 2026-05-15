"""Wave 0 stub — implemented in plan 03-06.

D-11: EventLookup Protocol satisfied structurally by StubEventLookup.
StubEventLookup.seed(snapshot) → get_event(id) returns snapshot.
StubEventLookup.get_event(unseeded_id) returns None.
StubEventLookup.seed_active(event_id, deadline=now+1h) convenience for tests.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-06")
