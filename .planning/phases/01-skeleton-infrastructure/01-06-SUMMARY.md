---
phase: 01-skeleton-infrastructure
plan: 06
subsystem: infra
tags: [ci, github-actions, pre-commit, ruff, mypy, pytest, uv]

requires:
  - phase: 01-skeleton-infrastructure
    provides: "Root pyproject.toml with ruff/mypy/pytest config, uv.lock for frozen install"
provides:
  - ".github/workflows/ci.yml — single quality job (ubuntu-latest) running ruff check + ruff format --check + mypy strict + pytest -q on every push and PR to main (D-06, D-07)"
  - "Pinned uv via astral-sh/setup-uv@v3 with version 0.11.14 and uv.lock-based cache (T-06-04 mitigation)"
  - "Python 3.10.20 pinned via uv python install (D-09 single pin, no matrix)"
  - "concurrency.cancel-in-progress for stale-run cancellation (T-06-05 mitigation)"
  - "permissions: contents: read at workflow level (T-06-01 mitigation, least privilege)"
  - ".pre-commit-config.yaml with 9 hooks from D-10: ruff fix + ruff-format (v0.15.12 matches pyproject pin), pre-commit-hooks v5.0.0 (check-merge-conflict, end-of-file-fixer, trailing-whitespace, check-yaml, check-toml, check-added-large-files --maxkb=500), local mypy strict via uv run"
  - "Local mypy hook (NOT mirrors-mypy) — preserves pydantic.mypy plugin and project deps inside the uv-managed venv"
affects: [phase-02-line-provider, phase-03-bet-maker-db, phase-04-http-integration, phase-05-rabbitmq, phase-06-reconciliation, phase-07-polish]

tech-stack:
  added:
    - "GitHub Actions ci.yml (workflow shape, no new runtime deps)"
    - "pre-commit configuration (no new pyproject deps — pre-commit itself already in [dependency-groups] dev)"
  patterns:
    - "Single CI job (no matrix) — D-09; expansion paths (PG/RMQ services) deferred to P3/P5 (D-08)"
    - "Local mypy pre-commit hook through uv run — avoids the upstream mirror's isolated venv that would lose pydantic.mypy plugin"
    - "Ruff version pinned identically in pyproject.toml (>=0.15,<0.16) and .pre-commit-config.yaml (v0.15.12) — drift-proof"
    - "Workflow-level least-privilege (contents: read) and concurrency cancel-in-progress — production hygiene patterns"

key-files:
  created:
    - ".github/workflows/ci.yml — CI workflow with quality job (8 steps per D-06)"
    - ".pre-commit-config.yaml — 9 hooks per D-10"
    - ".planning/phases/01-skeleton-infrastructure/deferred-items.md — out-of-scope trailing-whitespace fixes log"
  modified: []

key-decisions:
  - "Pinned astral-sh/setup-uv@v3 with explicit version 0.11.14 (T-06-03 mitigation, matches CLAUDE.md Technology Stack)"
  - "Used uv python install 3.10.20 (not setup-python) — keeps the runtime-installer aligned with local uv-managed Python; D-09 single-pin enforced (no matrix)"
  - "Mypy as a LOCAL pre-commit hook through entry: uv run mypy --strict src — required by D-10; upstream mirrors-mypy would spawn its own venv and lose the pydantic.mypy plugin"
  - "ruff rev locked to v0.15.12 in .pre-commit-config.yaml to match the pyproject pin (>=0.15,<0.16) — eliminates drift between local hooks and CI (T-06-04)"
  - "No PG/RMQ services in CI at P1 (D-08) — phase 3 (PG) and phase 5 (RMQ) add them when integration tests need them"
  - "check-added-large-files --maxkb=500 — prevents accidental commit of binaries/dumps (T-06-06 mitigation)"

patterns-established:
  - "All quality gates (ruff, mypy, pytest) executed through uv run so the local venv is the single source of truth — CI never installs its own ruff/mypy outside uv"
  - "Pre-commit hooks pinned by rev and version so they cannot drift independently of pyproject.toml"
  - "Concurrency group keyed by workflow + ref so feature-branch pushes cancel their stale runs automatically"

requirements-completed: [QA-02, QA-03, QA-10]

duration: 2min
completed: 2026-05-14
---

# Phase 1 Plan 6: CI + pre-commit Summary

**GitHub Actions ci workflow (ubuntu-latest, single quality job: ruff + mypy strict + pytest, uv 0.11.14 + Python 3.10.20 pinned) and 9-hook .pre-commit-config.yaml (ruff fix/format v0.15.12 matched to pyproject, hygiene hooks v5.0.0, local mypy strict via uv run) — closes QA-02, QA-03, QA-10.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-14T09:49:56Z
- **Completed:** 2026-05-14T09:52:13Z
- **Tasks:** 2 (both atomic-committed)
- **Files created:** 3 (2 in-plan + 1 deferred-items log)

## Accomplishments

- `.github/workflows/ci.yml` with one `quality` job on `ubuntu-latest` running the canonical D-06 chain (checkout v4 → setup-uv v3 with `enable-cache: true` and `cache-dependency-glob: uv.lock` → `uv python install 3.10.20` → `uv sync --frozen --all-extras` → `uv run ruff check .` → `uv run ruff format --check .` → `uv run mypy src` → `uv run pytest -q`)
- D-07 triggers wired: `push` on any branch (`["**"]`) + `pull_request` to `main` only
- `permissions: { contents: read }` at workflow level (T-06-01) and `concurrency.cancel-in-progress: true` (T-06-05) added without scope creep
- `.pre-commit-config.yaml` with all 9 hooks from D-10 in place: `ruff` (with `--fix`), `ruff-format`, `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`, `check-yaml`, `check-toml`, `check-added-large-files --maxkb=500`, and local `mypy strict`
- Local mypy hook uses `entry: uv run mypy --strict src`, `language: system`, `pass_filenames: false`, `types_or: [python, pyi]`, `require_serial: true` — exactly the D-10 spec; avoids `mirrors-mypy` which would create an isolated venv and silently lose `pydantic.mypy`
- Ruff version locked at `v0.15.12` inside `.pre-commit-config.yaml`, identical to the pyproject pin (`ruff>=0.15,<0.16`) — drift impossible
- `uv run pre-commit install` ran successfully (writes `.git/hooks/pre-commit`)
- `uv run pre-commit run --all-files` smoke run passed all gates: ruff/ruff-format clean, mypy strict clean, all hygiene hooks pass (the two existing planning files that were autofixed are documented in `deferred-items.md` and reverted — see Deviations)

## Task Commits

1. **Task 1: Create .github/workflows/ci.yml — quality job** — `1000775` (feat)
2. **Task 2: Create .pre-commit-config.yaml with D-10 hook set** — `5d7e4a7` (feat) — also includes `.planning/phases/01-skeleton-infrastructure/deferred-items.md`

## Files Created/Modified

- `.github/workflows/ci.yml` — single `quality` job, 8 D-06 steps, no services, no matrix, concurrency group keyed by workflow+ref, `permissions: contents: read`
- `.pre-commit-config.yaml` — 3 repo entries (ruff-pre-commit v0.15.12, pre-commit-hooks v5.0.0, local), 9 total hooks
- `.planning/phases/01-skeleton-infrastructure/deferred-items.md` — log of out-of-scope trailing-whitespace fixes surfaced by the smoke run (planning docs only)

## Decisions Made

- **Pinned `astral-sh/setup-uv@v3` to `version: "0.11.14"`** — matches CLAUDE.md Technology Stack and the orchestrator's note that local uv 0.10.8 must not propagate; explicit pin defeats T-06-03 (Python/uv drift) at the CI boundary
- **`uv python install 3.10.20` instead of `actions/setup-python`** — keeps the Python installer under uv so the CI matches local `.python-version` semantics
- **Local mypy pre-commit hook** through `uv run mypy --strict src` rather than the `mirrors-mypy` upstream — mirror creates its own isolated venv, would not see `pydantic.mypy` plugin nor the project's pinned types; local hook reuses the uv venv exactly like CI does
- **No PG/RMQ as CI services** in this plan (D-08) — adds nothing because no integration test currently needs them; deferred to P3 (PG) and P5 (RMQ)
- **No `pytest-cov` gate** in this CI run — there is no business logic yet to measure; the gate enters in P7 (QA-09)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Out-of-scope trailing-whitespace fixes surfaced by smoke pre-commit run**
- **Found during:** Task 2 verification (`uv run pre-commit run --all-files` smoke run before commit)
- **Issue:** `trailing-whitespace` hook trimmed trailing spaces in `.planning/phases/01-skeleton-infrastructure/01-05-PLAN.md` and `.planning/research/ARCHITECTURE.md`. Both files are outside plan 01-06's declared `files_modified` scope (`.github/workflows/ci.yml` and `.pre-commit-config.yaml`).
- **Fix:** Reverted the hook's auto-fix on those two files (`git checkout -- <file>`) to keep plan 01-06 commits minimal and focused. Logged the residual whitespace noise in `.planning/phases/01-skeleton-infrastructure/deferred-items.md` so a future housekeeping commit (or any future commit that legitimately touches those files) can clean them in-place.
- **Files modified:** Only `.planning/phases/01-skeleton-infrastructure/deferred-items.md` (new tracking log; not in `files_modified` but is a planning artefact about THIS plan, hence acceptable)
- **Verification:** `git status --short` after revert shows only `.pre-commit-config.yaml` and `deferred-items.md` staged for the Task 2 commit. Subsequent `git commit` runs the installed pre-commit hooks against the staged subset; all hooks pass (some report `(no files to check)` because no matching files are staged).
- **Committed in:** `5d7e4a7` (Task 2 commit, deferred-items.md included)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking)
**Impact on plan:** No scope creep. The auto-fix prevented an unrelated whitespace-cleanup commit from being entangled with the CI/pre-commit plan. Plan acceptance criteria (file existence, YAML validity, all grep checks, no emojis, no comments) all pass.

## Issues Encountered

- System Python lacks `PyYAML`, so the plan's `<automated>` verification (`python3 -c "import yaml; …"`) failed initially. Switched to `uv run python -c "…"` which uses the project venv where PyYAML is available transitively (via `pre-commit` → `cfgv` chain in `uv.lock`). All structural YAML checks pass.
- The plan's `<automated>` snippet uses bare `'on'` as a dict key, but PyYAML 1.1-mode parses bare `on` as the boolean `True`. Adjusted verification code to handle both `True` and `'on'` lookups before asserting. The actual `ci.yml` is correct (it uses the literal `on:` key, which YAML 1.1 collapses to `True` on parse but renders correctly back to `on:` everywhere outside Python). GitHub Actions itself parses `on:` correctly regardless.

## User Setup Required

None — the workflow runs the first time a commit is pushed to GitHub. No external secrets, no third-party integrations. The pre-commit hook is enabled locally by `uv run pre-commit install` (already done as part of this plan); collaborators just run that command after `git clone`.

## Next Phase Readiness

- **Ready for Phase 1 Plan 07 (README + smoke tests):** CI workflow exists, badge URL `https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg` is stable; smoke tests (D-11, D-12) plug into the existing `uv run pytest -q` step without workflow changes
- **Ready for Phase 3 (bet-maker DB):** when integration tests against PostgreSQL land, P3 can add a `services: postgres:` block to `ci.yml` and a `--cov` flag to the pytest step
- **Ready for Phase 5 (RabbitMQ integration):** P5 can add a `services: rabbitmq:` block following the same pattern
- **No blockers identified.**

## TDD Gate Compliance

Not a TDD plan (`type: execute`, all tasks `tdd="false"`). Gate sequence not applicable.

## Threat Flags

None — purely tooling config (CI workflow + pre-commit hooks). No new network surface, no auth paths, no trust-boundary schema changes, no runtime code added. All threat-model items from the plan (T-06-01..T-06-06) are addressed by the workflow itself (`permissions: contents: read`, `concurrency.cancel-in-progress`, ruff version match, explicit uv/Python pins, `check-added-large-files --maxkb=500`).

## Self-Check: PASSED

- `.github/workflows/ci.yml` — FOUND (commit `1000775`)
- `.pre-commit-config.yaml` — FOUND (commit `5d7e4a7`)
- `.planning/phases/01-skeleton-infrastructure/deferred-items.md` — FOUND (commit `5d7e4a7`)
- Commit `1000775` — FOUND in `git log`
- Commit `5d7e4a7` — FOUND in `git log`
- All Task 1 acceptance criteria grep-checked PASS (file exists, valid YAML, `name: ci`, push `["**"]`, PR `[main]`, `runs-on: ubuntu-latest`, `actions/checkout@v4`, `astral-sh/setup-uv@v3`, `enable-cache: true`, `cache-dependency-glob: "uv.lock"`, `uv python install 3.10.20`, `uv sync --frozen --all-extras`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest -q`, no `services:`, no `matrix:`, no emoji)
- All Task 2 acceptance criteria grep-checked PASS (file exists, valid YAML, all 9 hook ids present, ruff `rev: v0.15.12`, mypy `entry: uv run mypy --strict src`, `pass_filenames: false`, `types_or: [python, pyi]`, `language: system`, no emoji)
- `uv run pre-commit run --all-files` — VERIFIED green (ruff/ruff-format/check-merge-conflict/end-of-file-fixer/check-yaml/check-toml/check-added-large-files/mypy strict all PASS; the single trailing-whitespace finding documented in Deviations)
- No emojis in any created file — VERIFIED
- No code comments added — VERIFIED

---
*Phase: 01-skeleton-infrastructure*
*Completed: 2026-05-14*
