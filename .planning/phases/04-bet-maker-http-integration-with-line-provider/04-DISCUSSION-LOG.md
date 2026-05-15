# Phase 4: bet-maker HTTP integration with line-provider - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `04-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 04-bet-maker-http-integration-with-line-provider
**Areas discussed:** TTL cache scope, Retry policy, POST /bet on LP unavailability, Client architecture (incl. response schema)

---

## Selection of areas to discuss

Carrying forward (not re-asked, locked by P2/P3 CONTEXT + ROADMAP + CLAUDE.md):
- Singleton `httpx.AsyncClient` в lifespan с `Timeout(5.0)`, закрывается на shutdown
- Tenacity exponential backoff retries; 404/422 propagate как permanent
- `HttpEventLookup` имплементирует `EventLookup` Protocol (P3 D-11/D-13) — подмена одной строкой в lifespan
- `BetMakerSettings.line_provider_base_url` уже в P1
- Integration-тест: два apps через `ASGITransport`
- `EventState` enum уже задублирован в bet-maker (P3 D-12)

User выбрал обсуждать все 4 области: Scope и TTL-кэш, Retry-политика, POST /bet при недоступности LP, Архитектура клиента + место кэша.

---

## Area 1: TTL cache scope

### Question 1.1: Что покрываем TTL-кэшем в P4?

User задал контр-вопрос: "а кэш вообще нужен по ТЗ?" — критический spot-check.

Ответ Claude после проверки ТЗ: кэш не обязателен. ТЗ только разрешает lag и подсвечивает производительность. ROADMAP/REQUIREMENTS BM-04 — наша инженерная трактовка.

### Question 1.2 (re-asked после уточнения): Как решаем про кэш?

| Option | Description | Selected |
|--------|-------------|----------|
| Кэш только на GET /events, TTL=1s из settings | Tiny tuple-cache под asyncio.Lock; POST /bet ходит в LP напрямую. Engineering signal + Core Value не нарушается. | |
| Кэш на GET /events и GET /event/{id} | Большая разгрузка LP под нагрузкой POST /bet, но риск принять ставку на завершённое событие в окне TTL. | |
| Нет кэша, выпиливаем из ROADMAP | P4 = singleton client + tenacity + прокси; кэш как extension в README P7. | ✓ |

**User's choice:** "Нет кэша, выпиливаем из ROADMAP"

**Notes:** Первый task P4 (по паттерну Plan 02-01 / Plan 03-01) синхронизирует REQUIREMENTS.md BM-04 (убрать упоминание TTL cache) и ROADMAP P4 SC #1 (заменить "cached via TTL dict" → "with acceptable lag, свежий результат каждого запроса"). README P7 упомянёт кэш как next-step extension. Это поведенческое правило для будущих фаз: проверять ROADMAP-decisions против буквы ТЗ перед фиксированием.

---

## Area 2: Retry policy

### Question 2.1: На какие ошибки tenacity делает retry?

| Option | Description | Selected |
|--------|-------------|----------|
| Network + 5xx | httpx.TransportError + 5xx через manual raise_for_status. 4xx (404/422/400) propagate без retry. | ✓ |
| Только network (timeout/connect) | httpx.TransportError. 5xx пробрасываем как "осмысленную ошибку". | |
| Network + 5xx + 429 | + Retry-After на 429. Избыточно — LP не rate-limited. | |

**User's choice:** "Network + 5xx (рекомендую)"

**Notes:** —

### Question 2.2: Сколько попыток и какой backoff?

| Option | Description | Selected |
|--------|-------------|----------|
| 3 attempts, exp(0.5–2s), ~3s | Для пользовательского HTTP-роута — низкая tail-latency. | |
| 5 attempts, exp(1–10s), ~25s | CLAUDE.md цитирует stop_after_attempt(5), но для POST /bet слишком долго. | |
| Раздельные политики: 3 для HTTP-роутов, 5 для reconciler (P6) | Две retry-обёртки под разные контексты. | ✓ |

**User's choice:** "Разделить: 3 для HTTP-роутов, 5 для reconciler (P6)"

**Notes:** Фактическая реализация reconciler-настроек уходит в P6 BM-12. В P4 фиксируется factory-обёртка `make_retry_decorator(attempts, max_backoff)`, переиспользуемая P6. Параметры через `BetMakerSettings.line_provider_http_attempts` + `..._backoff_max_s`.

---

## Area 3: POST /bet on LP unavailability

### Question 3.1: POST /bet, HttpEventLookup исчерпал 3 attempts на 5xx/timeout. Что отдаём клиенту?

| Option | Description | Selected |
|--------|-------------|----------|
| 503 'line-provider unreachable' | HttpEventLookup raises LineProviderUnavailable; router отдаёт 503. Ставка НЕ сохраняется. | ✓ |
| 422 'event not bettable: validation unavailable' | Переиспользует EventNotBettable путь, но смешивает client-error и upstream-down. | |
| 504 Gateway Timeout | Семантичный для proxy-кейсов, но bet-maker не RFC-reverse-proxy. | |
| 200 PENDING (всё равно сохранить) + reconciler подберёт | Нарушает Core Value: если event не существует (404), ставка зависнет в PENDING навсегда. Отвергнуто. | |

**User's choice:** "503 'line-provider unreachable' (рекомендую)"

**Notes:** Новый exception `LineProviderUnavailable` живёт в `facades/line_provider_client.py`. Router POST /bet ловит до EventNotBettable (порядок важен: первый = LineProviderUnavailable → 503, второй = EventNotBettable → 422). 404 от LP → `get_event` возвращает None → interactor мапит в EventNotBettable("event not found") → 422; этот path не меняется.

---

## Area 4: Client architecture (incl. response schema)

### Question 4.1: Как структурируем клиент к line-provider?

| Option | Description | Selected |
|--------|-------------|----------|
| Один facade LineProviderClient с двумя методами | get_events + get_event; retry внутри методов; DRY. | |
| Два независимых facade | facades/http_event_lookup.py + selectors/list_active_events.py. Каждый путь explicit, retry-логика дублируется но локальна. | ✓ |
| Tenacity как Depends-обёртка поверх роутов | Нарушает слоистую архитектуру + теряет переиспользование в P6 reconciler. Отвергнуто. | |

**User's choice:** "Два независимых facade"

**Notes:** Общий `LineProviderUnavailable` + `make_retry_decorator(attempts, max_backoff)` factory в `facades/line_provider_client.py`. Singleton `httpx.AsyncClient` в `app.state.line_provider_http_client`, инжектится через `get_line_provider_http_client` provider в обе обёртки.

### Question 4.2: Что возвращает bet-maker GET /events?

| Option | Description | Selected |
|--------|-------------|----------|
| list[EventRead] полный | event_id + coefficient + deadline + state; дублируется в bet_maker/schemas/events.py (P3 D-12 pattern). | ✓ |
| list[EventListItem] subset | Без state (всегда NEW), минималистично. | |
| Re-прокси raw JSON | Без Pydantic-валидации; ломает type hints и OpenAPI; не согласуется с extra="forbid". Отвергнуто. | |

**User's choice:** "list[EventRead] полный (рекомендую)"

**Notes:** EventRead на стороне bet-maker — отдельный класс (intentional service-boundary duplication, симметрично с EventState из P3 D-12). Клиент видит coefficient для понимания payout-потенциала — типичный betting-API контракт.

---

## Claude's Discretion

- Точная структура `before_sleep` hook'а tenacity + structlog binding.
- Точное расположение `LineProviderUnavailable`: `facades/line_provider_client.py` (рекомендация Claude — вместе с factory).
- Точная сигнатура `make_retry_decorator` (декоратор vs context-manager vs AsyncRetrying — любой паттерн tenacity 9.x).
- Структура integration-теста: nested LifespanManager vs прямой lifespan_context.
- Реальный LP vs respx для negative-cases в `test_events_routes.py` — рекомендация: реальный для happy-path и 1-2 negative; respx для 5xx scenarios.
- Стиль определения LineProviderUnavailable (один exception с reason: str vs иерархия).

## Deferred Ideas

- TTL cache на GET /events — README P7 как extension
- GET /events?ids=1,2,3 batch — P6/perf extension
- Idempotency-Key header на POST /bet — README P7
- Circuit breaker — out of scope, README P7 "Reliability roadmap"
- 429 retry с Retry-After — out of scope (LP не rate-limited)
- OpenAPI tags/summaries/examples для GET /events — P7 DOC-02
- /health pinging line-provider — out of scope (LP-down не должен ронять bet-maker /health)
- EventState parity test между сервисами — P5 e2e
- respx vs pytest-httpx — D-15 фиксирует respx
