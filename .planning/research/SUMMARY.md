# Project Research Summary

**Project:** BSW Betting System (Middle Python test task)
**Domain:** Two-service asynchronous Python betting system — FastAPI + FastStream/RabbitMQ + asyncpg/SQLAlchemy 2.0 async + reconciliation worker
**Researched:** 2026-05-13
**Confidence:** HIGH

## Executive Summary

This is a **reviewer-graded test task**, not a real product. Two FastAPI services — `line-provider` (in-memory event store, publisher) and `bet-maker` (PostgreSQL + bet history, AMQP consumer) — communicate over RabbitMQ. The single non-negotiable invariant is **"a bet never stays PENDING after the event has finished"**; the entire architecture (durable queue + manual ack + DLQ + reconciliation worker + `FOR UPDATE SKIP LOCKED`) exists to defend that invariant in depth.

The recommended approach is opinionated and tightly scoped: pin every version in `pyproject.toml` (FastAPI 0.136 / FastStream 0.6 / SQLAlchemy 2.0.49 / asyncpg 0.31 / Pydantic 2.13), use FastStream's `RabbitRouter` for the AMQP-inside-FastAPI integration (officially supported, auto-lifespan ≥ 0.112.2), implement the Unit of Work + Repository pattern on bet-maker, and add a small set of **high-signal differentiators** (reconciliation worker, dependency-aware `/health`, structured logging with `request_id`/`correlation_id` propagation, DLQ, idempotent settle, CI badge) that a reviewer can recognise in 10–15 minutes without bloating dependency count.

The dominant risk is **integration reliability**: at-least-once AMQP semantics plus crash/restart/redeploy scenarios produce ~12 distinct ways to leave bets stuck in PENDING. The mitigation is layered (manual `AckPolicy.MANUAL` + `SELECT FOR UPDATE SKIP LOCKED` for consumer/reconciler safety + DLQ with bounded retries + reconciler as a second line of defence + durable queues with volumes for broker restarts + `python:3.10-slim-bookworm` exec-form CMD for clean SIGTERM). Confidence is HIGH across the board — every pinned version, AMQP API, and SQLAlchemy async pattern was verified against PyPI, Context7, or the project's official docs on 2026-05-13.

## Key Findings

### Recommended Stack

**Top 5 picks (pinned):**
- **FastAPI 0.136.1** (`>=0.115,<0.137`) — HTTP framework for both services; the `>=0.115` floor guarantees FastStream auto-lifespan.
- **FastStream 0.6.7** (`>=0.6,<0.7`) — `RabbitRouter` integrates AMQP into the FastAPI app; pulls `aio-pika>=9,<10` transitively; provides `TestRabbitBroker`, `AckPolicy.MANUAL`, AsyncAPI docs at `/asyncapi`.
- **SQLAlchemy 2.0.49** (`>=2.0.40,<2.1`) — async ORM with `async_sessionmaker.begin()` for UoW, typed `Mapped[...]`, and `with_for_update(skip_locked=True)` for the race-safe settle.
- **asyncpg 0.31.0** — fastest async Postgres driver; URL prefix MUST be `postgresql+asyncpg://`.
- **Pydantic 2.13.4** (`>=2.9,<3`) + **pydantic-settings 2.14.1** — single validation system across HTTP, AMQP, and typed config (`env_prefix="BET_MAKER_"`).

**Supporting pins:** `httpx 0.28.1` (reconciler + tests), `tenacity 9.1.4` (retries on PG/RMQ connect + reconciler HTTP), `structlog 25.5.0` (JSON logs with `contextvars` propagation), `alembic 1.18.4` (async template), `uvicorn 0.46 [standard]`, `uv 0.11.14`, `ruff 0.15.12`, `mypy 2.1.0` (strict + `pydantic.mypy`), `pytest 9.0.3` + `pytest-asyncio 1.1.0` + `pytest-cov 7.1.0`. Infra images: `python:3.10-slim-bookworm` (NOT rolling `-slim`), `postgres:16-alpine`, `rabbitmq:4.2-management-alpine`.

Full detail: `.planning/research/STACK.md`.

### Expected Features

The framing is **table stakes (TZ-required, missing = fail)** vs **differentiators (reviewer-signal extras)** vs **anti-features (deliberately out of scope)**.

**Table stakes (~17 items, all P0):** line-provider in-memory store + utility API + publish on state change; bet-maker `GET /events` (proxy), `POST /bet` (Decimal>0, 2dp), `GET /bets` (history), PG persistence via SQLAlchemy 2.0 async + UoW, RabbitMQ consumer with atomic settle; Docker images + docker-compose with healthchecks; Alembic migrations; mypy strict + pytest; README.

**Differentiators (10 picks, filtered for high signal / low effort):**
Top-3 P1 (do these even under time pressure):
1. **D1 — Reconciliation job** — the single strongest signal for this task; defence-in-depth against lost AMQP messages.
2. **D2 — `/health` that actually pings PG + RabbitMQ** — wired into compose healthchecks; visible in 2 seconds via `curl`.
3. **D3 — Structured logging with `request_id` + `correlation_id` propagation across HTTP and AMQP** — single visual proving "this candidate has worked in production."

Strong-P1 also: **D7** (`pydantic-settings`) and **D10** (GitHub Actions CI with badge).
P2: **D4** (idempotent settle via queue), **D5** (DLQ with bounded retries), **D8** (OpenAPI/AsyncAPI polish), **D9** (`SELECT FOR UPDATE SKIP LOCKED`).
P3: **D6** (graceful shutdown verification — mostly free with FastStream lifespan).

**Defer / anti-features (explicit out of scope with written rationale):** user auth, wallet/balance, KYC, draws, multiple bet types, live odds, payments, outbox pattern (incompatible with TZ's in-memory line-provider), Kafka, k8s, Prometheus metrics, OpenTelemetry, frontend, Redis cache. Each gets a one-line reason in README/PROJECT.md so the reviewer sees deliberate omission rather than oversight.

Full detail: `.planning/research/FEATURES.md`.

### Architecture Approach

**Two FastAPI services + RabbitMQ topic exchange + PostgreSQL + reconciliation worker.** Layered architecture inside each service: `entrypoints -> facades -> interactors/selectors -> repositories/helpers -> models/infrastructure`, one direction only. CQRS-lite split: `interactors/` own writes (with UoW + transaction), `selectors/` own reads (plain `AsyncSession`, return Pydantic DTOs). Cross-service communication is **one-way only** — line-provider publishes; bet-maker consumes; bet-maker pulls line-provider over HTTP for reconciliation; bet-maker NEVER publishes.

**Major components:**
1. **line-provider service** — FastAPI app + `InMemoryEventStore` (dict + `asyncio.Lock`) + `EventBus` facade wrapping `router.broker.publish`. Publishes `event.finished.win|lose` to topic exchange `events` AFTER in-memory commit.
2. **bet-maker service** — FastAPI app + `AsyncUnitOfWork` (wraps `async_sessionmaker.begin()`) + `BetRepository` (session-bound, `flush()` not `commit()`) + AMQP consumer with `AckPolicy.MANUAL` + asyncio reconciliation worker started in lifespan.
3. **RabbitMQ topology** — Exchange `events` (topic, durable); queue `bet_maker.events.finished` (durable, `x-dead-letter-exchange=events.dlx`); DLX `events.dlx` (fanout) -> DLQ `bet_maker.events.finished.dlq`. Manual ack; bounded retries via app-code redelivery tracking; classic queues acceptable for the test (quorum queues = production upgrade noted in README).
4. **Reconciliation worker** — `asyncio.Task` started in lifespan, ticks every N seconds (configurable), reuses the same `settle_bets_for_event` interactor as the AMQP consumer. Race-safe via `SELECT ... FOR UPDATE SKIP LOCKED` + `WHERE status='PENDING'` filter.
5. **Shared message schema** — `EventFinishedMessage(schema_version, event_id, new_state, coefficient, occurred_at, correlation_id)` with `extra="forbid"`, mirrored byte-for-byte in both services' `schemas/messages.py`.
6. **Lifespan composition** — Custom `asynccontextmanager` in bet-maker bootstraps in strict order: settings -> structlog -> engine + sessionmaker -> PG ping (tenacity-retried) -> httpx client -> FastStream router auto-attached -> reconciliation worker. Shutdown reverses; `graceful_timeout=30s` on broker, `stop_grace_period: 30s` in compose.
7. **Monorepo layout** — `src/line_provider/`, `src/bet_maker/`, single `pyproject.toml` at repo root, single `alembic/` at repo root targeting bet-maker only.

Full detail (with paste-ready directory trees, UoW code shape, AMQP topology, reconciliation blueprint, lifespan code): `.planning/research/ARCHITECTURE.md`.

### Critical Pitfalls

Top-5 highest-risk pitfalls (each violates the Core Value if missed), with the phase that prevents them:

1. **R1 — Auto-ack consumer + crash mid-handler -> message lost, bet stays PENDING.** FastStream 0.6's default is `AckPolicy.REJECT_ON_ERROR`. **Prevent in Phase 5 (RabbitMQ integration):** explicit `ack_policy=AckPolicy.MANUAL` + `await msg.ack()` AFTER the UoW commits.
2. **R3 / A2 — Consumer-vs-reconciler race + shared `AsyncSession` `another operation in progress`.** Two writers, one row, OR two coroutines, one session. **Prevent in Phase 3 (bet-maker DB) and Phase 5:** `with_for_update(skip_locked=True)` in `BetRepository.get_pending_locked()`; one `AsyncSession` per UoW per business operation, never share a session across tasks.
3. **R4 / R10 — Queue/messages not durable OR `docker compose down -v` wipes RabbitMQ volume -> in-flight messages lost on broker restart.** **Prevent in Phase 1 (skeleton):** declare `durable=True` on queue and exchange, mount `rabbitmq_data:/var/lib/rabbitmq` + `postgres_data:/var/lib/postgresql/data`, pin `hostname: rabbitmq` so mnesia node name stays stable.
4. **R8 — Reconciliation `asyncio.Task` dies silently; `/health` still reports OK; defence-in-depth gone.** **Prevent in Phase 6 (reconciliation):** wrap loop body in `try/except Exception:` (not `BaseException`); name the task; in `/health` assert `task.done() is False`; emit `reconciliation.heartbeat` log per tick.
5. **R11 / D4 — Shell-form `CMD` -> SIGTERM never reaches uvicorn -> SIGKILL after grace period -> unacked messages forcibly requeued.** **Prevent in Phase 1 (Dockerfile + compose):** exec form `CMD ["python", "-m", "uvicorn", ...]`, `ENV PYTHONUNBUFFERED=1`, `stop_grace_period: 30s`, FastStream `RabbitBroker(graceful_timeout=30.0)`.

Honorable-mention (must also be addressed, lower individual blast radius): **A1** `MissingGreenlet` (`expire_on_commit=False` in P3); **A4–A5** Decimal/NUMERIC precision (Pydantic `decimal_places=2` + `Mapped[Decimal] = mapped_column(Numeric(12,2))` in P3); **F7** schema versioning (`schema_version` field + `extra="forbid"` in P5); **D1** compose `depends_on: condition: service_healthy` with `start_period` to avoid initdb race in P1.

Full detail (12 reliability pitfalls + 7 async/DB + 8 FastStream/RabbitMQ + 8 Docker, plus phase-mapping, "Looks Done But Isn't" checklist, recovery strategies): `.planning/research/PITFALLS.md`.

## Implications for Roadmap

The architecture research already produced a minimum-dependency build order. **Adopt it as-is** — phases are sequenced so no phase depends on work in a later phase, and the Core Value path (1 -> 2 -> 5 -> 6) is on the critical path.

### Phase 1: Skeleton + Infrastructure
**Rationale:** Every later phase needs `docker compose up` to work; getting CI green and the compose topology right once is one-time cost that pays back every PR.
**Delivers:** pyproject + uv.lock, Dockerfiles (exec-form CMD, slim-bookworm, non-root, `PYTHONUNBUFFERED=1`), docker-compose (Postgres + RabbitMQ with healthchecks + volumes + `hostname: rabbitmq`), structlog config + RequestId middleware, pydantic-settings, pre-commit + ruff + mypy + GitHub Actions CI, README skeleton, empty `/health` on both services.
**Avoids:** R4, R10 (volumes), R11/D4 (exec form + grace period), D1 (compose healthcheck conditions), D2/D6 (start_period + bookworm pin), D5 (PYTHONUNBUFFERED), D8 (service names, 0.0.0.0 bind), A7 (structlog contextvars in middleware).

### Phase 2: line-provider domain (HTTP-only, no AMQP yet)
**Rationale:** Unblocks reconciliation in P4/P6 (`GET /events/{id}` is the source-of-truth fallback). Has no DB and no broker, so it can ship independently of P3.
**Delivers:** `InMemoryEventStore` (dict + `asyncio.Lock`), `EventCreate`/`EventRead`/`EventStatePatch` schemas, `helpers/state_machine.py`, interactors (`create_event`, `set_event_state` — no publish yet), selectors (`list_active_events`, `get_event_by_id`), `entrypoints/api/events.py`, unit tests on interactors/selectors/helpers.
**Avoids:** R9, R12 (interactor commits to store BEFORE publishing in P5), A7 in line-provider.

### Phase 3: bet-maker domain (DB-only, no AMQP yet) — parallelisable with P2
**Rationale:** Same blocker as P2 (P1). No shared code with P2. Two devs can run P2 and P3 in parallel; solo dev picks whichever produces visible progress fastest.
**Delivers:** `models/bet.py` (`Mapped[Decimal] = mapped_column(Numeric(12,2))`), Alembic initial migration (async template, env.py reads from settings), `infrastructure/db/engine.py` (`pool_size=10`, `pool_pre_ping=True`, `expire_on_commit=False`), `BetRepository` (with `get_pending_locked` using `FOR UPDATE SKIP LOCKED`), `AsyncUnitOfWork`, `helpers/money.py` + `helpers/status.py`, `BetCreate` (Pydantic `decimal_places=2`), `interactors/place_bet.py`, `selectors/list_bets.py` (returns DTOs, never raw ORM), `entrypoints/api/bets.py`, `/health` upgrades to ping PG.
**Avoids:** A1 (`expire_on_commit=False`), A2 (per-request UoW), A3 (pool config), A4/A5 (Decimal end-to-end), A6 (`alembic init -t async`), D2 (lifespan ping with retry).

### Phase 4: bet-maker `GET /events` + line-provider HTTP integration
**Rationale:** Splits "HTTP client to line-provider" out of P5 and P6 so P5 (the riskiest phase) doesn't have to debug httpx and AMQP simultaneously. Establishes the reconciler's HTTP path.
**Delivers:** `facades/line_provider_client.py` (`httpx.AsyncClient` + `tenacity` retries), tiny TTL cache, `selectors/list_active_events.py` (cached proxy), `entrypoints/api/events.py` on bet-maker, ASGI-transport integration test driving both apps without docker.
**Avoids:** stale connections / event-loop sharing on `httpx.AsyncClient`.

### Phase 5: RabbitMQ integration (publisher + consumer + DLQ)
**Rationale:** The single highest-risk phase — most pitfalls cluster here. Sequenced AFTER P2 (publisher needs line-provider domain) and P3 (consumer needs the bet repository + UoW + FOR UPDATE) so neither side is invented during integration.
**Delivers:** `infrastructure/broker/rabbit.py` in both services (exchange/queue/DLX with full `arguments` dict; declare-once-don't-edit), `schemas/messages.py` mirrored both sides (`schema_version`, `extra="forbid"`), line-provider `EventBus` + publish AFTER in-memory commit, bet-maker `@router.subscriber` with `AckPolicy.MANUAL`, `prefetch_count` set, `interactors/settle_bets_for_event.py`, broker `graceful_timeout=30.0`, `/health` upgraded to ping RabbitMQ + assert subscriber count > 0, structlog `clear_contextvars` at handler top in `try/finally`, `TestRabbitBroker` unit tests, one real-RabbitMQ e2e test.
**Avoids:** R1, R2, R3, R5, R7, R9, R12, F1, F2, F3, F4, F5, F6, F7, F8, A7 in consumer. (Roughly half of all critical pitfalls live in this phase — it warrants the most code-review attention.)

### Phase 6: Reconciliation job
**Rationale:** Needs both the HTTP client (P4) and the settle interactor (P5). Closes the Core Value loop — this is the "even if a message is lost, no bet stays PENDING" guarantee.
**Delivers:** `entrypoints/workers/reconciliation.py` (`while not shutdown.is_set():` + `try/except Exception:` + heartbeat log), `interactors/reconcile_pending_bets.py` (reuses `settle_bets_for_event`), `selectors/list_pending_event_ids.py`, lifespan start/cancel of the worker task, `/health` checks worker liveness, test that skips the publish and asserts the reconciler settles within one interval, test that runs consumer + reconciler concurrently against the same event and asserts no double-update.
**Avoids:** R8 (silent worker death), R3 (reconciler-vs-consumer race re-verified end-to-end).

### Phase 7: Documentation polish + final CI
**Rationale:** Single phase to gather "looks done but isn't" verifications (PITFALLS.md checklist), final API polish, and the README curl examples that the reviewer will literally execute.
**Delivers:** README with `docker compose up` flow, curl examples, ASCII architecture diagram, AsyncAPI link, "what I'd add next" section, CI badge; OpenAPI tags/summaries/response_model/examples (D8); pytest-cov threshold in CI; graceful-shutdown verification (D6) by capturing `docker compose down` logs; complete the "Looks Done But Isn't" 18-item checklist from PITFALLS.md.
**Avoids:** the visibility gap — every previous-phase fix only counts if it's visible to a 15-minute reviewer.

### Phase Ordering Rationale

- **1 -> {2, 3} -> 4 -> 5 -> 6 -> 7** is the minimum-dependency DAG. P2 and P3 are parallel; everything else is strictly sequential.
- **Critical path is 1 -> 2 -> 5 -> 6 -> 7** (covers the Core Value: line-provider publishes -> bet-maker consumes -> reconciler backs it up).
- **P5 is the risk-heavy phase** (~50% of pitfalls live there); P1 is the foundation-heavy phase (compose + Dockerfile mistakes are expensive to fix later). Both deserve double the code-review attention.
- **CQRS-lite split (interactors/selectors)** is established in P2/P3 and reused unchanged in P5/P6 — one code path, two triggers (HTTP and AMQP), which is the elegance signal.
- **Anti-pattern discipline carries across phases:** publish AFTER store commit (P2 + P5); never publish from inside `async with uow:` (P5); never share `AsyncSession` (P3+P5+P6); only `expire_on_commit=False` (P3); only `AckPolicy.MANUAL` (P5).

### Research Flags

**Phases that need NO deeper research during planning** (all patterns verified HIGH in research):
- **P1, P2, P3** — well-documented FastAPI / SQLAlchemy / docker-compose patterns; just execute.
- **P7** — pure polish on existing artefacts.

**Phases that MIGHT need targeted research during planning** (`/gsd-research-phase`):
- **P5 (RabbitMQ integration)** — only if implementation diverges from ARCHITECTURE.md's verified topology (e.g., if quorum queues are chosen over classic, the DLQ behaviour and `x-delivery-count` semantics change). Otherwise, ARCHITECTURE.md + PITFALLS.md already cover it.
- **P6 (Reconciliation)** — only if the worker is split into a separate container (out-of-scope decision in ARCHITECTURE.md but a reviewer might ask). Otherwise the asyncio.Task pattern is documented.

**Note for the roadmapper:** the architecture and pitfalls research is so concrete (paste-ready code shapes, specific queue names, exact `arguments` dicts, named pitfalls with prevention-phase mapping) that the roadmap can mostly translate findings 1:1 into phase tasks without further research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Every version verified against PyPI on 2026-05-13; FastStream/FastAPI integration cross-checked against Context7 (`/ag2ai/faststream`) and official `faststream.ag2.ai` docs; Python/PG/RabbitMQ EOL dates checked at endoflife.date. |
| Features | HIGH | Table stakes are 1:1 with TZ clauses (no inference). Differentiators filtered against three explicit criteria; each item references PROJECT.md or STACK.md. Anti-features each have a written rationale. |
| Architecture | HIGH | UoW shape verified against SQLAlchemy 2.0 async docs (Context7 `/websites/sqlalchemy_en_20`). FastStream `RabbitRouter` + `AckPolicy.MANUAL` + `RabbitQueue(arguments={...})` + `TestRabbitBroker` verified against `/ag2ai/faststream`. Lifespan auto-merge confirmed against FastAPI >= 0.112.2 docs. |
| Pitfalls | HIGH | Every pitfall anchored to an official doc page, a tracked GitHub issue, or a Context7-verified API. Phase mapping is explicit. "Looks Done But Isn't" checklist gives mechanical verification. |

**Overall confidence:** HIGH.

### Gaps to Address

- **Classic queues vs quorum queues** — the research recommends classic queues for the test task (simpler, adequate when app-code redelivery limiting is solid) and mentions quorum queues as the production upgrade. If the reviewer is known to care about quorum-queue features, the recommendation flips to quorum. **Handle in P5 planning:** decide once, stick with it; if quorum, declare `x-queue-type=quorum` and rely on the broker's default `delivery-limit=20`.
- **Idempotency-Key on POST /bet (D4 variant a)** — research recommends variant b (idempotency at queue consumer via `(event_id, bet_id)`) as must-have and variant a (HTTP `Idempotency-Key` header) as a README-mentioned extension. **Handle in P3 planning:** confirm variant b ships; defer variant a to "what I'd add next" unless time allows.
- **Reconciliation interval** — no value chosen yet; needs to be `< deadline_skew` of typical events and `> AMQP_redelivery_window` to avoid double-work. **Handle in P6 planning:** default to 30s, expose via `pydantic-settings` (`BET_MAKER_RECONCILIATION_INTERVAL_S`), document the trade-off in README.
- **`expose:` vs `ports:` for RabbitMQ management UI** — research notes that publishing `:15672` to host with `guest:guest` is a security trade-off, recommends `127.0.0.1:15672:15672` to limit blast radius. **Handle in P1 planning:** confirm the compose binds management UI to `127.0.0.1`, not `0.0.0.0`.

## Sources

### Primary (HIGH confidence)
- Context7 `/ag2ai/faststream` — FastAPI `RabbitRouter` integration, `AckPolicy.MANUAL`, `RabbitMessage.ack/nack/reject`, `RabbitQueue(arguments={...})`, `RabbitExchange(type="topic")`, `TestRabbitBroker`, `RabbitBroker(graceful_timeout=...)`, FastStream 0.6 release notes.
- Context7 `/websites/sqlalchemy_en_20` — `async_sessionmaker.begin()`, `expire_on_commit=False`, `with_for_update(skip_locked=True)`, `MissingGreenlet`, `AsyncAttrs`, pool config, `postgresql+asyncpg://` URL.
- Context7 `/fastapi/fastapi` — version listing, lifespan auto-merge behaviour.
- https://faststream.ag2.ai/latest/getting-started/integrations/fastapi/ — official FastStream + FastAPI integration page (auto-lifespan requires `fastapi>=0.112.2`).
- PyPI JSON for every pinned package (FastStream 0.6.7, FastAPI 0.136.1, SQLAlchemy 2.0.49, asyncpg 0.31.0, Pydantic 2.13.4, pydantic-settings 2.14.1, Alembic 1.18.4, structlog 25.5.0, httpx 0.28.1, tenacity 9.1.4, pytest 9.0.3, pytest-asyncio 1.1.0, pytest-cov 7.1.0, anyio 4.13.0, uv 0.11.14, ruff 0.15.12, mypy 2.1.0, pre-commit 4.6.0, uvicorn 0.46.0, aio-pika 9.6.2) — all dated 2026-05-13.
- https://docs.sqlalchemy.org/en/20/errors.html and /orm/extensions/asyncio.html — MissingGreenlet, async session semantics.
- https://www.rabbitmq.com/docs/quorum-queues and /docs/consumer-prefetch — `x-delivery-count`, default unlimited prefetch.
- https://www.postgresql.org/docs/current/transaction-iso.html — READ COMMITTED + FOR UPDATE SKIP LOCKED + EvalPlanQual semantics.
- https://docs.docker.com/compose/compose-file/#depends_on — `condition: service_healthy` semantics.
- https://hub.docker.com/_/python — slim tag distro defaults (bookworm vs trixie).
- https://petermalmgren.com/signal-handling-docker/ — exec-form CMD vs shell-form, SIGTERM propagation.
- https://endoflife.date/api/python.json, /postgres.json — EOL dates.
- https://www.rabbitmq.com/release-information — RabbitMQ 4.2 community support window.

### Secondary (MEDIUM confidence — community consensus)
- https://github.com/MagicStack/asyncpg/issues/258 and #863 — `InterfaceError: another operation in progress` from shared connections.
- https://github.com/sqlalchemy/sqlalchemy/issues/5967 — asyncpg + SQLAlchemy concurrent-operation issue.
- https://github.com/hynek/structlog/issues/248 and PR #302 — contextvars cross-task isolation fix.
- https://github.com/mosquito/aio-pika/issues/165 — declare_queue PRECONDITION_FAILED on argument mismatch.
- https://github.com/fastapi/fastapi/pull/9630 — nested lifespan merging.
- https://github.com/pydantic/pydantic/issues/6295 + /discussions/8505 — Decimal serialization in v2.

### Internal sources
- `/Users/dmitrydankov/Personal/BSW/.planning/PROJECT.md` — TZ requirements, Core Value, Out-of-Scope decisions, Key Decisions table.
- `/Users/dmitrydankov/Personal/BSW/.planning/research/STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` — full detail behind every summary above.

---
*Research completed: 2026-05-13*
*Ready for roadmap: yes*
