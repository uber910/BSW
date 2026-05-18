---
phase: 07-polish-documentation
plan: 02
type: execute
wave: 1
depends_on: [01]
files_modified:
  - src/line_provider/schemas/errors.py
  - src/bet_maker/schemas/errors.py
  - tests/line_provider/test_error_detail.py
  - tests/bet_maker/test_error_detail.py
autonomous: true
requirements: [DOC-01]
must_haves:
  truths:
    - "ErrorDetail Pydantic model exists in both line_provider and bet_maker schemas packages"
    - "ErrorDetail accepts {\"detail\": \"...\"} and rejects extras (extra=\"forbid\")"
    - "ErrorDetail is frozen=True (output DTO semantics, mirrors EventFinishedMessage pattern)"
    - "Each service's ErrorDetail is byte-for-byte the mirror of the other (per P5 D-28 duplication policy)"
  artifacts:
    - path: "src/line_provider/schemas/errors.py"
      provides: "ErrorDetail Pydantic model for line-provider"
      exports: ["ErrorDetail"]
    - path: "src/bet_maker/schemas/errors.py"
      provides: "ErrorDetail Pydantic model for bet-maker (byte-for-byte mirror)"
      exports: ["ErrorDetail"]
    - path: "tests/line_provider/test_error_detail.py"
      provides: "Unit tests for line-provider ErrorDetail (accept happy + reject extras)"
    - path: "tests/bet_maker/test_error_detail.py"
      provides: "Unit tests for bet-maker ErrorDetail (accept happy + reject extras)"
  key_links:
    - from: "src/line_provider/schemas/errors.py::ErrorDetail"
      to: "src/bet_maker/schemas/errors.py::ErrorDetail"
      via: "Byte-for-byte mirror (duplication policy P5 D-28); no cross-imports"
      pattern: "class ErrorDetail\\(BaseModel\\):"
---

<objective>
Create `ErrorDetail` Pydantic schemas in both services per CONTEXT.md D-09 + P5 D-28 (no cross-service imports — schemas duplicated byte-for-byte). Standard error envelope `{"detail": "..."}` shape returned by FastAPI `HTTPException(detail=...)`. Used in `responses={...}` declarations on routes in plans 07-04 and 07-05 so Swagger UI displays the exact JSON payload of 4xx/5xx error branches.

Purpose: enable D-07 typed error responses on route decorators. Schema is intentionally minimal (single `detail: str` field) — no field validation beyond Pydantic's default.

Output: two new schema files + two new unit-test files. No changes to existing code.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/phases/07-polish-documentation/07-CONTEXT.md
@.planning/phases/07-polish-documentation/07-PATTERNS.md
@.planning/phases/05-rabbitmq-integration/05-CONTEXT.md

<interfaces>
<!-- Existing pattern: ConfigDict(frozen=True, extra="forbid") on output DTOs -->

From src/bet_maker/schemas/messages.py (current state):
```python
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class EventTerminalState(str, Enum):
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"


class EventFinishedMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    event_id: UUID
    ...
```

The same `model_config = ConfigDict(frozen=True, extra="forbid")` style applies to `ErrorDetail`.
</interfaces>
</context>

<threat_model>
N/A — schema is documentation metadata, not user-input handling. The shape merely describes what FastAPI's built-in `HTTPException` already serialises.
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create ErrorDetail schema in line-provider with unit test</name>
  <files>src/line_provider/schemas/errors.py, tests/line_provider/test_error_detail.py</files>
  <read_first>
    - src/line_provider/schemas/messages.py (existing analog — ConfigDict(frozen=True, extra="forbid") pattern)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → src/line_provider/schemas/errors.py)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-09)
    - tests/line_provider/test_health.py (analog for plain-async-def test style under asyncio_mode=auto)
  </read_first>
  <behavior>
    - Test 1: `ErrorDetail(detail="hello")` succeeds and `instance.detail == "hello"`.
    - Test 2: `ErrorDetail(detail="x", extra_field="boom")` raises `pydantic.ValidationError` (extra="forbid").
    - Test 3: `ErrorDetail.model_json_schema()["properties"]["detail"]["type"] == "string"` (schema introspection — validates field type made it to OpenAPI).
  </behavior>
  <action>
    Create `src/line_provider/schemas/errors.py` with EXACT content (verbatim — mirror copy will go in plan 07-02 task 2 for bet_maker):

    ```python
    from __future__ import annotations

    from pydantic import BaseModel, ConfigDict


    class ErrorDetail(BaseModel):
        """Standard error envelope for FastAPI HTTPException responses.

        Used in route ``responses={...}`` declarations so Swagger UI renders the
        exact JSON shape under 4xx/5xx branches. Mirrors FastAPI's default
        ``{"detail": "..."}`` payload from ``HTTPException(detail=...)``.

        D-09 / P5 D-28 duplication policy: this schema is duplicated byte-for-byte
        in ``src/bet_maker/schemas/errors.py``. No cross-service imports.
        """

        model_config = ConfigDict(frozen=True, extra="forbid")

        detail: str
    ```

    Create `tests/line_provider/test_error_detail.py` with:

    ```python
    """Unit tests for line_provider ErrorDetail schema (D-09)."""

    from __future__ import annotations

    import pytest
    from pydantic import ValidationError

    from line_provider.schemas.errors import ErrorDetail


    def test_error_detail_accepts_detail_string() -> None:
        instance = ErrorDetail(detail="event not found")
        assert instance.detail == "event not found"


    def test_error_detail_rejects_extra_fields() -> None:
        with pytest.raises(ValidationError):
            ErrorDetail(detail="x", extra_field="boom")  # type: ignore[call-arg]


    def test_error_detail_schema_field_is_string() -> None:
        schema = ErrorDetail.model_json_schema()
        assert schema["properties"]["detail"]["type"] == "string"
        assert schema["required"] == ["detail"]
    ```

    Run `uv run pytest -q tests/line_provider/test_error_detail.py` — must pass.
    Run `uv run mypy src/line_provider/schemas/errors.py` — must pass with zero errors.
    Run `uv run ruff check tests/line_provider/test_error_detail.py src/line_provider/schemas/errors.py` — must pass.
  </action>
  <verify>
    <automated>uv run pytest -q tests/line_provider/test_error_detail.py</automated>
  </verify>
  <acceptance_criteria>
    - File `src/line_provider/schemas/errors.py` exists, `wc -l` ≤ 25 (single class, minimal docstring)
    - `grep -c "model_config = ConfigDict(frozen=True, extra=\"forbid\")" src/line_provider/schemas/errors.py` returns 1
    - `grep -c "detail: str$" src/line_provider/schemas/errors.py` returns 1
    - `uv run pytest -q tests/line_provider/test_error_detail.py` shows 3 passed
    - `uv run mypy src/line_provider/schemas/errors.py` shows zero errors
    - `uv run ruff check src/line_provider/schemas/errors.py tests/line_provider/test_error_detail.py` shows no issues
  </acceptance_criteria>
  <done>ErrorDetail importable as `from line_provider.schemas.errors import ErrorDetail`; accepts `{"detail": "..."}`; rejects extras; mypy strict + ruff clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create ErrorDetail schema in bet-maker with unit test (byte-for-byte mirror)</name>
  <files>src/bet_maker/schemas/errors.py, tests/bet_maker/test_error_detail.py</files>
  <read_first>
    - src/line_provider/schemas/errors.py (just created — mirror source)
    - src/bet_maker/schemas/messages.py (existing analog — same ConfigDict pattern; duplication policy P5 D-28)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → src/bet_maker/schemas/errors.py)
    - tests/bet_maker/test_health.py (analog for `@pytest.mark.asyncio(loop_scope="session")` style — though this test has no async, plain def is fine)
  </read_first>
  <behavior>
    - Test 1: `ErrorDetail(detail="bet 123 not found")` succeeds and `instance.detail == "bet 123 not found"`.
    - Test 2: `ErrorDetail(detail="x", extra_field="boom")` raises `pydantic.ValidationError`.
    - Test 3: `ErrorDetail.model_json_schema()["properties"]["detail"]["type"] == "string"` AND `model_json_schema()["required"] == ["detail"]`.
  </behavior>
  <action>
    Create `src/bet_maker/schemas/errors.py` byte-for-byte equivalent to the line-provider copy (only the module-level docstring reference flips — `src/line_provider/schemas/errors.py` → `src/bet_maker/schemas/errors.py`, plus the cross-reference flips to point at the line-provider sibling):

    ```python
    from __future__ import annotations

    from pydantic import BaseModel, ConfigDict


    class ErrorDetail(BaseModel):
        """Standard error envelope for FastAPI HTTPException responses.

        Used in route ``responses={...}`` declarations so Swagger UI renders the
        exact JSON shape under 4xx/5xx branches. Mirrors FastAPI's default
        ``{"detail": "..."}`` payload from ``HTTPException(detail=...)``.

        D-09 / P5 D-28 duplication policy: this schema is duplicated byte-for-byte
        in ``src/line_provider/schemas/errors.py``. No cross-service imports.
        """

        model_config = ConfigDict(frozen=True, extra="forbid")

        detail: str
    ```

    Create `tests/bet_maker/test_error_detail.py` (mirror of LP test):

    ```python
    """Unit tests for bet_maker ErrorDetail schema (D-09)."""

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
    ```

    Verify byte-for-byte parity between the two `errors.py` files (excluding docstring cross-reference one-line difference):
    - `diff <(sed 's|line_provider|XXX|g; s|bet_maker|XXX|g' src/line_provider/schemas/errors.py) <(sed 's|line_provider|XXX|g; s|bet_maker|XXX|g' src/bet_maker/schemas/errors.py)` must return zero diff lines (allowed difference is the cross-reference; both are masked by `sed`).

    Run `uv run pytest -q tests/bet_maker/test_error_detail.py` — must pass.
    Run `uv run mypy src/bet_maker/schemas/errors.py` — must pass with zero errors.
    Run `uv run ruff check src/bet_maker/schemas/errors.py tests/bet_maker/test_error_detail.py` — must pass.
  </action>
  <verify>
    <automated>uv run pytest -q tests/bet_maker/test_error_detail.py</automated>
  </verify>
  <acceptance_criteria>
    - File `src/bet_maker/schemas/errors.py` exists, `wc -l` ≤ 25
    - `grep -c "model_config = ConfigDict(frozen=True, extra=\"forbid\")" src/bet_maker/schemas/errors.py` returns 1
    - `grep -c "detail: str$" src/bet_maker/schemas/errors.py` returns 1
    - `diff <(sed 's|line_provider|XXX|g; s|bet_maker|XXX|g' src/line_provider/schemas/errors.py) <(sed 's|line_provider|XXX|g; s|bet_maker|XXX|g' src/bet_maker/schemas/errors.py)` produces no output (zero-diff modulo cross-reference)
    - `uv run pytest -q tests/bet_maker/test_error_detail.py` shows 3 passed
    - `uv run mypy src/bet_maker/schemas/errors.py` shows zero errors
    - `uv run ruff check src/bet_maker/schemas/errors.py tests/bet_maker/test_error_detail.py` shows no issues
  </acceptance_criteria>
  <done>ErrorDetail importable as `from bet_maker.schemas.errors import ErrorDetail`; byte-for-byte parity with line_provider sibling; mypy strict + ruff clean.</done>
</task>

</tasks>

<verification>
- `uv run pytest -q tests/line_provider/test_error_detail.py tests/bet_maker/test_error_detail.py` shows 6 passed
- Full suite green: `uv run pytest -q` (existing ~295 tests + 6 new)
- `uv run mypy src` shows zero errors
- `uv run ruff check . && uv run ruff format --check .` shows zero issues
- `diff` between the two `errors.py` files modulo cross-reference is empty (parity invariant)
</verification>

<success_criteria>
- Both `errors.py` files committed; both `ErrorDetail` classes are `BaseModel` subclasses with `model_config = ConfigDict(frozen=True, extra="forbid")` + single `detail: str` field.
- 6 unit tests green (3 per service).
- Schemas ready to be referenced from `responses={...}` in plans 07-04 (LP routes) and 07-05 (BM routes).
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-02-SUMMARY.md` listing: files created, tests added, mypy/ruff status, ready signal for plans 07-04 / 07-05 to import `ErrorDetail`.
</output>
