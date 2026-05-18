---
phase: 08-flatten-api
plan: 01
subsystem: api
tags: [fastapi, faststream, rabbitmq, refactor, bet_maker]

requires:
  - phase: 07-static-audit
    provides: "test_static.py audit framework for source-level invariants"
  - phase: 06-reconciliation-job
    provides: "lifespan.py + reconciler fully wired in bet_maker"
  - phase: 05-rabbitmq-integration
    provides: "RabbitRouter + messaging.py subscriber + DLQ topology"

provides:
  - "src/bet_maker/api/{bets,events,health,messaging}.py — flat api package"
  - "src/bet_maker/lifespan.py at service root"
  - "src/bet_maker/middleware.py at service root"
  - "tests/audit/test_no_entrypoints_dir — regression guard (bet_maker)"

affects:
  - 08-02 (line_provider entrypoints migration — sister plan)
  - 08-03 (full-suite green gate across both services)

tech-stack:
  added: []
  patterns:
    - "Flat src/<svc>/api/ package: HTTP routers + AMQP RabbitRouter colocated"
    - "lifespan.py + middleware.py at service-package root next to app.py"

key-files:
  created:
    - src/bet_maker/api/__init__.py
    - src/bet_maker/api/bets.py
    - src/bet_maker/api/events.py
    - src/bet_maker/api/health.py
    - src/bet_maker/api/messaging.py
    - src/bet_maker/lifespan.py
    - src/bet_maker/middleware.py
  modified:
    - src/bet_maker/app.py
    - src/bet_maker/facades/deps.py
    - src/bet_maker/jobs/__init__.py
    - tests/bet_maker/conftest.py
    - tests/bet_maker/test_health.py
    - tests/bet_maker/test_lifespan.py
    - tests/bet_maker/test_lifespan_reconciler.py
    - tests/bet_maker/test_messaging.py
    - tests/bet_maker/test_e2e_rabbitmq.py
    - tests/audit/test_static.py

key-decisions:
  - "Task 1 and Task 2 commits merged into one: pre-commit mypy strict checks all of src/ after stashing unstaged files; committing Task 1 (renamed files) without Task 2 (import rewrites) would fail mypy on app.py"
  - "test_no_entrypoints_dir asserts only bet_maker at this stage; line_provider assertion deferred to 08-02"
  - "test_e2e_rabbitmq.py line 131 (bet_maker side) fixed; line 113 (line_provider side) left for 08-02"

patterns-established:
  - "bet_maker routers imported as: from bet_maker.api import bets, events, health; from bet_maker.api.messaging import router"
  - "lifespan and middleware imported as: from bet_maker.lifespan import lifespan; from bet_maker.middleware import RequestContextMiddleware"

requirements-completed:
  - REFACTOR-01
  - REFACTOR-05

duration: 35min
completed: 2026-05-18
---

# Plan 08-01: bet_maker entrypoints flatten — Summary

**bet_maker entrypoints/ package eliminated: 7 files moved via git mv into flat src/bet_maker/api/ + service root; all 88 src files pass mypy strict; 245 tests green**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-05-18T12:00Z
- **Completed:** 2026-05-18T12:35Z
- **Tasks:** 3
- **Files modified:** 18 (7 moved + 11 import rewrites)

## Accomplishments

- Deleted `src/bet_maker/entrypoints/` directory; replaced with flat `src/bet_maker/api/` package containing `bets.py`, `events.py`, `health.py`, `messaging.py`
- Relocated `lifespan.py` and `middleware.py` to `src/bet_maker/` root next to `app.py`
- Rewritten all `bet_maker.entrypoints` references (production + test + audit) to new paths; grep gates confirmed zero hits
- Added `test_no_entrypoints_dir` static audit regression guard (bet_maker assertion active; line_provider deferred to 08-02)

## Task Commits

1. **Task 1 + Task 2: move files (git mv) + rewrite production imports** — `97420eb` (refactor)
2. **Task 3: rewrite test imports and update audit paths** — `a63905c` (test)

Note: Tasks 1 and 2 were combined into one commit — see Deviations below.

## Files Moved (git mv — history preserved)

History verification example:

```
git log --follow --oneline src/bet_maker/api/messaging.py
97420eb refactor(08-01): move bet_maker entrypoints to flat layout (git mv)
e03c788 refactor(quick): strip GSD planning markers from src comments
63698d4 fix(05): WR-01 accept raw dict payload in on_event_finished...
d1f96e5 test(05-05): replace stub test_messaging.py with full 7-branch TestRabbitBroker suite
1f88171 feat(05-05): implement RabbitRouter consumer entrypoint with manual-ack ladder
```

## Grep Gates (both confirmed zero)

```
git grep -E 'bet_maker\.entrypoints' src/ tests/   # 0 matches
git grep -E 'bet_maker/entrypoints' src/ tests/    # 0 matches
find src/bet_maker -type d -name entrypoints        # empty output
```

## New Audit Test

`tests/audit/test_static.py::test_no_entrypoints_dir` — asserts `src/bet_maker/entrypoints` does not exist. Active for bet_maker only at this stage; plan 08-02 expands it to also cover line_provider.

## test_e2e_rabbitmq.py Fix

- Line 131: `from bet_maker.entrypoints.messaging import router as bm_router` → `from bet_maker.api.messaging import router as bm_router` (fixed in this plan)
- Line 113: `from line_provider.entrypoints.messaging import router as lp_router` — left untouched; plan 08-02 moves line_provider, that edit belongs there. Both imports resolve at collection time: line 113 through legacy path (line_provider not moved yet), line 131 through new path.

## Files Created/Modified

- `src/bet_maker/api/__init__.py` — api package root (moved from entrypoints/api/)
- `src/bet_maker/api/bets.py` — POST /bet + GET /bets + GET /bet/{id} (moved)
- `src/bet_maker/api/events.py` — GET /events proxy router (moved)
- `src/bet_maker/api/health.py` — GET /health (moved)
- `src/bet_maker/api/messaging.py` — FastStream RabbitRouter + on_event_finished; docstring updated (moved + content edit)
- `src/bet_maker/lifespan.py` — bet_maker lifespan; imports rewritten (moved + content edit)
- `src/bet_maker/middleware.py` — RequestContextMiddleware (moved, no content changes)
- `src/bet_maker/app.py` — imports rewritten to new paths
- `src/bet_maker/facades/deps.py` — late import + docstring updated
- `src/bet_maker/jobs/__init__.py` — docstring updated
- `tests/bet_maker/conftest.py` — bet_maker-side import updated
- `tests/bet_maker/test_health.py` — patch target + 2 late imports updated
- `tests/bet_maker/test_lifespan.py` — 4 late imports + patch string + lifespan import updated
- `tests/bet_maker/test_lifespan_reconciler.py` — top-level import updated + import order fixed
- `tests/bet_maker/test_messaging.py` — top import + 6 patch strings + 1 path string + 1 _SCHEMA_VERSION patch updated
- `tests/bet_maker/test_e2e_rabbitmq.py` — line 131 late import updated
- `tests/audit/test_static.py` — 2 path strings updated + test_no_entrypoints_dir added

## Decisions Made

- Task 1 and Task 2 committed together: pre-commit mypy strict runs on all of `src/` (not just staged files) after stashing unstaged. With Task 1 staged alone, app.py still had old imports in the unstaged stash; pre-commit restores unstaged and then runs mypy against the full working tree with `app.py` still having old `entrypoints` imports → failure. Staging both Task 1 and Task 2 files together before committing is the only way to satisfy the pre-commit gate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Commit structure] Task 1 and Task 2 merged into single commit**
- **Found during:** Task 1 commit attempt
- **Issue:** pre-commit mypy strict scans all `src/` after stashing unstaged changes. Committing Task 1 (git mv only) without Task 2 import rewrites caused mypy to report 7 errors in app.py, lifespan.py, deps.py
- **Fix:** Added Task 2 files to staging before the first commit; Task 1 message retained
- **Files modified:** src/bet_maker/app.py, src/bet_maker/lifespan.py, src/bet_maker/api/messaging.py, src/bet_maker/facades/deps.py, src/bet_maker/jobs/__init__.py
- **Verification:** pre-commit passed; mypy strict: 0 errors in 88 files
- **Committed in:** 97420eb

**2. [ruff-format] test_static.py assert parentheses removed by ruff-format hook**
- **Found during:** Task 3 commit attempt
- **Issue:** New `test_no_entrypoints_dir` used parenthesised assert `assert not bm.exists(), (f"...")` which ruff-format collapsed to single-line
- **Fix:** Re-staged the reformatted file and re-ran commit; ruff-format passed on second attempt
- **Files modified:** tests/audit/test_static.py
- **Verification:** ruff-format hook passed on second commit attempt
- **Committed in:** a63905c

---

**Total deviations:** 2 auto-fixed (1 commit structure, 1 ruff-format hook)
**Impact on plan:** No scope creep; both fixes mechanical. Three logical tasks delivered in two commits instead of three.

## Issues Encountered

- ruff I001 (import sort order) on several test files after replacing `bet_maker.entrypoints.messaging` with `bet_maker.api.messaging`: `api.messaging` sorts before `app` alphabetically, requiring import block reorder in conftest.py and test_lifespan.py. Also `facades.http_event_lookup` sorts before `lifespan` in test_lifespan_reconciler.py. Fixed in same edit pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- bet_maker entrypoints fully flattened; all 245 tests green; mypy strict clean; ruff clean
- Plan 08-02 can proceed: moves line_provider entrypoints to flat layout; expands test_no_entrypoints_dir to cover line_provider; fixes line 113 of test_e2e_rabbitmq.py and the line_provider_app fixture in tests/bet_maker/conftest.py
- Plan 08-03 (final full-suite green gate) requires 08-02 to land first

---
*Phase: 08-flatten-api*
*Completed: 2026-05-18*
