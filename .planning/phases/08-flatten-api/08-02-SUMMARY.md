---
phase: 08-flatten-api
plan: 02
subsystem: api
tags: [fastapi, faststream, rabbitmq, refactor, line_provider]

requires:
  - plan: 08-01
    provides: "bet_maker entrypoints/ eliminated; test_no_entrypoints_dir (bet_maker assertion) added"

provides:
  - "src/line_provider/api/{events,health,messaging}.py — flat api package"
  - "src/line_provider/lifespan.py at service root"
  - "src/line_provider/middleware.py at service root"
  - "tests/audit/test_no_entrypoints_dir — regression guard expanded to both services"

affects:
  - 08-03 (full-suite green gate across both services)

tech-stack:
  added: []
  patterns:
    - "Flat src/line_provider/api/ package: HTTP routers + AMQP RabbitRouter colocated"
    - "lifespan.py + middleware.py at service-package root next to app.py"

key-files:
  created:
    - src/line_provider/api/__init__.py
    - src/line_provider/api/events.py
    - src/line_provider/api/health.py
    - src/line_provider/api/messaging.py
    - src/line_provider/lifespan.py
    - src/line_provider/middleware.py
  modified:
    - src/line_provider/app.py
    - src/line_provider/facades/event_bus.py
    - tests/line_provider/conftest.py
    - tests/line_provider/test_lifespan.py
    - tests/bet_maker/conftest.py
    - tests/bet_maker/test_e2e_rabbitmq.py
    - tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py
    - tests/audit/test_static.py

key-decisions:
  - "Task 1 and Task 2 committed together (same pattern as 08-01): pre-commit mypy strict scans all src/ after stashing unstaged; staging only renames without import rewrites causes mypy to fail on app.py"
  - "ruff I001 import sort order: line_provider.api.messaging sorts before line_provider.app — fixed in same edit pass across conftest.py and test_lifespan.py (4 blocks)"
  - "ruff-format reformatted test_no_entrypoints_dir assert parentheses in test_static.py — re-staged and committed on second attempt"

patterns-established:
  - "line_provider routers imported as: from line_provider.api import events, health; from line_provider.api.messaging import router"
  - "lifespan and middleware imported as: from line_provider.lifespan import lifespan; from line_provider.middleware import RequestContextMiddleware"

requirements-completed:
  - REFACTOR-01
  - REFACTOR-05

duration: 30min
completed: 2026-05-18
---

# Plan 08-02: line_provider entrypoints flatten — Summary

**line_provider entrypoints/ package eliminated: 6 files moved via git mv into flat src/line_provider/api/ + service root; all 87 src files pass mypy strict; 116 line_provider + audit tests green**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-18
- **Completed:** 2026-05-18
- **Tasks:** 3
- **Files modified:** 14 (6 moved + 8 import rewrites)

## Accomplishments

- Deleted `src/line_provider/entrypoints/` directory; replaced with flat `src/line_provider/api/` package containing `events.py`, `health.py`, `messaging.py`
- Relocated `lifespan.py` and `middleware.py` to `src/line_provider/` root next to `app.py`
- Rewritten all `line_provider.entrypoints` references in production code, line_provider tests, and cross-service bet_maker test files
- Expanded `test_no_entrypoints_dir` to assert both `bet_maker` AND `line_provider` directories do not exist — audit guard now fully covers both services

## Task Commits

1. **Task 1 + Task 2: move files (git mv) + rewrite production imports** — `043ccf4` (refactor)
2. **Task 3: rewrite test imports, fix cross-service refs, expand audit guard** — `aa2a2f6` (test)

Note: Tasks 1 and 2 were combined into one commit — same deviation as plan 08-01 (pre-commit mypy strict gate pattern).

## Files Moved (git mv — history preserved)

History verification:

```
git log --follow --oneline src/line_provider/api/messaging.py
043ccf4 refactor(08-02): move line_provider entrypoints to flat layout (git mv)
e03c788 refactor(quick): strip GSD planning markers from src comments
0ac3645 feat(05-06): create line_provider/entrypoints/messaging.py with singleton RabbitRouter

git log --follow --oneline src/line_provider/lifespan.py
043ccf4 refactor(08-02): move line_provider entrypoints to flat layout (git mv)
e03c788 refactor(quick): strip GSD planning markers from src comments
f45ec23 feat(05-07): extend line-provider lifespan with broker layer (D-24)
879ba2b feat(02-07): wire events router and singletons in app + lifespan
a2871c5 feat(01-03): scaffold line_provider settings, /health, middleware, lifespan
```

## Cross-Service Test Fixes

- `tests/bet_maker/test_e2e_rabbitmq.py` line 113: `from line_provider.entrypoints.messaging import router as lp_router` → `from line_provider.api.messaging import router as lp_router` (line 131 was already fixed by 08-01)
- `tests/bet_maker/conftest.py` `line_provider_app` fixture late import: `from line_provider.entrypoints.messaging import router as lp_rabbit_router` → `from line_provider.api.messaging import router as lp_rabbit_router`
- `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` docstring: `line_provider/entrypoints/lifespan.py` → `line_provider/lifespan.py` (INFO-level checker note moved here for cleaner intermediate state)

## Audit Guard Fully Expanded

`tests/audit/test_static.py::test_no_entrypoints_dir` now asserts BOTH services:

```python
bm = SRC / "bet_maker" / "entrypoints"
lp = SRC / "line_provider" / "entrypoints"
assert not bm.exists(), ...
assert not lp.exists(), ...
```

Both assertions active and passing non-vacuously (both directories deleted). 1 passed in 0.01s.

## Grep Gates (all confirmed zero — combining 08-01 + 08-02)

```
git grep -E '(bet_maker|line_provider)\.entrypoints' src/ tests/   # 0 matches
git grep -E '(bet_maker|line_provider)/entrypoints' src/ tests/ | grep -v '^\.planning/'  # 0 matches
find src -type d -name entrypoints                                  # empty output
```

## Files Created/Modified

- `src/line_provider/api/__init__.py` — api package root (moved from entrypoints/__init__.py)
- `src/line_provider/api/events.py` — POST/PUT/GET /event(s) HTTP router (moved from entrypoints/api/events.py)
- `src/line_provider/api/health.py` — GET /health HTTP router (moved from entrypoints/api/health.py)
- `src/line_provider/api/messaging.py` — FastStream RabbitRouter publisher-only singleton (moved from entrypoints/messaging.py)
- `src/line_provider/lifespan.py` — line_provider lifespan; import rewritten (moved + content edit)
- `src/line_provider/middleware.py` — RequestContextMiddleware (moved, no content changes)
- `src/line_provider/app.py` — imports rewritten to new paths
- `src/line_provider/facades/event_bus.py` — docstring self-reference updated
- `tests/line_provider/conftest.py` — late import rewritten; import sort fixed
- `tests/line_provider/test_lifespan.py` — 4 late import blocks rewritten; import sort fixed in all 4 blocks
- `tests/bet_maker/conftest.py` — line_provider_app fixture late import rewritten; import sort fixed
- `tests/bet_maker/test_e2e_rabbitmq.py` — line 113 late import rewritten
- `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` — docstring path updated
- `tests/audit/test_static.py` — test_no_entrypoints_dir expanded to both services

## Decisions Made

- Tasks 1 and 2 committed together for same reason as 08-01: pre-commit mypy strict runs after stashing unstaged; committing renames alone fails mypy on app.py.

## Deviations from Plan

### Auto-fixed Issues

**1. [Commit structure] Task 1 and Task 2 merged into single commit**
- **Found during:** Task 1 commit attempt
- **Issue:** Same as plan 08-01: pre-commit mypy strict scans all src/ after stashing; committing git mv only fails mypy on app.py (7 import errors)
- **Fix:** Staged Task 2 files (app.py, lifespan.py, facades/event_bus.py) together with Task 1 renames before first commit
- **Committed in:** 043ccf4

**2. [ruff I001] Import sort order — 5 occurrences across 3 files**
- **Found during:** Task 3 ruff check
- **Issue:** `line_provider.api.messaging` sorts before `line_provider.app` alphabetically (`api` < `app`); replaced imports landed in wrong order in conftest.py (line_provider), conftest.py (bet_maker), and 4 blocks of test_lifespan.py
- **Fix:** Reordered import pairs in same edit pass
- **Files modified:** tests/line_provider/conftest.py, tests/bet_maker/conftest.py, tests/line_provider/test_lifespan.py (4 blocks)

**3. [ruff-format] test_static.py assert parentheses reformatted**
- **Found during:** Task 3 commit attempt
- **Issue:** New `test_no_entrypoints_dir` multi-line assert with parentheses was reformatted by ruff-format hook to single-line style
- **Fix:** Re-staged the reformatted file and re-ran commit; ruff-format passed on second attempt
- **Committed in:** aa2a2f6

---

**Total deviations:** 3 auto-fixed (1 commit structure, 1 ruff sort, 1 ruff-format)
**Impact on plan:** No scope creep; all fixes mechanical. Three logical tasks delivered in two commits.

## Issues Encountered

None beyond the auto-fixed deviations above.

## User Setup Required

None.

## Next Phase Readiness

- Both bet_maker and line_provider entrypoints fully flattened; all grep gates confirmed zero; mypy strict clean; ruff clean
- Plan 08-03 can proceed: full repo pytest + coverage gate across both services
- `pytest --collect-only tests/bet_maker/test_e2e_rabbitmq.py` exits 0 (both line 113 and 131 resolve via new paths)

---
*Phase: 08-flatten-api*
*Completed: 2026-05-18*
