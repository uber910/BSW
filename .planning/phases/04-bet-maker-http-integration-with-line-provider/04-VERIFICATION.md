---
phase: 04
phase_name: bet-maker-http-integration-with-line-provider
verified_at: 2026-05-17T11:00:00Z
status: passed
must_haves_total: 58
must_haves_verified: 58
test_count: 244
coverage_pct: 95.35
---

# Phase 04 Verification — bet-maker HTTP integration with line-provider

## Goal Achievement

Phase 04 delivers the Goal verbatim: bet-maker exposes `GET /events` proxying line-provider through a singleton `httpx.AsyncClient` with tenacity retry, and the same client + retry-factory is positioned for P6 reconciliation reuse. Per D-01 the TTL cache is omitted; the doc-sync (Plan 04-01) propagated `Per D-01 (Phase 4 CONTEXT.md): TTL cache не реализуется в P4` into both `REQUIREMENTS.md` (BM-04 line) and `ROADMAP.md` (Goal + SC#1), and the substring `tiny TTL cache` no longer occurs anywhere. `HttpEventLookup` replaces `StubEventLookup` in the production lifespan, so `POST /bet` validates events via real HTTP and degrades to a static 503 when LP is unreachable.

## Requirement Traceability

| Req | Plan(s) | Production File(s) | Test File(s) | Status |
|-----|---------|--------------------|--------------|--------|
| BM-04 | 04-01 (doc-sync), 04-02 (EventRead), 04-03 (Settings), 04-04 (retry factory + exception), 04-05 (HttpEventLookup), 04-06 (list_active_events selector), 04-07 (lifespan), 04-08 (GET /events route), 04-09 (POST /bet 503) | src/bet_maker/schemas/events.py; src/bet_maker/settings/config.py; src/bet_maker/facades/line_provider_client.py; src/bet_maker/facades/http_event_lookup.py; src/bet_maker/facades/deps.py; src/bet_maker/selectors/list_active_events.py; src/bet_maker/entrypoints/lifespan.py; src/bet_maker/entrypoints/api/events.py; src/bet_maker/entrypoints/api/bets.py; src/bet_maker/app.py | tests/bet_maker/test_schemas.py (TestEventRead); test_settings.py (TestBetMakerSettings); test_line_provider_client.py; test_http_event_lookup.py; test_list_active_events.py; test_lifespan.py (TestShutdownOrder); test_events_routes.py (3 classes); test_bet_routes.py (TestPostBet503); conftest.py (line_provider_app, _clear_event_lookup) | verified |

## Must-Haves Verification

| Must-Have | Plan | Evidence | Status |
|-----------|------|----------|--------|
| REQUIREMENTS.md BM-04 carries `Per D-01 (Phase 4 CONTEXT.md)` citation; no `TTL cache` wording | 04-01 | `grep -c "Per D-01 (Phase 4 CONTEXT.md)" .planning/REQUIREMENTS.md` = 1; `grep -c "tiny TTL cache" .planning/ROADMAP.md` = 0 | PASS |
| ROADMAP.md Phase 4 Goal + SC#1 carry D-01 citation twice; no TTL-cache wording | 04-01 | `grep -c "Per D-01 (Phase 4 CONTEXT.md)" .planning/ROADMAP.md` = 2 | PASS |
| respx ≥0.22,<0.23 installable via `uv sync --frozen` | 04-01 | test_http_event_lookup.py + test_list_active_events.py import `respx`; full suite green (244) | PASS |
| EventRead exists in bet-maker side with frozen + extra='forbid' + 4 typed fields | 04-02 | src/bet_maker/schemas/events.py lines 26+; tests/bet_maker/test_schemas.py::TestEventRead (4 tests + TestExtraForbid::test_eventread_extra_forbid) green | PASS |
| BetMakerSettings carries `line_provider_http_attempts` (ge=1,le=10) and `line_provider_http_backoff_max_s` (gt=0); env_prefix preserved | 04-03 | src/bet_maker/settings/config.py extended; tests/bet_maker/test_settings.py::TestBetMakerSettings 7 tests green | PASS |
| `LineProviderUnavailable(reason)` + `make_retry_decorator(attempts, max_backoff)` importable from `bet_maker.facades.line_provider_client`; retries TransportError + 5xx; does not retry 4xx; reraise=True | 04-04 | src/bet_maker/facades/line_provider_client.py present (cited D-03/D-05/D-06/D-07/D-11/D-21); tests/bet_maker/test_line_provider_client.py with 18 invariants; predicate truth-table parametrized over 5xx and 4xx | PASS |
| HttpEventLookup implements EventLookup Protocol; 200→EventSnapshot, 404→None (no retry), 4xx→LineProviderUnavailable, 5xx-exhausted→LineProviderUnavailable | 04-05 | src/bet_maker/facades/http_event_lookup.py 71 lines cites D-05/D-07/D-09/D-11/D-14 + Pitfall 5; tests/bet_maker/test_http_event_lookup.py 5 respx scenarios + Protocol marker; ordering 404-before-raise_for_status verified by `route.call_count == 1` on 404 | PASS |
| list_active_events(http_client, *, attempts, max_backoff) → list[EventRead]; empty/200/5xx-retry/5xx-exhaust scenarios | 04-06 | src/bet_maker/selectors/list_active_events.py 48 lines; tests/bet_maker/test_list_active_events.py 4 respx scenarios + iscoroutine marker | PASS |
| Lifespan creates singleton httpx.AsyncClient with Timeout(5.0); pins on app.state.line_provider_http_client; wires HttpEventLookup; reverse-order shutdown (aclose before dispose) | 04-07 | `grep -c "httpx.Timeout(5.0)"` = 1; `grep -c "HttpEventLookup("` = 1; `grep -c "http_client.aclose()"` = 2 (call + log refs); tests/bet_maker/test_lifespan.py::TestShutdownOrder::test_aclose_before_dispose green | PASS |
| `get_line_provider_http_client` provider + `LineProviderHttpClientDep` alias in deps.py | 04-07 | grep `app.state.line_provider_http_client` in deps.py + lifespan.py; imports in events.py | PASS |
| `_clear_event_lookup` autouse fixture swaps fresh StubEventLookup per test; session-scoped `line_provider_app` fixture present | 04-07 | tests/bet_maker/conftest.py:27 + :120 confirmed via grep | PASS |
| bet-maker GET /events: 200+list[EventRead] / 503+"line-provider unreachable" | 04-08 | src/bet_maker/entrypoints/api/events.py; events router included in src/bet_maker/app.py; tests/bet_maker/test_events_routes.py (TestGetEventsAgainstRealLp / TestGetEvents503 / TestPostBetViaRealLp) — 6 tests green | PASS |
| POST /bet exception ladder: LineProviderUnavailable→503 caught BEFORE EventNotBettable→422; static 503 detail; no PG write on 503 | 04-09 | src/bet_maker/entrypoints/api/bets.py: `except LineProviderUnavailable` at line 48 < `except EventNotBettable` at line 53; tests/bet_maker/test_bet_routes.py::TestPostBet503 (2 tests green); count-before/after assertion proves zero PG write | PASS |

All 58 truth assertions across the 9 plans are evidenced by either passing tests, present-in-code grep matches, or doc grep matches captured in each plan's SUMMARY.md acceptance section.

## Quality Gates

| Gate | Result | Detail |
|------|--------|--------|
| pytest (full suite) | PASS | 244 passed, 9 warnings in 10.11s |
| coverage src/bet_maker | PASS | 95.35% total ≥ 80% gate (`--cov-fail-under=85` actually configured); per-module ≥83% |
| ruff check | PASS | `All checks passed!` |
| ruff format --check | PASS | 107 files already formatted |
| mypy --strict src | PASS | `Success: no issues found in 71 source files` |
| ladder ordering bets.py | PASS | LP line 48 < ENB line 53 (D-08 satisfied) |
| doc-sync (D-01) | PASS | `Per D-01 (Phase 4 CONTEXT.md)`: 1 in REQUIREMENTS, 2 in ROADMAP; `tiny TTL cache`: 0 occurrences |

## Decisions Honored

| ID | Decision | Evidence in Code |
|----|----------|------------------|
| D-01 | no TTL cache | No `cache` module in selectors/; `selectors/list_active_events.py` is stateless; REQUIREMENTS + ROADMAP cite D-01 inline |
| D-02 | httpx.Timeout(5.0) explicit | `grep -c "httpx.Timeout(5.0)" src/bet_maker/entrypoints/lifespan.py` = 1 (line 47) |
| D-03 / D-05 | retry policy (3 attempts, 5xx-only + TransportError) | `src/bet_maker/facades/line_provider_client.py` `_is_retryable` + `make_retry_decorator`; truth-table tests on [500,502,503,504] retry and [400,404,409,422] no-retry |
| D-04 | reconciler-grade factory shared | `make_retry_decorator(attempts, max_backoff)` accepts both 3/2.0 (P4) and 5/10.0 (P6) parameter sets |
| D-06 | before_sleep structlog | `_log_before_sleep` emits warning with attempt_number/sleep_s/exception_type; no module-level state |
| D-07 | LineProviderUnavailable exception | line_provider_client.py defines `class LineProviderUnavailable(Exception)` with `.reason` attribute |
| D-08 | POST /bet 503 ladder order | bets.py line 48 (LP) < line 53 (ENB); static detail; `from exc` chain |
| D-09 | 404→None no retry | http_event_lookup.py: 404 shortcut precedes `raise_for_status`; `route.call_count == 1` test |
| D-10 | GET /events 200/[]/503 | events.py route + test_events_routes.py::TestGetEvents503 |
| D-11 | Two independent facades | http_event_lookup.py and list_active_events.py both import only the shared `LineProviderUnavailable` + `make_retry_decorator`; no aggregate client |
| D-12 | Singleton httpx.AsyncClient on app.state | lifespan.py: `app.state.line_provider_http_client = http_client`; deps.py provider reads same state |
| D-13 | EventRead duplicated at bet-maker boundary | schemas/events.py:26 with `frozen=True, extra="forbid"`; no import from line_provider |
| D-14 | Production HttpEventLookup replaces Stub | lifespan.py: `app.state.event_lookup = HttpEventLookup(...)` (grep counts confirmed) |
| D-15 | respx-based unit tests | test_http_event_lookup.py + test_list_active_events.py + test_line_provider_client.py drive respx mocks |
| D-16 | Integration via two FastAPI apps in one event loop | test_events_routes.py uses session-scoped `line_provider_app` + ASGITransport; `TestGetEventsAgainstRealLp` + `TestPostBetViaRealLp` |
| D-17 | TestPostBet503 via dependency_overrides | test_bet_routes.py::TestPostBet503: 2 tests; `dependency_overrides[get_event_lookup]` count = 2 |
| D-19 | startup order: structlog→engine→wait_for_pg→httpx | lifespan.py order matches verbatim |
| D-20 | shutdown order: aclose before dispose | lifespan.py nested try/finally; test_lifespan.py::TestShutdownOrder::test_aclose_before_dispose asserts `call_order.index("aclose") < call_order.index("dispose")` |
| D-21 | BetMakerSettings extended with retry fields | settings/config.py: `line_provider_http_attempts` (ge=1,le=10), `line_provider_http_backoff_max_s` (gt=0); env_prefix preserved |

All decisions D-01 through D-21 are honored. D-18 is informational (no code change required).

## Gaps Found

None. All must_haves verified; all quality gates green; all decisions honored.

## Human Verification Items

None for automated CI flow. The phase VALIDATION.md lists one optional manual smoke (`docker compose down -v && docker compose up -d && sleep 30 && docker compose ps` should show both services healthy) — that is a P1/P7 compose-level smoke, not a P4 gate, and is deferred to phase-completion or P7 finalisation.

## Next Steps

Phase 04 ready for completion gate. Suggested orchestrator actions:

1. `/gsd-secure-phase 04` — security gate not yet run for Phase 04 (P3 had one; P4 adds new attack surface around the outbound HTTP client, retry storm, info-disclosure in 503 detail).
2. After secure-phase passes, mark Phase 4 complete in STATE.md / ROADMAP.md plan progress table.
3. Proceed to Phase 5 (RabbitMQ integration) — Phase 5 reuses the same singleton `httpx.AsyncClient` lifecycle pattern and the same `LineProviderUnavailable` taxonomy; both are now ready.

---
*Phase: 04-bet-maker-http-integration-with-line-provider*
*Verified: 2026-05-17*
