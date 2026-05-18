# Phase 7: Polish + Documentation - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 7 — финальный polish-проход. Никаких новых рантайм-фич: только видимое качество (README + curl-walkthrough + OpenAPI + AsyncAPI), enforcement-планка (mypy strict zero errors + pytest-cov ≥85% в CI), и одноразовый аудит «Looks Done But Isn't» (18 items, ROADMAP Phase 7 SC#6) — задокументированный + автоматизированный там, где возможно.

Цель: reviewer открывает репозиторий → читает README → выполняет copy-paste docker-compose-блок + curl-последовательность (create event → place bet → finish event → list bets) → видит зелёный CI badge + coverage badge → за ≤5 минут понимает, что Core Value invariant защищён, и может пробежаться глазами по «Looks Done But Isn't» аудиту.

**В скоупе:**

- `README.md` — финальная редакция:
  - Заголовок + краткое описание (1-2 абзаца, что система делает).
  - **Quick start** (расширяет существующий блок) — `docker compose up -d`, healthcheck-ожидание, ports, RabbitMQ Management UI.
  - **Reviewer walkthrough** (новый блок) — copy-paste curl-последовательность: создать событие в line-provider (`POST /event`) → положить ставку в bet-maker (`POST /bet`) → завершить событие (`PUT /event/{id}` со `state=FINISHED_WIN`) → `GET /bets` показывает `WON` (settled_via='consumer'); + второй сценарий с drop-publish для демонстрации reconciler-ветки опционален в `.planning/research/` (не в README — слишком много).
  - **Architecture** (DOC-02) — ASCII-диаграмма топологии (LP / BM / PG / RMQ + DLX/DLQ), описание слоёв (entrypoints / facades / interactors / selectors / helpers + UoW + Repository), краткое описание RMQ-топологии (exchange `bsw.events` → queue `bet_maker.events.finished` + DLX `bsw.events.dlx` → DLQ), reconciler — defence-in-depth. Ссылка на `./.planning/research/ARCHITECTURE.md` для глубокого описания.
  - **Development** (DOC-03) — `uv sync`, `uv run alembic upgrade head`, `uv run pytest -q`, `uv run ruff check . && uv run ruff format --check .`, `uv run mypy src`, `uv run pre-commit install`. Локальный запуск без docker (порты, env vars, нужны живые PG + RMQ).
  - **Reliability** (DOC-04) — описание Core Value инварианта; перечисление защит эшелонированно: (a) durable classic queue + persistent messages + named volume `bsw_rabbitmq_data`, (b) `AckPolicy.MANUAL` + ack ПОСЛЕ UoW commit (R2/F4), (c) `FOR UPDATE SKIP LOCKED` + status-filter для идемпотентности и concurrent-safety (R3), (d) DLX + DLQ + bounded in-handler retries для poison/transient (R7), (e) reconciler `asyncio.Task` поднимает PENDING-ставки при drop publish (R8), (f) lifespan-порядок (R4/F3) и SIGTERM exec-form CMD (R11/D4). Раздел заканчивается ссылкой на `./.planning/research/PITFALLS.md` для полного перечня.
  - **CI / coverage badges** — CI badge уже есть, добавить coverage badge (Shields.io статический SVG).
  - **Project status** — обновить таблицу: все 7 фаз complete.
  - **CANCELLED-расширение** — отдельный абзац в Reliability (D-05): почему ввели и что это нестандартное extension ТЗ (трактовка для recovery; ссылка на `feedback_verify_against_tz`).
- `OpenAPI` polish на обоих сервисах:
  - `FastAPI(title=..., description=..., version=..., contact=..., license_info=...)` — добавить `description` (1-2 предложения, что сервис делает) и `contact`/`license_info` опционально. `title` и `version` уже есть.
  - Каждый route получает `summary=` (1 строка) и при необходимости `description=` (расширенная docstring переезжает в `description`).
  - `responses={...}` для error-веток (422 на BM-06 / 503 на LineProviderUnavailable / 404 на BM-13/GET /event/{id}) — с `model=` (Pydantic-схема ошибки `ErrorDetail` или существующая FastAPI `HTTPValidationError`).
  - `Body(..., examples={...})` для `POST /bet` и `POST/PUT /event` — конкретные UUID/Decimal-примеры из текущих тестов.
- `AsyncAPI` — FastStream `RabbitRouter` экспонирует `/asyncapi` по дефолту на bet-maker'е (consumer side); проверить, что endpoint доступен после `app.include_router(router)`. На line-provider'е тоже включить (publisher side) для документации publish-контракта. Никаких ручных схем — FastStream сам генерирует.
- `mypy --strict` финальный pass (QA-01):
  - `uv run mypy src` — zero errors enforcement в CI уже на месте (P1 / .github/workflows/ci.yml).
  - Audit: grep по `# type: ignore` в `src/` — для каждого случая обосновать или убрать. Особенно на критических путях (UoW, repositories, consumer handler, reconciler) — НЕ должно быть `# type: ignore`. На уровне тестов допустимо.
- `pytest-cov` coverage gate (QA-09):
  - `pyproject.toml` `[tool.coverage.report] fail_under = 85` уже выставлен; CI команда `uv run pytest -q` НЕ запускает coverage сейчас → добавить `--cov` в CI step + `--cov-fail-under=85` (ROADMAP SC#4 ≥80%, существующий pyproject уже строже на 85%, оставляем 85).
  - Coverage badge — статический SVG через Shields.io (или endpoint shields.io с динамическим парсингом coverage.xml в CI artefact). Recommended: статический shields.io badge "coverage 85%" с ручным апдейтом — для test-task этого достаточно, codecov/coveralls — overkill.
- `07-AUDIT.md` (новый файл в phase dir) — 18-item «Looks Done But Isn't» (ROADMAP P7 SC#6 + `PITFALLS.md` §«Looks Done But Isn't»). Каждый item — строка таблицы с тремя колонками: `Item | Evidence (file:line / test / command) | Status (verified / fix-applied / waived)`. Все 18 должны быть `verified` или `fix-applied`; ни одного `waived` без письменного обоснования в комментарии. Где возможно — добавить автоматический pytest-чек:
  - Manual ack: grep-test `tests/audit/test_static.py::test_subscribers_have_manual_ack` (rg `@router.subscriber(` → AST или regex assert `ack_policy=AckPolicy.MANUAL`).
  - exec-form CMD: grep-test на `Dockerfile` — `CMD [` начало.
  - PYTHONUNBUFFERED: grep-test на `Dockerfile` или `docker-compose.yml`.
  - `python:3.10-slim-bookworm`: grep-test на `Dockerfile`.
  - SQL-факт (FOR UPDATE SKIP LOCKED): grep-test на `repositories/bets.py`.
  - `expire_on_commit=False`: grep-test на `infrastructure/db.py`.
  - schema duplication parity: contract-test уже есть (P5 D-29) — переиспользуется.
  - durable queue: grep-test на `messaging.py` `durable=True` + reference на existing P5 e2e test, что проверяет реальное `rabbitmqctl list_queues`-эквивалент.
  - DLQ wired: e2e test P5 `test_e2e_rabbitmq.py` poison-сценарий уже это покрывает.
  - SIGTERM: ручная проверка `docker compose down` exit-code (зафиксирована в audit как manual + screenshot/log-фрагмент).

**Не в скоупе:**

- Любые новые рантайм-фичи (новые routes, новые interactor'ы, новые статусы).
- Расширение test-suite сверх того, что нужно для аудита (статические grep-тесты + переиспользование P5/P6 интеграционных).
- Кэш `GET /events` TTL — отложено в P4 D-01 (упомянуто в README §«Next-step extensions»).
- Prometheus / OpenTelemetry / Grafana — v2, не P7.
- Codecov / Coveralls — overkill для test-task. Статический Shields.io badge достаточен.
- ADR-документы — `.planning/research/ARCHITECTURE.md` и `PITFALLS.md` уже играют их роль.
- Документация на английском — single Russian README (соответствует существующим артефактам и memory `user`).
- `pyproject.toml` `requires-python` расширение до 3.11 — `<3.11` зафиксировано CLAUDE.md, не трогаем.
- Удаление `# type: ignore` со scope сверх критических путей — pragmatic balance: тесты остаются как есть.

</domain>

<decisions>
## Implementation Decisions

### README structure (DOC-01..04)

- **D-01:** README — **single Russian primary**. Соответствует стилю `.planning/`-документации, `CLAUDE.md` constraints, и memory `feedback_verify_against_tz` (ТЗ — русский). Технические термины (FastAPI, RabbitMQ, mypy, pytest и т.п.) — без перевода.
- **D-02:** README sections (фиксированный порядок):
  1. Заголовок + 2 badge (CI + coverage) + 1-2 абзаца описания
  2. **Quick start** — расширение существующего блока
  3. **Reviewer walkthrough** — новый блок, copy-paste curl-сценарий happy-path (создать event → bet → finish → assert WON)
  4. **Architecture** (DOC-02) — ASCII-диаграмма + слои + RMQ-топология + ссылка на ARCHITECTURE.md
  5. **Reliability** (DOC-04) — Core Value + эшелонированные защиты + CANCELLED-extension абзац + ссылка на PITFALLS.md
  6. **Development** (DOC-03) — uv / migrations / pytest / linters / pre-commit
  7. **Next-step extensions** — TTL cache (P4 deferred), metrics, AsyncAPI snapshot — одной строкой каждый
  8. **Project status** — обновлённая таблица 7/7 phases complete
- **D-03:** ASCII-диаграмма в Architecture section — inline, не SVG:
  ```
  ┌──────────────┐   POST/PUT/GET   ┌──────────────┐
  │ reviewer cli │ ───────────────▶ │ line-provider│
  └──────────────┘                  │   (8000)     │
                                    └──────┬───────┘
                                           │ AMQP publish
                                           ▼
                                    ┌──────────────┐
                                    │   RabbitMQ   │ ──▶ DLX/DLQ
                                    └──────┬───────┘
                                           │ AMQP consume
                                           ▼
  ┌──────────────┐  POST/GET /bet   ┌──────────────┐    SELECT/UPDATE  ┌──────────────┐
  │ reviewer cli │ ───────────────▶ │  bet-maker   │ ────────────────▶ │  PostgreSQL  │
  └──────────────┘                  │   (8001)     │  FOR UPDATE       │              │
                                    │  + reconciler│  SKIP LOCKED      └──────────────┘
                                    └──────────────┘
                                           │ HTTP GET /event/{id}
                                           └──── reconciler ───▶ line-provider
  ```
  Каркас, в плане можно адаптировать форматирование, главное — единая 6-стрелочная картина (LP↔reviewer, LP→RMQ, RMQ→BM, BM→PG, BM→LP reconciler, RMQ→DLX).
- **D-04:** **Reviewer walkthrough** — концертная copy-paste-последовательность (ожидаемый output для каждого шага):
  ```bash
  # 1. start stack
  cp .env.example .env && docker compose up -d
  # 2. wait healthy
  watch -n 1 'docker compose ps'
  # 3. create event
  EVENT_ID=$(curl -s -X POST :8000/event -H 'content-type: application/json' \
    -d '{"event_id":"00000000-0000-0000-0000-000000000001","coefficient":"1.50","deadline":"2030-01-01T00:00:00+00:00","state":"NEW"}' | jq -r .event_id)
  # 4. place bet
  curl -s -X POST :8001/bet -H 'content-type: application/json' \
    -d "{\"event_id\":\"$EVENT_ID\",\"amount\":\"10.00\"}"
  # 5. finish event
  curl -s -X PUT :8000/event/$EVENT_ID -H 'content-type: application/json' \
    -d '{"coefficient":"1.50","deadline":"2030-01-01T00:00:00+00:00","state":"FINISHED_WIN"}'
  # 6. observe settled
  sleep 1
  curl -s :8001/bets | jq '.[] | {id, status, settled_via}'
  ```
  Ожидаемый итог: `status: "won"`, `settled_via: "consumer"` (если consumer succeeded; reconciler — fallback). Уточняет, что reviewer завершает за 1-2 минуты после `up -d`.
- **D-05:** **Reliability section narrative (DOC-04)** — структурированный список из 6 пунктов (см. domain «Reliability»), каждый со ссылкой на конкретный source-файл (например, `src/bet_maker/entrypoints/messaging.py` для manual ack, `src/bet_maker/repositories/bets.py::get_pending_locked` для FOR UPDATE SKIP LOCKED). Завершается отдельным абзацем про **CANCELLED extension** (Phase 6 D-25): «Статус CANCELLED — наша инженерная трактовка для recovery (LP вернул 404). ТЗ описывает только PENDING/WON/LOST; расширение задокументировано в `REQUIREMENTS.md` BM-05 и `.planning/research/PITFALLS.md`».

### OpenAPI metadata polish (QA visibility)

- **D-06:** **На уровне `FastAPI(...)`** обоих сервисов: добавить `description` (одну фразу — что сервис делает), `contact={"name":"...","email":"..."}` опционально (Claude's discretion — можно опустить, не критично), `license_info` опустить (нет публичной лицензии у test-task). `title` + `version` уже на месте.
- **D-07:** **На уровне роутов** — для каждого `@router.{get,post,put}(...)` добавить:
  - `summary="One-line summary"` (новое).
  - `description=` существующий docstring остаётся (FastAPI сам подхватывает).
  - `responses={...}` для error-веток с явными статусами:
    - line-provider: `POST/PUT /event` → `{422: {"model": HTTPValidationError, "description": "..."}}` (FastAPI auto-добавляет 422, но добавим явный `description`).
    - bet-maker: `POST /bet` → `{422: {...}, 503: {"model": ErrorDetail, "description": "line-provider unreachable"}}`.
    - bet-maker: `GET /bet/{bet_id}` → `{404: {"model": ErrorDetail, "description": "bet not found"}}`.
- **D-08:** **`Body(..., examples=...)`** на `POST /bet` (один UUID-пример из тестов P3) и `POST /event` / `PUT /event/{id}` line-provider'а (UUID + decimal + deadline). Использовать Pydantic v2 `openapi_examples` синтаксис.
- **D-09:** **`ErrorDetail` Pydantic schema** — единый `class ErrorDetail(BaseModel): detail: str` на сервис (`src/{line_provider,bet_maker}/schemas/errors.py`, по аналогии с P5 D-28 — дублируется между сервисами без cross-imports). Используется в `responses={...}` для всех error-веток. Простая модель, удобная для swagger-UI.

### AsyncAPI publication

- **D-10:** **FastStream RabbitRouter** генерирует AsyncAPI doc автоматически на `/asyncapi` при `app.include_router(router)`. Phase 7 plan убеждается, что endpoint доступен на обоих сервисах (consumer side BM, publisher side LP), и упоминает URL в README §Architecture. Никаких ручных схем — FastStream сам читает `@router.subscriber` / `@router.publisher` декораторы.
- **D-11:** **AsyncAPI snapshot не коммитим в репо** — endpoint достаточно для приёмки. Если reviewer хочет offline-копию — `curl :8001/asyncapi -o asyncapi.json` упоминается в README §Next-step extensions одной строкой.

### mypy strict cleanup (QA-01)

- **D-12:** **Финальный pass:** `uv run mypy src` — zero errors enforcement в CI уже работает с P1. Phase 7 plan делает аудит-grep по `# type: ignore` в `src/`:
  - На критических путях (UoW, repositories, consumer handler, reconciler, interactors, schemas) — НЕ должно быть `# type: ignore`. Если найдётся — обосновать (комментарий рядом) или убрать (правильный type narrowing).
  - На границах фреймворков (FastAPI/FastStream dispatch, dependency overrides в тестах) допускается `# type: ignore[arg-type]` или `# type: ignore[no-untyped-def]` с inline-комментарием.
- **D-13:** **CI gate:** `uv run mypy src` уже на месте (CI step `Mypy strict`); никаких изменений в pipeline'е не требуется. Plan'у достаточно убедиться, что step зелёный после всех правок.
- **D-14:** **Phase 7 НЕ расширяет mypy на тесты** (`disallow_untyped_defs = false` override уже в pyproject). Это сознательное послабление: типизация хелперов и fixture-функций в pytest даёт мало value за много шумных правок. Test-coverage и assert'ы — основной источник доверия, не mypy на тестах.

### Coverage gate (QA-09)

- **D-15:** **Coverage gate в CI:** заменить `uv run pytest -q` → `uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85`. `xml`-репорт — для будущего badge'а (если уйдёт в codecov). `--cov-fail-under=85` дублирует `[tool.coverage.report] fail_under = 85`, но явный CLI-флаг страхует от случайных правок pyproject. ROADMAP SC#4 ≥80%, существующий конфиг строже (85), оставляем 85.
- **D-16:** **Coverage badge** — статический Shields.io URL вида `https://img.shields.io/badge/coverage-85%25-brightgreen.svg`. Никакого codecov/coveralls — для test-task overkill (требует регистрации сервиса, токенов, push в внешний сервис). Badge обновляется руками в README, если планка изменится. Подход явно описан в `D-16` без претензий на real-time tracking.
- **D-17:** **fail-under планка = 85** — выше ROADMAP-минимума 80%, ниже current pyproject 85 (т.е. совпадает). Тест-suite уже это покрывает после P6 (~295 тестов). Не поднимаем до 90: рискуем сорваться на нерелевантных error-веках в `entrypoints/api/*.py`.

### Audit (Looks Done But Isn't, ROADMAP P7 SC#6)

- **D-18:** **Отдельный артефакт `07-AUDIT.md`** в `.planning/phases/07-polish-documentation/` — таблица из 19 строк (18 items из ROADMAP P7 SC#6, перечисленные в `PITFALLS.md` §«Looks Done But Isn't»):
  - Колонки: `Item | Evidence | Status | Notes`.
  - `Evidence` — конкретный `file:line` или название pytest-теста или shell-команда с ожидаемым выводом.
  - `Status` — `verified` (без правок), `fix-applied` (правки в этой фазе), `waived` (с обязательным письменным обоснованием в Notes — должно стремиться к нулю).
- **D-19:** **Автоматизация audit-items, где можно** — новый файл `tests/audit/test_static.py` со статическими grep/regex/AST-проверками:
  - `test_subscribers_have_manual_ack` — AST-обход `src/bet_maker/entrypoints/messaging.py`, для каждого `@router.subscriber(...)` ищем kwarg `ack_policy=AckPolicy.MANUAL`.
  - `test_repositories_use_for_update_skip_locked` — regex-проверка `with_for_update(skip_locked=True)` в `src/bet_maker/repositories/bets.py`.
  - `test_async_sessionmaker_expire_on_commit_false` — regex-проверка `expire_on_commit=False` в `src/bet_maker/infrastructure/db.py`.
  - `test_dockerfile_exec_form_cmd` — read `Dockerfile`, assert `CMD [` начало (не `CMD python ...`).
  - `test_dockerfile_pinned_python_bookworm` — regex `python:3.10-slim-bookworm`.
  - `test_pythonunbuffered_set` — grep `PYTHONUNBUFFERED=1` в `Dockerfile` / `docker-compose.yml`.
  - `test_durable_queue_args` — AST-обход `src/bet_maker/entrypoints/messaging.py` на `durable=True` для `RabbitQueue` и `RabbitExchange`.
  - `test_schema_duplication_parity` — переиспользует существующий contract-test P5 D-29 (импорт обоих `EventFinishedMessage` и сравнение `model_json_schema()`).
- **D-20:** **Manual-only items** (не автоматизируем, ручная верификация — фиксируем в AUDIT.md команды + ожидаемый выход):
  - `docker compose down` exit-code 0 в < 5s — ручной тест (cтрока вида `$ docker compose down → 0`).
  - `docker volume ls` показывает named volumes — ручной тест.
  - `rabbitmqctl list_queues durable=true` (или RMQ Management UI screenshot) — ручной тест.
  - Decimal exact roundtrip `POST /bet amount="10.00"` → `GET /bets` `"10.00"` — уже покрыт P3 integration-тестами (`test_bet_routes.py::TestPostBet201`), AUDIT.md ссылается на конкретный test_id.
- **D-21:** **Идемпотентность consumer'а** (item #2) — уже покрыто P5 `test_e2e_rabbitmq.py` (concurrent settle scenarios via TestRabbitBroker + real-RMQ); AUDIT.md ссылается без новых тестов.
- **D-22:** **Reconciler dies-silently guard** (item #3) — уже покрыто P6 `test_reconciliation.py::TestReconcilerLoop::test_tick_exception_isolation` + `/health` 503 при `task.done()`; AUDIT.md ссылается на конкретные test-id.

### Sync-task (Plan 07-01)

- **D-23:** **Первый план Phase 7** — sync-task проверка (паттерн P2 02-01 / P3 03-01 / P4 04-01 / P5 05-10 / P6 06-01) НЕ всегда заканчивается правкой, но всегда выполняется:
  - Сверить `REQUIREMENTS.md` BM-05 (CANCELLED, P6 D-25) против текущего `src/bet_maker/schemas/bets.py::BetStatus` — должно сходиться.
  - Сверить `ROADMAP.md` Phase 7 success criteria #1..#6 против артефактов, которые мы здесь же создаём (README sections, mypy gate, coverage gate, OpenAPI/AsyncAPI, AUDIT.md).
  - Проверить `./Тестовое задание Middle Python developer.pdf` (memory `feedback_verify_against_tz`) — нет ли drift'а между ТЗ и нашими доками. Особенно проверить статусы ставки (ТЗ: PENDING/WON/LOST — у нас 4 с CANCELLED): убедиться, что extension явно задокументировано в `REQUIREMENTS.md` BM-05 и упомянуто в README §Reliability.
  - Если drift найден → minimal-edit fix в первом плане; иначе — план фиксирует «sync verified, no changes» и идёт дальше.

### Claude's Discretion

- Точный URL Shields.io для coverage badge (статический vs query-параметризованный) — planner решит. Главное — не codecov.
- Расположение `ErrorDetail` schema (`schemas/errors.py` vs встроить в каждый route-handler) — planner выберет читаемость; рекомендую отдельный модуль, симметрично существующим schemas (`bets.py`, `events.py`).
- Стиль AST-чеков в `tests/audit/test_static.py` (Python `ast` модуль vs grep через `Path.read_text` + regex) — planner возьмёт что проще; для test-task scope regex достаточно, AST overkill.
- Финальный nameplate badges в README (1 vs 2 vs 3) — planner подберёт; recommended minimum: CI + coverage.
- Точное количество запросов в Reviewer walkthrough (5 vs 6 — стоит ли добавить `GET /events`-step) — planner выберет лаконичность. Recommended: 5 шагов (create / bet / finish / sleep / get-bets); `GET /events` отдельным шагом необязателен.
- Размер ASCII-диаграммы (минимальная 6-line vs детальная с DLX-веткой) — planner выберет. Рекомендую среднюю: PG/RMQ + main flow + DLX/DLQ + reconciler arrow.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth — ТЗ

- `./Тестовое задание Middle Python developer.pdf` — первоисточник.
  - стр.1: «надёжности (к примеру, невозможности зависания ставки)» — Core Value, отражается в DOC-04 §Reliability.
  - стр.2: «Bet может иметь один из трёх статусов: ещё не сыграла / выиграна / проиграна» — CANCELLED — наша инженерная трактовка; D-05 фиксирует обязательное упоминание в README + REQUIREMENTS BM-05.
  - стр.3 диаграмма + текстовое описание API — сверка с фактическими роутами в OpenAPI polish (D-06..09).
- Memory `feedback_verify_against_tz` — sync-task в Plan 07-01 проверяет drift между ТЗ и REQUIREMENTS/ROADMAP/README.

### Requirements & roadmap

- `.planning/REQUIREMENTS.md` — DOC-01..04, QA-01, QA-09 (все 6 requirements Phase 7).
- `.planning/ROADMAP.md` §«Phase 7: Polish + Documentation» — 6 SC + 3 pitfalls (visibility gap + R6 final + R11 final). SC#6 — 18-item «Looks Done But Isn't» checklist.
- `.planning/PROJECT.md` — Out of scope (нет auth, нет UI, нет CANCELLED в ТЗ — расширение); таблица Key Decisions.

### Прошлые фазы — locked decisions

- `.planning/phases/01-skeleton-infrastructure/01-CONTEXT.md` — Dockerfile pin `bookworm` (D-19/D-20), exec-form CMD, PYTHONUNBUFFERED, structlog setup, CI workflow.
- `.planning/phases/02-line-provider-domain/02-CONTEXT.md` — D-05 UUID4, D-12 commit-before-publish, EventFinishedMessage schema, OpenAPI route docstrings.
- `.planning/phases/03-bet-maker-domain-db/03-CONTEXT.md` — D-09 Bet schema, D-11 EventLookup Protocol, D-12 schema duplication policy, D-18 AsyncUnitOfWork, D-22 wait_for_postgres, `expire_on_commit=False`.
- `.planning/phases/04-bet-maker-http-integration-with-line-provider/04-CONTEXT.md` — D-01 TTL cache deferred to README §Next-step extensions, D-13 EventRead schema, D-19/D-20 lifespan order.
- `.planning/phases/05-rabbitmq-integration/05-CONTEXT.md` — D-01..D-06 RMQ topology (упоминается в README §Architecture ASCII-диаграмме), D-07 AckPolicy.MANUAL, D-09 poison/transient classification, D-12/D-15 idempotency, D-17 settle_bets_for_event signature, D-20 /health, D-21 lifespan, D-28/D-29 schema duplication + contract test.
- `.planning/phases/06-reconciliation-job/06-CONTEXT.md` — D-01..D-04 reconciler branching (settle/cancel/skip), D-13 /health reconciler check, D-15/D-16 lifespan порядок, D-25 sync-task `CANCELLED` extension в REQUIREMENTS BM-05 / ROADMAP P6 Goal — закрепляется в README §Reliability.

### Project instructions

- `./CLAUDE.md` §«Project» — Core Value invariant, constraints (Python 3.10 fix, FastAPI fix, async, in-memory LP, dockerized, PEP8 + type hints + tests).
- `./CLAUDE.md` §«Custom rules» — «No emojis in docs and code», «DB readonly commands only», «SingleStore queries: always use context7» (последнее не применимо к P7).
- `./CLAUDE.md` §«Recommended Stack» — все версии библиотек, версия Python, Docker base image.
- `./CLAUDE.md` §«Stack Patterns by Variant» — `0.0.0.0` binding, service names в URL, `pydantic-settings` env-driven config — упоминаются в README §Architecture.

### Existing artefacts — будут отредактированы или прочитаны

- `./README.md` — финальная редакция (D-01..D-05).
- `./pyproject.toml` — coverage уже настроен (`fail_under=85`), нужна правка `--cov` в CI (D-15).
- `./.github/workflows/ci.yml` — добавить `--cov --cov-fail-under=85` в pytest step (D-15).
- `./Dockerfile` — exec-form CMD + `python:3.10-slim-bookworm` + PYTHONUNBUFFERED — уже на месте, audit-static-tests проверяют (D-19).
- `./docker-compose.yml` — healthchecks + volumes — уже на месте, audit-tests проверяют (D-19/D-20).
- `./alembic/versions/*.py` — миграции 0001/0002/0003 на месте, audit ссылается.
- `src/{line_provider,bet_maker}/app.py` — FastAPI `description` (D-06).
- `src/{line_provider,bet_maker}/entrypoints/api/*.py` — `summary` + `responses` + `Body(examples=)` (D-06..D-09).
- `src/{line_provider,bet_maker}/schemas/errors.py` (**новый**) — `ErrorDetail` (D-09).
- `tests/audit/test_static.py` (**новый**) — D-19 static-grep audit tests.
- `tests/contract/test_event_finished_message_schema.py` — переиспользуется без правок (D-19 `test_schema_duplication_parity`).
- `tests/bet_maker/test_e2e_rabbitmq.py`, `tests/bet_maker/test_reconciliation_e2e.py`, `tests/bet_maker/test_reconciliation.py`, `tests/bet_maker/test_bet_routes.py` — references из AUDIT.md (D-18..D-22).

### External references

- `.planning/research/ARCHITECTURE.md` — ссылка из README §Architecture для глубокой топологии (DOC-02).
- `.planning/research/PITFALLS.md` §«Looks Done But Isn't» — источник 18-item checklist для AUDIT.md (D-18). §«Pitfall-to-Phase Mapping» — для cross-reference в README §Reliability.
- `.planning/research/STACK.md` — pinned versions, упомянутые в README §Development (опционально).
- Shields.io static badge URL spec — для D-16 coverage badge.
- FastAPI `openapi_examples` v2 API — для D-08 (Pydantic v2 syntax).
- FastStream `RabbitRouter.docs_url='/asyncapi'` — default value, упоминается в D-10.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **FastAPI app factories** — `src/{line_provider,bet_maker}/app.py::build_app()` уже имеют `FastAPI(title=..., version="0.1.0")`. Polish добавляет `description=...` без структурной правки (D-06).
- **APIRouter с tags=** — все 3 router'а на сервис (`api/bets.py`, `api/events.py`, `api/health.py`) уже имеют `tags=["..."]`. Добавляем только `summary=` + `responses=` (D-07).
- **Pydantic schemas** — `BetRead`, `EventRead`, `BetCreate`, `EventCreate` — уже `extra="forbid"` + `frozen=True`. Новая `ErrorDetail` строится по тому же паттерну (D-09).
- **CI workflow** (`.github/workflows/ci.yml`) — ruff + mypy + pytest steps уже на месте; D-15 — точечное расширение pytest step.
- **Coverage config** (`pyproject.toml [tool.coverage.*]`) — `source`, `branch=true`, `fail_under=85`, `exclude_lines` — на месте. CLI-инвокацию pytest нужно дополнить `--cov`.
- **Schema parity contract test** (`tests/contract/test_event_finished_message_schema.py`, P5 D-29) — переиспользуется в AUDIT.md (D-19).
- **Existing e2e tests** — `test_e2e_rabbitmq.py` (consumer happy + poison→DLQ) и `test_reconciliation_e2e.py` (drop-publish + cancel) — references для AUDIT.md без новых тестов (D-21/D-22).
- **`.env.example`** — на месте; в README §Quick start ссылка `cp .env.example .env`.
- **structlog с `bind_contextvars` / `clear_contextvars`** — упомянуто в README §Reliability как защита от cross-task contamination (A7).

### Established Patterns

- **Single Russian docs** — все `.planning/*.md` и `CLAUDE.md` content — на русском (за исключением кода/файловых путей). README соблюдает (D-01).
- **`extra="forbid"` + `frozen=True`** на Pydantic schemas — `ErrorDetail` пишется так же (D-09).
- **Sync-task в первом плане фазы** (P2 02-01, P3 03-01, P4 04-01, P5 05-10, P6 06-01) — Phase 7 повторяет (D-23).
- **Lazy-loaded artifacts (`.planning/phases/{N}-*/`)** — `07-AUDIT.md` живёт там же по конвенции (D-18); CONTEXT/DISCUSSION-LOG/PLAN/SUMMARY рядом.
- **Static analysis в pytest** — нет существующего прецедента, но `tests/audit/` — новая, изолированная директория (D-19); не загрязняет существующие unit/integration test packages.
- **No emojis в docs/code** — `CLAUDE.md` §«Custom rules» — README редактирование строго без эмодзи (даже декоративных).

### Integration Points

- `README.md` — единая точка финальной редакции (D-01..D-05).
- `.github/workflows/ci.yml` pytest step — расширяется `--cov` (D-15).
- `src/{line_provider,bet_maker}/app.py` — FastAPI `description=` (D-06).
- `src/{line_provider,bet_maker}/entrypoints/api/*.py` — route `summary` + `responses` + `Body(examples=...)` (D-07..D-09).
- `src/{line_provider,bet_maker}/schemas/errors.py` (новый) — `ErrorDetail` (D-09).
- `tests/audit/__init__.py` + `tests/audit/test_static.py` (новые) — D-19.
- `.planning/phases/07-polish-documentation/07-AUDIT.md` (новый) — D-18 таблица 18 items.
- `pyproject.toml` — НЕ меняется в Phase 7 (coverage уже настроен); кроме `[tool.pytest.ini_options] addopts` можно опционально добавить `--strict-config` (но не обязательно).
- `Dockerfile`, `docker-compose.yml`, `alembic.ini`, `alembic/versions/*.py` — НЕ меняются (D-19 audit-tests читают их, не правят).
- `src/bet_maker/{schemas,interactors,repositories,facades,entrypoints/messaging.py}` — НЕ меняются (mypy strict уже зелёный по P1..P6; D-12 audit — проверка `# type: ignore`).

</code_context>

<specifics>
## Specific Ideas

- **README primary language = Russian** — соответствует существующим артефактам, ТЗ и CLAUDE.md.
- **6-stroke ASCII-диаграмма** — LP↔reviewer, LP→RMQ, RMQ→BM, RMQ→DLX, BM→PG, BM→LP reconciler-stroke; компактная, читается за 10 секунд.
- **5-step Reviewer walkthrough** — без `GET /events` отдельным шагом (compact).
- **Coverage gate = 85%** — выше ROADMAP-минимума, совпадает с current pyproject.
- **Shields.io static badge** — не codecov.
- **`tests/audit/test_static.py`** — отдельная test-директория для audit-static-checks (regex/AST).
- **`07-AUDIT.md` отдельный артефакт** — таблица 18 items + Status + Evidence; не вклеивается в CONTEXT.md.
- **CANCELLED extension** упоминается явно в README §Reliability + ссылка на REQUIREMENTS BM-05 (D-05).
- **No new runtime features** — только docs / OpenAPI / coverage / audit / mypy cleanup.

</specifics>

<deferred>
## Deferred Ideas

- **TTL cache для `GET /events`** — отложено в P4 D-01. README §Next-step extensions упоминает одной строкой.
- **Codecov / Coveralls интеграция** — overkill для test-task. Shields.io static badge достаточен. Future hardening — отдельный milestone.
- **AsyncAPI snapshot в репо** (`docs/asyncapi.json`) — `/asyncapi` endpoint достаточен; offline-копия — opt-in одной curl-командой в README §Next-step extensions.
- **English README перевод** — single Russian primary; English summary не нужен для test-task reviewer'а (русскоязычный).
- **Prometheus / OpenTelemetry / Grafana** — v2 OBS-01..03 в REQUIREMENTS; out of scope.
- **`Idempotency-Key` header / API versioning / Rate limiting / RFC7807 errors** — v2 API-01..04 в REQUIREMENTS; out of scope.
- **Quorum queues / Outbox / Saga** — v2 REL-01..03; out of scope.
- **Multi-region / Kubernetes / Helm-charts** — out of scope.
- **mypy strict на тестах** — pragmatic послабление в pyproject (`disallow_untyped_defs = false` override). Не убираем.
- **EventState parity test между line_provider/schemas/events.EventState и bet_maker/schemas/events.EventState** — упомянуто как P6 deferred; реально это уже покрыто общим контрактом через `EventFinishedMessage.new_state` parity (P5 D-29). Можно опционально добавить отдельный тест на `EventState` enum equality в `tests/audit/test_static.py`, но это nice-to-have.
- **README на отдельной branch / docs/ subdir с MkDocs** — overkill, single README в репозитории достаточен.

### Reviewed Todos (not folded)

None — no open todos in this project (`gsd-sdk query todo.match-phase 7` returned empty per init).

</deferred>

---

*Phase: 07-polish-documentation*
*Context gathered: 2026-05-18*
