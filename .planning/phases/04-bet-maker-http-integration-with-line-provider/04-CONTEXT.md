# Phase 4: bet-maker HTTP integration with line-provider - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 превращает `bet-maker` в реального HTTP-консьюмера `line-provider`. Делается ровно три вещи: (1) поднимается singleton `httpx.AsyncClient` в lifespan, (2) добавляется новый эндпоинт `GET /events` на bet-maker, проксирующий список активных событий из line-provider с tenacity-retry на транзиентные сбои, (3) `StubEventLookup` подменяется на `HttpEventLookup` (реализация того же `EventLookup` Protocol из P3 D-11) — теперь POST /bet валидирует событие через реальный HTTP-вызов в line-provider, а не через in-process dict.

**В скоупе:**
- Sync-task: убрать TTL cache из `REQUIREMENTS.md` BM-04 и `ROADMAP.md` Phase 4 success criterion #1 (см. D-01). Это первый task фазы — по паттерну Phase 2 Plan 02-01 и Phase 3 Plan 03-01.
- `facades/line_provider_client.py` — общий модуль с `LineProviderUnavailable` exception, фабрика singleton `httpx.AsyncClient` (timeout=5s, base_url из settings) для lifespan, общий `_retry_decorator(attempts, max_backoff)` для tenacity (переиспользуется reconciler'ом в P6).
- `facades/http_event_lookup.py` — `HttpEventLookup(EventLookup Protocol)`: метод `get_event(event_id)` бьёт `GET /event/{event_id}` через httpx, с retry-обёрткой. 200 → `EventSnapshot`, 404 → `None`, 5xx/timeout (после retry) → `raise LineProviderUnavailable`.
- `bet_maker/schemas/events.py` — добавить `EventRead` (`event_id: UUID, coefficient: Decimal, deadline: datetime, state: EventState`); `EventState` уже есть с P3 D-12.
- `selectors/list_active_events.py` — `async def list_active_events(http_client) -> list[EventRead]`: бьёт `GET /events` line-provider с retry, парсит JSON через `EventRead.model_validate`. 5xx/timeout (после retry) → `raise LineProviderUnavailable`.
- `entrypoints/api/events.py` (новый) — `GET /events` → вызывает selector → 200 + `list[EventRead]`; на `LineProviderUnavailable` → 503 `{"detail":"line-provider unreachable"}`.
- `entrypoints/api/bets.py` — расширить обработчик `POST /bet`: ловить `LineProviderUnavailable` → 503 `{"detail":"event validation unavailable: line-provider unreachable"}`. Существующий `EventNotBettable → 422` не трогаем.
- `entrypoints/lifespan.py` — расширить: создать singleton `httpx.AsyncClient(base_url=str(settings.line_provider_base_url), timeout=httpx.Timeout(5.0))`, пинить в `app.state.line_provider_http_client`, заменить `app.state.event_lookup = StubEventLookup()` на `HttpEventLookup(http_client=...)`. В `finally` — `await http_client.aclose()` ПЕРЕД `await engine.dispose()`.
- `facades/deps.py` — добавить `get_line_provider_http_client(request)` provider и `LineProviderHttpClientDep` alias. Provider для `EventLookup` уже есть — структура (`get_event_lookup` → `app.state.event_lookup`) не меняется, благодаря Protocol-симметрии (P3 D-13).
- Unit-тесты `HttpEventLookup` через `respx` (mock httpx transport): 200/404/5xx/timeout/retry-eventually-fails-then-succeeds сценарии. Новая dev-deps: `respx>=0.22`.
- Unit-тесты `list_active_events` через `respx`: пустой список, несколько событий, 5xx-retry-eventually-succeeds, 5xx-exhausts-raises.
- Integration-тест `test_events_routes.py` (новый): два FastAPI app в одном процессе через `httpx.AsyncClient(transport=ASGITransport(app=line_provider_app))`. bet-maker'у инжектируется этот transport-mounted client как `app.state.line_provider_http_client` (override `app.dependency_overrides[get_line_provider_http_client]`). Сценарии: создать event в LP → GET /events bet-maker'а возвращает его → закончить event (PATCH/PUT в LP) → GET /events возвращает пустой; POST /bet после реальной валидации через LP.
- Расширить `test_bet_routes.py` POST /bet 503 path: подсунуть фейковый `EventLookup` который raises `LineProviderUnavailable` → router возвращает 503.
- Pyproject: добавить `respx` в dev-deps (это единственная новая зависимость P4 — `httpx`, `tenacity` уже pinned в P1).

**Не в скоупе:**
- TTL cache на `GET /events` — НЕ делаем (D-01). README P7 (DOC-02) упомянет как "next-step extension".
- Реальная замена `StubEventLookup` повсюду — `StubEventLookup` остаётся в `facades/event_lookup.py` и используется в unit-тестах interactor'а `place_bet` (P3 D-11 + D-23 truncate-fixture pattern). В production lifespan — только `HttpEventLookup`.
- Reconciler retry-политика (5 attempts) — фиксируем намерение D-04, реализация в P6 BM-12.
- RabbitMQ — P5 (LP-06, BM-09..BM-11).
- `GET /events?ids=1,2,3` batch для reconciler'а — P6 perf-extension, не сейчас.
- Single-flight / anti-thundering-herd — не нужен без кэша.
- 429 retry / circuit breaker — LP не rate-limited (REQUIREMENTS v2 API-03 deferred); добавление таких retry-классов рисует некорректную картину.

</domain>

<decisions>
## Implementation Decisions

### Sync с REQUIREMENTS.md и ROADMAP.md
- **D-01:** **TTL cache на `GET /events` не делаем в P4.** Обоснование: ТЗ кэш не требует — ТЗ только разрешает "небольшое отставание в свежести" и подсвечивает важность производительности. ROADMAP/REQUIREMENTS BM-04 наша инженерная трактовка, для test-task scope (один docker-compose) кэш — premature optimization без видимого reviewer-checklist benefit'а без бенчмарка. Первый task P4 (по паттерну Plan 02-01 / Plan 03-01) синхронизирует:
  - `REQUIREMENTS.md` BM-04: убрать "+ tiny TTL cache" / "TTL cache"; оставить только "проксирует список активных событий из line-provider через httpx с retry (tenacity)".
  - `ROADMAP.md` Phase 4 Success Criterion #1: заменить "with acceptable lag (cached via TTL dict)" → "with acceptable lag (свежий результат каждого запроса; отставание = длительность одного HTTP-вызова к LP плюс retry-backoff)".
  - README P7 (DOC-02) добавить TTL cache в "next-step extensions" одним абзацем.

### httpx client + retry-политика
- **D-02:** **Singleton `httpx.AsyncClient`** создаётся в `entrypoints/lifespan.py`:
  ```python
  http_client = httpx.AsyncClient(
      base_url=str(settings.line_provider_base_url),
      timeout=httpx.Timeout(5.0),  # total — ROADMAP P4 pitfall mitigation
  )
  app.state.line_provider_http_client = http_client
  ```
  В `finally` — `await http_client.aclose()` ПЕРЕД `await engine.dispose()` (порядок shutdown — обратный startup).
- **D-03:** **Retry-политика для HTTP-роутов bet-maker'а:** 3 attempts, `wait_exponential(multiplier=0.5, min=0.5, max=2)`, worst case ~3s суммарно перед ответом клиенту. `reraise=True` — оригинальное исключение пробрасывается в traceback. Параметры через `BetMakerSettings`:
  - `BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS: int = 3`
  - `BET_MAKER_LINE_PROVIDER_HTTP_BACKOFF_MAX_S: float = 2.0`
  Retry-decorator живёт в `facades/line_provider_client.py` как factory `make_retry_decorator(attempts, max_backoff)`, переиспользуется и `HttpEventLookup`, и `list_active_events`.
- **D-04:** **Retry для reconciler — отдельная политика 5 attempts**, реализуется в P6 BM-12 через тот же factory с другими параметрами. В P4 фиксируем намерение; в P6 добавляются настройки `BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS: int = 5` + `..._BACKOFF_MAX_S: float = 10.0`.
- **D-05:** **Retry-on-what:** `httpx.TransportError` (включает TimeoutException, ConnectError, ReadError, NetworkError) + ручной `response.raise_for_status()` после ответа (`httpx.HTTPStatusError` где `status_code >= 500`). 4xx (404/422/400) **пробрасываются без retry** — это контрактные ответы LP. 429 — НЕ retry'им (LP не rate-limited, добавление 429-retry рисует некорректную картину).
- **D-06:** **Логирование retry-попыток:** `tenacity.before_sleep` hook + structlog binding (event_id, attempt_number, sleep_s). Реализация — Claude's discretion (likely небольшой wrapper, передающий контекст в `bind_contextvars` или один структурированный log-call).

### Поведение POST /bet при недоступности LP
- **D-07:** **`HttpEventLookup` на 5xx/timeout после исчерпания retry → `raise LineProviderUnavailable`** (новый exception, живёт в `facades/line_provider_client.py`). Сигнатура: `LineProviderUnavailable(reason: str)`.
- **D-08:** **POST /bet ловит `LineProviderUnavailable` → 503** с `{"detail":"event validation unavailable: line-provider unreachable"}`. Семантика честная: upstream-зависимость недоступна, клиенту понятно что это не его вина, можно retry'ить. Ставка НЕ сохраняется, PG не трогаем. `EventNotBettable → 422` остаётся как было (P3 D-06).
- **D-09:** **404 от LP** в `HttpEventLookup.get_event(id)` — `return None` (текущий контракт Protocol). Interactor `place_bet` мапит `None → EventNotBettable("event not found") → 422 с detail "event {id} is not bettable: event not found"`. Существующий happy-path P3 не меняется.
- **D-10:** **GET /events bet-maker'а** на LineProviderUnavailable → 503 `{"detail":"line-provider unreachable"}`. На пустой список активных событий — 200 + `[]` (нормальный успех).

### Архитектура клиента и факт-распределение
- **D-11:** **Два независимых facade** вместо одного объединяющего:
  - `facades/http_event_lookup.py` — `HttpEventLookup` имплементирует `EventLookup` Protocol (P3 D-11). Конструктор: `(http_client: httpx.AsyncClient, *, attempts=3, max_backoff=2.0)`. Метод `get_event` использует `make_retry_decorator(attempts, max_backoff)` из общего модуля.
  - `selectors/list_active_events.py` — `async def list_active_events(http_client: httpx.AsyncClient, *, attempts=3, max_backoff=2.0) -> list[EventRead]`. Использует тот же `make_retry_decorator`.
  - Общий `LineProviderUnavailable` exception + `make_retry_decorator` factory — в `facades/line_provider_client.py`.
  - **Что НЕ делаем:** не строим единый `LineProviderClient(http_client).get_events()/.get_event(id)` фасад. Каждый путь explicit и локальный. Защищает от случайного coupling между read-path (`GET /events`) и write-path-validation (`POST /bet`).
- **D-12:** **Один singleton `httpx.AsyncClient`** на сервис, пинуется в `app.state.line_provider_http_client`. Provider `get_line_provider_http_client(request) -> httpx.AsyncClient` в `facades/deps.py` + `LineProviderHttpClientDep` alias. Оба facade инжектируются через этот provider в роуты.

### GET /events response schema
- **D-13:** **bet-maker `GET /events` возвращает `list[EventRead]` полный** — с полями `event_id (UUID)`, `coefficient (Decimal)`, `deadline (datetime)`, `state (EventState)`. Дублируем `EventRead` в `bet_maker/schemas/events.py` (P3 D-12 pattern: intentional duplication между сервисами, симметрично уже задублированному `EventState`). `extra="forbid"` + `frozen=True`. Клиент получает coefficient — это нужно для понимания потенциального payout, типичный betting-API контракт.

### EventLookup замена
- **D-14:** **В production lifespan `app.state.event_lookup` устанавливается в `HttpEventLookup(http_client=...)`** вместо `StubEventLookup()`. `StubEventLookup` НЕ удаляется из `facades/event_lookup.py` — он по-прежнему используется в unit-тестах `test_place_bet.py` (P3 Plan 03-07 закладывал) и в `test_bet_routes.py` `app.dependency_overrides`. Структура Protocol-симметрии (P3 D-13) обеспечивает что `place_bet` interactor не меняется между P3 и P4.

### Тесты
- **D-15:** **Unit-тесты HttpEventLookup и list_active_events** — через `respx` mock-transport. `respx` подменяет `httpx.AsyncClient`'у transport без поднятия реального сервера. Новая dev-dep: `respx>=0.22,<0.23`. Сценарии:
  - `test_http_event_lookup.py`: 200 → EventSnapshot, 404 → None, 422/400 → пробрасывает без retry, 503 повторяется 3 раза → raises LineProviderUnavailable, 503 → 503 → 200 (retry succeeds).
  - `test_list_active_events.py`: 200 + пустой массив, 200 + N событий, 5xx retry-eventually-succeeds, 5xx exhausts.
- **D-16:** **Integration-тест `tests/bet_maker/test_events_routes.py`** (новый):
  - Fixture `line_provider_app` поднимает реальное line-provider `build_app()` с `InMemoryEventStore` (lifespan через `LifespanManager`).
  - bet-maker `client` fixture получает `app.dependency_overrides[get_line_provider_http_client] = lambda: httpx.AsyncClient(transport=ASGITransport(app=line_provider_app))`. Поверх — обычный `httpx.AsyncClient(transport=ASGITransport(app=bet_maker_app))`.
  - Сценарии: POST event в LP → GET /events bet-maker'а возвращает его; PUT event в LP в FINISHED_WIN → GET /events bet-maker'а возвращает пустой; POST /bet — happy path через реальный LP, 422 на несуществующий event, 422 на past-deadline (POST event с deadline в прошлом через FastAPI test-bypass или через freezegun), 422 на FINISHED-state.
  - **Гигиена fixture-scope** (ROADMAP P4 pitfall): транспортный AsyncClient должен иметь fixture-scope, совпадающий с event-loop scope тестов (`asyncio_mode="auto"` + `asyncio_default_fixture_loop_scope="session"` уже в pyproject — стабильно).
- **D-17:** **Расширение `test_bet_routes.py`** одним классом `TestPostBet503` — подсовываем фейковый `EventLookup` который raises `LineProviderUnavailable("simulated")` через `app.dependency_overrides[get_event_lookup]`, ожидаем 503 + detail. Старые happy-path / 422 тесты не меняются (используют `StubEventLookup` через override).
- **D-18:** **`test_health.py` не меняется** в P4. /health на текущем этапе пингует только PG (P5 расширит на RMQ); HTTP-клиент к LP в health-чек не добавляем — line-provider down не должен ронять bet-maker /health (read-side endpoint GET /events просто вернёт 503 для запросов, /bets и /bet/{id} продолжают работать).

### Lifespan порядок (R-4 mitigation)
- **D-19:** **Startup порядок:**
  1. `configure_structlog`
  2. `engine, sessionmaker = create_engine_and_sessionmaker(settings)`
  3. `await wait_for_postgres(engine)` (P3 D-27)
  4. `http_client = httpx.AsyncClient(base_url=..., timeout=Timeout(5.0))`
  5. `app.state.{settings, engine, sessionmaker, line_provider_http_client, event_lookup}` пинятся
  6. `yield`
- **D-20:** **Shutdown порядок (обратный):**
  1. `await http_client.aclose()` — закрыть pool до dispose'а engine
  2. `await engine.dispose()` — закрыть PG pool
  Логирование `bet_maker.shutdown` — после aclose, перед dispose.

### Settings (P1 schema extension)
- **D-21:** **`BetMakerSettings` дополняется** двумя полями (env_prefix `BET_MAKER_` сохраняется):
  - `line_provider_http_attempts: int = Field(default=3, ge=1, le=10)`
  - `line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)`
  Существующее поле `line_provider_base_url: HttpUrl` (P1) — уже есть, не трогаем.

### Claude's Discretion
- Точная структура `before_sleep` hook'а tenacity + structlog (декоратор-фабрика vs closure vs partial). Главное — log включает `attempt_number, sleep_s, exception_type`.
- Точное расположение `LineProviderUnavailable`: `facades/line_provider_client.py` (вместе с factory) vs `facades/errors.py`. Предлагаю первое — реже импортов и нет circular между selectors и facades.
- Точная сигнатура `make_retry_decorator`: возвращает декоратор `Callable` vs возвращает контекст-менеджер vs возвращает `AsyncRetrying`. Любой из паттернов tenacity 9.x подходит — выбрать самый читаемый.
- Структура integration-теста: fixture-orchestration через nested `LifespanManager` vs прямое использование `lifespan_context`. Главное — оба app живут в одном event loop.
- Что именно мокаем в `test_events_routes.py` для negative-cases: использовать реальный LP с подкрученными settings (короткий deadline) vs `respx` поверх `line_provider_http_client`. Предпочтительно — реальный LP для happy-path и 1-2 negative; respx для 5xx scenarios.

### Folded Todos
None — no open todos in this project.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth — ТЗ
- `./Тестовое задание Middle Python developer.pdf` — **первоисточник**. Для P4 релевантны:
  - стр.2: «Взаимодействие между сервисами может быть реализовано, к примеру, запросами к API сервиса line-provider...» — P4 реализует именно этот вариант (HTTP API).
  - стр.3 `GET /events`: «Список событий предоставляется сервисом line-provider, в целях оптимизации взаимодействий **допускается небольшое отставание** в свежести списка для новых событий». Это разрешение под TTL cache, но не обязанность — мы выбираем НЕ кэшировать (D-01); каждый GET /events свежий, lag = ровно длительность одного HTTP-вызова + backoff.
  - стр.4 «надёжности (к примеру, невозможности зависания ставки) и **производительности** (в реальном мире количество активных событий измеряется тысячами, ставок — на порядки больше)» — обоснование retry-политики D-03; защита от «зависания» в P4 — через 503 на POST /bet когда LP unreachable (D-08) и P6 reconciler для существующих PENDING.
- **NB:** ТЗ ни в одном месте не требует кэш; D-01 синхронизирует REQUIREMENTS.md и ROADMAP.md.

### Проектные документы
- `./CLAUDE.md` §«Technology Stack» + §«Supporting Libraries»:
  - `httpx 0.28.1` — primary HTTP lib для prod (singleton AsyncClient в lifespan) и тестов (`TestClient` использует его внутренне). Patterns: «Use `httpx.AsyncClient` as a singleton», «Wrap calls in `tenacity.retry` with `wait_exponential` + `stop_after_attempt(5)`», «Never share an `AsyncClient` across event loops».
  - `tenacity 9.1.4` — production retry library; декораторная форма; `reraise=True` обязателен для traceback hygiene.
  - `pydantic-settings 2.14.1` — для новых полей `BetMakerSettings` (D-21).
- `.planning/PROJECT.md` — Core Value + Constraints + Out of Scope. Конкретно для P4: «Аутентификация/авторизация — out of scope»; «`Idempotency-Key` header на POST /bet — v2 API-01, не реализовать».
- `.planning/REQUIREMENTS.md` BM-04 — **СОДЕРЖИТ ДРИФТ** относительно D-01: фраза «(retry tenacity) + tiny TTL cache» (или эквивалент) сейчас в активе → первый task P4 убирает упоминание TTL cache. Так же `.planning/ROADMAP.md` Phase 4 Success Criterion #1 (см. D-01).
- `.planning/ROADMAP.md` §«Phase 4: bet-maker HTTP integration with line-provider» — 5 success criteria + 2 pitfalls. **NB:** SC#1 будет переписан в D-01; остальные четыре остаются.
- `.planning/STATE.md` — Phase 3 complete (94.28% coverage src/bet_maker), Phase 4 starting state. После P4 — Phase 5.

### Прошлые фазы (P1/P2/P3 — НЕ менять решения)
- `.planning/phases/01-skeleton-infrastructure/01-CONTEXT.md` D-15 — `BetMakerSettings(env_prefix="BET_MAKER_")`. P4 расширяет (D-21), не пересоздаёт.
- `.planning/phases/02-line-provider-domain/02-CONTEXT.md`:
  - D-05 — `event_id: UUID4` сквозь все три сервиса. P4 HttpEventLookup парсит UUID из ответа LP.
  - D-17 — `Event` frozen Pydantic. P4 EventRead на стороне bet-maker (D-13) — отдельный класс, не импортируется из line-provider (service boundary).
  - LP API контракт: `POST /event` (201), `PUT /event/{id}` (200), `GET /event/{id}` (200/404), `GET /events` (200 list). P4 HttpEventLookup читает только GET /event/{id}; selector list_active_events читает только GET /events.
- `.planning/phases/03-bet-maker-domain-db/03-CONTEXT.md`:
  - D-11 — `EventLookup` Protocol + `EventSnapshot` frozen. P4 `HttpEventLookup` имплементирует ровно этот Protocol.
  - D-12 — `EventState` enum уже задублирован в `bet_maker/schemas/events.py`. P4 туда же добавляет `EventRead` (D-13).
  - D-13 — `app.state.event_lookup` подменяется в lifespan; P3 ставит StubEventLookup, P4 ставит HttpEventLookup без правок в `facades/deps.py` Protocol-симметрия.
  - D-14 — `place_bet` interactor не меняется между P3 и P4 (получает любой EventLookup через DI).
  - D-23 — TRUNCATE-fixture (autouse) для bet-maker integration тестов; P4 наследует.

### Architecture / Research
- `.planning/research/ARCHITECTURE.md` §«Phase 4: bet-maker GET /events + line-provider HTTP integration» (строки 816–828) — buildlist того же phase. **Поправка:** `facades/cache.py` из списка УБРАН (D-01); paste-ready tree (строки 176–246) перечисляет `cache.py` — это устаревший item для нашей трактовки.
- `.planning/research/ARCHITECTURE.md» §«FastAPI + FastStream lifespan composition» (строки 571–668) — образец lifespan. В P4 поднимается только httpx-часть; FastStream broker остаётся на P5.
- `.planning/research/ARCHITECTURE.md» §«HTTP integration testing» (строки 990–1016) — паттерн «два FastAPI app в одном процессе через ASGITransport». D-16 следует этому паттерну.
- `.planning/research/ARCHITECTURE.md» §«Scaling Considerations» строка 1031 — «GET /events?ids=...» batch для reconciler — отложено в P6/perf.

### Pitfalls (mitigations locked here)
- `.planning/research/PITFALLS.md` §«Stale `httpx.AsyncClient` connections / event-loop sharing in tests» — D-12 (singleton в lifespan, не per-request) + D-16 (fixture-scope = event-loop scope).
- `.planning/research/PITFALLS.md» §«Integration Gotcha: `httpx.Timeout` infinite default» — D-02 (timeout=5.0 явно).
- `.planning/research/PITFALLS.md» §«Pitfall A7: structlog contextvars cross-task contamination» — D-06 (logging retry попыток через bind_contextvars, не module-level state).

### External docs (когда понадобится planner / researcher)
- httpx 0.28.1 — `httpx.AsyncClient`, `httpx.ASGITransport`, `httpx.Timeout`, `httpx.TransportError`, `httpx.HTTPStatusError`. Через Context7 — `/encode/httpx` (если researcher нужен).
- tenacity 9.1.4 — `retry(stop=stop_after_attempt(N), wait=wait_exponential(...), retry=retry_if_exception_type((...)), before_sleep=..., reraise=True)`. Через Context7 — `/jd/tenacity`.
- respx — mock backend для httpx, API: `respx.mock(base_url=...)`, `respx.get("/event/{id}").respond(200, json={...})`. Через Context7 — `/lundberg/respx`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (P1+P2+P3)
- `src/bet_maker/settings/config.py` — `BetMakerSettings.line_provider_base_url: HttpUrl = "http://line-provider:8000"` уже определён (P1 D-15). P4 добавляет два новых поля (D-21), env_prefix не меняется.
- `src/bet_maker/facades/event_lookup.py` — `EventLookup` Protocol + `EventSnapshot` (frozen) + `StubEventLookup`. P4 не меняет Protocol/EventSnapshot/StubEventLookup. P4 ДОБАВЛЯЕТ `HttpEventLookup` в `facades/http_event_lookup.py` (не в том же файле — service-boundary хочется явное разделение; Protocol живёт там, где «контракт», реализации — рядом).
- `src/bet_maker/facades/deps.py` — `get_event_lookup` provider читает `app.state.event_lookup`. **НЕ меняется.** P4 только добавляет `get_line_provider_http_client` provider + `LineProviderHttpClientDep` alias.
- `src/bet_maker/entrypoints/lifespan.py` — текущий код:
  ```python
  app.state.event_lookup = StubEventLookup()
  ```
  P4 заменяет на (примерно):
  ```python
  http_client = httpx.AsyncClient(base_url=str(settings.line_provider_base_url), timeout=httpx.Timeout(5.0))
  app.state.line_provider_http_client = http_client
  app.state.event_lookup = HttpEventLookup(http_client=http_client, attempts=settings.line_provider_http_attempts, max_backoff=settings.line_provider_http_backoff_max_s)
  ```
  + в `finally`:
  ```python
  await http_client.aclose()
  await engine.dispose()
  ```
- `src/bet_maker/app.py` — `build_app()` factory + include health/bets routers (P3 Plan 03-08). P4 добавляет `events.router` третьим include.
- `src/bet_maker/entrypoints/api/bets.py` — POST /bet handler уже ловит `EventNotBettable → 422`. P4 расширяет: ловит `LineProviderUnavailable → 503`. Получает порядок: 1) try place_bet, 2) except LineProviderUnavailable → 503, 3) except EventNotBettable → 422. Порядок важен: `LineProviderUnavailable` НЕ subclass `EventNotBettable`.
- `src/bet_maker/schemas/events.py` — текущий код содержит только `EventState`. P4 добавляет `EventRead` (D-13).
- `src/bet_maker/interactors/place_bet.py` — **НЕ меняется.** Получает любой `EventLookup` через DI; HttpEventLookup пробросит свои exception'ы (None, EventNotBettable не вызывает; LineProviderUnavailable пробрасывается сквозь interactor наружу — interactor не ловит).
- `tests/bet_maker/conftest.py` — fixtures `app`, `client`, `seed_event` (через `StubEventLookup`). **РАСШИРЯЕТСЯ** в P4: добавляется fixture `line_provider_app` (другой FastAPI app в том же процессе) и `bet_maker_client_with_line_provider` для integration-тестов D-16. Существующие `client` fixture для unit-тестов с `StubEventLookup` остаются (через `app.dependency_overrides`).

### Established Patterns (зеркало P2 / P3)
- **Facade Protocol + Stub → Real реализация в следующей фазе.** P2 EventBus (Noop → RabbitEventBus в P5). P3 EventLookup (Stub → **Http в P4**). P4 фактически закрывает этот pattern.
- **Sync-task в первом плане фазы.** P2 Plan 02-01 (LP-02 str→UUID4), P3 Plan 03-01 (BM-01/05/13 coefficient removal). P4 Plan 04-01 (D-01: убрать TTL cache из BM-04 + ROADMAP).
- **REQ-ID в docstrings тестов** (P1 Plan 01-07 ввёл convention) — каждый тест ссылается на BM-04 / D-XX для grep-traceability.
- **`extra="forbid"` на всех Pydantic schemas** — `EventRead` (D-13) тоже с forbid + frozen.
- **Service-boundary: НЕ импортируем из соседнего сервиса.** `bet_maker/schemas/events.EventRead` дублируется symmetrically с `line_provider/schemas/events.EventRead`. По D-13 + P3 D-12.

### Integration Points
- `entrypoints/api/events.py` (новый файл) → `selectors/list_active_events.list_active_events` → singleton `httpx.AsyncClient` через `Depends(get_line_provider_http_client)`.
- `entrypoints/api/bets.py` (расширение) → `place_bet(uow, event_id, amount, event_lookup=HttpEventLookup(...))` → внутри HttpEventLookup → singleton `httpx.AsyncClient` (shared с selector через `app.state`).
- `entrypoints/lifespan.py` — точка сборки. Расширения P4: создание + закрытие `httpx.AsyncClient`. **Все добавления — через `app.state.*`, никаких module-level singletons** (PITFALLS A2).
- `docker-compose.yml` — `bet-maker` уже depends_on `line-provider` (P1 implicit через networking). Если `condition: service_started` не выставлен — добавится в P4 (можно `service_healthy`, у line-provider уже есть healthcheck в P1). Verify — это часть Plan 04-01 sync-task.
- `pyproject.toml` — добавить `respx` в dev-deps. `httpx`, `tenacity`, `pydantic-settings` уже pinned.

</code_context>

<specifics>
## Specific Ideas

- **«а кэш вообще нужен по ТЗ?»** — критический spot-check пользователя. ТЗ не требует кэш, только разрешает lag. ROADMAP/REQUIREMENTS BM-04 — наша трактовка с риском over-engineering для test-task scope. Результат: D-01 убирает TTL cache из P4, README P7 упоминает как extension. Это поведенческое правило для всех будущих фаз: **проверять ROADMAP-decisions против буквы ТЗ перед фиксированием в плане**.
- **«разделить retry-политику HTTP-роутов и reconciler'а»** — выбор пользователя. POST /bet под синхронным HTTP — нужна низкая tail-latency (3 attempts, ~3s); reconciler — фоновая, может ждать дольше (5 attempts, ~25s). Реализация через factory `make_retry_decorator(attempts, max_backoff)`, переиспользуемый в P6. D-03 + D-04.
- **«два независимых facade»** — выбор пользователя поверх альтернативы «единый LineProviderClient». Защищает от случайного coupling read-path (GET /events) и validation-path (POST /bet); каждый путь explicit. D-11.
- **«503 на LineProviderUnavailable, не 422»** — выбор пользователя. Семантика честная: upstream down ≠ event invalid. Клиент видит, что это не его вина, можно retry. D-08.
- **«полный EventRead с coefficient в response»** — выбор пользователя. Типичный betting-API контракт, клиент видит payout-потенциал. D-13.

</specifics>

<deferred>
## Deferred Ideas

- **TTL cache на GET /events** — D-01 убирает из P4. Упомянуть в README P7 (DOC-02) как "next-step extension" одним абзацем со ссылкой на `httpx`+`asyncio.Lock` для single-flight.
- **`GET /events?ids=1,2,3` batch endpoint в line-provider + reconciler** — P6 perf-extension (ARCHITECTURE.md Scaling Considerations). В P6 reconciler сейчас будет звонить `GET /events` (или N×`GET /event/{id}`) — оптимизация когда reviewer обозначит проблему.
- **Idempotency-Key header на POST /bet** — REQUIREMENTS v2 API-01. README P7 "what I'd add next" одним абзацем.
- **Circuit breaker (например, через `aiocircuitbreaker`)** — out of scope. Для test-task scale ненужно. Упомянуть в README "Reliability roadmap".
- **429 retry с Retry-After header** — out of scope. LP не rate-limited.
- **OpenAPI tags/summaries/examples для bet-maker GET /events** — P7 (DOC-02). В P4 минимальный `tags=["events"]` + `response_model=list[EventRead]`.
- **Smoke /health check для line-provider connectivity** — out of scope. Bet-maker /health пингует только локальный PG (P3 D-26..D-29). LP-down НЕ должен ронять bet-maker /health — read-side GET /events просто отдаст 503; bet-history и GET /bet/{id} продолжают работать.
- **EventState parity test между line_provider/schemas/events.EventState и bet_maker/schemas/events.EventState** — P5 e2e (где оба сервиса в одном тесте). Не в P4.
- **respx vs httpx-mock — выбор библиотеки** — D-15 фиксирует respx. respx — современный (≥0.22), API чище для httpx 0.28, активно поддерживается. Альтернативы (`pytest-httpx`) — equivalent, но respx — стандарт сообщества; planner может пересмотреть если найдёт concrete reason.

### Reviewed Todos (not folded)
None.

</deferred>

---

*Phase: 04-bet-maker-http-integration-with-line-provider*
*Context gathered: 2026-05-15*
