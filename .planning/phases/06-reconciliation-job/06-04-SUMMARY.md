---
phase: 06-reconciliation-job
plan: "04"
subsystem: bet-maker/settings
tags: [settings, pydantic-settings, reconciler-retry, BM-12]
dependency_graph:
  requires: ["06-01", "06-02"]
  provides: ["BetMakerSettings.line_provider_reconciler_attempts", "BetMakerSettings.line_provider_reconciler_backoff_max_s"]
  affects: ["06-08 (lifespan wires these fields into HttpEventLookup)"]
tech_stack:
  added: []
  patterns: ["pydantic-settings Field with ge/le/gt validators", "env_prefix BET_MAKER_ override pattern"]
key_files:
  created: []
  modified:
    - src/bet_maker/settings/config.py
    - tests/bet_maker/config/test_settings_reconciler.py
decisions:
  - "D-09: reconciler retry profile is separate from route-layer profile (attempts=5 vs 3, backoff=10s vs 2s)"
  - "le=10 upper bound kept identical to route-layer field for symmetric validation surface"
  - "Wave-0 stub lines replaced; method names preserved per Plan 06-02 lock"
metrics:
  duration: "~3 min"
  completed: "2026-05-18"
---

# Phase 06 Plan 04: Reconciler Settings Summary

Two new typed `BetMakerSettings` fields that give the reconciler its own HTTP retry profile, independent of the request-time route profile (P4 D-04 / CONTEXT.md D-07).

## What Was Built

Added to `src/bet_maker/settings/config.py` immediately before `reconciliation_interval_s`:

```python
line_provider_reconciler_attempts: int = Field(default=5, ge=1, le=10)
line_provider_reconciler_backoff_max_s: float = Field(default=10.0, gt=0)
```

Replaced Wave-0 stub `tests/bet_maker/config/test_settings_reconciler.py` with 5 real assertions covering defaults, validation bounds, and env-var override.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add reconciler-retry fields + replace Wave-0 stub | 02a4f9b | src/bet_maker/settings/config.py, tests/bet_maker/config/test_settings_reconciler.py |

## Verification Results

- `pytest tests/bet_maker/config/test_settings_reconciler.py`: 5 passed
- `pytest tests/bet_maker/test_settings.py`: 7 passed (no regressions)
- `mypy src/bet_maker/settings/config.py tests/bet_maker/config/test_settings_reconciler.py`: Success
- `ruff check src/bet_maker/settings/config.py tests/bet_maker/config/`: All checks passed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff E501 line-too-long violations in test file**
- **Found during:** Task 1 verification
- **Issue:** Plan's code template had 3 assert lines exceeding 100-char limit (107, 109, 121 chars)
- **Fix:** Extracted intermediate variables (`s1`, `s10`, `s`) before assertions
- **Files modified:** tests/bet_maker/config/test_settings_reconciler.py
- **Commit:** 02a4f9b (same commit — fix applied before commit)

## Known Stubs

None. Wave-0 stub fully replaced. All 5 test methods have real assertions.

## Threat Surface Scan

No new network endpoints or auth paths introduced. Config validation bounds (ge=1, le=10, gt=0) enforce T-06-04-01 (Tampering via config injection) as planned.

## Self-Check: PASSED

- `src/bet_maker/settings/config.py` — exists, contains both new fields
- `tests/bet_maker/config/test_settings_reconciler.py` — exists, 5 real tests, no stub text
- commit `02a4f9b` — verified via `git rev-parse --short HEAD`
