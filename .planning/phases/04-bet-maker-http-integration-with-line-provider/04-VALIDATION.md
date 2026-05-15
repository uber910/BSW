---
phase: 4
slug: bet-maker-http-integration-with-line-provider
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-15
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `04-RESEARCH.md` section "Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x + pytest-asyncio 1.1.x + pytest-cov 7.1.x + respx 0.22.x (NEW) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` + `[tool.coverage.run]` (lines 75-97) |
| **Quick run command** | `uv run pytest tests/bet_maker -q -x` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~30s quick / ~60s full |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/bet_maker -q -x`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green AND `uv run pytest --cov=src/bet_maker --cov-fail-under=80` AND `uv run mypy src` AND `uv run ruff check` AND `uv run ruff format --check`
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-XX-XX | 04 | * | BM-04 / D-10 | T-04-DoS-timeout / T-04-DoS-retry | `GET /events` returns 200 + list of active events from LP | integration | `uv run pytest tests/bet_maker/test_events_routes.py::TestGetEvents::test_returns_active_events -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | BM-04 / D-10 | — | `GET /events` returns 200 + `[]` when LP has no active events | integration | `uv run pytest tests/bet_maker/test_events_routes.py::TestGetEvents::test_returns_empty_list -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | BM-04 / D-10 | T-04-Info-disclosure | `GET /events` returns 503 when LP unreachable (5xx exhausted) | unit (respx) | `uv run pytest tests/bet_maker/test_events_routes.py::TestGetEvents::test_503_on_line_provider_unavailable -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | BM-04 / D-05 | T-04-DoS-retry | `list_active_events` retries on TransportError; succeeds when LP recovers | unit (respx) | `uv run pytest tests/bet_maker/test_list_active_events.py::test_5xx_then_200_retry_succeeds -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | BM-04 / D-05 / D-07 | T-04-DoS-retry | `list_active_events` exhausts on persistent 5xx → LineProviderUnavailable | unit (respx) | `uv run pytest tests/bet_maker/test_list_active_events.py::test_5xx_exhausts_raises_unavailable -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | BM-04 / D-13 | T-04-InputValidation | `EventRead` parses LP `GET /events` payload (UUID, Decimal, datetime, state) | unit | `uv run pytest tests/bet_maker/test_schemas.py::TestEventRead -x` | ✅ (extend) | ⬜ pending |
| 04-XX-XX | 04 | * | D-09 | — | `HttpEventLookup.get_event` returns `EventSnapshot` on 200 | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_200_returns_snapshot -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | D-09 | — | `HttpEventLookup.get_event` returns None on 404 (no retry) | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_404_returns_none -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | D-05 | T-04-DoS-retry | `HttpEventLookup.get_event` propagates 422/400 from LP without retry | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_4xx_propagates_no_retry -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | D-07 | T-04-DoS-retry | `HttpEventLookup.get_event` raises LineProviderUnavailable after 5xx exhaustion | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_5xx_exhausts_raises -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | D-05 | — | `HttpEventLookup.get_event` retries 5xx → succeeds on 200 | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_5xx_then_200 -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | D-08 | T-04-Info-disclosure | `POST /bet` returns 503 on LineProviderUnavailable; no PG write | integration | `uv run pytest tests/bet_maker/test_bet_routes.py::TestPostBet503 -x` | ✅ (extend) | ⬜ pending |
| 04-XX-XX | 04 | * | D-09 | T-04-InputValidation | `POST /bet` returns 422 when LP returns 404 (event_id missing) | integration | `uv run pytest tests/bet_maker/test_events_routes.py::TestPostBetViaRealLp::test_404_maps_to_422 -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | D-12 / D-19 | — | `app.state.line_provider_http_client` is an httpx.AsyncClient after startup | unit | `uv run pytest tests/bet_maker/test_lifespan.py::TestLifespanStatePins::test_http_client_pinned_on_state -x` | ✅ (extend) | ⬜ pending |
| 04-XX-XX | 04 | * | D-14 / D-19 | — | `app.state.event_lookup` is `HttpEventLookup` (not Stub) in production lifespan | unit | `uv run pytest tests/bet_maker/test_lifespan.py::TestLifespanStatePins::test_event_lookup_is_http_in_production -x` | ✅ (extend) | ⬜ pending |
| 04-XX-XX | 04 | * | D-20 | — | `http_client.aclose()` called before `engine.dispose()` on shutdown | unit | `uv run pytest tests/bet_maker/test_lifespan.py::TestShutdownOrder::test_aclose_before_dispose -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | D-21 | T-04-Config | `BetMakerSettings.line_provider_http_attempts` reads `BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS` env | unit | `uv run pytest tests/bet_maker/test_settings.py::test_line_provider_http_attempts_default_and_env -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | * | D-21 | T-04-Config | `BetMakerSettings.line_provider_http_backoff_max_s` reads env | unit | `uv run pytest tests/bet_maker/test_settings.py::test_backoff_max_s_default_and_env -x` | ❌ W0 | ⬜ pending |
| 04-XX-XX | 04 | 1 | D-01 (sync) | — | `REQUIREMENTS.md` BM-04 + `ROADMAP.md` Phase 4 SC#1 no longer mention TTL cache | manual diff | `! grep -i "TTL cache" .planning/REQUIREMENTS.md .planning/ROADMAP.md` | manual / Plan 04-01 | ⬜ pending |
| 04-XX-XX | 04 | * | D-16 | — | Integration test exercises `POST /event(LP) → GET /events(BM)` round-trip in one event loop | integration | `uv run pytest tests/bet_maker/test_events_routes.py::TestIntegration -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: Task IDs are placeholder (`04-XX-XX`) — populated by the planner once PLAN.md files are committed.*

---

## Wave 0 Requirements

- [ ] `uv add --group dev "respx>=0.22,<0.23"` + `uv sync --frozen` — only new dev dependency
- [ ] `tests/bet_maker/test_http_event_lookup.py` — new file; covers BM-04, D-05, D-07, D-09 (HttpEventLookup unit tests via respx)
- [ ] `tests/bet_maker/test_list_active_events.py` — new file; covers BM-04, D-05, D-07, D-10 (selector unit tests via respx)
- [ ] `tests/bet_maker/test_events_routes.py` — new file; covers BM-04, D-10, D-16 (integration via ASGITransport + LifespanManager)
- [ ] `tests/bet_maker/test_bet_routes.py::TestPostBet503` — new class added to existing file; covers D-08, D-17
- [ ] `tests/bet_maker/test_settings.py` — settings tests for D-21 (new file or extend existing config-test file if one exists)
- [ ] `tests/bet_maker/conftest.py` — add session-scoped `line_provider_app` fixture (mirror of existing `app` fixture, wrapped in `LifespanManager`)
- [ ] Extension of `tests/bet_maker/test_lifespan.py` — update existing `test_event_lookup_pinned_on_state` (currently asserts StubEventLookup at line 36-38) to assert `HttpEventLookup`; add `test_http_client_pinned_on_state` + `TestShutdownOrder` class

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| TTL cache wording removed from REQUIREMENTS.md BM-04 and ROADMAP.md Phase 4 SC#1 | D-01 | Source-of-truth doc diff; no value in scripted assertion beyond grep | After Plan 04-01: `! grep -i "TTL cache" .planning/REQUIREMENTS.md .planning/ROADMAP.md` returns 0 matches |
| `docker compose up` from clean state still brings up both services healthy | INFR-01 (smoke) | Compose-level smoke; covered by P1 but P4 changes lifespan, so re-verify before phase exit | `docker compose down -v && docker compose up -d && sleep 30 && docker compose ps` shows both `(healthy)` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
