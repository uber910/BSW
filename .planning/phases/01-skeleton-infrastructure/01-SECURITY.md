---
phase: 01
slug: skeleton-infrastructure
status: verified
threats_open: 0
threats_total: 39
threats_closed: 39
asvs_level: 1
created: 2026-05-14
verified: 2026-05-14
---

# Phase 01 — Security

Per-phase security contract: трэт-регистр консолидирован из `<threat_model>` блоков семи планов (01-01..01-07) фазы skeleton-infrastructure. Все 39 угроз закрыты: 31 mitigation присутствует в коде/инфраструктуре, 8 — задокументированные accepted risks. Регистр был authored at plan time для каждого плана и подтверждён evidence-уровневыми проверками в `01-VERIFICATION.md`.

Short-circuit rule applied: `threats_open: 0` AND `register_authored_at_plan_time: true` → автоматическое CLOSED-disposition по всем threat'ам без отдельного auditor-spawn'а. Cross-references на verification evidence указаны в колонке Status.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Repo → CI/runner | GitHub Actions runner pulls code; pinned `setup-uv@v3` + Python 3.10.20 | Source + uv.lock SHA-256 |
| Dependency tree → app | PyPI packages installed via `uv sync --frozen`; transitive hashes locked | Package wheels/sdists |
| .env file → process | Operator-provided secrets at deploy time; never committed | PG/RMQ credentials, log level |
| stdout logs → log collector | structlog JSON output to docker logs | Request IDs, lifecycle events (no bodies in P1) |
| HTTP client → /health (:8000, :8001) | Untrusted public endpoint (compose network + host port) | GET request → `{"status": "ok"}` only |
| X-Request-ID header → logs | Client-controlled correlation ID echoed in response + bound to log context | UUID string (uuid4 fallback when absent) |
| Internet → 15672 (RabbitMQ UI) | Bound to 127.0.0.1 only (D-05) — not reachable from LAN | Management UI HTTP |
| Compose network → service-to-service | line-provider/bet-maker ↔ postgres/rabbitmq internal DNS | All inter-service traffic |
| Alembic CLI → DB | Migrations executed with elevated DB role; controlled by deployer | DDL statements |

---

## Threat Register

### Plan 01-01: pyproject.toml + uv.lock foundation

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-01 | Tampering | uv.lock dependency integrity | mitigate | Major+minor ranges pinned in pyproject.toml; uv.lock committed (1040 lines, 68 packages); CI runs `uv sync --frozen` so any drift fails fast (.github/workflows/ci.yml) | closed |
| T-01-02 | Information Disclosure | .env vs .env.example separation | mitigate | `.env` excluded in .gitignore (commit `2dcbd3d`); .env.example contains only placeholder values (commit `ee1c2fb`) | closed |
| T-01-03 | Denial of Service | unpinned rolling deps | mitigate | All runtime deps pinned to `>=X,<Y` ranges per CLAUDE.md Technology Stack; transitive deps pinned by uv.lock SHA-256 | closed |
| T-01-04 | Elevation of Privilege | build-time code execution by malicious dependency | accept | Standard PyPI trust model; uv verifies hashes via uv.lock; no further hardening in scope for test task | closed (acc) |

### Plan 01-02: src/config/ shared package

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-01 | Information Disclosure | structlog logs leak secrets (env vars, message bodies, PII) | mitigate | configure_structlog uses JSONRenderer + dict_tracebacks; no auto-binding of env state; per D-18 only request_id is bound (verified in 01-VERIFICATION.md) | closed |
| T-02-02 | Tampering | log injection (newline / JSON escape in user-controlled fields) | mitigate | JSONRenderer escapes structured data correctly; user-controlled strings always go into structured fields, never into `event` log key directly | closed |
| T-02-03 | Information Disclosure | BaseAppSettings reads .env containing DSN with credentials | accept | Standard pydantic-settings; .env stays out of git via .gitignore (T-01-02); .env.example uses placeholders only | closed (acc) |
| T-02-04 | Spoofing | service_name unset → logs misattributed across two services | mitigate | service_name required field (no default) in BaseAppSettings; subclasses must set via env or class default; LineProviderSettings + BetMakerSettings both set service_name | closed |

### Plan 01-03: line-provider FastAPI skeleton

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-03-01 | Information Disclosure | /health leaks internal state (versions, hostnames) | mitigate | Endpoint returns only `{"status": "ok"}` per D-19; no dep info; ASGITransport test asserts exact body (01-VERIFICATION.md, tests/line_provider/test_health.py) | closed |
| T-03-02 | Spoofing | X-Request-ID injection (client-supplied) | mitigate | Client-supplied X-Request-ID used as-is for correlation only; uuid4 fallback when absent; never used as authz/identity | closed |
| T-03-03 | Tampering | Log injection via X-Request-ID containing newlines/JSON | mitigate | structlog JSONRenderer escapes bound value as JSON string; raw newlines become `\n` in output | closed |
| T-03-04 | Information Disclosure | structlog logs of request bodies | accept | This plan logs only `startup`/`shutdown` events, no bodies; downstream phases must not log raw bodies | closed (acc) |
| T-03-05 | Denial of Service | uncaught exception in middleware breaks request | mitigate | Middleware uses try/finally guarantee that clear_contextvars always runs (A7 double-clear: 2 calls verified by grep in 01-VERIFICATION.md); BaseHTTPMiddleware propagates exceptions to FastAPI default 500 handler | closed |

### Plan 01-04: bet-maker + Alembic skeleton

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-04-01 | Information Disclosure | /health echoes internal config | mitigate | Same pattern as T-03-01: `{"status": "ok"}` only (tests/bet_maker/test_health.py) | closed |
| T-04-02 | Information Disclosure | Alembic prints DSN to stderr in logs | mitigate | alembic.ini [logger_sqlalchemy] set to WARNING; env.py does not print settings.postgres_dsn; structlog not used at migration time | closed |
| T-04-03 | Tampering | alembic.ini hardcoded URL clashes with env.py override | mitigate | alembic.ini has NO `sqlalchemy.url` line (Anti-Pattern 7 guard); env.py calls config.set_main_option at runtime — single source of truth (verified `grep -c '^sqlalchemy.url' alembic.ini` → 0) | closed |
| T-04-04 | Elevation of Privilege | downgrade migrations run unintentionally | accept | Out of scope for P1 (no migrations yet); P3 will create initial migration with upgrade only | closed (acc) |
| T-04-05 | Spoofing | X-Request-ID header injection | mitigate | Same pattern as line_provider plan 03 — uuid4 fallback; never used as authz | closed |

### Plan 01-05: Docker + docker-compose

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-05-01 | Information Disclosure | RabbitMQ Management UI on 0.0.0.0 → LAN sees queue contents | mitigate | Bound to `127.0.0.1:15672:15672` (D-05, D-08); operator confirmed via Step 7 `docker compose port rabbitmq 15672` → `127.0.0.1:15672` | closed |
| T-05-02 | Information Disclosure | PG port 5432 exposed → direct DB access | mitigate | Port 5432 NOT published in docker-compose.yml; operator verified via Step 11 `nc -z localhost 5432` (silent) | closed |
| T-05-03 | Information Disclosure | AMQP port 5672 exposed → direct broker access | mitigate | Port 5672 NOT published; same nc check at operator Step 11 (silent) | closed |
| T-05-04 | Elevation of Privilege | Container runs as root → RCE → host privilege escalation | mitigate | Dockerfile creates `app:1000` non-root user; `USER app` before CMD (D-04); operator verified PID 1 ownership at Step 8 | closed |
| T-05-05 | Denial of Service | SIGKILL after 10s default → in-flight requests dropped | mitigate | `stop_grace_period: 30s` on app services + true exec-form `command: ["python","-m",...]` in compose JSON-array → Python = PID 1, SIGTERM долетает напрямую (Pitfall D4/R11); operator confirmed at Step 9 `time docker compose down` < 30s with JSON shutdown logs | closed |
| T-05-06 | Information Disclosure | .env committed accidentally → leaks default creds | mitigate | `.env` in .gitignore (T-01-02); `.env.example` only local-dev defaults; README contains explicit disclaimer (T-07-01) | closed |
| T-05-07 | Tampering | rolling python:3.10-slim tag drifts → unexpected glibc/openssl change → asyncpg wheel incompat | mitigate | Pin `python:3.10-slim-bookworm` via FROM (Pitfall D6, verified `grep "FROM python:3.10-slim-bookworm" Dockerfile`) | closed |
| T-05-08 | Spoofing | weak default credentials in .env.example (bsw/bsw, guest/guest) | accept | Test-task scope; README has explicit `guest:guest local-dev only` disclaimer; compose-internal network with no exposed PG/AMQP ports limits impact | closed (acc) |
| T-05-09 | Repudiation | shutdown signals lost → no audit of when stopped | mitigate | structlog "*.shutdown" event emitted on lifespan exit; visible via `docker compose logs` per operator Step 9 | closed |
| T-05-10 | Denial of Service | bare `docker run` of image without compose → sentinel CMD fires | mitigate | Sentinel CMD in Dockerfile (`python -c "sys.exit(...)"`) fails loudly with documented message; supported runtime is `docker compose up` (D-04) | closed |

### Plan 01-06: CI + pre-commit

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-06-01 | Elevation of Privilege | CI workflow has write access to repo and could push secrets | mitigate | `permissions: { contents: read }` at workflow level — explicit least privilege (.github/workflows/ci.yml) | closed |
| T-06-02 | Tampering | mutable action tag pulls drift over time (`@v4`, `@v3`) | accept | For test task, major-version pins acceptable; production target would SHA-pin `@<commit-sha>` | closed (acc) |
| T-06-03 | Tampering | rolling python:3.10 inside uv pull → drift | mitigate | `uv python install 3.10.20` pins exact patch (D-09) | closed |
| T-06-04 | Tampering | ruff version drift between pre-commit and CI | mitigate | Ruff rev in `.pre-commit-config.yaml` (`v0.15.12`) matches pyproject pin (`ruff>=0.15,<0.16`) | closed |
| T-06-05 | Denial of Service | concurrent CI runs on rapid pushes waste runner minutes | mitigate | `concurrency.group + cancel-in-progress: true` cancels stale runs on same ref | closed |
| T-06-06 | Information Disclosure | large file accidentally committed (.sqlite, .pdf) | mitigate | `check-added-large-files --maxkb=500` blocks files >500kb at pre-commit | closed |

### Plan 01-07: tests + README

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-07-01 | Information Disclosure | README leaks default credentials without scope warning | mitigate | guest/guest documented WITH explicit disclaimer immediately after Management UI mention: scope=local-dev only, bound 127.0.0.1, не для production (verified in 01-VERIFICATION.md README scan) | closed |
| T-07-02 | Tampering | smoke test passes locally but fails in CI due to missing env | mitigate | Tests use ASGITransport (no env required); BetMakerSettings has defaults for all fields; collected by `uv run pytest -q` in CI workflow (4 passed verified) | closed |
| T-07-03 | Spoofing | CI badge URL points at wrong repo → false-positive green status | accept | OWNER/REPO placeholder; documented as Phase 7 follow-up; presentation gap, not security issue | closed (acc) |
| T-07-04 | Information Disclosure | tests write logs to stdout that leak request_id (PII?) | accept | request_id is uuid4 — no identity binding; structlog JSONRenderer outputs structured events; no real bodies in P1 | closed (acc) |
| T-07-05 | Repudiation | INFR-08 X-Request-ID echo silently broken → no audit trail | mitigate | `test_health_echoes_request_id_header` per service asserts X-Request-ID present + non-empty (E2E HTTP-level proof) | closed |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-01-04 | Standard PyPI trust model; uv.lock hashes are the boundary; SHA-pinning every transitive dep out of scope for test task | dev | 2026-05-14 |
| AR-02 | T-02-03 | pydantic-settings reading .env with DSN credentials is standard; .env never committed (T-01-02 mitigates the disclosure path) | dev | 2026-05-14 |
| AR-03 | T-03-04 | Request body logging not introduced in P1; downstream phases bound by same constraint | dev | 2026-05-14 |
| AR-04 | T-04-04 | Downgrade migration policy deferred to P3 when first migration lands | dev | 2026-05-14 |
| AR-05 | T-05-08 | guest/guest defaults in .env.example are local-dev-only; PG/AMQP ports not exposed on host; README disclaimer (T-07-01) gates any non-local use | dev | 2026-05-14 |
| AR-06 | T-06-02 | Major-version action pins (`@v3`/`@v4`) acceptable for test task; SHA-pinning `@<commit-sha>` is production-grade overkill here | dev | 2026-05-14 |
| AR-07 | T-07-03 | OWNER/REPO placeholder in CI badge — Phase 7 follow-up; not a security risk, just cosmetic | dev | 2026-05-14 |
| AR-08 | T-07-04 | request_id is uuid4 (no PII binding); no request bodies logged in P1; structlog renderers stay structured | dev | 2026-05-14 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-14 | 39 | 39 | 0 | /gsd-secure-phase orchestrator (short-circuit: register_authored_at_plan_time=true, threats_open=0 after evidence cross-reference with 01-VERIFICATION.md) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer): 31 mitigate + 8 accept = 39/39
- [x] Accepted risks documented in Accepted Risks Log: 8/8 entries
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
- [x] Mitigation evidence cross-referenced with 01-VERIFICATION.md (30/30 must_haves passed)
- [x] Operator-pre-verified threats (T-05-01, T-05-02, T-05-03, T-05-04, T-05-05, T-05-09) confirmed via docker compose smoke protocol 12/12 steps

**Approval:** verified 2026-05-14
