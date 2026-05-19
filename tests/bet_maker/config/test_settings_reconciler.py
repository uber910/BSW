"""BetMakerSettings reconciler-field assertions.

Validates the two fields (attempts + backoff_max_s) used by the
reconciler HttpEventLookup profile. The third reconciler-related field
(reconciliation_interval_s) is exercised by
``tests/bet_maker/test_settings.py``.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from bet_maker.settings.config import BetMakerSettings


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerSettings:
    async def test_default_line_provider_reconciler_attempts_is_5(self) -> None:
        assert BetMakerSettings().line_provider_reconciler_attempts == 5

    async def test_default_line_provider_reconciler_backoff_max_s_is_10(self) -> None:
        assert BetMakerSettings().line_provider_reconciler_backoff_max_s == 10.0

    async def test_attempts_validated_between_1_and_10(self) -> None:
        with pytest.raises(ValidationError):
            BetMakerSettings(line_provider_reconciler_attempts=0)
        with pytest.raises(ValidationError):
            BetMakerSettings(line_provider_reconciler_attempts=11)
        s1 = BetMakerSettings(line_provider_reconciler_attempts=1)
        assert s1.line_provider_reconciler_attempts == 1
        s10 = BetMakerSettings(line_provider_reconciler_attempts=10)
        assert s10.line_provider_reconciler_attempts == 10

    async def test_backoff_max_s_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            BetMakerSettings(line_provider_reconciler_backoff_max_s=0)
        with pytest.raises(ValidationError):
            BetMakerSettings(line_provider_reconciler_backoff_max_s=-1.0)
        s = BetMakerSettings(line_provider_reconciler_backoff_max_s=0.1)
        assert s.line_provider_reconciler_backoff_max_s == 0.1

    async def test_env_var_override_via_BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS(  # noqa: N802
        self,
    ) -> None:
        os.environ["BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS"] = "7"
        try:
            assert BetMakerSettings().line_provider_reconciler_attempts == 7
        finally:
            os.environ.pop("BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS", None)
