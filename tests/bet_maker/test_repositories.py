"""Wave 0 stub — implemented in plan 03-06.

BM-02 / D-18: BetRepository.add (session.add — caller controls flush),
BetRepository.get_by_id (select + scalar_one_or_none).
Anti-Pattern 1: repository MUST NOT commit; only UoW commits.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-06")
