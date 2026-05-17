# Phase 5: RabbitMQ integration — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 5-rabbitmq-integration
**Areas discussed:** RMQ topology & owner; Manual-ack ladder & retry budget; Idempotency in settle_bets_for_event; Consumer host & lifespan

---

## RMQ Topology & Owner

### Exchange type / name

| Option | Description | Selected |
|---|---|---|
| topic exchange `bsw.events` | Routing keys `event.finished.win` / `event.finished.lose`; bind через `event.finished.*`. Гибкость под будущие event-типы. | ✓ |
| direct exchange `bsw.events.finished` | Ровно 2 ключа win/lose; проще, но при расширении придётся переименовывать exchange (R5). | |
| fanout `bsw.events.finished` | Никаких ключей. Противоречит ROADMAP-фиксированным routing keys. | |

### Main queue name / type

| Option | Description | Selected |
|---|---|---|
| classic durable `bet_maker.events.finished` | Согласовано с ROADMAP-именем DLQ; single-node docker-compose — достаточно. | ✓ |
| quorum durable `bet_maker.events.finished` | Production-grade replication, для demo overkill. | |
| Другое имя | — | |

### Topology owner

| Option | Description | Selected |
|---|---|---|
| Разделённая владельность | line-provider declare-ит exchange `bsw.events`; bet-maker declare-ит main queue + DLX + DLQ + bindings. | ✓ |
| bet-maker владеет всем | Consumer declare-ит все объекты. Слабее выражает service boundaries. | |
| Вручную вне кода (definitions.json) | Production-стиль, но прячет топологию от ревью. | |

### DLQ binding strategy

| Option | Description | Selected |
|---|---|---|
| Отдельный DLX + DLQ | `bsw.events.dlx` (direct, durable) + `bet_maker.events.finished.dlq`. Two-exchange separation. | ✓ |
| Default exchange + DLQ | `x-dead-letter-exchange=""`. Меньше объектов, но wiring неявный. | |
| Same exchange, другой routing-key | DLQ биндится в `bsw.events`. Смешивает happy и error path. | |

---

## Manual-ack Ladder & Retry Budget

### Where retry budget lives

| Option | Description | Selected |
|---|---|---|
| In-handler tenacity перед reject | 3 attempts с backoff внутри одной доставки; не получилось → reject(requeue=False) → DLQ. | ✓ |
| RabbitMQ-cycling через x-death header | nack(requeue=True) + cycle через DLX; сложнее, требует binding-fanout. | |
| Hybrid: in-handler + max-redelivery cap | Tenacity + cap по `msg.redelivered`. | |

### Concrete retry budget

| Option | Description | Selected |
|---|---|---|
| 5 attempts, exp backoff 0.5–10s | Как в Phase 4 (httpx D-05). | |
| 3 attempts, exp backoff 0.2–2s | Fail-fast; пусть reconciler Phase 6 добирает. | ✓ |
| Другое | — | |

### Poison vs transient classification

| Option | Description | Selected |
|---|---|---|
| Строгая таблица | POISON: ValidationError, DecodeError, schema_version!=1, IntegrityError. TRANSIENT: OperationalError, DBAPIError(connection_invalidated), TimeoutError. | ✓ |
| Минимальная | POISON: только ValidationError. TRANSIENT: всё остальное. | |
| Обратная (whitelist transient) | TRANSIENT: только OperationalError + asyncpg.PostgresConnectionError. | |

### Default policy (unknown / exhausted)

| Option | Description | Selected |
|---|---|---|
| Оба → reject→DLQ | Неизвестные сразу в DLQ; исчерпанные retry → DLQ; reconciler Phase 6 подхватит. | ✓ |
| Unknown → retry, exhausted → DLQ | Неизвестные ретраятся, потом DLQ. | |
| Unknown → nack(requeue=True), exhausted → reject | Риск poison-loop, противоречит R7. | |

---

## Idempotency in settle_bets_for_event

### Observability columns on Bet

| Option | Description | Selected |
|---|---|---|
| Да: settled_at + settled_via | Когда и кто (consumer / reconciler). | ✓ |
| Только settled_at | Без различения источника. | |
| Ничего не добавляем | Status — единственный след. | |

### consumed_events bookkeeping table

| Option | Description | Selected |
|---|---|---|
| Нет — status-filter достаточно | WHERE status='PENDING' даёт идемпотентность; reconciler выводит «видел/не видел» через отсутствие PENDING. | ✓ |
| Да — простая таблица consumed_events | `event_id PK, terminal_state, message_id, consumed_at`. Audit + reconciler fast-path. | |
| Да, только message_id для dedup | `processed_messages(message_id PK, processed_at)`. | |

### 0 PENDING-ставок reaction

| Option | Description | Selected |
|---|---|---|
| info-log + ack | `settle.noop` info; нормальный идемпотентный исход. | ✓ |
| warn-log + ack | Громче; при работающем reconciler будет шумно. | |
| metric counter + ack | Prometheus / STATE.md — для test task излишне. | |

### Interactor signature

| Option | Description | Selected |
|---|---|---|
| `-> int` (число) | Компактно, минимум зависимостей. | |
| `-> SettleResult` DTO | Pydantic DTO с event_id, terminal_state, settled_count, settled_bet_ids, settled_via, settled_at. | ✓ |
| `-> None` | Информация только в логах. | |

### settled_at semantics & source

| Option | Description | Selected |
|---|---|---|
| Время обработки, PG `func.now()` | В той же транзакции; конвенция Phase 3. | ✓ |
| Время обработки, Python `datetime.now(UTC)` | Тестируется freezegun; но рассинхрон с created_at/updated_at. | |
| Время события, `payload.occurred_at` | Reconciler не имеет этого времени — рассинхрон. | |

### Transaction isolation level

| Option | Description | Selected |
|---|---|---|
| READ COMMITTED (PG default) | FOR UPDATE SKIP LOCKED + status-filter достаточны. | ✓ |
| REPEATABLE READ | Без выигрыша; повышает риск serialization_failure. | |
| SERIALIZABLE | Overkill для нашего сценария. | |

---

## Consumer Host & Lifespan

### Where the consumer lives

| Option | Description | Selected |
|---|---|---|
| Тот же bet-maker (HTTP + subscriber в одном lifespan) | FastAPI + RabbitRouter в одном процессе; один docker-сервис, один /health. | ✓ |
| Отдельный `bet-maker-worker` | bet-maker (HTTP) + bet-maker-worker (consumer + reconciler Phase 6). | |
| FastStream standalone (без FastAPI в worker) | Минимальный footprint; теряет /health конвенцию. | |

### /health: how to check RMQ + subscriber_count

| Option | Description | Selected |
|---|---|---|
| `broker.ping()` + `len(broker.subscribers)` | FastStream API: `await router.broker.ping(timeout=1.0)` + `len(router.broker.subscribers)`. | ✓ |
| `broker.ping()` только | Игнорирует SC#5 явное требование. | |
| Низкоуровневый aio-pika ping | Противоречит CLAUDE.md «DO NOT declare aio-pika directly». | |

### Lifespan startup order

| Option | Description | Selected |
|---|---|---|
| PG → httpx → broker.connect → yield | Strict sequence (F3). Shutdown обратный. | ✓ |
| PG и httpx параллельно, потом broker | asyncio.gather; ~200ms быстрее, но cancellation cascade. | |
| FastStream auto-lifespan (без кастомного) | Теряется контроль PG/httpx startup. | |

### /health behavior during startup window

| Option | Description | Selected |
|---|---|---|
| 503 до окончания startup | Lifespan держит порт закрытым; никаких промежуточных состояний. | ✓ |
| 200 сразу, ping в background | Производственный k8s-pattern, но без readiness/liveness split — false-green окно. | |
| 503 с explicit «starting» флагом | Требует мутабельный флаг в app.state. | |

---

## Claude's Discretion

Captured в CONTEXT.md §«Claude's Discretion»:
- Точный API `prefetch_count` (broker-level vs subscriber-level QoS) — researcher уточнит по FastStream docs.
- Точный путь `RabbitQueue.arguments` для DLQ-headers vs FastStream `dlq` shortcut — researcher выберет.
- Размещение `messaging/routing.py` (новый под-пакет vs внутри `entrypoints/`) — planner решит.
- Точная форма tenacity-обёртки на `settle_bets_for_event` (декоратор vs контекст-менеджер) — переиспользуем `make_retry_decorator` factory из Phase 4 D-05.

## Deferred Ideas

Captured в CONTEXT.md §«Deferred Ideas»:
- Reconciliation job → Phase 6 (с грунтом в виде SettleResult.settled_via Literal).
- DLQ replay / inspection endpoints → отдельная фаза, не Phase 5.
- Publisher confirms → researcher оценит.
- Quorum queues / cluster → когда поднимем HA.
- Schema migration v2 → пока нет триггера.
- Outbox-pattern для line-provider → явный out of scope (PROJECT.md).
- Prometheus / metrics → future hardening.
- k8s readiness/liveness split → docker-compose не требует.
