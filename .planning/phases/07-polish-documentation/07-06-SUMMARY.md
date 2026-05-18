---
plan: 07-06-ci-coverage-gate
status: complete
date: 2026-05-18
---

# Plan 07-06 — CI Coverage Gate

## Purpose

Extend the CI Pytest step to enforce ≥85% coverage per CONTEXT.md D-15.
Single-line change in `.github/workflows/ci.yml`; pyproject.toml untouched.

## Diff

```yaml
# BEFORE
- name: Pytest
  run: uv run pytest -q

# AFTER
- name: Pytest
  run: uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85
```

## Local Verification

```
$ uv run pytest -q --cov --cov-report=term-missing --cov-fail-under=85
...
Required test coverage of 85% reached. Total coverage: 95.47%
349 passed, 26 warnings in 26.13s
```

**Coverage: 95.47%** (well above the 85% gate). Total tests: 349 (includes
6 new ErrorDetail tests added by plan 07-02).

## Verification Against Pitfall 2 (RESEARCH.md)

Used bare `--cov` (no path argument) so `[tool.coverage.run] source = ["src/line_provider", "src/bet_maker"]` from pyproject.toml is honored. `--cov=src/` would silently exclude one package.

## Verified

- `grep -c -- "--cov-fail-under=85" .github/workflows/ci.yml` → 1
- `grep -c -- "--cov-report=xml" .github/workflows/ci.yml` → 1
- `grep -c -- "--cov-report=term-missing" .github/workflows/ci.yml` → 1
- `grep -F -- "--cov=" .github/workflows/ci.yml` → 0 (no path arg; only --cov-report/--cov-fail-under)
- `git diff pyproject.toml` → empty (no edit)

## Decisions Honored

- D-15: `--cov --cov-fail-under=85` belt-and-braces alongside pyproject `fail_under=85`
- D-16: no codecov / coveralls integration (Shields.io static badge to follow in plan 07-10)
- D-17: 85% threshold (above ROADMAP minimum 80, matches pyproject)
- D-23: no scope creep — no new tests added in this plan even though coverage already passes

## Commits

- `cd62dae` ci(07-06): enforce coverage gate ≥85% in CI Pytest step (D-15)
