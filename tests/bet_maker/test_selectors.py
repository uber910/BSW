"""Wave 0 stub — implemented in plan 03-07.

BM-07 / D-07: list_bets returns list[BetRead] ordered by created_at DESC.
BM-13 / D-08: get_bet_by_id returns BetRead or None (router maps None→404).
Selectors take AsyncSession (no UoW for read paths), use model_validate
from_attributes=True per Anti-Pattern 5 mitigation.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-07")
