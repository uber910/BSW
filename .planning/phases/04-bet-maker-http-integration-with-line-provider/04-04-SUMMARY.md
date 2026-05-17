---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 04
subsystem: facades
tags: [tenacity, httpx, retry, structlog, exception, factory, bet-maker]

requires:
  - phase: 01-skeleton-infrastructure
    provides: "tenacity 9.1.4 + structlog 25.5.0 + httpx 0.28.1 baseline deps"
  - phase: 04-bet-maker-http-integration-with-line-provider
    provides: "Plan 04-03 BetMakerSettings line_provider_http_attempts (ge=1, le=10) + line_provider_http_backoff_max_s (gt=0) — read at construction site in Plan 04-07 lifespan"
provides:
  - "src/bet_maker/facades/line_provider_client.py — single source of truth for retry policy + LineProviderUnavailable exception"
  - "LineProviderUnavailable(reason: str) public exception with .reason attribute (D-07)"
  - "_is_retryable(exc) predicate enforcing D-05 retry truth table (TransportError + 5xx -> True; 4xx + non-http -> False)"
  - "_log_before_sleep(retry_state) structlog warning emitter (D-06)"
  - "make_retry_decorator(attempts, max_backoff) tenacity factory returning Callable[[_F], _F]"
  - "tests/bet_maker/test_line_provider_client.py with 18 unit invariants across 3 classes"
affects:
  - "04-05 HttpEventLookup — imports LineProviderUnavailable + make_retry_decorator"
  - "04-06 list_active_events selector — imports same two names"
  - "04-08 events.py route — catches LineProviderUnavailable -> 503"
  - "04-09 bets.py route extension — catches LineProviderUnavailable -> 503"
  - "06 (P6) BM-12 reconciler — reuses make_retry_decorator with attempts=5, max_backoff=10.0 per D-04"

tech-stack:
  added: []
  patterns:
    - "Tenacity factory-of-decorator pattern — single call site returns reusable decorator parameterised by attempts + max_backoff (D-11 reuse across two facades + one P6 reconciler)"
    - "retry_if_exception(predicate) over retry_if_exception_type(...) — surgical truth-table predicate avoids accidental amplification on 4xx user errors (Pitfall 4 mitigation)"
    - "before_sleep hook reads retry_state.next_action.sleep + retry_state.outcome.exception() — no module-level contextvars (Pitfall A7 mitigation)"
    - "Module-level numeric constant _HTTP_5XX_FLOOR = 500 instead of inline magic number — ruff PLR2004 compliance"
    - "`# noqa: N818` on domain exception class names that are fixed by plan/decision (LineProviderUnavailable per D-07 is not renamable to LineProviderUnavailableError)"

key-files:
  created:
    - "src/bet_maker/facades/line_provider_client.py (96 lines — module + exception + predicate + log hook + factory)"
    - "tests/bet_maker/test_line_provider_client.py (131 lines — 18 tests across 3 classes)"
  modified: []

key-decisions:
  - "Predicate `_is_retryable` exported with leading underscore but unit-tested directly via bare import (matches helpers/money.quantize_amount style) — small pure helpers tested at their definition site, not exclusively through callers"
  - "`# type: ignore[return-value]` on tenacity `retry(...)` return removed — tenacity 9.1.4 type stubs return a compatible callable; mypy strict flags the ignore as [unused-ignore]"
  - "`LineProviderUnavailable` keeps its plan-mandated name (no `Error` suffix) — `# noqa: N818` is the correct escape valve, NOT renaming"
  - "Magic number 500 lifted to module-level `_HTTP_5XX_FLOOR` constant — clearer-than-inline + ruff PLR2004 clean"

patterns-established:
  - "Shared retry-factory module pattern: one factory + one exception in facades/line_provider_client.py; downstream callers (Plans 04-05 / 04-06 / P6 BM-12) parameterise via `make_retry_decorator(attempts, max_backoff)` — no second source of truth for retry policy"
  - "Retry truth table test pattern: parametrize on [500,502,503,504] for retryable 5xx and on [400,404,409,422] for non-retryable 4xx — directly proves Pitfall 4 mitigation (T-04-04-DoS-amplify-422)"
  - "Retry exhaustion test asserts call-count == attempts exactly — proves stop_after_attempt semantics and protects against silent off-by-one regressions (T-04-04-DoS-retry mitigation)"

requirements-completed: []
requirements-progressed: [BM-04]

duration: ~3min
completed: 2026-05-17
---

# Phase 04 / Plan 04: shared retry-factory + LineProviderUnavailable (D-03/D-05/D-06/D-07/D-11) — Summary

**Single module `facades/line_provider_client.py` becomes the only source of truth for line-provider HTTP retry policy and the unreachable-after-retry signal, ready to be imported verbatim by HttpEventLookup (04-05), list_active_events (04-06), and the P6 BM-12 reconciler.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-17
- **Completed:** 2026-05-17
- **Tasks:** 2 (both TDD-shaped, both autonomous)
- **Files modified:** 2 (both new)

## Accomplishments

- `src/bet_maker/facades/line_provider_client.py` created with five public-ish names:
  - `LineProviderUnavailable(reason: str)` — Exception subclass with public `.reason` attribute; `str(exc) == reason`. Route layer maps to HTTP 503 (D-08 POST /bet, D-10 GET /events); `place_bet` interactor MUST NOT catch (Pitfall 7).
  - `_is_retryable(exc)` — boolean predicate over `httpx.TransportError` (always True) and `httpx.HTTPStatusError` (True iff `status_code >= _HTTP_5XX_FLOOR`); everything else False.
  - `_log_before_sleep(retry_state)` — structlog `warning("line_provider.http.retry", ...)` with `attempt_number`, `sleep_s`, `exception_type`. No module-level contextvars (Pitfall A7).
  - `make_retry_decorator(attempts, max_backoff) -> Callable[[_F], _F]` — tenacity factory wired with `stop_after_attempt(attempts)`, `wait_exponential(multiplier=0.5, min=0.5, max=max_backoff)`, `retry_if_exception(_is_retryable)`, `before_sleep=_log_before_sleep`, `reraise=True`.
- Tenacity parameter values match D-03 (HTTP-routes default `attempts=3`, `max_backoff=2.0` — settings-driven via Plan 04-03) and are forward-compatible with D-04 (reconciler will pass `attempts=5`, `max_backoff=10.0`).
- `tests/bet_maker/test_line_provider_client.py` created with 18 invariants across 3 test classes (truth-table parametrize for both 5xx and 4xx, async retry-and-succeed + exhaustion-reraise + non-retryable-immediate cases).
- All bet_maker tests passing (128 total; +18 new); `mypy --strict` clean (68 source files); `ruff check` clean.

## Task Commits

1. **Task 1: Create src/bet_maker/facades/line_provider_client.py** — `2801b0a` (feat — module + exception + predicate + factory)
2. **Task 2: Create tests/bet_maker/test_line_provider_client.py** — `e2aba8b` (test — 18 invariants)

**Plan metadata:** _to be committed by this wrap-up_ (docs — STATE/ROADMAP/SUMMARY)

## Files Created/Modified

- `src/bet_maker/facades/line_provider_client.py` — new (96 lines). Module docstring cites D-07/D-03/D-11/D-05; per-symbol docstrings cite D-05/D-06/D-03/D-11 inline. Imports: `httpx`, `structlog`, `tenacity.{RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential}`, `collections.abc.{Awaitable, Callable}`, `typing.{Any, TypeVar}`.
- `tests/bet_maker/test_line_provider_client.py` — new (131 lines). Three classes: `TestLineProviderUnavailable` (3 tests), `TestIsRetryable` (3 standalone + 2 parametrize sets x 4 = 11 invariants total), `TestMakeRetryDecorator` (4 tests including 3 `@pytest.mark.asyncio` cases).

## Decisions Made

Plan dictated verbatim content; three small Rule 1 auto-fixes were needed during the lint/type pass and folded into the same commit:
- `# type: ignore[return-value]` on tenacity `retry(...)` was rejected by mypy strict as `[unused-ignore]` because tenacity 9.1.4 stubs already return a compatible callable type. Removed it. No semantic change.
- ruff `N818` flagged `LineProviderUnavailable` for missing `Error` suffix. The name is plan-mandated (D-07 contract for downstream imports in 04-05/04-06). Added `# noqa: N818` rather than rename.
- ruff `PLR2004` flagged the inline `500` literal. Lifted to module-level `_HTTP_5XX_FLOOR = 500`.

## Deviations from Plan

- `make_retry_decorator` signature collapsed by `ruff format` from the multi-line form in the plan to a single-line `def make_retry_decorator(attempts: int, max_backoff: float) -> Callable[[_F], _F]:` because it fits within the 100-char line limit. Auto-fix folded into Task 1 commit. No semantic change.
- `httpx.HTTPStatusError(...)` constructor calls in the test file were similarly collapsed by `ruff format` to single-line form. Auto-fix folded into Task 2 commit. No semantic change.

## Issues Encountered

None.

## Tenacity Parameter Values

Values used in `make_retry_decorator(attempts, max_backoff)`:

| Parameter | Value | Source |
|-----------|-------|--------|
| `stop` | `stop_after_attempt(attempts)` | D-03 (caller passes 3 for HTTP routes, D-04 passes 5 for reconciler) |
| `wait` | `wait_exponential(multiplier=0.5, min=0.5, max=max_backoff)` | D-03 (worst-case cumulative ~3s for attempts=3, max=2.0) |
| `retry` | `retry_if_exception(_is_retryable)` | D-05 (predicate-based, surgical) |
| `before_sleep` | `_log_before_sleep` | D-06 (structlog warning) |
| `reraise` | `True` | D-03 (original exc propagates — RetryError suppressed) |

## Retry Predicate Truth Table

| Exception | Status code | `_is_retryable` | Tested by |
|-----------|-------------|------------------|-----------|
| `httpx.ConnectError` (TransportError subclass) | — | True | `test_transport_error_is_retryable` |
| `httpx.ReadTimeout` (TransportError subclass) | — | True | `test_read_timeout_is_retryable` |
| `httpx.HTTPStatusError` | 500/502/503/504 | True | `test_5xx_http_status_error_is_retryable[500,502,503,504]` |
| `httpx.HTTPStatusError` | 400/404/409/422 | False | `test_4xx_http_status_error_is_not_retryable[400,404,409,422]` |
| `ValueError` (non-http) | — | False | `test_value_error_is_not_retryable` |

## Pitfall 4 Mitigation Trace

**Pitfall 4 (T-04-04-DoS-amplify-422):** blanket `retry_if_exception_type(httpx.HTTPStatusError)` would also retry user-side 422 responses (amount > 2dp), turning each user error into N upstream requests.

**Mitigation:** `_is_retryable` filters `HTTPStatusError` by `status_code >= _HTTP_5XX_FLOOR (500)` — 4xx never retries.

**Test evidence:**
- `test_4xx_http_status_error_is_not_retryable` parametrized on `[400, 404, 409, 422]` — directly asserts predicate returns False for the very status codes a faulty blanket policy would amplify.
- `test_non_retryable_propagates_immediately` wraps a function that raises HTTPStatusError(422) inside `make_retry_decorator(attempts=3, ...)`, asserts the exception propagates after exactly `1` call (no retry).

## STRIDE Threat Coverage (as of this plan)

- **T-04-04-DoS-retry (DoS — retry storm):** mitigated via `stop_after_attempt(attempts)` cap + `attempts` bounded by Settings (ge=1, le=10 per D-21, Plan 04-03). Verified by `test_exhaustion_reraises_original` (calls == attempts exactly).
- **T-04-04-DoS-amplify-422 (DoS — retry on user error):** mitigated via 5xx-only filter. Verified as above.
- **T-04-04-InputValidation (Tampering — retry args):** Settings is the input gate; factory does not re-validate (single-validation point per Plan 04-03 invariants).
- **T-04-04-Info-disclosure (Info disclosure via retry log):** accepted; before_sleep logs only `exception_type` (class name), `attempt_number`, `sleep_s` — no payload, no DSN.

## Tests

- 18 new unit tests in `tests/bet_maker/test_line_provider_client.py` — all pass.
- 128 bet_maker tests total (was 110 before plan 04-04).
- Coverage signal: full bet_maker suite green; production module covered by 18 direct invariants.

## Verification Commands Run

- `uv run pytest tests/bet_maker/test_line_provider_client.py -q -x` → 18 passed.
- `uv run pytest tests/bet_maker -q -x` → 128 passed.
- `uv run mypy src` → Success: no issues found in 68 source files.
- `uv run ruff check` → All checks passed.

## Downstream Readiness

Plans 04-05 (HttpEventLookup) and 04-06 (list_active_events) can now do `from bet_maker.facades.line_provider_client import LineProviderUnavailable, make_retry_decorator` and parameterise with `settings.line_provider_http_attempts` + `settings.line_provider_http_backoff_max_s` (already in `BetMakerSettings` via Plan 04-03). No further refactoring of this module is anticipated until P6 BM-12 reconciler imports it with different parameters per D-04.

## Requirements Progress

- **BM-04:** still Pending; closes in Plan 04-08 (GET /events route on bet-maker).
