---
plan: 07-02-error-detail-schemas
status: complete
date: 2026-05-18
---

# Plan 07-02 — ErrorDetail Pydantic Schemas

## Purpose

Create `ErrorDetail` schema in both services per CONTEXT.md D-09. Used by
route `responses={...}` declarations in plans 07-04 / 07-05 so Swagger UI
renders the exact JSON shape under 4xx/5xx branches.

Cross-service schema duplication per P5 D-28 — no imports between
`src/line_provider/` and `src/bet_maker/`.

## Files Created

- `src/line_provider/schemas/errors.py` — `ErrorDetail(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` + `detail: str`
- `src/bet_maker/schemas/errors.py` — byte-for-byte mirror (only the cross-reference in the docstring flips)
- `tests/line_provider/test_error_detail.py` — 3 tests (happy path, extra-field rejection, schema introspection)
- `tests/bet_maker/test_error_detail.py` — 3 tests (mirror)

## Test Results

- `uv run pytest -q tests/line_provider/test_error_detail.py tests/bet_maker/test_error_detail.py` → 6 passed, 0 failed
- mypy strict — no errors (schemas use Pydantic v2 ConfigDict + str only)
- ruff — clean

## Decisions Honored

- D-09: minimal `{detail: str}` model with `extra="forbid"`
- D-28 (P5): byte-for-byte duplication between services, no cross-imports
- Pydantic v2 `ConfigDict(frozen=True, extra="forbid")` — same idiom as `EventFinishedMessage`

## Commits

- `86b544f` feat(07-02): add ErrorDetail schema in line_provider (D-09)
- `8a40204` feat(07-02): mirror ErrorDetail schema in bet_maker (D-09, P5 D-28)
