---
phase: 06-reconciliation-job
plan: 04
type: execute
wave: 1
depends_on: [01, 02]
files_modified:
  - src/bet_maker/settings/config.py
  - tests/bet_maker/config/test_settings_reconciler.py
autonomous: true
requirements: [BM-12]
tags: [settings, pydantic-settings, reconciler-retry]

must_haves:
  truths:
    - "BetMakerSettings exposes line_provider_reconciler_attempts: int (default 5, ge=1, le=10)"
    - "BetMakerSettings exposes line_provider_reconciler_backoff_max_s: float (default 10.0, gt=0)"
    - "Pre-existing reconciliation_interval_s is UNCHANGED (default 30.0, gt=0)"
    - "Env-var override via BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS works"
    - "Validation rejects attempts < 1, attempts > 10, and backoff_max_s <= 0"
  artifacts:
    - path: "src/bet_maker/settings/config.py"
      provides: "Two new typed fields on BetMakerSettings"
      contains: "line_provider_reconciler_attempts"
    - path: "tests/bet_maker/config/test_settings_reconciler.py"
      provides: "5 real assertions replacing the Wave-0 stub"
      contains: "BetMakerSettings"
  key_links:
    - from: "src/bet_maker/settings/config.py BetMakerSettings"
      to: "src/bet_maker/entrypoints/lifespan.py (will read these in Plan 06-08)"
      via: "lifespan instantiates HttpEventLookup(attempts=settings.line_provider_reconciler_attempts, max_backoff=settings.line_provider_reconciler_backoff_max_s)"
      pattern: "settings\\.line_provider_reconciler_(attempts|backoff_max_s)"
---

<objective>
Add two new typed configuration fields to `BetMakerSettings` so the reconciler can be tuned independently of the route-layer HTTP client (per CONTEXT.md D-07 and P4 D-04):

- `line_provider_reconciler_attempts: int = 5` — total tenacity attempts for reconciler HTTP calls. Higher than route default (3) because reconciler tolerates more latency.
- `line_provider_reconciler_backoff_max_s: float = 10.0` — upper bound on exponential backoff. Higher than route default (2.0) for the same reason.

Purpose: CONTEXT.md D-07 mandates the reconciler use its own retry profile distinct from the request-time profile. Without these settings, the reconciler would either reuse the route's 3-attempts/2-second profile (insufficient for a 30s tick) or hard-code values (not configurable). This plan creates the typed surface; Plan 06-08 consumes it in lifespan.

Output: Two new Field(...) declarations + 5 real test assertions replacing the Wave-0 stub.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@src/bet_maker/settings/config.py
@tests/bet_maker/test_settings.py
@tests/bet_maker/config/test_settings_reconciler.py
</context>

<interfaces>
Current state of `src/bet_maker/settings/config.py` (do NOT modify the other fields):
```python
class BetMakerSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BET_MAKER_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = Field(default="bet-maker")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001, ge=1, le=65535)

    postgres_dsn: PostgresDsn = Field(default=PostgresDsn("postgresql+asyncpg://bsw:bsw@postgres:5432/bsw"))
    rabbitmq_url: AmqpDsn = Field(default=AmqpDsn("amqp://guest:guest@rabbitmq:5672/"))
    line_provider_base_url: HttpUrl = Field(default=HttpUrl("http://line-provider:8000"))
    line_provider_http_attempts: int = Field(default=3, ge=1, le=10)
    line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)
    reconciliation_interval_s: float = Field(default=30.0, gt=0)
```

Note: `reconciliation_interval_s` (default 30.0) is already present from Phase 1 (Plan 01-04). We do NOT add it again — RESEARCH.md confirms this. Only the two NEW fields below are added.

Env-var pattern: pydantic-settings strips `env_prefix="BET_MAKER_"` then uppercases the field name. So `line_provider_reconciler_attempts` → env var `BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS`.
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add two reconciler-retry fields to BetMakerSettings + replace Wave-0 stub with real assertions</name>
  <files>src/bet_maker/settings/config.py, tests/bet_maker/config/test_settings_reconciler.py</files>
  <read_first>
    - src/bet_maker/settings/config.py (full file — to insert the new fields at the right point)
    - tests/bet_maker/test_settings.py (existing test patterns for env-override + validation)
    - tests/bet_maker/config/test_settings_reconciler.py (Wave-0 stub — class TestReconcilerSettings, 5 method names already locked)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-09 (default values, validation bounds)
  </read_first>
  <behavior>
    - `BetMakerSettings().line_provider_reconciler_attempts == 5`
    - `BetMakerSettings().line_provider_reconciler_backoff_max_s == 10.0`
    - `BetMakerSettings().reconciliation_interval_s == 30.0` (unchanged)
    - `BetMakerSettings(line_provider_reconciler_attempts=0)` raises ValidationError (ge=1)
    - `BetMakerSettings(line_provider_reconciler_attempts=11)` raises ValidationError (le=10)
    - `BetMakerSettings(line_provider_reconciler_backoff_max_s=0)` raises ValidationError (gt=0)
    - With `os.environ["BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS"]="7"`, `BetMakerSettings()` reflects 7.
  </behavior>
  <action>
    Step A — Edit `src/bet_maker/settings/config.py`. Add two new Field(...) lines IMMEDIATELY BEFORE the existing `reconciliation_interval_s` line (so reconciler-related fields cluster visually):

    ```python
    line_provider_reconciler_attempts: int = Field(default=5, ge=1, le=10)
    line_provider_reconciler_backoff_max_s: float = Field(default=10.0, gt=0)
    reconciliation_interval_s: float = Field(default=30.0, gt=0)
    ```

    No other lines change. Do NOT change `line_provider_http_attempts` or `line_provider_http_backoff_max_s` — they belong to the route-layer profile and are independent (P4 D-04 / CONTEXT.md D-07).

    Step B — Replace the Wave-0 stub `tests/bet_maker/config/test_settings_reconciler.py` with real assertions. Keep the locked class name (`TestReconcilerSettings`) and method names exactly (per Plan 06-02). Body:

    ```python
    """BetMakerSettings reconciler-field assertions (Plan 06-04 / BM-12 / D-09).

    Validates the two new fields (attempts + backoff_max_s) introduced for
    the reconciler HttpEventLookup profile. The third reconciler-related
    field (reconciliation_interval_s) was added in Phase 1 (Plan 01-04) and
    is exercised by existing tests/bet_maker/test_settings.py.
    """

    from __future__ import annotations

    import os

    import pytest
    from pydantic import ValidationError

    from bet_maker.settings.config import BetMakerSettings


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerSettings:
        async def test_default_line_provider_reconciler_attempts_is_5(self) -> None:
            assert BetMakerSettings().line_provider_reconciler_attempts == 5

        async def test_default_line_provider_reconciler_backoff_max_s_is_10(self) -> None:
            assert BetMakerSettings().line_provider_reconciler_backoff_max_s == 10.0

        async def test_attempts_validated_between_1_and_10(self) -> None:
            with pytest.raises(ValidationError):
                BetMakerSettings(line_provider_reconciler_attempts=0)
            with pytest.raises(ValidationError):
                BetMakerSettings(line_provider_reconciler_attempts=11)
            # boundaries are inclusive
            assert BetMakerSettings(line_provider_reconciler_attempts=1).line_provider_reconciler_attempts == 1
            assert BetMakerSettings(line_provider_reconciler_attempts=10).line_provider_reconciler_attempts == 10

        async def test_backoff_max_s_must_be_positive(self) -> None:
            with pytest.raises(ValidationError):
                BetMakerSettings(line_provider_reconciler_backoff_max_s=0)
            with pytest.raises(ValidationError):
                BetMakerSettings(line_provider_reconciler_backoff_max_s=-1.0)
            # any positive value accepted
            assert BetMakerSettings(line_provider_reconciler_backoff_max_s=0.1).line_provider_reconciler_backoff_max_s == 0.1

        async def test_env_var_override_via_BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS(self) -> None:
            os.environ["BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS"] = "7"
            try:
                assert BetMakerSettings().line_provider_reconciler_attempts == 7
            finally:
                os.environ.pop("BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS", None)
    ```

    Notes:
    - All five method names are locked by Plan 06-02 — DO NOT rename them.
    - Each test instantiates BetMakerSettings() locally (no fixture dependency).
    - Env override test cleans up via try/finally so it does not bleed into other tests in the session.
    - mypy strict: passing `int`/`float` to BetMakerSettings(...) via kwargs is type-checked.
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/config/test_settings_reconciler.py && uv run mypy src/bet_maker/settings/config.py tests/bet_maker/config/test_settings_reconciler.py && uv run ruff check src/bet_maker/settings/config.py tests/bet_maker/config/</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "line_provider_reconciler_attempts: int = Field(default=5, ge=1, le=10)" src/bet_maker/settings/config.py` == 1
    - `grep -c "line_provider_reconciler_backoff_max_s: float = Field(default=10.0, gt=0)" src/bet_maker/settings/config.py` == 1
    - `grep -c "reconciliation_interval_s: float = Field(default=30.0, gt=0)" src/bet_maker/settings/config.py` == 1 (unchanged)
    - `grep -c "line_provider_http_attempts: int = Field(default=3, ge=1, le=10)" src/bet_maker/settings/config.py` == 1 (P4 unchanged)
    - `uv run python -c "from bet_maker.settings.config import BetMakerSettings; s = BetMakerSettings(); assert s.line_provider_reconciler_attempts == 5 and s.line_provider_reconciler_backoff_max_s == 10.0"` exits 0
    - `uv run pytest -x -q tests/bet_maker/config/test_settings_reconciler.py` reports 5 passed
    - `uv run pytest -x -q tests/bet_maker/test_settings.py` reports zero regressions (existing P1-P4 settings tests untouched)
    - `uv run mypy src/bet_maker/` exits 0
    - `uv run ruff check src/bet_maker/` exits 0
    - The stub is fully replaced: `grep -c "Wave-0 stub" tests/bet_maker/config/test_settings_reconciler.py` == 0
  </acceptance_criteria>
  <done>Two new typed Field(...) declarations added; 5 settings tests green; route-layer P4 fields and reconciliation_interval_s untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| env-vars → BetMakerSettings | Untyped env strings parsed into typed values; pydantic-settings is the validation layer |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-04-01 | Tampering (config injection) | env-var parsing | mitigate | Field(ge=1, le=10) and Field(gt=0) bound the surface; ValidationError raised on out-of-range values — verified by tests |
| T-06-04-02 | Information Disclosure | settings repr | accept | Values are tunables, not secrets; default repr is acceptable for logging |
</threat_model>

<verification>
- `uv run pytest -x -q tests/bet_maker/config/ tests/bet_maker/test_settings.py` returns all green.
- `uv run mypy src/bet_maker/` exits 0.
</verification>

<success_criteria>
- Two new typed fields added with correct bounds.
- 5 settings tests pass; existing test_settings.py regression-free.
- mypy + ruff clean.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-04-SUMMARY.md` with the two-line config.py diff and the pytest summary output.
</output>

## Decision Coverage

- D-09: Two new `BetMakerSettings` fields (`line_provider_reconciler_attempts`, `line_provider_reconciler_backoff_max_s`); `reconciliation_interval_s` already present from P1 Plan 01-04.
