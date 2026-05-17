---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 03
subsystem: settings
tags: [pydantic-settings, config, env, retry, bet-maker]

requires:
  - phase: 01-skeleton-infrastructure
    provides: "BetMakerSettings(BaseAppSettings) with env_prefix=BET_MAKER_ (D-15)"
provides:
  - "Two new typed config fields on BetMakerSettings: line_provider_http_attempts (int, ge=1, le=10) and line_provider_http_backoff_max_s (float, gt=0)"
  - "tests/bet_maker/test_settings.py with TestBetMakerSettings (7 tests)"
affects: [04-04 retry factory, 04-07 lifespan wiring (HttpEventLookup construction)]

tech-stack:
  added: []
  patterns:
    - "pydantic-settings 2.x env-driven config with Field(ge=, le=) / Field(gt=) bounds"
    - "monkeypatch.setenv + monkeypatch.delenv pattern for env-bound settings tests"
    - "Fail-loud on bad config: out-of-range env values raise ValidationError at instantiation (Pitfall A2)"

key-files:
  created:
    - "tests/bet_maker/test_settings.py"
  modified:
    - "src/bet_maker/settings/config.py"

key-decisions:
  - "Field(ge=1, le=10) bound on attempts — tighter than int-only, prevents both 0 (no retry) and absurdly high values (DoS via retry-storm); T-04-03-Config mitigation"
  - "Field(gt=0) bound on backoff_max_s — rejects 0 and negative values"
  - "monkeypatch.delenv used on *_default tests to neutralise inherited env vars (defensive — CI baseline is clean but local invocations may inherit)"

patterns-established:
  - "D-21: BetMakerSettings extension pattern — append new BET_MAKER_LINE_PROVIDER_HTTP_* fields after line_provider_base_url, preserve env_prefix"
  - "Settings invariant test layout — TestBetMakerSettings class with default + from_env + rejects_* triad per bounded field"

requirements-completed: []
requirements-progressed: [BM-04]

duration: ~2min
completed: 2026-05-17
---

# Phase 04 / Plan 03: BetMakerSettings HTTP retry fields (D-21) — Summary

**Two new typed env-driven configuration fields added to `BetMakerSettings` so that Plan 04-04 (retry factory) and Plan 04-07 (lifespan) can construct a tenacity policy and `HttpEventLookup` from settings — preserving the project's "no os.getenv" invariant.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-17
- **Completed:** 2026-05-17
- **Tasks:** 2 (both TDD)
- **Files modified:** 2 (1 new test file, 1 production extension)

## Accomplishments

- `src/bet_maker/settings/config.py` extended with two new fields, inserted between `line_provider_base_url` and `reconciliation_interval_s`:
  - `line_provider_http_attempts: int = Field(default=3, ge=1, le=10)`
  - `line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)`
- `env_prefix="BET_MAKER_"` preserved (D-15 invariant) — env vars are `BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS` and `BET_MAKER_LINE_PROVIDER_HTTP_BACKOFF_MAX_S`.
- `tests/bet_maker/test_settings.py` created with `class TestBetMakerSettings` exercising 7 invariants: default, from-env, rejects-zero, rejects-above-max for attempts; default, from-env, rejects-zero for backoff_max_s.
- All bet_maker tests passing (110); `mypy --strict` clean (67 source files); `ruff check` clean.

## Task Commits

1. **Task 1: Extend BetMakerSettings with two new fields** — `eb0484f` (feat — D-21 schema extension)
2. **Task 2: Create tests/bet_maker/test_settings.py with TestBetMakerSettings** — `3a2230f` (test)

**Plan metadata:** _to be committed by this wrap-up_ (docs — STATE/ROADMAP/SUMMARY)

## Files Created/Modified

- `src/bet_maker/settings/config.py` — two new field declarations appended after `line_provider_base_url` (line 31) before `reconciliation_interval_s`. No other lines changed; `model_config` block preserved verbatim.
- `tests/bet_maker/test_settings.py` — new file (75 lines). Module docstring cites BM-04 / D-21 and the Pitfall A2 "fail loud on bad config" rationale. Single `TestBetMakerSettings` class with 7 tests using `pytest.MonkeyPatch` for env var control.

## Decisions Made

None new — plan dictated the verbatim spec for both the schema extension and tests (PROJECT-level decision D-21 is the source). Implementation followed the spec exactly.

## Deviations from Plan

- Plan's `test_*_default` tests originally took no `monkeypatch` parameter; added `monkeypatch.delenv("BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS", raising=False)` (and the matching backoff variant) to both default tests — defensive cleanup of inherited env. Plan note explicitly anticipated this: "If a parent fixture has already set ... add `monkeypatch.delenv(...)` to the default tests." No semantic change to test behaviour; CI baseline already clean.
- Pre-commit `ruff format` collapsed multi-line `def` signatures that fit within the 100-char limit. Auto-fix folded into Task 2 commit. No semantic change.

## Issues Encountered

None.

## Settings Diff (key bits)

```python
# src/bet_maker/settings/config.py — diff
    line_provider_base_url: HttpUrl = Field(
        default=HttpUrl("http://line-provider:8000"),
    )
+   line_provider_http_attempts: int = Field(default=3, ge=1, le=10)
+   line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)
    reconciliation_interval_s: float = Field(default=30.0, gt=0)
```

## Test Inventory

New tests added (7 total in `class TestBetMakerSettings`):

1. `test_line_provider_http_attempts_default` — env unset → attempts == 3.
2. `test_line_provider_http_attempts_from_env` — `BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS=5` → attempts == 5.
3. `test_line_provider_http_attempts_rejects_zero` — env=0 raises ValidationError (ge=1).
4. `test_line_provider_http_attempts_rejects_above_max` — env=11 raises ValidationError (le=10).
5. `test_line_provider_http_backoff_max_s_default` — env unset → backoff_max_s == 2.0.
6. `test_line_provider_http_backoff_max_s_from_env` — `BET_MAKER_LINE_PROVIDER_HTTP_BACKOFF_MAX_S=5.5` → backoff_max_s == 5.5.
7. `test_line_provider_http_backoff_max_s_rejects_zero` — env=0 raises ValidationError (gt=0).

## What Comes Next

- Plan 04-04 (Wave 3) — `make_retry_decorator` tenacity factory in `facades/line_provider_client.py` consumes both new settings fields.
- Plan 04-07 (Wave 5) — `entrypoints/lifespan.py` reads `settings.line_provider_http_attempts` and `settings.line_provider_http_backoff_max_s` when constructing the `HttpEventLookup` singleton.

## Acceptance Criteria — All Passed

- `grep -c "line_provider_http_attempts: int = Field(default=3, ge=1, le=10)" src/bet_maker/settings/config.py` → 1
- `grep -c "line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)" src/bet_maker/settings/config.py` → 1
- `grep -c 'env_prefix="BET_MAKER_"' src/bet_maker/settings/config.py` → 1 (preserved)
- `grep -c "reconciliation_interval_s: float = Field(default=30.0, gt=0)" src/bet_maker/settings/config.py` → 1 (preserved)
- `grep -c "^class TestBetMakerSettings:" tests/bet_maker/test_settings.py` → 1
- `grep -c "def test_" tests/bet_maker/test_settings.py` → 7
- `uv run pytest tests/bet_maker/test_settings.py -q -x` → 7 passed
- `uv run pytest tests/bet_maker -q -x` → 110 passed
- `uv run mypy src` → 67 source files clean
- `uv run ruff check` → clean

## Threat Model Closure

- **T-04-03-Config (Tampering on env attempts):** mitigated by `Field(ge=1, le=10)` — `test_line_provider_http_attempts_rejects_zero` + `test_line_provider_http_attempts_rejects_above_max` prove both bounds raise `ValidationError` at instantiation.
- **T-04-03-Config (Tampering on env backoff_max_s):** mitigated by `Field(gt=0)` — `test_line_provider_http_backoff_max_s_rejects_zero` proves the bound.
- **T-04-03-DoS-retry (retry-storm via large attempts):** indirect mitigation — the `le=10` bound caps the attempts that can reach tenacity's `stop_after_attempt` in Plan 04-04, preventing CONFIG-PATH amplification.
