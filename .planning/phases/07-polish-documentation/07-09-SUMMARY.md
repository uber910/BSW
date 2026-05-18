---
plan: 07-09-audit-md
status: complete
date: 2026-05-18
---

# Plan 07-09 — 07-AUDIT.md

## Purpose

Create `07-AUDIT.md` codifying ROADMAP P7 SC#6 + PITFALLS.md «Looks Done But
Isn't» as a 19-row + 1-row evidence table. Every row maps to concrete
`file:line`, pytest node ID, or shell command + expected output.

## Status Histogram

- **verified:** 20 (all 19 main rows + 1 schema-parity row)
- **fix-applied:** 0
- **waived:** 0
- Total `| verified |` matches: 20 (every row Status column)

## Self-Checks

- `grep -cE "^\| [0-9]+ \| " 07-AUDIT.md` → 24 (19 main rows + 4 manual sub-table rows + 1 schema-parity = 24)
- `grep -c "| verified |" 07-AUDIT.md` → 20
- `grep -cE "\| (fix-applied\|waived) \|" 07-AUDIT.md` → 0
- `grep -cE "TBD\|<LINE-of-" 07-AUDIT.md` → 0 (no placeholders, no TBDs)
- `grep -c "tests/audit/test_static.py::" 07-AUDIT.md` → 8 (rows 1, 4, 5, 11, 12, 13, 14, 15 reference static-audit tests from plan 07-07)
- `grep -c "tests/bet_maker/" 07-AUDIT.md` → 7 (rows 2, 3, 9, 16, 18, 19 reference P3/P5/P6 existing tests)

## Resolved file:line References (samples)

- Row 1 ack_policy → `src/bet_maker/entrypoints/messaging.py:131`
- Row 4 with_for_update(skip_locked=True) → `src/bet_maker/repositories/bets.py:61`
- Row 11 async_sessionmaker(..., expire_on_commit=False) → `src/bet_maker/infrastructure/db/engine.py:37`
- Row 12/15 CMD exec form → `Dockerfile:50`
- Row 13 python:3.10-slim-bookworm → `Dockerfile:2`
- Row 14 PYTHONUNBUFFERED → `Dockerfile:6, 30`
- Row 5 RabbitQueue/Exchange durable=True → `src/bet_maker/entrypoints/messaging.py:121-130`
- Row 8 /health checks → `src/bet_maker/entrypoints/api/health.py:47` (pg_ok start)
- Row 9 DLX wiring → `src/bet_maker/entrypoints/messaging.py:126-127`
- Row 10 schema_version check → `src/bet_maker/entrypoints/messaging.py:162-163`

## Sign-Off

All 19 «Looks Done But Isn't» items + 1 schema-parity item are `verified`
with concrete evidence (source file:line, pytest node ID, or manual shell
command). Phase 7 introduces no new runtime code on the audited paths —
only static-audit tests (plan 07-07) catch future regressions; OpenAPI
metadata polish (plans 07-04 / 07-05) leaves handler bodies unchanged.

Plan 07-12 phase-gate will re-verify against this artefact and confirm zero
unjustified `waived` rows.

## Commits

- `9ea232b` docs(07-09): codify 19-item 'Looks Done But Isn't' audit (D-18)
