# Phase 2: line-provider domain - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 02-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-14
**Phase:** 2-line-provider-domain
**Areas discussed:** HTTP-API контракт, тип event_id, семантика обновления (PUT), publish stub для P5

---

## HTTP-API контракт

### Round 1: общая форма

| Option | Description | Selected |
|--------|-------------|----------|
| PUT /event upsert + PATCH /event/{id}/state | Один upsert-эндпоинт + отдельный PATCH для state | |
| POST /event + PUT /event/{id} + PATCH state | Разделение create / update / state-change | ✓ (round 1) |
| PUT /event upsert (всё включая state) | Единый PUT, state меняется через тот же endpoint | |
| POST /event + PATCH /event/{id} | Create + partial-update PATCH для всего | |

### Round 2: форма PATCH state

| Option | Description | Selected |
|--------|-------------|----------|
| {state} в теле, 200 + EventRead | JSON-тело со state, ответ — обновлённое событие | |
| {state, reason?} + 204 No Content | Тело + опциональный reason, без ответа | |
| {state} в query или path | PATCH без тела | |

**User's response:** «да пускай будут только put и post, patch тут же не нужен» — пересмотр round 1: убрать PATCH полностью.

### Round 3: финальная форма

| Option | Description | Selected |
|--------|-------------|----------|
| POST = create (409 на дубль), PUT = update only (404 если нет) | Чёткое разделение, REST-canonical | ✓ |
| PUT = upsert (создаёт или обновляет) | Идемпотентный PUT, POST для server-generated id | |

**Final shape:**
- `POST /event` — create only, 201 + EventRead, 409 на дубль.
- `PUT /event/{id}` — update only, 200 + EventRead, 404 если нет, state-change через тот же эндпоинт.
- `GET /event/{id}` — 200 + EventRead, 404 если нет.
- `GET /events` — список активных.
- `GET /health` — стаб 200.

---

## Тип event_id

### Round 1

| Option | Description | Selected |
|--------|-------------|----------|
| UUIDv4, генерирует клиент | Pydantic UUID4, idempotent | |
| Свободная строка, генерирует клиент | LP-02 буквально, regex validation | |
| int, генерирует клиент | Совпадает с ARCHITECTURE messages.py, конфликтует с LP-02 | |
| UUIDv4, генерирует сервер | POST возвращает id; не idempotent | |

**User's response:** «а у нас же есть второй сервис который их стримит, так? он же их и отдает, валидация на пайдантике норм, но надо еще и в базе чекать» — потребовалось уточнение архитектуры.

**Claude's clarification:** line-provider — источник событий, никто их в него не стримит. Клиент line-provider'а (reviewer / оператор / админ-скрипт) создаёт события через POST. bet-maker только читает через GET (P4) и AMQP-сообщения (P5).

### Round 2

| Option | Description | Selected |
|--------|-------------|----------|
| UUIDv4, клиент присылает в POST | Pydantic UUID4, idempotent (повтор → 409), AMQP/PG также UUID | ✓ |
| UUIDv4, сервер генерирует | POST 201 + id в ответе, не idempotent | |
| Свободная строка с регексом | Читаемые id (`match-42`), PG VARCHAR(64) | |

**Final:** `event_id: UUID4` client-generated. AMQP `EventFinishedMessage.event_id: UUID`, bet-maker `bets.event_id: UUID` в P3. REQUIREMENTS.md LP-02 нуждается в синхронизации (str → UUID4) — первый task плана.

---

## Семантика обновления (PUT)

### Round 1: какие поля мутабельны

| Option | Description | Selected |
|--------|-------------|----------|
| Все поля кроме event_id (coefficient, deadline, state) | Полный replace | ✓ |
| Только state, coefficient/deadline immutable | Самый безопасный, но PUT с full body избыточен | |
| coefficient/deadline только пока state == NEW | После финиша событие фризится | |

### Round 2: deadline в прошлом

| Option | Description | Selected |
|--------|-------------|----------|
| Да — deadline в прошлом возможен на PUT | Только POST требует deadline > now | ✓ |
| Нет — deadline > now всегда | На PUT тоже требуется | |
| Нет, но только если state остаётся NEW | Условный валидатор | |

**Final:** PUT мутирует coefficient/deadline/state. На PUT любой deadline; на POST deadline > now обязательно. State-machine разрешает только NEW → FINISHED_*; реверс → 422. No-op (state == current) — успех, но без публикации в P5.

---

## Publish stub для P5

| Option | Description | Selected |
|--------|-------------|----------|
| EventBus facade с NoopEventBus сейчас | Интерфейс готов, P5 подменяет реализацию через app.state | ✓ |
| TODO-комментарий, без facade сейчас | YAGNI; P5 добавляет всё одним коммитом | |
| Ничего не пишем про P5 | P5 сам разберётся | |

**Final:** `facades/event_bus.py` с `EventBus` protocol + `NoopEventBus`. Interactor `set_event_state` вызывает `await event_bus.publish(...)` ПОСЛЕ store commit (Anti-Pattern 2 mitigated). `schemas/messages.py` с финальным `EventFinishedMessage` создаётся в P2 (P5 импортирует тот же модуль).

---

## Claude's Discretion

Перечислены в CONTEXT.md `### Claude's Discretion`:
- Pydantic-валидаторы (`@field_validator` vs `condecimal` vs `Annotated[..., AfterValidator]`)
- Конкретный тип `Event` (Pydantic vs `dataclass(frozen=True)`)
- Сигнатура методов `InMemoryEventStore` (replace/update/upsert)
- Структура `state_machine.py` (set / dict / pattern match)
- 200 vs 201 на PUT (выбран 200)
- Location `EventState` enum (один импортируется обеими schemas)

## Deferred Ideas

Перечислены в CONTEXT.md `<deferred>`:
- Реальная AMQP-публикация (P5, LP-06)
- Deep-pings `/health` (P5, LP-07)
- AsyncAPI docs (P7, DOC-04)
- OpenAPI tags/summaries (P7, DOC-01..04)
- Pagination `GET /events` (вне ТЗ)
- Idempotency-Key header (v2, REL/API-01)
- Per-event locks (преждевременная оптимизация)
- Sequence event_id (требует БД)
