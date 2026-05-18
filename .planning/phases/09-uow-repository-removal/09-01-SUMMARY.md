---
phase: 09-uow-repository-removal
plan: 01
subsystem: database
tags: [sqlalchemy, selectors, for-update-skip-locked, async, postgres, refactor]

# Dependency graph
requires:
  - phase: 03-database-foundation
    provides: BetRepository.get_pending_locked + get_pending_event_ids (source for SQL migration)
  - phase: 07-quality-gates
    provides: tests/audit/test_static.py R3 audit (the one being retargeted in D-08)
provides:
  - src/bet_maker/selectors/get_pending_locked.py — thin AsyncSession-based read with FOR UPDATE SKIP LOCKED + status=PENDING
  - src/bet_maker/selectors/get_pending_event_ids.py — thin AsyncSession-based read with SELECT DISTINCT event_id WHERE status=PENDING
  - tests/bet_maker/selectors/ — new test package with 7 integration + static tests against the two selectors
  - tests/audit/test_static.py::test_pending_locked_selector_uses_for_update_skip_locked — R3 audit retargeted to the new seam
affects: [09-02-call-site-rewires, 09-03-repository-deletion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Selector = async (session: AsyncSession, ...) -> T. No UoW knowledge. No flush/commit/rollback. (D-05)"
    - "Static-audit invariant moves with the SQL: when SQL relocates, retarget audit in the SAME commit/plan to avoid FileNotFoundError window (Pitfall #5)."

key-files:
  created:
    - src/bet_maker/selectors/get_pending_locked.py
    - src/bet_maker/selectors/get_pending_event_ids.py
    - tests/bet_maker/selectors/__init__.py
    - tests/bet_maker/selectors/test_get_pending_locked.py
    - tests/bet_maker/selectors/test_get_pending_event_ids.py
  modified:
    - tests/audit/test_static.py

key-decisions:
  - "D-05: selectors accept AsyncSession directly (not AbstractUnitOfWork) — uniform contract with existing get_bet / list_bets."
  - "D-08: tests/audit/test_static.py::test_repositories_use_for_update_skip_locked renamed to test_pending_locked_selector_uses_for_update_skip_locked and retargeted to selectors/get_pending_locked.py — invariant moves with the SQL."
  - "D-09: No additional 'no repositories dir' static audit added — Phase 9 success criteria DOD (git grep 'class BetRepository' = 0) is enforced by Plan 03 alone."
  - "Pitfall #5 honored: new selector file shipped BEFORE / in the SAME plan as the audit retarget — no window where audit reads a non-existent path."

patterns-established:
  - "Pattern: thin SQL wrapper selector — async function over AsyncSession with no transactional verbs; caller (interactor) owns the UoW."
  - "Pattern: per-selector static-source guard inside the integration test module (inspect.getsource + literal substring asserts) so a refactor that drops .distinct() / .with_for_update fails the unit suite even before the dedicated audit fires."

requirements-completed: [REFACTOR-02]

# Metrics
duration: ~10 min
completed: 2026-05-18
---

# Phase 09 Plan 01: Selector seam introduction Summary

**Two new selectors (`get_pending_locked`, `get_pending_event_ids`) own the FOR UPDATE SKIP LOCKED and DISTINCT-pending-event-ids queries; the R3 static audit follows the SQL to the new seam; `BetRepository` stays in place so the suite remains green at 363 tests.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-05-18T21:08:00Z (approx — after `gsd-execute-phase` spawn)
- **Completed:** 2026-05-18T21:18:19Z
- **Tasks:** 3 (all autonomous, none required checkpoint)
- **Files modified:** 6 (5 created + 1 modified)

## Accomplishments

- New selector layer for the two queries that `BetRepository` currently owns — both are pure `AsyncSession`-based reads with zero transactional verbs.
- 7 new tests (3 integration + 1 static for `get_pending_locked`, 3 integration + 1 static for `get_pending_event_ids`) cover the new seam against the testcontainers PG and pass.
- R3 invariant audit (`with_for_update(skip_locked=True)`) atomically retargeted from `src/bet_maker/repositories/bets.py` to `src/bet_maker/selectors/get_pending_locked.py` per D-08 — no audit-window gap.
- Old `BetRepository` and `tests/bet_maker/repositories/` stay in place untouched; Plan 02 will swap call-sites and Plan 03 will delete the directory.
- Full pytest suite: **363 tests passed** (was 356 at end of Phase 8 = +7 new tests, zero regressions). `uv run mypy --strict src/bet_maker/selectors` clean. `uv run ruff check src/bet_maker/selectors tests/bet_maker/selectors tests/audit/test_static.py` clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create `src/bet_maker/selectors/get_pending_locked.py`** — `baab0d0` (feat)
2. **Task 2: Create `src/bet_maker/selectors/get_pending_event_ids.py` + `tests/bet_maker/selectors/` test package** — `7d8548b` (feat)
3. **Task 3: Retarget audit to new selector seam (D-08)** — `ce90ddf` (refactor)

## Files Created/Modified

- `src/bet_maker/selectors/get_pending_locked.py` — async `get_pending_locked(session, event_id) -> list[Bet]` with `with_for_update(skip_locked=True)` + `Bet.status == BetStatus.PENDING`. R3-carrying file. No flush/commit/rollback.
- `src/bet_maker/selectors/get_pending_event_ids.py` — async `get_pending_event_ids(session) -> list[UUID]` with `.distinct()` over `Bet.status == BetStatus.PENDING`. Read-only.
- `tests/bet_maker/selectors/__init__.py` — empty package marker so pytest discovers siblings (inherits `session_factory` fixture from `tests/conftest.py`).
- `tests/bet_maker/selectors/test_get_pending_locked.py` — 3 tests ported from `TestGetPendingLocked`: only-PENDING for event_id, empty when no PENDING, source-level `with_for_update(skip_locked=True)` assertion.
- `tests/bet_maker/selectors/test_get_pending_event_ids.py` — 4 tests ported from `repositories/test_get_pending_event_ids.py`: DISTINCT distinct event_ids, empty when no PENDING, skips WON/LOST/CANCELLED, source-level no-commit/no-flush + `.distinct()` assertion. No more `AsyncUnitOfWork` wrapping — direct selector call with `session_factory()`.
- `tests/audit/test_static.py` — function `test_repositories_use_for_update_skip_locked` renamed to `test_pending_locked_selector_uses_for_update_skip_locked`; path inside `read_text()` switched from `repositories/bets.py` to `selectors/get_pending_locked.py`; error message updated. All 7 sibling audit tests untouched (manual ack, expire_on_commit, compose exec-form, Dockerfile pin, PYTHONUNBUFFERED, durable queue/exchange, no-entrypoints).

## Decisions Made

- Followed D-05 verbatim (selector signature = `(session: AsyncSession, ...)`, no UoW knowledge).
- Followed D-08 verbatim (audit renamed + retargeted to new selector file, NOT duplicated).
- Followed D-09 verbatim (no separate "no repositories dir" audit; deletion is Plan 03's job).
- Edited docstring of `get_pending_locked` to say "the FOR UPDATE SKIP LOCKED row lock" instead of the literal substring `with_for_update(skip_locked=True)` so the acceptance `grep -c 'with_for_update(skip_locked=True)' src/bet_maker/selectors/get_pending_locked.py` returns exactly 1 (only the SQL itself). Pure cosmetic — docstring still names the invariant clearly.

## Deviations from Plan

None - plan executed exactly as written. The only minor adjustments were:
- Reformat of line 50 in `test_get_pending_event_ids.py` (CANCELLED bet `session.add(...)` call) split across multiple lines so `ruff` E501 (line-length ≤100) passes. Pure formatting; no behaviour change. ruff-format auto-applied a small follow-up tweak on the same file during the second `git commit` pre-commit pass — accepted as-is.
- Docstring tweak in `get_pending_locked.py` to keep the acceptance grep count at exactly 1 — documented under "Decisions Made" above. Not a deviation per se, just a literal-text adjustment.

**Total deviations:** 0
**Impact on plan:** None — every acceptance criterion in the plan and every verification step from the `<verification>` block passes.

## Issues Encountered

None blocking. The two pytest warnings ("test marked with `@pytest.mark.asyncio` but is not async") are inherited from the same class-level `@pytest.mark.asyncio(loop_scope="session")` decorator pattern used throughout the existing codebase (`tests/bet_maker/test_repositories.py::TestAntiPattern1`, `repositories/test_get_pending_event_ids.py::test_no_commit_no_flush`) — not a Phase 9 regression and out of scope.

## Verification Output

Grep verification block (from plan):
```
with_for_update(skip_locked=True) in get_pending_locked: 1
.distinct() in get_pending_event_ids:                   1
commit/flush/rollback in get_pending_locked:            0
commit/flush/rollback in get_pending_event_ids:         0
UoW class in get_pending_locked:                        0
UoW class in get_pending_event_ids:                     0
new audit name (test_pending_locked_selector_...):      1
old audit name (test_repositories_...):                 0
tests/bet_maker/selectors/ exists:                      OK
tests/bet_maker/selectors/__init__.py:                  OK
```

Test outcomes:
```
uv run pytest tests/bet_maker/selectors/ -q --no-cov   → 7 passed
uv run pytest tests/audit/test_static.py -q --no-cov   → 8 passed
uv run pytest -q --no-cov                              → 363 passed (was 356; +7 new)
uv run mypy --strict src/bet_maker/selectors           → Success, no issues in 6 source files
uv run ruff check src/bet_maker/selectors tests/bet_maker/selectors tests/audit/test_static.py
                                                       → All checks passed
```

## Next Phase Readiness

- **Plan 02 unblocked.** Both selectors and their tests exist; Plan 02 can rewire `place_bet`, `settle_bets_for_event`, `cancel_bets_for_event` and `jobs/reconciler.py` to call the new selectors instead of `uow.bets.*` without scaffolding gaps.
- **Plan 03 unaffected.** `src/bet_maker/repositories/bets.py` is still in place and still works — Plan 03 will delete it (and `tests/bet_maker/repositories/`) once Plan 02 removes the last call-site.
- **Phase 9 success criterion #2** (R3 invariant under static audit at the new seam): already locked in by this plan.

---

## Self-Check: PASSED

Files created exist:
- src/bet_maker/selectors/get_pending_locked.py — FOUND
- src/bet_maker/selectors/get_pending_event_ids.py — FOUND
- tests/bet_maker/selectors/__init__.py — FOUND
- tests/bet_maker/selectors/test_get_pending_locked.py — FOUND
- tests/bet_maker/selectors/test_get_pending_event_ids.py — FOUND

Commits exist in `git log --all`:
- baab0d0 — FOUND (Task 1)
- 7d8548b — FOUND (Task 2)
- ce90ddf — FOUND (Task 3)

---
*Phase: 09-uow-repository-removal*
*Completed: 2026-05-18*
