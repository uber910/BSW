"""Tests for BetMakerSettings line-provider HTTP fields.

``line_provider_http_attempts`` and ``line_provider_http_backoff_max_s``
are env-driven via env_prefix=BET_MAKER_. Bounded by ``Field(ge=1, le=10)``
and ``Field(gt=0)`` respectively — out-of-range values raise
``ValidationError`` at instantiation, surfacing config errors at startup
(fail loud on bad config).

Pattern follows pydantic-settings 2.x docs (monkeypatch.setenv +
instantiate + assert).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bet_maker.settings.config import BetMakerSettings


class TestBetMakerSettings:
    """Two BET_MAKER_LINE_PROVIDER_HTTP_* env-driven fields."""

    def test_line_provider_http_attempts_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default attempts == 3 when env unset."""
        monkeypatch.delenv("BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS", raising=False)
        settings = BetMakerSettings()
        assert settings.line_provider_http_attempts == 3

    def test_line_provider_http_attempts_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS=5 is honoured."""
        monkeypatch.setenv("BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS", "5")
        settings = BetMakerSettings()
        assert settings.line_provider_http_attempts == 5

    def test_line_provider_http_attempts_rejects_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ge=1 — 0 raises ValidationError."""
        monkeypatch.setenv("BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS", "0")
        with pytest.raises(ValidationError):
            BetMakerSettings()

    def test_line_provider_http_attempts_rejects_above_max(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """le=10 — 11 raises ValidationError."""
        monkeypatch.setenv("BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS", "11")
        with pytest.raises(ValidationError):
            BetMakerSettings()

    def test_line_provider_http_backoff_max_s_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default backoff_max_s == 2.0 when env unset."""
        monkeypatch.delenv("BET_MAKER_LINE_PROVIDER_HTTP_BACKOFF_MAX_S", raising=False)
        settings = BetMakerSettings()
        assert settings.line_provider_http_backoff_max_s == 2.0

    def test_line_provider_http_backoff_max_s_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BET_MAKER_LINE_PROVIDER_HTTP_BACKOFF_MAX_S=5.5 is honoured."""
        monkeypatch.setenv("BET_MAKER_LINE_PROVIDER_HTTP_BACKOFF_MAX_S", "5.5")
        settings = BetMakerSettings()
        assert settings.line_provider_http_backoff_max_s == 5.5

    def test_line_provider_http_backoff_max_s_rejects_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gt=0 — 0 raises ValidationError."""
        monkeypatch.setenv("BET_MAKER_LINE_PROVIDER_HTTP_BACKOFF_MAX_S", "0")
        with pytest.raises(ValidationError):
            BetMakerSettings()
