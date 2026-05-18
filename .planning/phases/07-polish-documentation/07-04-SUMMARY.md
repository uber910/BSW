---
plan: 07-04-openapi-route-polish-line-provider
status: complete
date: 2026-05-18
---

# Plan 07-04 — line-provider OpenAPI route polish

## Purpose

Add `summary=` + `responses={...}` + `Body(openapi_examples=...)` to all
line-provider routes per CONTEXT.md D-07 + D-08. Handlers unchanged.

## Changes

| Route | summary | responses (ErrorDetail) | openapi_examples |
|---|---|---|---|
| `POST /event` | "Create new event in NEW state" | 409 | happy (UUID + 1.50 + 2030 deadline) |
| `PUT /event/{event_id}` | "Update event (state transition NEW -> FINISHED_WIN/LOSE)" | 404, 422 | finish_win, finish_lose |
| `GET /event/{event_id}` | "Fetch event by id" | 404 | — |
| `GET /events` | "List active events (deadline in future, state == NEW)" | — | — |
| `GET /health` | "Liveness probe" | — | — |

## Implementation Notes

- Used `Annotated[Schema, Body(openapi_examples=...)]` form instead of
  default-value `body: Schema = Body(...)` — `Annotated` is the modern
  FastAPI v2 idiom and avoids ruff B008 ("function call in default").
- `ErrorDetail` imported from `line_provider.schemas.errors` (P5 D-28 — no cross-imports).
- Handler bodies unchanged — existing `HTTPException(detail=...)` ladder honors `responses=` declarations at OpenAPI doc level only.

## Verification

- `uv run pytest -q tests/line_provider/` → 108 passed (no behaviour change)
- `uv run mypy src/line_provider/entrypoints/api/` → zero errors
- `uv run ruff check src/line_provider/entrypoints/api/` → clean

## Commits

- `d9601c5` feat(07-04): polish OpenAPI metadata on line-provider routes (D-07/D-08)
