"""Unit tests for bet_maker ErrorDetail schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bet_maker.schemas.errors import ErrorDetail


def test_error_detail_accepts_detail_string() -> None:
    instance = ErrorDetail(detail="bet 123 not found")
    assert instance.detail == "bet 123 not found"


def test_error_detail_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(detail="x", extra_field="boom")  # type: ignore[call-arg]


def test_error_detail_schema_field_is_string() -> None:
    schema = ErrorDetail.model_json_schema()
    assert schema["properties"]["detail"]["type"] == "string"
    assert schema["required"] == ["detail"]
