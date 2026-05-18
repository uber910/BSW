"""Wave-0 stub — Plan 06-04. Target req: BM-12.

Replace pytest.fail(...) with real assertions when Plan 06-04 adds
line_provider_reconciler_attempts and line_provider_reconciler_backoff_max_s
to BetMakerSettings in src/bet_maker/settings.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerSettings:
    async def test_default_line_provider_reconciler_attempts_is_5(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-04 — reconciler settings not yet implemented")

    async def test_default_line_provider_reconciler_backoff_max_s_is_10(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-04 — reconciler settings not yet implemented")

    async def test_attempts_validated_between_1_and_10(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-04 — reconciler settings not yet implemented")

    async def test_backoff_max_s_must_be_positive(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-04 — reconciler settings not yet implemented")

    async def test_env_var_override_via_BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS(  # noqa: N802
        self,
    ) -> None:
        pytest.fail("Wave-0 stub for Plan 06-04 — reconciler settings not yet implemented")
