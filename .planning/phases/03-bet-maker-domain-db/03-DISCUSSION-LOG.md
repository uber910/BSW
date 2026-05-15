# Phase 3: bet-maker domain (DB) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 03-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 03-bet-maker-domain-db
**Areas discussed:** Event validation in P3 + coefficient source, bets schema specifics, Test DB strategy (QA-07), /health PG ping + lifespan startup

---

## Area 1: Event validation в P3 + coefficient source

### First framing (rejected — incorrect assumption)

Первоначальный вопрос: «Как P3 получает информацию о событии (coefficient + deadline + state) при POST /bet до P4?»

Пользователь ответил: «из базы, это один и тот же сервис же» — реплика указала на потенциальное непонимание архитектуры. Re-framed: line-provider и bet-maker — два отдельных сервиса; line-provider держит события in-memory (явное требование ТЗ), bet-maker имеет только PG со ставками; общей БД нет.

| Option | Description | Selected |
|--------|-------------|----------|
| Protocol EventLookup + StubEventLookup | facades/event_lookup.py: EventLookup(Protocol) c StubEventLookup в P3, P4 подменит на HttpEventLookup | ✓ |
| Временно принимать coefficient в body | POST /bet body = {event_id, amount, coefficient} в P3, P4 убирает (breaking change) | |
| Bring P4 forward — httpx-клиент в P3 | Сразу real line_provider_client; ломает roadmap parallelization | |
| В P3 вообще не валидировать event | Любой event_id, coefficient placeholder; нарушает BM-06 | |

**User's choice:** Protocol EventLookup + StubEventLookup
**Notes:** Пользователь дополнительно запросил verification против оригинала ТЗ перед фиксацией, что привело к re-discovery критической ошибки в REQUIREMENTS.md.

### TZ verification (critical re-frame)

После чтения `./Тестовое задание Middle Python developer.pdf` (страницы 1–4) обнаружено: ТЗ НЕ требует coefficient в записи ставки. POST /bet body буквально `{идентификатор события, сумма ставки}`; GET /bets буквально «id + status». Coefficient — атрибут события, живёт в line-provider. Также обнаружено: `GET /bet/{bet_id}` есть на диаграмме ТЗ, отсутствует в текстовом описании.

### Sub-question 1.1: Coefficient snapshot в записи ставки

| Option | Description | Selected |
|--------|-------------|----------|
| Убрать колонку (TZ-minimal) | Bet: id, event_id, amount, status, created_at. Никакого event lookup для coefficient | ✓ |
| Оставить как maturity-signal | coefficient Numeric(6,2), StubEventLookup также возвращает coefficient | |
| Оставить колонку, филлить в P5 | nullable coefficient, заполняется консьюмером из EventFinishedMessage | |

**User's choice:** Убрать колонку (TZ-minimal)
**Notes:** REQUIREMENTS.md BM-01 / BM-05 синхронизируется в первом sync-task P3 — по аналогии с P2 Plan 02-01 (sync LP-02 str→UUID4).

### Sub-question 1.2: Event validation при POST /bet

| Option | Description | Selected |
|--------|-------------|----------|
| Нет валидации event (TZ-minimal) | Любой event_id принимается; ставка на несуществующее событие остаётся PENDING навсегда | |
| Добавить валидацию (maturity-signal) | EventLookup Protocol + StubEventLookup; P4 подменит на HttpEventLookup; 422 на event-not-found/expired/finished | ✓ |
| Только amount-валидация в P3 | amount > 0, 2dp; event-валидация переносится в P4 | |

**User's choice:** Добавить валидацию (maturity-signal)
**Notes:** Закрывает Core Value defense-in-depth: даже без P4/P5 ставки на несуществующие события блокируются.

### Sub-question 1.3: Event_id type

| Option | Description | Selected |
|--------|-------------|----------|
| Оставить UUID4 (как P2) | P2 D-05 уже зафиксировал; EventFinishedMessage.event_id: UUID; client-generated | ✓ |
| Перейти на str (TZ-literal) | ТЗ допускает «строка или число»; требует rollback P2 D-05 | |

**User's choice:** Оставить UUID4 (как P2)
**Notes:** Backwards compatibility с P2 schemas/messages.py + строжайший engineering signal.

### Sub-question 1.4: GET /bet/{bet_id} в P3

| Option | Description | Selected |
|--------|-------------|----------|
| Да, реализовать в P3 | Эндпоинт есть на диаграмме ТЗ; новое требование BM-13 в REQUIREMENTS.md | ✓ |
| Не реализовывать | Текст ТЗ не упоминает; конфликт диаграмма↔текст решаем в пользу текста | |

**User's choice:** Да, реализовать в P3
**Notes:** Дёшево (один selector get_bet_by_id), закрывает диаграмму ТЗ полностью.

---

## Area 2: bets schema specifics

### Sub-question 2.1: Status тип

| Option | Description | Selected |
|--------|-------------|----------|
| PG ENUM type | CREATE TYPE bet_status AS ENUM (...); native PG, prod-signal | ✓ |
| VARCHAR + CHECK constraint | Гибче в миграциях, но ниже prod-signal | |

**User's choice:** PG ENUM type (рекомендую)
**Notes:** Статусы фиксированы (PENDING/WON/LOST); расширение не предвидится.

### Sub-question 2.2: Indexes в P3

| Option | Description | Selected |
|--------|-------------|----------|
| (event_id, status) в P3 сразу | Закладывается под P5 settle-путь; одна миграция | |
| (event_id, status) + (created_at DESC) | Полный prod-ready, но overengineering для test-task | |
| Только PK | Минимум в P3; (event_id, status) в P5 отдельной миграцией | ✓ |

**User's choice:** Только PK
**Notes:** P5 settle-логика всё равно требует новой миграции — индекс добавится там.

### Sub-question 2.3: updated_at

| Option | Description | Selected |
|--------|-------------|----------|
| PG trigger ON UPDATE | Триггер DDL-уровня | |
| ORM onupdate=func.now() | SA 2.0 best-practice (server_default + onupdate) | ✓ |
| Убрать updated_at вообще | TZ-minimal | |

**User's choice:** «по бест практикам SQLAlchemy» → ORM-managed `server_default=func.now()` + `onupdate=func.now()`
**Notes:** Канонический SA 2.0 pattern. В нашей архитектуре все UPDATE идут через UoW → onupdate срабатывает корректно.

### Sub-question 2.4: Idempotency column

| Option | Description | Selected |
|--------|-------------|----------|
| Идемпотентность через status state-machine | FOR UPDATE SKIP LOCKED + WHERE status='PENDING'; без доп. колонки (PITFALLS R3) | ✓ |
| Добавить idempotency_key в P3 профилактически | nullable string(64) unique; P5 пишет message_id | |

**User's choice:** Идемпотентность через status state-machine (без доп. колонки)
**Notes:** R3 mitigated тем же механизмом; FEATURES.md D4 (header-based idempotency) — extension в README P7, не в коде.

---

## Area 3: Test DB strategy (QA-07)

### Sub-question 3.1: Container scope

| Option | Description | Selected |
|--------|-------------|----------|
| session-scoped | Один контейнер на pytest-run; standard prod-style | ✓ |
| function-scoped | Новый контейнер на каждый тест; медленно | |
| module-scoped | Один на test-module; компромисс | |

**User's choice:** session-scoped (рекомендую)

### Sub-question 3.2: Schema bootstrap

| Option | Description | Selected |
|--------|-------------|----------|
| alembic upgrade head | Реальный миграционный путь; закрывает ROADMAP success criterion #5 | ✓ |
| Base.metadata.create_all | Быстрее, но пропускает migration bugs | |
| Hybrid (alembic для integration, create_all для unit) | Усложняет conftest | |

**User's choice:** alembic upgrade head (рекомендую)

### Sub-question 3.3: Per-test isolation

| Option | Description | Selected |
|--------|-------------|----------|
| Nested transaction + rollback (savepoint) | Быстро, но ломает FOR UPDATE testing (P5 hazard) | |
| TRUNCATE bets RESTART IDENTITY CASCADE | Реальные COMMIT-транзакции; FOR UPDATE работает как в prod | ✓ |
| DROP/CREATE schema per-test | Overkill | |

**User's choice:** TRUNCATE после каждого теста (рекомендую)
**Notes:** Критично для QA-07 «ловить FOR UPDATE баги» — savepoint-isolation сломал бы этот flow в P5.

### Sub-question 3.4: CI strategy

| Option | Description | Selected |
|--------|-------------|----------|
| testcontainers (single code path) | Один путь для local + CI; testcontainers[postgresql] dev-dep | ✓ |
| GHA services: postgres | Два пути; риск local works ≠ CI fails | |

**User's choice:** testcontainers (тот же код, рекомендую)

---

## Area 4: /health PG ping + lifespan startup

### Sub-question 4.1: PG ping caching

| Option | Description | Selected |
|--------|-------------|----------|
| Каждый раз SELECT 1 | Живые 503; ~5мс overhead | ✓ |
| Кэш 1-2s | Overkill для test-task; docker-compose interval 5s | |

**User's choice:** Каждый раз SELECT 1 (рекомендую)

### Sub-question 4.2: Lifespan startup retry

| Option | Description | Selected |
|--------|-------------|----------|
| tenacity retry при startup | RuntimeError при fail; понятный лог | ✓ |
| Только depends_on healthy + pool_pre_ping | Не закрывает D2 для local-run | |
| И то и другое | belt-and-braces | |

**User's choice:** tenacity retry при startup (рекомендую)
**Notes:** pool_pre_ping=True всё равно остаётся (PITFALLS A3 не отменён); фактически выбран gradient к «belt-and-braces».

### Sub-question 4.3: /health response format

| Option | Description | Selected |
|--------|-------------|----------|
| 503 + JSON с деталями | {"status":"ok","checks":{"postgres":"ok"}}; расширяемо под P5 | ✓ |
| Flat {"status":"ok|down"} | Проще, но P5 всё равно расширит | |
| 503 без тела | Не даёт ревьюверу понять что сломано | |

**User's choice:** 503 + JSON с деталями (рекомендую)
**Notes:** P1 контракт `{"status":"ok"}` остаётся (backwards compatible — поле сохранилось); P1 smoke-тест test_health_returns_status_ok сломается на строгом `body == {"status":"ok"}` и должен быть обновлён в первом implementing-task P3.

---

## Claude's Discretion

Передано планировщику:
- Точная сигнатура fixtures (testcontainers + Alembic + pytest-asyncio).
- Subprocess vs programmatic Alembic запуск в тестах.
- Стиль `(str, Enum)` vs `StrEnum` для BetStatus (зафиксирован Python 3.10 → `(str, Enum)`).
- Точная форма `EventNotBettable` (одно сообщение vs дерево исключений).
- Локация `BetStatus` enum (`schemas/bets.py` или `models/enums.py`).
- Импорт `Mapped[uuid.UUID]` vs `Mapped[UUID]`.

## Deferred Ideas

- Idempotency-Key header — extension в README P7.
- Rate limiting на POST /bet — out of scope.
- GET /bets pagination — out of scope для P3.
- (event_id, status) индекс — P5.
- (created_at DESC) индекс — P7 опционально.
- EventState parity tests между сервисами — P5 e2e.
- OpenAPI tags/examples — P7 DOC-02.
