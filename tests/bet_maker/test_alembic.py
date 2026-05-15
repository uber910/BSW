"""Wave 0 stub — implemented in plan 03-04.

SC-5 (ROADMAP P3): alembic upgrade head applies migration AND second run
is idempotent (no-op). RESEARCH §Pattern 3 / Pitfall 2: ENUM.create
checkfirst=True + create_type=False prevents 'type bet_status already exists'
on rerun. Test runs `command.upgrade(cfg, 'head')` twice — both must succeed.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-04")
