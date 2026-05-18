---
plan: 07-03-openapi-app-metadata
status: complete
date: 2026-05-18
---

# Plan 07-03 — FastAPI App-level Description

## Purpose

Add `description=` kwarg to both `FastAPI(...)` constructors per CONTEXT.md
D-06 so Swagger UI headers explain what each service does and points the
reviewer at `/asyncapi`. `contact=` / `license_info=` deliberately omitted.

## Files Modified

- `src/line_provider/app.py` — single-block edit adding `description=(...)` between `title=` and `version=`
- `src/bet_maker/app.py` — same pattern

## Description Strings (verbatim)

**line-provider:**
> Источник событий и их статусов. Хранит события в памяти, публикует EventFinishedMessage в RabbitMQ exchange `bsw.events` при переходе в FINISHED_WIN / FINISHED_LOSE. AsyncAPI: /asyncapi.

**bet-maker:**
> Сервис приёма и истории ставок. Хранит ставки в PostgreSQL, получает финальные статусы событий из RabbitMQ (queue `bet_maker.events.finished`), reconciler как защита от потерянных сообщений. AsyncAPI: /asyncapi.

## Verification

- `uv run mypy src/line_provider/app.py src/bet_maker/app.py` → zero errors
- `uv run ruff check src/line_provider/app.py src/bet_maker/app.py` → clean
- pre-commit hooks → passed (mypy strict pass on both files)

## Decisions Honored

- D-06: description in Russian (CLAUDE.md "single Russian docs"), no emojis, no `contact=` / `license_info=`
- D-10: description mentions `/asyncapi` endpoint URL — anchors plan 07-08 smoke test target

## Commits

- `5a1063d` feat(07-03): add OpenAPI description on both services (D-06)
