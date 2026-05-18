---
plan: 07-05-openapi-route-polish-bet-maker
status: complete
date: 2026-05-18
---

# Plan 07-05 — bet-maker OpenAPI route polish

## Purpose

Add `summary=` + `responses={...}` + `Body(openapi_examples=...)` to all
bet-maker routes per CONTEXT.md D-07 + D-08. Handlers unchanged.

## Changes

| Route | summary | responses (ErrorDetail) | openapi_examples |
|---|---|---|---|
| `POST /bet` | "Place a bet on a bettable event" | 422, 503 | happy (10.00), bad_decimal (10.123) |
| `GET /bets` | "List all bets (newest first)" | — | — |
| `GET /bet/{bet_id}` | "Fetch single bet by id" | 404 | — |
| `GET /events` (proxy) | "List active events (proxied from line-provider)" | 503 | — |
| `GET /health` | "Service health (PG + RMQ + consumer + reconciler)" | 503 (description only, no model) | — |

## Implementation Notes

- `Annotated[BetCreate, Body(openapi_examples=...)]` form on POST /bet — modern FastAPI v2 idiom, avoids ruff B008.
- `ErrorDetail` imported from `bet_maker.schemas.errors` in `bets.py` and `events.py`.
- `/health` 503 entry has `description` only (no `model=`) — payload is multi-key `{"status": "degraded", "checks": {...}}`, NOT the flat `ErrorDetail` envelope (Pitfall 5 per PATTERNS.md).
- Handler bodies unchanged — existing exception ladder (LineProviderUnavailable → 503; EventNotBettable → 422; bet-not-found → 404) honors `responses=` declarations at OpenAPI level only.

## Verification

- `uv run pytest -q tests/bet_maker/` → 240 passed
- `uv run mypy src/bet_maker/entrypoints/api/` → zero errors (4 source files)
- `uv run ruff check src/bet_maker/entrypoints/api/` → clean

## Commits

- `eb1d492` feat(07-05): polish OpenAPI metadata on bet-maker routes (D-07/D-08)
