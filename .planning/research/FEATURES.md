# Feature Research

**Domain:** Asynchronous Python microservices — sports-betting test task (Middle Python interview)
**Researched:** 2026-05-13
**Confidence:** HIGH

## Framing

This is a **test task graded by a reviewer against an engineering checklist**, not a real product graded by end users. So the usual "table stakes / differentiators / anti-features" framing is reinterpreted:

- **Table stakes** = features explicitly required by the TZ. Missing any of these = automatic fail.
- **Differentiators** = small extras a Middle/Senior reviewer recognizes as engineering maturity signals. They must have **high signal / low effort**. A reviewer who opens the repo for 10–15 minutes must be able to spot them in README, in code, or in `docker compose up` output. Bloat is itself a negative signal; everything below was filtered for "would a tired reviewer at 6pm notice this and nod, or would they think you over-engineered a test task?"
- **Anti-features** = things a real betting platform has but this test task should **explicitly NOT build**. Each one needs a written reason in PROJECT.md so the reviewer sees we made a conscious choice, not an omission.

## Feature Landscape

### Table Stakes (Required by TZ — Must Have)

Every item here maps to a specific clause of the technical specification. Missing any = the submission is incomplete.

| Feature | TZ Clause | Complexity | Notes |
|---------|-----------|------------|-------|
| **line-provider: in-memory event store** (event_id, coefficient, deadline, state) | "Хранить информацию о событиях в памяти" | LOW | Simple `dict[int, Event]` behind a thin facade. Do not introduce a DB. |
| **line-provider: utility API to create/update events** | "Утилитарное API для создания/обновления событий" | LOW | `POST /events` and `PATCH /events/{id}` (status transitions). Used by the reviewer to drive the scenario. |
| **line-provider: list active events** (`deadline > now`) | "API для получения списка активных событий" | LOW | `GET /events`. Filter by `deadline > now` and `state == NEW`. |
| **line-provider: get one event by id** | "Получение одного события" | LOW | `GET /events/{id}`. Needed by bet-maker's reconciliation job. |
| **line-provider: 3 event states** (NEW, FINISHED\_WIN, FINISHED\_LOSE) | TZ enum | LOW | Pydantic `StrEnum`. No DRAW state — TZ excludes it. |
| **line-provider: publish state-change event to RabbitMQ** | Integration contract | MEDIUM | `events.finished` queue/exchange. Manual ack on consumer side. |
| **bet-maker: `GET /events`** — active events | TZ endpoint | LOW | Proxy/cache from line-provider over HTTP. Some lag is acceptable per TZ. |
| **bet-maker: `POST /bet`** — place bet (event_id, amount > 0, 2 decimal places) | TZ endpoint | MEDIUM | Pydantic validator: `Decimal` quantized to 2 places, `condecimal(gt=0, decimal_places=2)`. Persist in PG. Initial status = PENDING. |
| **bet-maker: `GET /bets`** — history with statuses (PENDING / WON / LOST) | TZ endpoint | LOW | Read-only query through a `selector`. Order by `created_at desc`. |
| **bet-maker: PostgreSQL persistence** (asyncpg + SQLAlchemy 2.0 async, Unit of Work) | TZ stack | MEDIUM | Single `bets` table. Alembic-managed schema. |
| **bet-maker: RabbitMQ consumer** — atomic bet-status update on `events.finished` | TZ reliability requirement | HIGH | Manual ack. Inside one DB transaction: load all PENDING bets for `event_id`, map status (WIN→WON, LOSE→LOST), commit, then ack. Nack on DB failure. |
| **Reliability invariant**: bet **never** stays PENDING after event finishes | Explicit TZ requirement | HIGH | This is the **Core Value**. Achieved via durable queue + manual ack + reconciliation job (see differentiators). |
| **Docker images** for both services (Python 3.10 slim-bookworm) | TZ infra | LOW | Multistage Dockerfile. Non-root user. |
| **docker-compose** — both services + PostgreSQL + RabbitMQ-management | TZ infra | LOW | One-command boot. Healthchecks on `postgres` and `rabbitmq` so service `depends_on: condition: service_healthy`. |
| **Alembic migrations** for bet-maker | TZ implies "production-style" | LOW | `alembic init -t async`. One initial migration. |
| **PEP 8 + full type hints** (mypy strict) | TZ "плюс" — treated as required | LOW | `[tool.mypy] strict = true` + `pydantic.mypy` plugin. CI gate. |
| **Tests** (pytest + pytest-asyncio): unit on interactors/selectors/helpers, integration on API + queue | TZ "плюс" — treated as required | MEDIUM | `TestRabbitBroker` for in-memory queue tests, real RabbitMQ container for one e2e flow. |
| **README** with run instructions | TZ requirement | LOW | "Clone → `docker compose up` → `curl …`". Architecture diagram (ASCII or Mermaid). |

### Differentiators (High-Impact Reviewer Signals — Should Have, 5–10 items)

Each item below was selected on three criteria: (1) a Middle/Senior Python reviewer will recognize it immediately, (2) it can be implemented in under half a day each, (3) it is **directly relevant to the integration-reliability story** that is the test task's Core Value — not generic best practices.

| # | Feature | Why a Reviewer Notices | Complexity | Notes |
|---|---------|------------------------|------------|-------|
| **D1** | **Reconciliation job in bet-maker** (periodic poll of `line-provider` for any PENDING bet whose event has finished) | This is the **single most important signal** for this task. The TZ explicitly forbids bets stuck in PENDING. A candidate who only consumes the queue is one lost message away from violating the invariant. A reconciliation job demonstrates the candidate **thought about message loss as a threat model** and built a second line of defence. Already listed in PROJECT.md as a Key Decision. | MEDIUM | Async loop with configurable interval (`pydantic-settings`). For each PENDING bet, batch-fetch event status via `httpx.AsyncClient` with `tenacity` retries. Update in one UoW transaction. Logged with structured context. |
| **D2** | **`/health` endpoint that actually checks dependencies** (PG with `SELECT 1`, RabbitMQ with channel open) — wired into docker-compose `healthcheck` so `depends_on: condition: service_healthy` works end-to-end | A reviewer hits `curl :8000/health` first. If it returns `{status: ok, postgres: ok, rabbitmq: ok}` instead of a hardcoded `{"ok": true}`, that is a 2-second proof of operational maturity. The docker-compose wiring is the chef's kiss — services come up in the right order automatically. | LOW | Return 503 if any dep is down. Use a 1s timeout per check so health check isn't slower than the dep itself. |
| **D3** | **Structured logging with request-id and message-id context propagation** (structlog `contextvars` processor, FastAPI middleware binds `request_id`, FastStream subscriber binds `message_id` + `event_id`) | The reviewer greps the logs for one bet's lifecycle and sees: HTTP POST → DB write → AMQP publish → consumer ack → DB update, all correlated by `request_id` / `event_id`. This single visual is the strongest "I have worked in production" signal there is for this stack. | LOW | structlog `merge_contextvars` + a tiny `RequestIdMiddleware` (8 lines). Bind `event_id` in the subscriber's first line. JSON renderer to stdout. |
| **D4** | **Idempotency on POST /bet** via client-supplied `Idempotency-Key` header (or implicit unique key on `(event_id, amount, client_id?)`) — accidental double-POST returns the same bet, doesn't create two | Real-world betting endpoints get retried by clients all the time; a reviewer who has run a payment or order system will look for this and be impressed it's there. Demonstrates understanding of at-least-once HTTP delivery. | MEDIUM | Either: (a) `Idempotency-Key` header → unique partial index on `bets(idempotency_key)`; on conflict return the existing bet, or (b) simpler: dedupe at the queue consumer using `(event_id, bet_id)` so the **status update** is idempotent even if the broker redelivers. **Pick (b) for must-have; mention (a) in README as a clear extension** — that itself is a maturity signal. |
| **D5** | **Dead-letter queue for `events.finished` consumer** (RabbitMQ DLX bound to `events.finished.dlq`, max 3 retries via `x-message-ttl` + retry exchange, then park) | A reviewer who has run RabbitMQ in production knows that "the consumer crashes on bad message → infinite redelivery → broker melts" is a real failure mode. A DLQ with bounded retries is the canonical defence. FastStream supports this declaratively, so the cost is ~5 lines of config. | LOW | FastStream `RabbitQueue("events.finished", arguments={"x-dead-letter-exchange": "events.dlx"})`. Park visibly in RabbitMQ Management UI — reviewer can literally see it. |
| **D6** | **Graceful shutdown** — both services trap SIGTERM, finish in-flight HTTP requests, drain the FastStream consumer (stop accepting new messages, finish the current ack cycle), close PG pool and AMQP connection. No "force kill" warnings in `docker compose down` logs. | The reviewer runs `docker compose down` and reads the logs. A clean shutdown ("draining consumer", "closing pool", exit 0) vs. a SIGKILL after 10s is the difference between "this candidate has shipped" and "this candidate has only ever run pytest". FastAPI lifespan + FastStream auto-lifespan does most of this for free; you just need to not break it. | LOW | Mostly free with FastStream's FastAPI integration. Verify with a 5-line note in README: "to demonstrate graceful shutdown, run `docker compose down`, observe drain logs." |
| **D7** | **Typed configuration via `pydantic-settings`** — one `Settings` class per service, `env_prefix="LINE_PROVIDER_"` / `"BET_MAKER_"`, `.env.example` checked in, all secrets/URLs come from env, no `os.getenv` anywhere | A reviewer skimming `config.py` instantly sees the operational surface area of the service. Beats `os.getenv("FOO", "default")` scattered across modules. Also lets `mypy --strict` actually type-check config access. | LOW | `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", env_prefix=...)`. Inject via FastAPI `Depends(get_settings)` with `@lru_cache`. |
| **D8** | **OpenAPI quality**: tags, summaries, descriptions, response models, example payloads — and FastStream's **AsyncAPI docs at `/asyncapi`** for the AMQP contract | A reviewer who opens `/docs` and sees `POST /bet` with a one-line description, a 422 example for invalid amount, and a 201 example with a real UUID gets a clear "this candidate understands HTTP-as-product" signal. AsyncAPI for the queue contract is rarely seen in test tasks — instant differentiator. Free with FastStream's RabbitRouter. | LOW | `@router.post("/bet", response_model=BetRead, status_code=201, summary="Place a bet", responses={422: {...}})`. AsyncAPI `schema_url="/asyncapi"`. |
| **D9** | **Database concurrency-safety on bet status update** — `SELECT ... FOR UPDATE SKIP LOCKED` (or a dedicated unique index + `INSERT ... ON CONFLICT DO NOTHING` for status idempotency) so two consumer replicas / a consumer + reconciler can't double-update a bet | The TZ is one consumer in docker-compose, but a reviewer thinking "what if they scale this?" will look for the lock pattern. **One sentence in README** ("status updates are serialised via `FOR UPDATE` so consumer + reconciler are safe to run concurrently") sells the maturity for free. Combined with D4, makes the integration provably exactly-once on the **bet status** even though delivery is at-least-once. | LOW | One `select(Bet).where(...).with_for_update(skip_locked=True)` in the interactor. Add a unique index `(event_id, bet_id)` on the status-update path. |
| **D10** | **GitHub Actions CI**: lint (`ruff check` + `ruff format --check`), typecheck (`mypy --strict`), tests (`pytest --cov`), all gated on PR. README badge. | The reviewer clicks the badge, sees green, and the conversation is over. Zero-effort proof that the code actually passes the standards you claim it does. | LOW | One `.github/workflows/ci.yml` with `uv sync --frozen --no-dev` for runtime install and `uv sync --frozen` for full dev tools. Cache `~/.cache/uv`. |

**Deliberately not picked** (mentioned so the reviewer of this research doc sees they were considered and rejected):

- **Prometheus metrics endpoint** — high value in production, but adds a dep (`prometheus-client`), and reviewer can't *do* anything with a `/metrics` page in a 15-min review. Mention as "would add in production" in README; do not implement. Skipped to keep dep count honest.
- **OpenTelemetry tracing** — same reason as metrics, only more so. Three new deps for a value the reviewer can't see locally without a Jaeger sidecar. Hard skip.
- **Rate limiting on POST /bet** — would need Redis or in-memory state; both are scope-creep. Skip.
- **API versioning (`/v1/bets`)** — premature for a test task; mention it as an extension in README at most.
- **Custom exception handler with RFC 7807 problem-details** — nice but invisible unless reviewer specifically POSTs invalid input. Default FastAPI 422 with Pydantic detail is already very good. Skip.

### Anti-Features (Explicitly Out of Scope for This Test Task)

Each row gets a written rationale so the reviewer sees this is **deliberate omission, not oversight**. PROJECT.md's Out-of-Scope section is where these get echoed; this table is the research-level justification.

| Feature | Why a Real Betting Product Has It | Why NOT for This Test Task |
|---------|------------------------------------|----------------------------|
| **User accounts / auth (login, JWT, OAuth)** | Every bet must be attributable to a user; KYC; account lockout | TZ never mentions a user model. Adding auth would balloon scope (user table, token issuance, dependency injection of `current_user`, integration tests for unauthenticated cases) and contribute zero signal beyond "candidate knows OAuth," which the reviewer is not testing. **The TZ tests integration-reliability and async patterns, not authn/authz.** |
| **User balance / wallet** | A bet debits balance at placement, credits on WON | TZ explicitly defines `POST /bet` as `(event_id, amount)` — no balance check, no insufficient-funds path. Adding a wallet requires a second table, debit/credit logic, transactional consistency between bet and ledger — a whole subsystem. Reviewer would see scope drift. |
| **KYC / age verification / compliance** | Legal requirement in regulated markets | Not a Python engineering signal. Out of scope. |
| **Multiple bet types** (over/under, parlays, accumulators, draw, both-teams-score) | Core product offering | TZ says only "team-1 wins" — `FINISHED_WIN` / `FINISHED_LOSE`. **The TZ literally restricts this.** Building more would mean ignoring the spec. |
| **Draws / FINISHED_DRAW** | Real sports have draws | **TZ explicitly excludes draws.** Adding a third terminal state would force a meaningless mapping ("what happens to a bet if event drew?") that contradicts the spec. |
| **Live odds updates** (in-play betting, coefficient streaming via WebSocket) | Modern sportsbook feature | Way out of scope. The TZ models events as "set coefficient once, deadline, decide". Adding live odds means WebSockets, optimistic locking on coefficients, broadcast fan-out — a different product entirely. |
| **Payment integration** (deposit / withdraw, card processors, crypto) | Required to monetise | TZ has no money flow. The `amount` in `POST /bet` is a notional `Decimal` — there is no debit and no payout. Adding payments would mean PSP integration, webhooks, idempotent retries on a different domain — completely orthogonal. |
| **Fraud detection / velocity checks / device fingerprinting** | Risk management | Production-only concern. Adds zero engineering signal in a 1-week task. |
| **Admin UI / back-office** | Operators need to grade events, adjust odds, refund | TZ uses the "utility API" on line-provider as the admin surface; that is sufficient for the reviewer to drive scenarios with `curl`. Building a UI = front-end work that the TZ does not ask for. |
| **Multi-language / i18n** | Consumer-facing app needs locales | API-only product per TZ. No copy to translate. |
| **CDN / global geo-distribution / multi-region** | Latency for global users | Single docker-compose stack per TZ. |
| **Sophisticated risk engine** (liability calculation, market suspension, max-bet-per-event) | Core to a sportsbook's P&L | Out of scope. The TZ models a record-keeping system, not a sportsbook. |
| **Notifications** (email/SMS/push on bet result) | UX expectation in real products | TZ exposes results via `GET /bets`. Polling is the implicit interaction model. Pushing would require choosing a transport (SMTP? FCM? webhooks?) that the TZ never specifies. |
| **Outbox pattern in line-provider** | "Industry best practice" for transactional messaging | Outbox requires a DB. **TZ mandates in-memory storage in line-provider.** Outbox is structurally incompatible with the constraint. (Already in PROJECT.md Out-of-Scope.) |
| **Kafka / Pulsar / horizontal sharding** | High-throughput resilience | RabbitMQ + durable queue + manual ack + DLQ covers all TZ reliability requirements at the expected scale of a test task. Using Kafka would signal "I throw heavyweight tools at small problems." (Already in PROJECT.md Out-of-Scope.) |
| **Kubernetes manifests / Helm charts** | Production deployment | TZ asks for `docker compose up`. Adding k8s manifests is a scope flag (and may make the reviewer wonder if you actually understand what's appropriate). (Already in PROJECT.md Out-of-Scope.) |
| **Caching layer (Redis) in front of line-provider's `GET /events`** | Hot-path optimisation | The TZ allows bet-maker to lag — caching in bet-maker's process memory (a TTL'd dict, ~20 lines) is enough. Adding Redis as a third infra container costs a docker service + a client lib for value the reviewer cannot observe in a test. |
| **Frontend / Swagger-customised UI / dashboards** | Real product surface | API-only per TZ. `/docs` (default OpenAPI UI) is enough. |
| **Webhooks out to client systems on bet settlement** | B2B integration feature | Not in TZ. Out of scope. |
| **Soft-delete / bet cancellation / event refund** | Operational features | Not in TZ. The state machine is linear: NEW → FINISHED_*; bets are PENDING → WON/LOST. No reversal. |
| **Analytics / data warehouse / event sourcing** | BI requirement | Out of scope. `GET /bets` provides all the introspection the TZ asks for. |

## Feature Dependencies

```
[POST /bet]
    └──requires──> [bets table + Alembic migration]
                       └──requires──> [PostgreSQL service in compose + asyncpg]
    └──requires──> [Pydantic Decimal validator (>0, 2dp)]

[bet-maker GET /events]
    └──requires──> [httpx.AsyncClient to line-provider]
    └──enhances-with──> [tiny TTL cache] (optional)

[line-provider PATCH state]
    └──triggers──> [FastStream publisher → events.finished]
                       └──consumed-by──> [bet-maker subscriber]
                                              └──requires──> [SELECT ... FOR UPDATE]
                                              └──requires──> [manual ack + DLQ]

[Reconciliation job]
    └──requires──> [httpx client to line-provider GET /events/{id}]
    └──requires──> [tenacity retries]
    └──requires──> [PENDING bet selector + bulk update interactor]
    └──provides-fallback-for──> [RabbitMQ consumer] (defence in depth)

[/health endpoint]
    └──requires──> [PG ping helper]
    └──requires──> [RabbitMQ channel ping helper]
    └──used-by──> [docker-compose healthcheck]
                       └──enables──> [depends_on: condition: service_healthy]

[Structured logging with request_id]
    └──requires──> [structlog + contextvars processor]
    └──requires──> [FastAPI middleware]
    └──extends-to──> [FastStream subscriber binding event_id]

[Idempotent status update]
    └──requires──> [unique index on (event_id, bet_id) in status flow]
    └──complements──> [SELECT FOR UPDATE]
    └──enables──> [safe concurrent consumer + reconciler]
```

### Dependency Notes

- **Reconciliation job ↔ RabbitMQ consumer:** they are deliberately redundant. The reconciler is the defence-in-depth that makes the Core Value (no stuck PENDING) survive message loss. They must both be idempotent w.r.t. bet status — hence D9.
- **`/health` ↔ docker-compose:** the health endpoint is half-useless without the compose-level `healthcheck` wiring it. Build them together or skip both.
- **Structured logging ↔ request-id middleware ↔ FastStream context binding:** these are one feature pretending to be three. Implement together.
- **Idempotency (D4) ↔ FOR UPDATE (D9):** complementary, not alternative. Idempotency protects against duplicate **messages**; FOR UPDATE protects against concurrent **workers** racing on the same row.
- **DLQ (D5) requires graceful shutdown (D6):** during shutdown, you must finish the current message's ack/nack cycle, otherwise an in-flight message is requeued ambiguously and may end up in the DLQ for no reason.

## MVP Definition

### Launch With (v1 — the only release for a test task)

Everything in **Table Stakes** plus all 10 differentiators. The differentiators were filtered specifically so that "table stakes + all of them" is still deliverable in the test-task budget (target: ~5 working days for an experienced Middle).

**Critical path (P1 — fail without these):**
- [ ] All Table Stakes rows above
- [ ] D1 Reconciliation job — directly implements the Core Value
- [ ] D2 Real `/health` endpoints — required for compose healthchecks anyway
- [ ] D3 Structured logging with request_id — every other debugging story depends on it
- [ ] D7 pydantic-settings configuration — required for clean env handling across two services
- [ ] D10 GitHub Actions CI — single biggest "this is real" signal

**Strong-should (P2 — drop only under time pressure):**
- [ ] D4 Idempotent status updates (variant b — at queue consumer)
- [ ] D5 Dead-letter queue with bounded retries
- [ ] D8 OpenAPI/AsyncAPI quality
- [ ] D9 SELECT FOR UPDATE on the status path

**Nice-to-have (P3 — drop first):**
- [ ] D6 Explicit graceful shutdown verification — mostly works for free; only needs explicit attention if it doesn't.

### Add After Validation (v1.x — N/A for test task)

Not applicable — this is a one-shot delivery. Documented in README as "what I would add next" to show roadmap thinking:

- [ ] Idempotency-Key header variant (D4 variant a)
- [ ] Prometheus `/metrics` endpoint with bet/event counters
- [ ] OpenTelemetry tracing across HTTP + AMQP boundary
- [ ] Per-IP rate limiting on POST /bet
- [ ] Outbox pattern *if* line-provider gains a DB (it won't, per TZ)

### Future Consideration (v2+ — N/A for test task)

Not applicable. Listed in the Anti-Features table.

## Feature Prioritization Matrix

For the test-task context, "user value" reads as "reviewer signal value."

| Feature | Reviewer Signal | Implementation Cost | Priority |
|---------|----------------|---------------------|----------|
| All Table Stakes | N/A (binary — pass/fail) | varies | P0 |
| D1 Reconciliation job | HIGH | MEDIUM | P1 |
| D2 Real `/health` | HIGH | LOW | P1 |
| D3 Structured logging + request_id | HIGH | LOW | P1 |
| D7 pydantic-settings | MEDIUM | LOW | P1 |
| D10 GitHub Actions CI | HIGH | LOW | P1 |
| D4 Idempotent status update | HIGH | MEDIUM | P2 |
| D5 DLQ + bounded retries | HIGH | LOW | P2 |
| D8 OpenAPI / AsyncAPI quality | MEDIUM | LOW | P2 |
| D9 SELECT FOR UPDATE | MEDIUM | LOW | P2 |
| D6 Verified graceful shutdown | LOW (free with stack) | LOW | P3 |
| Prometheus `/metrics` | LOW (invisible to reviewer) | MEDIUM | OUT |
| OpenTelemetry tracing | LOW (invisible without sidecar) | HIGH | OUT |
| Custom RFC7807 problem-details | LOW (FastAPI default suffices) | LOW | OUT |
| API versioning | LOW | LOW | OUT |

**Priority key:**
- **P0:** Required by TZ. Non-negotiable.
- **P1:** Differentiator chosen for "do this even under time pressure."
- **P2:** Differentiator chosen for "do this if time allows" — still high value.
- **P3:** Verify, but mostly free with the stack.
- **OUT:** Considered and rejected; mention as "would add in production" in README to signal awareness.

## Competitor Feature Analysis

"Competitors" here = other candidate submissions the reviewer has seen. The framing is **what differentiates a Middle-grade submission from a Junior one**.

| Feature | Typical Junior submission | Typical Middle submission | Our Approach |
|---------|---------------------------|---------------------------|--------------|
| Integration between services | Sync `httpx` call from bet-maker to line-provider on `POST /bet` | RabbitMQ consumer in bet-maker | **Both:** RabbitMQ consumer **+** reconciliation job using `httpx` over `line-provider` API. Defence in depth for the Core Value. |
| Bet status update | One `UPDATE bets SET status=... WHERE event_id=...` | Same + transaction | **Idempotent + locked**: `SELECT … FOR UPDATE SKIP LOCKED`, status state-machine check, single UoW commit. Works under concurrent consumer + reconciler. |
| Error handling | `try/except` returning 500 | FastAPI exception handler returning Pydantic error | Default FastAPI 422 (already excellent) + structured log line with `request_id`. Don't reinvent. |
| Logging | `print()` or stdlib `logging.basicConfig` | stdlib `logging` with JSON formatter | **structlog with contextvars**: every log line correlates HTTP → DB → AMQP by `request_id` and `event_id`. |
| Config | Hardcoded URLs or `os.getenv("PG", "postgres://...")` | `os.getenv` in a `config.py` | **`pydantic-settings`** typed Settings, `.env.example` checked in, single source of truth, type-checked by mypy. |
| Tests | A couple of `TestClient` smoke tests | TestClient tests + maybe a Postgres fixture | **Three layers**: unit (interactors/selectors/helpers, no IO), API integration (`TestClient` + ephemeral PG schema), queue integration (`TestRabbitBroker` in-memory + one real RabbitMQ e2e). pytest-cov in CI. |
| Healthchecks | None, or `return {"ok": true}` | `/health` returns service status | `/health` actually pings PG + RabbitMQ. Wired into docker-compose `healthcheck` so `depends_on: condition: service_healthy` works. |
| Shutdown | `Ctrl+C`, hope for the best | Lifespan hook to close pool | FastAPI lifespan + FastStream lifespan both wired through `RabbitRouter` so SIGTERM drains consumer cleanly. README mentions it. |
| Docs | README with `docker compose up` | README with curl examples | README with curl examples + ASCII architecture diagram + AsyncAPI link + "what I would add next" section + CI badge. |
| Message handling | Auto-ack in consumer | Manual ack on success | Manual ack + nack-to-DLQ after bounded retries + reconciliation as last-resort safety net. |

## Sources

- `/Users/dmitrydankov/Personal/BSW/.planning/PROJECT.md` — TZ requirements, Core Value, Out-of-Scope, Key Decisions
- `/Users/dmitrydankov/Personal/BSW/.planning/research/STACK.md` — confirmed stack: FastStream `RabbitRouter` integration, `TestRabbitBroker`, structlog contextvars, pydantic-settings, tenacity
- TZ (test task specification) as paraphrased in PROJECT.md — endpoints, in-memory storage, status enum, "ставка не зависает в PENDING" reliability requirement
- Internal judgement: prior reviews of Middle Python test submissions — which signals reviewers consistently react to (logging correlation, healthchecks, CI green badge, DLQ presence, reconciliation as defence in depth)

---
*Feature research for: asynchronous Python microservices test task (Middle Python interview)*
*Researched: 2026-05-13*
