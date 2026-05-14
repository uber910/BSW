---
phase: 01-skeleton-infrastructure
plan: 01
subsystem: infra
tags: [python, uv, ruff, mypy, pytest, hatch, monorepo, src-layout]

requires: []
provides:
  - "Single root pyproject.toml ('bsw' distribution, PEP 621-compliant, requires-python >=3.10,<3.11)"
  - "uv.lock with 68 resolved packages, deterministic via uv sync --frozen"
  - "[tool.hatch.build.targets.wheel] packages = src/line_provider, src/bet_maker, src/config (D-01)"
  - "[tool.ruff] with rule set E,W,F,I,B,UP,N,SIM,ASYNC,PL,RUF (QA-02 baseline)"
  - "[tool.mypy] strict=true with pydantic.mypy plugin (QA-01 baseline; full src/ gate deferred to plan 06/07)"
  - "[tool.pytest.ini_options] asyncio_mode='auto', pythonpath=['src'] (D-13)"
  - ".python-version pinned to 3.10.20"
  - ".gitignore covering .venv, __pycache__, .env, tooling caches, dist/build"
  - "Empty package stubs src/line_provider/__init__.py, src/bet_maker/__init__.py, src/config/__init__.py (Rule 3 — required for hatch editable build)"
affects: [phase-02-line-provider, phase-03-bet-maker-db, phase-04-http-integration, phase-05-rabbitmq, phase-06-reconciliation, phase-07-polish]

tech-stack:
  added:
    - "fastapi (>=0.115,<0.137)"
    - "uvicorn[standard] (>=0.46,<0.47)"
    - "pydantic (>=2.13,<3)"
    - "pydantic-settings (>=2.14,<3)"
    - "faststream[rabbit] (>=0.6,<0.7) — pulls aio-pika>=9,<10 transitively"
    - "sqlalchemy[asyncio] (>=2.0.40,<2.1)"
    - "asyncpg (>=0.31,<0.32)"
    - "alembic (>=1.18,<2)"
    - "httpx (>=0.28,<0.29)"
    - "tenacity (>=9.1,<10)"
    - "structlog (>=25.5,<26)"
    - "pytest (>=9.0,<10) + pytest-asyncio (>=1.1,<2) + pytest-cov (>=7.1,<8)"
    - "ruff (>=0.15,<0.16), mypy (>=2.1,<3), pre-commit (>=4.6,<5)"
  patterns:
    - "src/ layout monorepo, single root pyproject.toml, single uv.lock"
    - "Three logical packages declared via hatch: line_provider, bet_maker, config (no [tool.uv.workspace] — D-01 explicit)"
    - "Dev dependencies in [dependency-groups] dev (PEP 735), not in [project.optional-dependencies]"
    - "Distribution build via hatchling; package = true in [tool.uv] so editable installs work"

key-files:
  created:
    - "pyproject.toml — single source of truth for deps, build, ruff, mypy, pytest"
    - "uv.lock — pinned dependency graph (1040 lines, 68 packages)"
    - ".python-version — 3.10.20 (CLAUDE.md Technology Stack)"
    - ".gitignore — standard Python ignores + .env + tooling caches"
    - "README.md — placeholder (DOC-01 expands in Phase 7)"
    - "src/line_provider/__init__.py — empty stub (Phase 2 fills)"
    - "src/bet_maker/__init__.py — empty stub (Phase 3 fills)"
    - "src/config/__init__.py — empty stub (Phase 5 fills shared Settings)"
  modified: []

key-decisions:
  - "Pinned distribution name 'bsw' with semver-style range pins (>=X,<Y) for every runtime dep — pinned by CLAUDE.md Technology Stack, transitive resolution captured in uv.lock"
  - "Used [dependency-groups] dev (PEP 735) per uv documentation, not the legacy [project.optional-dependencies] pattern"
  - "No [tool.uv.workspace] section — D-01 explicitly mandates a single package, not a workspace"
  - "Created empty package __init__.py stubs in Wave 1 (Rule 3 deviation) — without them hatch fails the editable build that uv sync --frozen performs; real modules land in plans 02/03/04"
  - "uv 0.10.8 used locally (CLAUDE.md recommends 0.11.14); the resolver behaviour is compatible for this lock, and CI image (plan 06) will pin 0.11.x"

patterns-established:
  - "Single root pyproject.toml as the single source of truth — no per-package pyproject"
  - "Editable install (uv sync) builds the wheel against src/<package>/ — all imports from src/ must use absolute paths from these three roots"
  - "ruff + mypy strict + pytest config all live in [tool.*] sections of the root pyproject"

requirements-completed: [INFR-01, INFR-02, QA-02, QA-10]

duration: 4min
completed: 2026-05-14
---

# Phase 1 Plan 1: Project Skeleton (pyproject + uv.lock + ignore) Summary

**Single root pyproject.toml for the 'bsw' distribution with pinned runtime + dev dependencies, hatch-declared src/ packages, ruff/mypy/pytest config, deterministic uv.lock (68 packages), and .python-version pin to 3.10.20 — foundation for all subsequent phases.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-14T09:24:00Z
- **Completed:** 2026-05-14T09:27:59Z
- **Tasks:** 2 (both atomic-committed)
- **Files created:** 7 (4 in-plan + 3 Rule 3 stubs)

## Accomplishments

- Root `pyproject.toml` with all 11 runtime deps and 6 dev deps pinned per CLAUDE.md Technology Stack ranges
- `uv.lock` generated (1040 lines, 68 resolved packages); `uv sync --frozen` is deterministic
- Build target: three hatch packages under `src/` (D-01), not a uv workspace
- `[tool.ruff] select` includes the full mandated rule set `E,W,F,I,B,UP,N,SIM,ASYNC,PL,RUF` with `tests/**` ignoring `PLR2004,S101` and `alembic/versions/*.py` ignoring `E501,N999`
- `[tool.mypy] strict = true` with `pydantic.mypy` plugin and per-file relaxation for `tests.*`
- `[tool.pytest.ini_options]` sets `asyncio_mode = "auto"` and `pythonpath = ["src"]` (D-13)
- `.python-version` pinned to `3.10.20`, `.gitignore` excludes `.venv/`, `__pycache__/`, `.env`, all tooling caches and build artefacts
- `uv run mypy --version`, `uv run ruff check .`, `uv run pytest --collect-only` all succeed (Wave 1 tool gates are green; full `uv run mypy src` deferred to plan 06/07 as planned)

## Task Commits

1. **Task 1: Create pyproject.toml** — `0af1bcd` (feat)
2. **Task 2: Create .python-version, .gitignore, uv.lock (+ Rule 3 stubs)** — `2dcbd3d` (feat)

## Files Created/Modified

- `pyproject.toml` — root project config: [project], [dependency-groups], [build-system], [tool.hatch.build.targets.wheel], [tool.ruff], [tool.mypy], [tool.pydantic-mypy], [tool.pytest.ini_options], [tool.uv]
- `uv.lock` — 1040 lines, 68 resolved packages, includes fastapi 0.136.x, faststream 0.6.x (with aio-pika 9.6.x transitive), sqlalchemy 2.0.49, asyncpg 0.31.x, alembic 1.18.x, pydantic 2.13.4, pydantic-settings 2.14.1, structlog 25.5.0, httpx 0.28.x, tenacity 9.1.4, uvicorn 0.46.0, plus dev deps
- `.python-version` — `3.10.20`
- `.gitignore` — Python + tooling-cache + .env + IDE + build/dist coverage
- `README.md` — placeholder (DOC-01 expands in Phase 7)
- `src/line_provider/__init__.py` — empty (Phase 2 fills with entrypoint, facades, interactors, helpers)
- `src/bet_maker/__init__.py` — empty (Phase 3 fills)
- `src/config/__init__.py` — empty (Phase 5 fills shared Settings class)

## Decisions Made

- **Range pins, not exact pins**, in `pyproject.toml` — exact versions captured in `uv.lock`; this matches the CLAUDE.md guidance and `pip-tools`/`uv` best practice
- **`[dependency-groups] dev`** (PEP 735) chosen over `[project.optional-dependencies]` — uv-native, future-proof
- **No `[tool.uv.workspace]`** — D-01 explicitly mandates single-package model
- **`package = true`** under `[tool.uv]` — required so `uv sync` performs the editable install and exposes `line_provider`, `bet_maker`, `config` modules to the venv
- **Empty `__init__.py` stubs in Wave 1** — Rule 3 deviation (see below); without them hatch refuses to build the editable wheel and `uv sync --frozen` (an acceptance criterion) fails. Real module content lands in plans 02/03/04.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Added README.md placeholder and three empty `__init__.py` package stubs**
- **Found during:** Task 2 (running `uv sync --frozen`)
- **Issue:** hatchling refuses to build the editable wheel because (a) `[project] readme = "README.md"` references a missing file and (b) `[tool.hatch.build.targets.wheel] packages = ["src/line_provider", "src/bet_maker", "src/config"]` references three non-existent directories. The plan's own acceptance criterion `uv sync --frozen` exits 0 therefore cannot be met without these files. Creating `src/` was outside the plan's declared `files_modified` list (which lists only `pyproject.toml`, `.python-version`, `.gitignore`, `uv.lock`), but the alternative — disabling `package = true` or removing the hatch packages list — would break D-01 and contradict the plan's explicit instruction.
- **Fix:** Created (a) a one-line `README.md` placeholder noting that Phase 7 DOC-01 expands it, and (b) empty `src/line_provider/__init__.py`, `src/bet_maker/__init__.py`, `src/config/__init__.py`. These are namespace markers — zero code, zero behaviour, no API surface introduced. Phases 02/03/04 will populate the actual modules.
- **Files modified:** `README.md`, `src/line_provider/__init__.py`, `src/bet_maker/__init__.py`, `src/config/__init__.py`
- **Verification:** `uv sync --frozen` exits 0; `uv run mypy --version` exits 0; `uv run ruff check .` returns "All checks passed!"; `uv run pytest --collect-only` runs (no tests collected, expected)
- **Committed in:** `2dcbd3d` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking)
**Impact on plan:** Necessary for the plan's own acceptance criterion `uv sync --frozen` to pass. Zero scope creep — stubs are empty, no code or behaviour added. Subsequent plans simply add files inside the existing directories.

## Issues Encountered

- Local `uv` version is `0.10.8`, but CLAUDE.md Technology Stack lists `0.11.14`. The resolver and lock format are compatible (the lock validates and `uv sync --frozen` is deterministic), so the produced `uv.lock` is portable to a 0.11.x environment. Plan 06 (CI workflow) should pin the CI image to `uv>=0.11`.

## User Setup Required

None — purely tooling artefacts. No external services required at this stage.

## Next Phase Readiness

- **Ready for Phase 2 (line-provider domain):** `src/line_provider/__init__.py` exists; Phase 2 plans can populate `entrypoints/`, `facades/`, `interactors/`, `selectors/`, `helpers/` under it.
- **Ready for Phase 3 (bet-maker DB):** `src/bet_maker/__init__.py` exists; Phase 3 will add SQLAlchemy models, Alembic env, UoW.
- **Ready for Phase 5 (RabbitMQ integration):** `src/config/__init__.py` exists; Phase 5 (or earlier shared-settings plan) will populate the typed `Settings` class on top of pydantic-settings.
- **No blockers identified.**

## TDD Gate Compliance

Not a TDD plan (plan frontmatter `type: execute`, all tasks `tdd="false"`). Gate sequence not applicable.

## Threat Flags

None — purely tooling config. No new network surface, no auth paths, no trust-boundary schema changes.

## Self-Check: PASSED

- `pyproject.toml` — FOUND (commit `0af1bcd`)
- `.python-version` — FOUND (commit `2dcbd3d`)
- `.gitignore` — FOUND (commit `2dcbd3d`)
- `uv.lock` — FOUND, 1040 lines (commit `2dcbd3d`)
- `README.md` — FOUND (commit `2dcbd3d`, placeholder)
- `src/line_provider/__init__.py`, `src/bet_maker/__init__.py`, `src/config/__init__.py` — FOUND (commit `2dcbd3d`)
- Commit `0af1bcd` — FOUND in `git log`
- Commit `2dcbd3d` — FOUND in `git log`
- `uv sync --frozen` exit code 0 — VERIFIED
- All plan acceptance criteria (Task 1 + Task 2) grep-checked PASS — VERIFIED
- No emojis in any created file — VERIFIED
- No code comments added (only standard `.gitignore` section headers, which are allowed) — VERIFIED

---
*Phase: 01-skeleton-infrastructure*
*Completed: 2026-05-14*
