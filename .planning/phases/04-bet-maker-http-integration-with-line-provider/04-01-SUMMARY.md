---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 01
subsystem: planning
tags: [doc-sync, requirements, roadmap, respx, dev-deps, uv]

# Dependency graph
requires:
  - phase: 03-bet-maker-domain-db
    provides: 193-test baseline + StubEventLookup (to be replaced by HttpEventLookup in Plan 04-05)
provides:
  - REQUIREMENTS.md BM-04 wording aligned with D-01 (no TTL cache)
  - ROADMAP.md Phase 4 Goal + SC#1 aligned with D-01
  - respx>=0.22,<0.23 dev-dep installable via uv sync --frozen
affects: [04-02, 04-03, 04-04, 04-05, 04-06, 04-07, 04-08, 04-09]

# Tech tracking
tech-stack:
  added: [respx==0.22.0]
  patterns: [phase-opening doc-sync first-task pattern — mirrors P2 Plan 02-01 and P3 Plan 03-01]

key-files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - pyproject.toml
    - uv.lock

key-decisions:
  - "D-01 (no TTL cache in P4) propagated inline into REQUIREMENTS.md BM-04 and ROADMAP.md Phase 4 Goal + SC#1 — grep-visible for future audits"
  - "respx chosen over pytest-httpx per D-15 — modern, cleaner API for httpx 0.28, community standard"
  - "Inline citation pattern `Per D-01 (Phase 4 CONTEXT.md)` reused from P3 Plan 03-01 (BM-01 coefficient removal)"

patterns-established:
  - "Phase-opening doc-sync: first task of each phase reconciles REQUIREMENTS.md/ROADMAP.md drift against CONTEXT.md decisions and adds inline `Per D-XX` citations"
  - "TZ-first verification: every decision that contradicts ROADMAP/REQUIREMENTS must first be verified against the source TZ PDF (Тестовое задание Middle Python developer.pdf)"
  - "uv add --group dev pin range — dev-deps added via `uv add --group dev 'pkg>=X,<Y'` to keep pyproject.toml and uv.lock in lockstep automatically"

requirements-completed: []

# Metrics
duration: ~5 min
completed: 2026-05-17
---

# Phase 04: Doc-sync per D-01 + respx dev-dep Summary

**REQUIREMENTS.md BM-04 and ROADMAP.md Phase 4 Goal/SC#1 aligned with D-01 (no TTL cache); respx>=0.22,<0.23 added to dev-deps; 193 tests still green.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-17T08:25:00Z
- **Completed:** 2026-05-17T08:30:00Z
- **Tasks:** 4 (1 verification + 3 file-modifications)
- **Files modified:** 4 (REQUIREMENTS.md, ROADMAP.md, pyproject.toml, uv.lock)

## Accomplishments

- TZ pages 2-3 verified: zero "кэш"/"cache"/"TTL" tokens in the binary; only "допускается небольшое отставание в свежести" (the wording that justifies D-01 NOT to cache)
- REQUIREMENTS.md BM-04 line rewritten with inline `Per D-01 (Phase 4 CONTEXT.md): TTL cache не реализуется в P4` citation
- ROADMAP.md Phase 4 Goal (line 114) dropped `+ tiny TTL cache`; replaced with `retry (tenacity)` and inline D-01 citation
- ROADMAP.md Phase 4 SC#1 (line 118) replaced `cached via TTL dict` wording with `свежий результат каждого запроса; отставание = длительность одного HTTP-вызова к LP плюс retry-backoff` and inline D-01 citation
- pyproject.toml `[dependency-groups] dev` array gained `respx>=0.22,<0.23`; uv.lock regenerated with respx 0.22.0 entry
- Existing test suite remains green: 193 passed (no regression); mypy strict 95 files clean; ruff check + format clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Verify TZ does not require cache** — no commit (read-only verification; result captured in Task 2 commit message)
2. **Task 2: Rewrite REQUIREMENTS.md BM-04 per D-01** — `3f17b49` (docs)
3. **Task 3: Rewrite ROADMAP.md Phase 4 Goal + SC#1 per D-01** — `45e300d` (docs)
4. **Task 4: Add respx dev-dependency and regenerate uv.lock** — `7a257d5` (chore)

**Plan metadata:** committed together with STATE.md, ROADMAP.md plan-progress update, and this SUMMARY.md.

## Files Created/Modified

- `.planning/REQUIREMENTS.md` — BM-04 line 35 single-line edit: append `Per D-01 (Phase 4 CONTEXT.md): TTL cache не реализуется в P4 — ТЗ кэш не требует, только разрешает отставание в свежести; кэш отложен в README P7 как "next-step extension".`
- `.planning/ROADMAP.md` — two-line edit in Phase 4 block: Goal (line 114) drops `tiny TTL cache`; SC#1 (line 118) replaces `cached via TTL dict` with `свежий результат каждого запроса; отставание = длительность одного HTTP-вызова к LP плюс retry-backoff`
- `pyproject.toml` — new array element `"respx>=0.22,<0.23",` in `[dependency-groups] dev`
- `uv.lock` — new `[[package]] name = "respx"` block (version 0.22.0)

## Decisions Made

None - plan executed exactly as written. D-01 and D-15 (from CONTEXT.md) drove every line; no new decisions emerged.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - planning artefacts and dev-dep only; no external service configuration.

## Next Phase Readiness

- Phase 4 doc-set internally consistent: REQUIREMENTS.md BM-04, ROADMAP.md Phase 4 Goal + SC#1, and CONTEXT.md D-01 all carry the same wording (no TTL cache).
- respx is installable through `uv sync --frozen` — Plans 04-05, 04-06, 04-08 can `import respx` in their unit tests without further dep changes.
- 193-test baseline preserved; no production code touched.
- Ready for Plan 04-02 (EventRead schema in `bet_maker/schemas/events.py`, Wave 2).

---
*Phase: 04-bet-maker-http-integration-with-line-provider*
*Completed: 2026-05-17*
