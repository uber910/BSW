# Phase 01 - Deferred Items

Items discovered during plan execution but out of the current plan's scope. Tracked here for future cleanup.

## From Plan 01-06 (CI + pre-commit)

### Trailing-whitespace noise in planning documents

**Discovered during:** `uv run pre-commit run --all-files` smoke run.

**Files affected:**
- `.planning/phases/01-skeleton-infrastructure/01-05-PLAN.md`
- `.planning/research/ARCHITECTURE.md`

**What pre-commit reported:** `trailing-whitespace` hook trimmed trailing spaces on existing lines.

**Why deferred:** These are planning artefacts written before pre-commit was installed; they are out of scope of plan 01-06 (`files_modified` covers only `.github/workflows/ci.yml` and `.pre-commit-config.yaml`). Auto-fix has been reverted to keep plan 01-06 commit minimal and focused.

**Resolution:** Will be cleaned automatically the first time any future commit touches these files (pre-commit will fix them in-place). Alternatively, a single housekeeping commit can run `uv run pre-commit run --all-files` and commit the fixes once Phase 1 closes.
