"""Wave 0 stub — implemented in plan 03-04.

BM-01: Bet SQLAlchemy 2.0 typed model — id UUID PK, event_id UUID (no FK),
amount Numeric(12,2), status BetStatus PG-ENUM ('PENDING'/'WON'/'LOST'),
created_at/updated_at server_default=func.now() + onupdate.
Default status=PENDING. RESEARCH §A1: after flush + refresh, created_at
is populated (server_default → PG → refresh loads).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-04")
