---
phase: 07-polish-documentation
plan: 10
type: execute
wave: 4
depends_on: [02, 03, 04, 05, 06, 07, 08, 09]
files_modified:
  - README.md
autonomous: true
requirements: [DOC-01, DOC-02, DOC-03, DOC-04]
must_haves:
  truths:
    - "README.md has a Shields.io coverage badge (https://img.shields.io/badge/coverage-85%25-brightgreen.svg)"
    - "README.md has a Reviewer walkthrough section with 5-step copy-paste curl sequence (create event -> place bet -> finish event -> sleep -> get bets)"
    - "README.md Architecture section contains a 6-stroke ASCII diagram (LP <-> reviewer, LP -> RMQ, RMQ -> BM, RMQ -> DLX, BM -> PG, BM -> LP reconciler) and links to .planning/research/ARCHITECTURE.md"
    - "README.md Reliability section enumerates 6 defence-in-depth mechanisms with file references AND includes a dedicated CANCELLED-extension paragraph linking to REQUIREMENTS.md BM-05 and PITFALLS.md"
    - "README.md Development section retains existing uv/pytest/ruff/mypy/pre-commit commands AND adds local coverage invocation"
    - "README.md Next-step extensions section mentions TTL cache (P4 deferred), Prometheus/Grafana, AsyncAPI snapshot, codecov as opt-in"
    - "README.md Project status table shows 7/7 phases complete"
    - "No emojis in README.md (CLAUDE.md rule)"
  artifacts:
    - path: "README.md"
      provides: "Final Russian README per CONTEXT.md D-01..D-05"
      min_lines: 150
      contains: "Reviewer walkthrough"
  key_links:
    - from: "README.md §Architecture"
      to: ".planning/research/ARCHITECTURE.md"
      via: "markdown link"
      pattern: "\\.planning/research/ARCHITECTURE\\.md"
    - from: "README.md §Reliability"
      to: ".planning/research/PITFALLS.md and REQUIREMENTS.md BM-05"
      via: "markdown link + reference"
      pattern: "PITFALLS\\.md|BM-05"
---

<objective>
Final README pass per CONTEXT.md D-01..D-05. Single Russian primary README, no emojis (CLAUDE.md). Sections (fixed order per D-02):
1. Header + 2 badges (CI + Shields.io coverage) + 1-2 paragraph description
2. Quick start (extend existing block — minimal changes)
3. Reviewer walkthrough (NEW, 5-step curl sequence per D-04)
4. Architecture (DOC-02, ASCII diagram per D-03 + layers + RMQ topology + link to ARCHITECTURE.md)
5. Reliability (DOC-04, 6-point enumerated list per D-05 + CANCELLED-extension paragraph)
6. Development (DOC-03, retain existing + add coverage line)
7. Next-step extensions (one line per item: TTL cache, Prometheus/Grafana, AsyncAPI snapshot, codecov)
8. Project status (7/7 complete)

Output: rewritten README.md. No code changes. Phase 7 deliverable for DOC-01..DOC-04 lands in this single file.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/phases/07-polish-documentation/07-CONTEXT.md
@.planning/phases/07-polish-documentation/07-PATTERNS.md
@.planning/phases/07-polish-documentation/07-RESEARCH.md
@.planning/phases/07-polish-documentation/07-AUDIT.md
@.planning/research/ARCHITECTURE.md
@.planning/research/PITFALLS.md
@README.md
</context>

<threat_model>
N/A — documentation only. No code change. README content is static markdown; technical strings (URLs, command examples) are reviewer-facing instructions, not user input.
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite README.md final pass</name>
  <files>README.md</files>
  <read_first>
    - README.md (current state — preserve Quick start block verbatim; replace Architecture/Reliability TODOs; update Project status)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-01..D-05 — section content directives)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (README skeleton section)
    - .planning/phases/07-polish-documentation/07-RESEARCH.md (ASCII diagram in lines 181-208; README skeleton in lines 608-659)
    - src/bet_maker/entrypoints/messaging.py (cite exact line numbers for Reliability §1, §2, §4)
    - src/bet_maker/repositories/bets.py (cite line for Reliability §3 — FOR UPDATE SKIP LOCKED)
    - src/bet_maker/jobs/reconciler.py (cite for Reliability §5)
    - Dockerfile (cite for Reliability §6)
    - .planning/research/ARCHITECTURE.md (cross-reference link)
    - .planning/research/PITFALLS.md (cross-reference link)
  </read_first>
  <action>
    Rewrite `README.md` using the Write tool. The target structure is below — preserve existing content verbatim where indicated; replace TODO blocks with new content.

    **Critical preservation:** the existing Quick start block (`## Quick start` section, currently ~lines 9-41) must be kept verbatim — it already covers `docker compose up`, healthcheck wait, port mapping, RabbitMQ Management UI, `guest:guest` security note, and `docker compose down`. Only ADD a one-line pointer to the new Reviewer walkthrough.

    The existing Development block (currently ~lines 43-77) must be kept verbatim with one added line for local coverage invocation.

    Replace the existing TODO `## Architecture` / `## Reliability` placeholder sections with full content.

    Replace the Project status table — all 7 rows become `complete`.

    Add new sections: Reviewer walkthrough (after Quick start), Next-step extensions (after Development).

    Target file content (final pass):

    ```markdown
    # BSW Betting System

    [![ci](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
    [![coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)]()

    Тестовое задание Middle Python developer: микросервисная система приёма ставок на спортивные события. Два асинхронных сервиса (`line-provider`, `bet-maker`), интеграция через RabbitMQ, история ставок в PostgreSQL, reconciliation как защита от потерянных сообщений.

    **Core Value:** ставка никогда не остаётся в статусе PENDING после того, как событие завершилось. Вся архитектура интеграции (durable queue + manual ack + reconciliation job) подчинена этому инварианту.

    Полная архитектура: [.planning/research/ARCHITECTURE.md](.planning/research/ARCHITECTURE.md). Каталог требований: [.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md). Каталог известных pitfalls: [.planning/research/PITFALLS.md](.planning/research/PITFALLS.md).

    ## Quick start

    Запуск всего стека из корня репозитория:

    ```bash
    cp .env.example .env
    docker compose up -d
    ```

    Дождаться `(healthy)` на всех сервисах (около 30 секунд):

    ```bash
    docker compose ps
    ```

    Проверить health-эндпоинты обоих сервисов:

    ```bash
    curl -s http://localhost:8000/health   # line-provider
    curl -s http://localhost:8001/health   # bet-maker
    ```

    Оба должны вернуть `{"status":"ok"}` (для bet-maker — `{"status":"ok", "checks": {...}}`).

    RabbitMQ Management UI: http://127.0.0.1:15672 (логин/пароль: `guest` / `guest`).

    > **Note:** `guest:guest` — это дефолтные test-credentials RabbitMQ, использующиеся только в локальной разработке. Management UI забинден на `127.0.0.1` (loopback) и недоступен извне хоста; AMQP-порт 5672 не публикуется наружу. Эти credentials НЕ предназначены для production или любого non-local развёртывания — перед публичным деплоем нужно сменить и применить тонкую настройку доступа RabbitMQ.

    OpenAPI документация: http://localhost:8000/docs (line-provider) и http://localhost:8001/docs (bet-maker). AsyncAPI документация publish/consume контракта: http://localhost:8000/asyncapi и http://localhost:8001/asyncapi.

    Полный happy-path сценарий — см. раздел [Reviewer walkthrough](#reviewer-walkthrough) ниже.

    Остановить стек:

    ```bash
    docker compose down
    ```

    ## Reviewer walkthrough

    Полный happy-path сценарий «создать событие → поставить ставку → завершить событие → проверить settle» в 5 шагов (≤ 1 минуты после `docker compose up -d`):

    ```bash
    # 1. start stack (если ещё не запущен)
    cp .env.example .env && docker compose up -d

    # 2. дождаться healthy
    docker compose ps   # ожидаем (healthy) на postgres / rabbitmq / line-provider / bet-maker

    # 3. создать событие в line-provider (state=NEW по умолчанию)
    EVENT_ID=00000000-0000-0000-0000-000000000001
    curl -s -X POST http://localhost:8000/event \
      -H 'content-type: application/json' \
      -d "{\"event_id\":\"$EVENT_ID\",\"coefficient\":\"1.50\",\"deadline\":\"2030-01-01T00:00:00+00:00\"}"

    # 4. положить ставку в bet-maker
    curl -s -X POST http://localhost:8001/bet \
      -H 'content-type: application/json' \
      -d "{\"event_id\":\"$EVENT_ID\",\"amount\":\"10.00\"}"

    # 5. завершить событие FINISHED_WIN -> consumer settle -> bet становится WON
    curl -s -X PUT http://localhost:8000/event/$EVENT_ID \
      -H 'content-type: application/json' \
      -d '{"coefficient":"1.50","deadline":"2030-01-01T00:00:00+00:00","state":"FINISHED_WIN"}'

    # 6. убедиться, что ставка settled (status=WON, обычно через ~1с — consumer; reconciler — fallback)
    sleep 1
    curl -s http://localhost:8001/bets | jq '.[] | {id, status, amount}'
    ```

    Ожидаемый итог 6-го шага: `{"status": "WON", "amount": "10.00", ...}`. `settled_via` в response доступен через `GET /bet/{id}` — на happy-path equals `"consumer"`; если AMQP-сообщение потеряно, через `RECONCILIATION_INTERVAL_S` (default 30s) reconciler доводит до того же `WON` с `settled_via="reconciler"`.

    Сценарий drop-publish (демонстрация reconciler-ветки) автоматизирован в `tests/bet_maker/test_reconciliation_e2e.py` (см. Phase 6).

    ## Architecture

    ```
                      HTTP (reviewer curl)
                        |
                        v
    +----------------+   POST/PUT/GET   +----------------+
    | reviewer cli   | ---------------> | line-provider  |
    +----------------+                  |    :8000       |
                                        |  (in-memory)   |
                                        +-------+--------+
                                                | AMQP publish
                                                | exchange: bsw.events
                                                | routing: event.finished.{win|lose}
                                                v
                                        +----------------+
                                        |   RabbitMQ     | --(x-dead-letter-exchange)--> DLX -> DLQ
                                        |   :5672        |   bsw.events.dlx
                                        +-------+--------+   bet_maker.events.finished.dlq
                                                | AMQP consume
                                                | queue: bet_maker.events.finished
                                                | manual ack, prefetch=10
                                                v
    +----------------+   POST/GET /bet  +----------------+   FOR UPDATE     +----------------+
    | reviewer cli   | ---------------> |   bet-maker    | SKIP LOCKED      |  PostgreSQL    |
    +----------------+                  |    :8001       | ---------------> |    :5432       |
                                        | + reconciler   |   SELECT/UPDATE  |   (bsw DB)     |
                                        +-------+--------+                  +----------------+
                                                | HTTP GET /event/{id}
                                                | (reconciler defence-in-depth)
                                                +-----> line-provider
    ```

    **Слои** (одинаково для обоих сервисов):
    - `entrypoints/` — FastAPI routes + FastStream RabbitRouter handler + lifespan + middleware
    - `facades/` — DI-провайдеры (UoW, EventBus, http-клиенты) и Protocol-абстракции
    - `interactors/` — бизнес-операции (create_event, set_event_state, place_bet, settle_bets_for_event, cancel_bets_for_event)
    - `selectors/` — read-only запросы (get_event_by_id, list_active_events, list_bets, get_bet_by_id)
    - `repositories/` — SQLAlchemy 2.0 async-репозитории (только bet-maker; не коммитят — UoW владеет транзакцией)
    - `helpers/` — чистые функции (state-machine, quantize_amount, quantize_coefficient)
    - `schemas/` — Pydantic v2 DTO (request/response + AMQP-сообщения; ErrorDetail)
    - `infrastructure/` — engine + sessionmaker (bet-maker); in-memory store (line-provider)
    - `jobs/` — reconciliation background task (только bet-maker)
    - `messaging/` — routing keys (константы)

    **RabbitMQ топология:**
    - Exchange `bsw.events` (topic, durable). Routing key `event.finished.{win|lose}`.
    - Queue `bet_maker.events.finished` (durable, manual ack, prefetch=10). Bound через wildcard `event.finished.*`.
    - DLX `bsw.events.dlx` + DLQ `bet_maker.events.finished.dlq` для poison-сообщений (ValidationError / UnsupportedSchemaVersion / IntegrityError).

    **Unit of Work + Repository:** одна `AsyncSession` на бизнес-операцию, открывается `async_sessionmaker.begin()`, репозитории добавляют/читают, UoW коммитит на успешном выходе. `expire_on_commit=False` — после commit можно безопасно читать ORM-атрибуты.

    **Reconciliation** — `asyncio.Task` в lifespan, period = `RECONCILIATION_INTERVAL_S` (default 30s). Тянет PENDING-event_id через `BetRepository.get_pending_event_ids()`, дёргает `GET /event/{id}` у line-provider; если LP вернул FINISHED — settle через тот же `settle_bets_for_event` interactor, что и consumer; если LP вернул 404 — `cancel_bets_for_event` помечает ставки `CANCELLED`.

    Подробная топология, лестницы вызовов, и обоснования каждого решения — [.planning/research/ARCHITECTURE.md](.planning/research/ARCHITECTURE.md).

    AsyncAPI документация AMQP-контракта: `:8000/asyncapi` (publisher side) и `:8001/asyncapi` (consumer side). Генерируется FastStream автоматически из `@router.publisher` / `@router.subscriber` декораторов — никаких ручных YAML.

    ## Reliability

    Core Value: **ставка никогда не остаётся в статусе PENDING после того, как событие завершилось.** Эшелонированные защиты:

    1. **Durable queue + persistent messages.** RabbitMQ-сообщения переживают рестарт брокера. Queue `bet_maker.events.finished` и exchange `bsw.events` объявлены `durable=True`. См. `src/bet_maker/entrypoints/messaging.py` (`RabbitQueue(..., durable=True)` + `RabbitExchange(..., durable=True)`).
    2. **Manual ack ПОСЛЕ commit транзакции.** Consumer вызывает `await msg.ack()` только после успешного выхода из `async with AsyncUnitOfWork(...)`. На любом исключении до commit — `reject(requeue=False)` (poison → DLQ) или `nack`-эквивалент через выход из tenacity-retry. См. `src/bet_maker/entrypoints/messaging.py` (`ack_policy=AckPolicy.MANUAL`).
    3. **FOR UPDATE SKIP LOCKED.** При одновременной работе consumer и reconciler против одного `event_id` row-lock с `skip_locked=True` гарантирует, что один из них получает строки на settle, второй наблюдает 0 строк и идёт в no-op-ветку. Status-фильтр `WHERE status='PENDING'` довершает идемпотентность для redelivery после успешного settle. См. `src/bet_maker/repositories/bets.py::get_pending_locked`.
    4. **DLX + DLQ + bounded in-handler retries.** Poison (`ValidationError` / `UnsupportedSchemaVersion` / `IntegrityError`) → `reject(requeue=False)` → DLQ сразу. Transient (`OperationalError`, `asyncio.TimeoutError`) — 3 попытки с exponential backoff внутри handler через tenacity; на исчерпании — тоже `reject(requeue=False)` → DLQ (reconciler доберёт). `nack(requeue=True)` НЕ используется — это путь к unbounded requeue loops. См. `src/bet_maker/entrypoints/messaging.py`.
    5. **Reconciler defence-in-depth.** Если AMQP-сообщение всё-таки потерялось (broker рестарт без durable, queue не bound в нужный момент, race на startup) — `asyncio.Task` каждые `RECONCILIATION_INTERVAL_S` опрашивает line-provider, доводит PENDING-ставки до WON/LOST или CANCELLED. Loop body обёрнут в `try/except Exception:` — одна неудачная итерация не убивает worker. `/health` возвращает 503 если task мёртв. См. `src/bet_maker/jobs/reconciler.py`.
    6. **Lifespan order + SIGTERM exec-form CMD.** Lifespan поднимает PG → httpx → broker → reconciler в нужном порядке; шатдаун — в обратном. `CMD ["python", ...]` exec-form в Dockerfile + `stop_grace_period: 30s` в docker-compose обеспечивают, что SIGTERM доходит до процесса, consumer успевает дренажить in-flight сообщения, и `docker compose down` выходит чисто.

    **CANCELLED — extension сверх ТЗ.** ТЗ описывает три статуса ставки: PENDING / WON / LOST. Мы ввели четвёртый — `CANCELLED` — как recovery-статус: reconciler помечает ставки `CANCELLED`, если `GET /event/{id}` у line-provider вернул 404 (событие удалено или line-provider пересоздан без истории). Это инженерная трактовка ТЗ, явно задокументированная в [REQUIREMENTS.md](.planning/REQUIREMENTS.md) BM-05 и memory `feedback_verify_against_tz`. Без CANCELLED ставка осталась бы в PENDING навсегда, что прямо нарушает Core Value.

    Полный перечень pitfalls и их митигаций: [.planning/research/PITFALLS.md](.planning/research/PITFALLS.md). Codified-аудит «Looks Done But Isn't» с pytest-evidence по каждой проверке: [.planning/phases/07-polish-documentation/07-AUDIT.md](.planning/phases/07-polish-documentation/07-AUDIT.md).

    ## Development

    Установить зависимости (требуется `uv` 0.11.x, Python 3.10.20):

    ```bash
    uv sync
    ```

    Запустить сервисы локально (без Docker, нужны PG + RabbitMQ доступными):

    ```bash
    uv run python -m line_provider   # порт 8000
    uv run python -m bet_maker       # порт 8001
    ```

    Линтеры и тесты:

    ```bash
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy src
    uv run pytest -q
    uv run pytest -q --cov --cov-report=term-missing --cov-fail-under=85   # локальный coverage gate
    ```

    Установить pre-commit хуки в локальный clone:

    ```bash
    uv run pre-commit install
    ```

    Миграции для bet-maker:

    ```bash
    uv run alembic upgrade head
    ```

    ## Next-step extensions

    Намеренно не реализовано в v1 — упомянуто для transparency:

    - **TTL cache `GET /events`** — отложено в P4 D-01 (ТЗ кэш не требует). Готовая точка расширения — `src/bet_maker/selectors/list_active_events.py`.
    - **Prometheus / OpenTelemetry / Grafana** — v2 OBS-01..03 (см. REQUIREMENTS.md).
    - **AsyncAPI snapshot offline** — `curl :8001/asyncapi -o asyncapi.json` снимает endpoint в JSON-файл. Endpoint достаточен для онлайн-просмотра; в репо не коммитим, чтобы не дрифтить.
    - **Codecov / Coveralls динамический badge** — overkill для test-task. Сейчас static Shields.io 85%. При переходе на public Github можно добавить codecov upload step + динамический badge.
    - **`Idempotency-Key` / API versioning / Rate limiting / RFC7807** — v2 API-01..04.
    - **Quorum queues / Outbox / Saga** — v2 REL-01..03.

    ## Project status

    | Phase | Description | Status |
    |-------|-------------|--------|
    | 1 | Skeleton + Infrastructure | complete |
    | 2 | line-provider domain | complete |
    | 3 | bet-maker domain (DB) | complete |
    | 4 | bet-maker HTTP integration | complete |
    | 5 | RabbitMQ integration | complete |
    | 6 | Reconciliation job | complete |
    | 7 | Polish + Documentation | complete |
    ```

    **Important constraints during edit:**
    - **NO emojis** (CLAUDE.md rule — strict).
    - **Russian primary** (D-01). Technical identifiers (FastAPI, RabbitMQ, mypy, pytest, FOR UPDATE SKIP LOCKED) in English without translation.
    - **No `OWNER/REPO` substitution** (per RESEARCH.md Pitfall 9): the placeholder stays — test-task delivery via zip/private fork is the expected mode. If/when repo is published, badge URLs would be swapped (out of scope here).
    - **Shields.io URL format:** `https://img.shields.io/badge/coverage-85%25-brightgreen.svg` (`%25` URL-encodes `%`). Hardcoded — no codecov.
    - **6-stroke ASCII diagram** (D-03): reviewer→LP, LP→RMQ, RMQ→BM, RMQ→DLX, BM→PG, BM→LP reconciler.
    - **5-step Reviewer walkthrough** (D-04): create event / place bet / finish event / sleep / get bets.
    - **6-point Reliability list** (D-05) with file references + CANCELLED-extension paragraph (REQUIREMENTS.md BM-05 link + memory `feedback_verify_against_tz` reference).

    After write, run quick self-verification:
    - `wc -l README.md` — expect ≥ 150 lines.
    - `grep -c "^## " README.md` — expect 8 sections (header is not a section, so: Quick start, Reviewer walkthrough, Architecture, Reliability, Development, Next-step extensions, Project status — 7; plus check for any anchor section if needed).
    - `grep -F "coverage-85%25-brightgreen" README.md` — 1 line (badge).
    - `grep -F "CANCELLED" README.md` — ≥ 1 line (extension paragraph).
    - `grep -F "feedback_verify_against_tz" README.md` — 1 line.
    - `grep -F "PITFALLS.md" README.md` — ≥ 1 line.
    - `grep -F "ARCHITECTURE.md" README.md` — ≥ 1 line.
    - `grep -F "07-AUDIT.md" README.md` — ≥ 1 line.
    - `grep -cE "^\| [1-7] \| .* \| complete \|" README.md` — 7 (Project status all complete).
    - `grep -P "[\x{1F300}-\x{1F9FF}\x{2600}-\x{27BF}]" README.md` — 0 matches (no emojis).
  </action>
  <verify>
    <automated>wc -l README.md && grep -c "^## " README.md && grep -F "coverage-85%25-brightgreen" README.md && grep -cE "^\| [1-7] \| .* \| complete \|" README.md</automated>
  </verify>
  <acceptance_criteria>
    - `wc -l README.md` ≥ 150
    - `grep -c "^## " README.md` returns 7 (Quick start, Reviewer walkthrough, Architecture, Reliability, Development, Next-step extensions, Project status)
    - `grep -F "coverage-85%25-brightgreen" README.md` returns 1 line
    - `grep -F "ci.yml/badge.svg" README.md` returns 1 line (CI badge intact)
    - `grep -cE "^\| [1-7] \| .* \| complete \|" README.md` returns 7 (all 7 phases marked complete)
    - `grep -F "Reviewer walkthrough" README.md` ≥ 2 (heading + section reference)
    - `grep -F "Core Value" README.md` ≥ 1
    - `grep -F "CANCELLED" README.md` ≥ 1 (extension paragraph)
    - `grep -F "feedback_verify_against_tz" README.md` returns 1 (memory reference)
    - `grep -F "PITFALLS.md" README.md` ≥ 1 (Reliability link)
    - `grep -F "ARCHITECTURE.md" README.md` ≥ 1 (Architecture link)
    - `grep -F "07-AUDIT.md" README.md` ≥ 1 (audit table link)
    - `grep -F "FOR UPDATE SKIP LOCKED" README.md` ≥ 1
    - `grep -F "manual ack" README.md` ≥ 1 (Reliability §2)
    - `grep -F "durable" README.md` ≥ 1 (Reliability §1)
    - `grep -F "DLX" README.md` ≥ 1 (architecture + Reliability §4)
    - `grep -F "reconciler" README.md` ≥ 2 (architecture + Reliability §5)
    - `grep -F "5672:5672" README.md` returns 0 (AMQP port deliberately NOT published per existing security note)
    - `grep -F "/asyncapi" README.md` ≥ 1 (AsyncAPI endpoint mentioned)
    - No emojis (visual review on write — CLAUDE.md rule)
  </acceptance_criteria>
  <done>README.md final pass complete; 7 sections; 2 badges; ASCII diagram; 5-step walkthrough; 6-point Reliability + CANCELLED extension; 7/7 Project status complete; no emojis.</done>
</task>

</tasks>

<verification>
- `wc -l README.md` ≥ 150
- `grep -c "^## " README.md` returns 7
- `grep -F "coverage-85%25-brightgreen" README.md` returns 1
- All required substrings present (CANCELLED, feedback_verify_against_tz, PITFALLS.md, ARCHITECTURE.md, 07-AUDIT.md, FOR UPDATE SKIP LOCKED, manual ack, durable, DLX, reconciler, /asyncapi)
- All 7 phases marked `complete` in Project status table
- No emojis in file
- `uv run pytest -q` — full suite still green (no code touched)
- `uv run mypy src` — zero errors
</verification>

<success_criteria>
- README.md is single-language Russian, no emojis, ≥150 lines
- 2 badges (CI + Shields.io coverage)
- Quick start preserved verbatim; minor addition of OpenAPI/AsyncAPI URL + Reviewer walkthrough pointer
- Reviewer walkthrough is a 5-step copy-paste curl block
- Architecture has the 6-stroke ASCII diagram + layers explanation + RMQ topology
- Reliability has 6 enumerated mechanisms with src file references + CANCELLED extension paragraph + links to PITFALLS.md / 07-AUDIT.md / REQUIREMENTS.md BM-05
- Development retains existing commands + adds local coverage line
- Project status table shows all 7 phases complete
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-10-SUMMARY.md` recording:
- README.md final line count
- Section list (7 sections)
- Badge URLs (CI + coverage)
- Cross-reference links (ARCHITECTURE.md, PITFALLS.md, 07-AUDIT.md, REQUIREMENTS.md BM-05)
- Confirmation no emojis, no code changes, full test suite still green
</output>
