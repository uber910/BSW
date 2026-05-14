---
phase: 01-skeleton-infrastructure
plan: 02
subsystem: shared-config
tags: [config, structlog, pydantic-settings, shared, internal]

requires:
  - "Plan 01-01 (root pyproject.toml with structlog>=25.5, pydantic>=2.13, pydantic-settings>=2.14 pinned; src/config/__init__.py stub from Wave 1)"
provides:
  - "src/config/logging.py — configure_structlog(level) with processors [merge_contextvars, add_log_level, TimeStamper(iso,utc), dict_tracebacks, JSONRenderer] (D-17)"
  - "src/config/settings_base.py — BaseAppSettings(BaseSettings) parent with service_name (required), log_level (default INFO), env_file=.env, case_sensitive=False, extra=ignore"
  - "src/config/time.py — utc_now() returns timezone-aware UTC datetime (D-02 single patching point for freeze_time)"
  - "src/config/py.typed — PEP 561 marker so downstream packages see config/ as typed under mypy --strict"
  - "src/config/__init__.py — re-exports BaseAppSettings, configure_structlog, utc_now"
affects: [phase-01-line_provider-bet_maker-skeletons, phase-02, phase-03, phase-05, phase-06]

tech-stack:
  added: []
  patterns:
    - "Shared internal-only package src/config/ (D-02) — both services import from it, no public distribution"
    - "structlog processors chain locked: merge_contextvars first (enables bind/clear pattern A7), JSONRenderer last"
    - "pydantic-settings v2 SettingsConfigDict — subclasses (LineProviderSettings/BetMakerSettings in plans 03/04) override model_config to add env_prefix"
    - "Centralised utc_now() — every domain timestamp goes through one function for deterministic freeze_time in tests"

key-files:
  created:
    - "src/config/logging.py"
    - "src/config/settings_base.py"
    - "src/config/time.py"
    - "src/config/py.typed"
  modified:
    - "src/config/__init__.py — re-exports BaseAppSettings, configure_structlog, utc_now"

key-decisions:
  - "structlog wrapper_class = make_filtering_bound_logger(log_level) — drops sub-level events without running the processor chain, cheap idle-log path"
  - "logger_factory = PrintLoggerFactory(file=sys.stdout) instead of stdlib LoggerFactory — single sink, no logging-module config drift; logging.basicConfig still set so third-party libs (uvicorn, sqlalchemy, aio-pika via FastStream) emit through stdlib root logger which structlog formatters do not handle (those libs log their own non-JSON lines — acceptable for skeleton; full unified routing deferred to plan 01-07 / phase 7)"
  - "BaseAppSettings.service_name is required (no default) per threat T-02-04 — subclasses must set it via env or class default to avoid cross-service log misattribution"
  - "Field descriptions are wrapped to multi-line Field(...) form to satisfy line-length=100 (ruff E501); semantics unchanged"

requirements-completed: [INFR-07, INFR-08]

duration: 4min
completed: 2026-05-14
---

# Phase 1 Plan 2: src/config/ shared internal package Summary

**Shared internal package src/config/ provides configure_structlog (D-17 processors chain), BaseAppSettings (pydantic-settings v2 parent), utc_now (D-02 timezone-aware UTC), and PEP 561 marker — single point of import for both line-provider and bet-maker, single patching point for tests.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-14T09:31:55Z
- **Completed:** 2026-05-14T09:33:02Z
- **Tasks:** 2 (both atomic-committed)
- **Files created:** 4 (logging.py, settings_base.py, time.py, py.typed)
- **Files modified:** 1 (__init__.py — re-exports)

## Accomplishments

- `configure_structlog(level: str = "INFO")` configures structlog 25.5.0 with the exact D-17 processors chain:
  `[contextvars.merge_contextvars, add_log_level, TimeStamper(fmt="iso", utc=True), dict_tracebacks, JSONRenderer()]`
- `wrapper_class=make_filtering_bound_logger(log_level)` — cheap idle path for sub-level events
- `logger_factory=PrintLoggerFactory(file=sys.stdout)` — direct stdout JSON, no double-buffering through stdlib logging
- `logging.basicConfig(...)` mirrors level + stream so third-party libs (uvicorn, sqlalchemy, aio-pika) inherit the same root level
- `BaseAppSettings` reads .env (utf-8), case-insensitive, extra="ignore"; service_name required, log_level default "INFO"
- `utc_now()` — single function returning `datetime.now(timezone.utc)`; downstream tests will patch this one symbol
- `py.typed` empty file present — mypy strict treats `config.*` as typed package, no implicit-any leakage
- All four files pass `uv run mypy --strict src/config/` (4 source files, no issues)
- `uv run ruff check src/config/` and `uv run ruff format --check src/config/` both green
- `uv run python -c "from config import BaseAppSettings, configure_structlog, utc_now; print('imports ok')"` succeeds — package surface is wired

## Task Commits

1. **Task 1: Create src/config/ package with logging.py, time.py, py.typed (+ partial __init__)** — `6766075` (feat)
2. **Task 2: Create src/config/settings_base.py with BaseAppSettings parent** — `58f4a81` (feat)

## Files Created/Modified

- `src/config/logging.py` — `configure_structlog(level)` with D-17 processors chain
- `src/config/settings_base.py` — `BaseAppSettings(BaseSettings)` parent class with SettingsConfigDict
- `src/config/time.py` — `utc_now()` returning timezone-aware UTC datetime
- `src/config/py.typed` — PEP 561 typed-package marker (empty)
- `src/config/__init__.py` — re-exports `BaseAppSettings`, `configure_structlog`, `utc_now`

## Decisions Made

- **structlog wrapper_class = make_filtering_bound_logger(log_level)** — filters at the `bound_logger` boundary, no processor invocation for filtered events; matches structlog 25.x recommended pattern for production performance
- **logger_factory = PrintLoggerFactory(file=sys.stdout)** — direct print of the JSON-rendered string to stdout; avoids stdlib `logging` formatter interference. Uvicorn / SQLAlchemy / aio-pika still log via stdlib (acceptable for skeleton — non-JSON service lines are clearly distinguishable from app lines; full unified routing through `LoggerFactory()` + stdlib `ProcessorFormatter` is a polish-phase concern)
- **service_name is required (no default)** — threat T-02-04 (Spoofing: cross-service log misattribution) is mitigated structurally: subclasses must override or supply via env, so a misconfigured deployment fails fast at Settings instantiation rather than silently emitting unattributed logs
- **Field(...) wrapped to multi-line** — pyproject ruff line-length=100; the single-line form (104 chars) would have tripped E501. Auto-fixed during Task 2 verification (Rule 1 — lint error)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Split __init__.py BaseAppSettings re-export across Task 1 and Task 2**
- **Found during:** Task 1 (running `uv run python -c "from config.logging import configure_structlog; ..."`)
- **Issue:** Plan Task 1's `<action>` writes the full `src/config/__init__.py` re-exporting `configure_structlog`, `BaseAppSettings`, and `utc_now`. But `settings_base.py` is not created until Task 2. Importing anything from the `config` package (including the verify command, since Python evaluates the package `__init__.py` on submodule import) immediately raises `ModuleNotFoundError: No module named 'config.settings_base'`. Task 1 would therefore commit a broken package.
- **Fix:** In Task 1, wrote a minimal `__init__.py` re-exporting only `configure_structlog` and `utc_now`. In Task 2, updated `__init__.py` to add `BaseAppSettings` and the matching `__all__` entry — restoring the plan's intended final shape. End state of `__init__.py` matches the plan exactly.
- **Files modified:** `src/config/__init__.py` (Task 1 + Task 2)
- **Commits:** `6766075` (Task 1 partial), `58f4a81` (Task 2 complete)

**2. [Rule 1 — Lint Error] Wrapped Field(...) calls in settings_base.py to multi-line**
- **Found during:** Task 2 verification (`uv run ruff check src/config/`)
- **Issue:** The plan's sample code has `service_name: str = Field(..., description="Logical service name for logs and OpenAPI title")` (101 chars) and `log_level: str = Field(default="INFO", description="Root log level: DEBUG / INFO / WARNING / ERROR")` (104 chars). Both exceed `[tool.ruff] line-length = 100` set in plan 01-01.
- **Fix:** Reformatted each `Field(...)` call to a multi-line form. Field types, default values, descriptions, and required/optional status are unchanged.
- **Files modified:** `src/config/settings_base.py`
- **Verification:** `uv run ruff check src/config/` returns "All checks passed!"; `uv run mypy --strict src/config/` succeeds; runtime instantiation `BaseAppSettings(service_name="test")` still produces `service_name="test"` and `log_level="INFO"`.
- **Committed in:** `58f4a81` (Task 2)

---

**Total deviations:** 2 auto-fixed (Rule 3 — blocking; Rule 1 — lint).
**Impact on plan:** Zero scope creep. End state of all files matches plan acceptance criteria. The Rule 3 split was necessary so each task could be committed atomically with a working `uv run python -c "from config..."` verify command.

## Issues Encountered

None.

## User Setup Required

None — purely shared-config plumbing. No external services, no secrets, no UI verification.

## Next Phase Readiness

- **Ready for plan 01-03 (line-provider FastAPI skeleton):** can import `from config import BaseAppSettings, configure_structlog, utc_now`; subclass `BaseAppSettings` with `model_config = SettingsConfigDict(env_prefix="LINE_PROVIDER_", ...)` and add domain fields
- **Ready for plan 01-04 (bet-maker FastAPI + Alembic skeleton):** same import surface; subclass with `env_prefix="BET_MAKER_"` and add PG DSN + RabbitMQ URL
- **Ready for plan 01-05 (Dockerfile + docker-compose + .env.example):** `.env.example` will list both prefixes; pydantic-settings reads them transparently at process start
- **No blockers identified.**

## TDD Gate Compliance

Not a TDD plan (frontmatter `type: execute`, both tasks `tdd="false"`). RED/GREEN/REFACTOR gate sequence not applicable.

## Known Stubs

None — every file is functional (no placeholder values flowing to UI, no TODO/FIXME markers, no empty function bodies). `py.typed` is intentionally empty per PEP 561 spec.

## Threat Flags

None — no new network surface, no auth paths, no schema changes at trust boundaries. The package is internal-only (D-02). Threats T-02-01 through T-02-04 from the plan's threat model are mitigated structurally:

- **T-02-01 / T-02-02** (log injection / sensitive data leak): JSONRenderer escapes structured fields; `dict_tracebacks` is structured output, not raw `repr()`. Downstream phases must follow the "request_id only, never request body" discipline (D-18).
- **T-02-03** (.env secret exposure): `BaseAppSettings` reads `.env` but the file itself is gitignored (`.gitignore` from plan 01-01); `.env.example` (plan 01-05) will use placeholders.
- **T-02-04** (service_name misattribution): `service_name` field is required (no default), so misconfiguration fails fast at Settings instantiation.

## Self-Check: PASSED

- `src/config/logging.py` — FOUND (commit `6766075`)
- `src/config/time.py` — FOUND (commit `6766075`)
- `src/config/py.typed` — FOUND (commit `6766075`)
- `src/config/__init__.py` — FOUND and modified twice (commits `6766075`, `58f4a81`)
- `src/config/settings_base.py` — FOUND (commit `58f4a81`)
- Commit `6766075` — FOUND in `git log`
- Commit `58f4a81` — FOUND in `git log`
- `uv run mypy --strict src/config/` — exit 0 (4 source files, no issues) — VERIFIED
- `uv run ruff check src/config/` — "All checks passed!" — VERIFIED
- `uv run ruff format --check src/config/` — "4 files already formatted" — VERIFIED
- `uv run python -c "from config import BaseAppSettings, configure_structlog, utc_now"` — exit 0 — VERIFIED
- JSON log emission test produced `{"event": "boot.ok", "level": "info", "timestamp": "..."}` — VERIFIED
- `utc_now().tzinfo == timezone.utc` — VERIFIED
- No emojis in any created file — VERIFIED
- No code comments added — VERIFIED

---
*Phase: 01-skeleton-infrastructure*
*Completed: 2026-05-14*
