"""Wave 0 stub — implemented in plan 03-08.

D-27: wait_for_postgres tenacity retry — stop_after_attempt(10) +
wait_exponential(multiplier=1, min=1, max=10). Test: override settings
to attempts=2 for speed; bad DSN → after 2 retries RuntimeError propagates.
RESEARCH §Critical Risk Axis 5.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-08")
