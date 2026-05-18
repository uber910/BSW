---
phase: 06-reconciliation-job
plan: "01"
subsystem: docs
tags: [docs, sync, cancelled-status, reconciliation, wave-0]
dependency_graph:
  requires: []
  provides: [REQUIREMENTS.md BM-05 CANCELLED status set, REQUIREMENTS.md BM-12 CANCELLED-on-404 branch, ROADMAP.md Phase 6 Goal/SC/Plans populated]
  affects: [".planning/REQUIREMENTS.md", ".planning/ROADMAP.md"]
tech_stack:
  added: []
  patterns: [doc-sync-first pattern (P2 02-01 / P3 03-01 / P4 04-01 / P5 05-10)]
key_files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
decisions:
  - "CANCELLED is an engineering interpretation of TZ (404 from LP = event deleted/LP recreated). Documented explicitly per memory feedback_verify_against_tz."
  - "BM-12 rewritten with full method names (get_pending_event_ids, HttpEventLookup reconciler-params) and references D-02/D-03/D-04 in Phase 6 CONTEXT.md."
  - "ROADMAP.md Phase 6 Plans list populated with 11 entries matching planner-assigned filenames (06-01 through 06-11)."
metrics:
  duration: "~4 min (2 tasks, 2 files)"
  completed_date: "2026-05-18"
---

# Phase 6 Plan 1: Doc Sync (REQUIREMENTS BM-05/BM-12 + ROADMAP Phase 6) Summary

Wave-0 doc-sync: extended BM-05 to four-status set (PENDING|WON|LOST|CANCELLED), rewrote BM-12 with reconciler method names and 404→CANCELLED branch, populated ROADMAP.md Phase 6 with updated Goal/SC and 11-plan checklist.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update REQUIREMENTS.md BM-05 and BM-12 | 2d5709f | .planning/REQUIREMENTS.md |
| 2 | Update ROADMAP.md Phase 6 Goal/SC#1/SC#5 and Plans list | 73594c8 | .planning/ROADMAP.md |

## Changes Made

### Task 1 — REQUIREMENTS.md

**BM-05** (`.planning/REQUIREMENTS.md` line 36): Appended new sentence at end of existing bullet:
> Статусы ставки: `PENDING | WON | LOST | CANCELLED` (Phase 6 / D-03). `CANCELLED` — recovery-статус: ставка помечается reconciler'ом при 404 от line-provider (событие удалено или LP пересоздан) — инженерная трактовка ТЗ (memory `feedback_verify_against_tz`), отдельно отмечена в README §Reliability (DOC-04).

**BM-12** (`.planning/REQUIREMENTS.md` line 43): Replaced terse description with full spec including:
- `BetRepository.get_pending_event_ids()` method name
- `HttpEventLookup` reconciler-params (5 attempts / max_backoff 10s — P4 D-04)
- Three terminal branches: `WON` / `LOST` (terminal_state) or `CANCELLED` (404 от LP)
- References D-02/D-03/D-04 (Phase 6 CONTEXT.md)

### Task 2 — ROADMAP.md

**Goal** (`.planning/ROADMAP.md` Phase 6): Added CANCELLED branch clause:
> …or marks the bets `CANCELLED` via a new `cancel_bets_for_event` interactor when line-provider returns 404 (event deleted / LP recreated).

**SC#1**: Clarified outcomes — `WON`/`LOST` when LP reports FINISHED_WIN/FINISHED_LOSE, or `CANCELLED` when LP returns 404 for the event_id.

**SC#5**: Added scenario (c): create event → place bet → delete event from line-provider → assert bet becomes CANCELLED via reconciler within one interval.

**Plans block**: Replaced `TBD` with `**Plans:** 11 plans across 7 waves (0..6)` and full checklist of 11 plan files (06-01 through 06-11), all unchecked.

## Acceptance Criteria Verification

| Check | Command | Expected | Result |
|-------|---------|----------|--------|
| CANCELLED in BM-05 | `grep -c "PENDING \| WON \| LOST \| CANCELLED" REQUIREMENTS.md` | 1 | 1 |
| get_pending_event_ids in BM-12 | `grep -c "BM-12.*get_pending_event_ids" REQUIREMENTS.md` | 1 | 1 |
| CANCELLED+404 mapping | `grep -cE "CANCELLED.*404\|404.*CANCELLED" REQUIREMENTS.md` | ≥1 | 2 |
| feedback_verify_against_tz | `grep -c "feedback_verify_against_tz" REQUIREMENTS.md` | 1 | 1 |
| Section headings unchanged | `grep -cE "^### (Infrastructure\|line-provider\|bet-maker\|Quality\|Documentation)" REQUIREMENTS.md` | 5 | 5 |
| BM bullet count unchanged | `grep -cE "^- \[[ x]\] \*\*BM-[0-9]+\*\*" REQUIREMENTS.md` | 13 | 13 |
| 06-01 in ROADMAP | `grep -c "06-01-doc-sync-PLAN.md" ROADMAP.md` | 1 | 1 |
| 06-11 in ROADMAP | `grep -c "06-11-phase-gate-PLAN.md" ROADMAP.md` | 1 | 1 |
| 11 plan checkboxes | `grep -cE "^- \[ \] 06-\d{2}-" ROADMAP.md` | 11 | 11 |
| 11 plans header | `grep -c "11 plans across 7 waves" ROADMAP.md` | 1 | 1 |
| CANCELLED count in ROADMAP | `grep -c "CANCELLED" ROADMAP.md` | ≥3 | 5 |
| delete-event scenario | `grep -c "delete event from line-provider" ROADMAP.md` | 1 | 1 |
| Phase sections unchanged | `grep -cE "^### Phase " ROADMAP.md` | 7 | 7 |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — documentation-only plan, no runtime code.

## Threat Flags

None — documentation-only change, no network endpoints or runtime code introduced.

## Self-Check: PASSED

Files confirmed to exist:
- `.planning/REQUIREMENTS.md` — FOUND
- `.planning/ROADMAP.md` — FOUND

Commits confirmed to exist:
- 2d5709f — FOUND (docs(06-01): extend BM-05 status set and BM-12 description)
- 73594c8 — FOUND (docs(06-01): update ROADMAP.md Phase 6 Goal/SC and populate Plans list)
