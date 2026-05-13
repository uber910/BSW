# Phase 1: Skeleton + Infrastructure - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 строит инфраструктурный скелет, на который опираются все последующие фазы:

- `docker compose up` поднимает 4 здоровых контейнера: `postgres`, `rabbitmq`, `line-provider`, `bet-maker` (все `(healthy)` в течение 30s)
- Оба сервиса отвечают `200 {"status":"ok"}` на `GET /health` (deep dep-pings PG/RMQ откладываются до P3/P5)
- `docker compose down` завершается с кодом 0; именованные volumes (`postgres_data`, `rabbitmq_data`) переживают перезапуск
- GitHub Actions CI прогоняет `ruff check + ruff format --check + mypy --strict + pytest` на каждом push/PR
- structlog настроен на JSON в stdout с `bind_contextvars` для request_id-пропагации

Никакой бизнес-логики: ни in-memory store (P2), ни PG-моделей (P3), ни AMQP топологии (P5).

</domain>

<decisions>
## Implementation Decisions

### Layout (single root pyproject)
- **D-01:** Один корневой `pyproject.toml`. Distribution name — `bsw`. `[tool.hatch.build.targets.wheel] packages = ["src/line_provider", "src/bet_maker", "src/config"]`. Один `uv.lock` на репозиторий. **Не** uv workspace — упрощает читаемость для ревьюера.
- **D-02:** `src/config/` — shared internal-only пакет (не отдельный distribution), содержит:
  - `logging.py` — `configure_structlog(level: str)` единый для обоих сервисов (processors=[contextvars, timestamper, add_log_level, JSONRenderer])
  - `settings_base.py` — `BaseAppSettings(BaseSettings)` родитель для `LineProviderSettings` и `BetMakerSettings` (общие поля: `log_level`, `service_name`, `env_file_encoding`)
  - `time.py` — `utc_now()` (центральная точка для `freeze_time` в тестах)
  Импорт: `from config.logging import configure_structlog`.
- **D-03:** Запуск через `python -m line_provider` и `python -m bet_maker` (`__main__.py` в каждом пакете вызывает `uvicorn.run("module.app:build_app", factory=True, host="0.0.0.0", port=…)`).

### Dockerfile + docker-compose
- **D-04:** Один `Dockerfile` в корне, multi-stage, параметризованный через `ARG SERVICE` (`line_provider` / `bet_maker`).
  - `builder` stage на `python:3.10-slim-bookworm`: установка `uv`, копирование `pyproject.toml` + `uv.lock`, `uv sync --frozen --no-dev` (только prod-зависимости).
  - `runtime` stage на `python:3.10-slim-bookworm`: копирование venv + `src/`. Non-root user `app` (UID 1000), `WORKDIR /app`, `USER app`.
  - `ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1`.
  - `CMD ["python", "-m", "${SERVICE}"]` — exec-form, чтобы SIGTERM долетел до Python (R11/D4).
  - Для bet-maker `alembic.ini` и каталог `alembic/` копируются в образ (миграции в P3 запускают `alembic upgrade head` на старте контейнера или отдельной командой; в P1 файлы существуют, миграций ещё нет).
- **D-05:** `docker-compose.yml` в корне:
  - Services: `postgres` (`postgres:16-alpine`, healthcheck `pg_isready -U bsw`, volume `postgres_data:/var/lib/postgresql/data`), `rabbitmq` (`rabbitmq:4.2-management-alpine`, `hostname: rabbitmq` (R5), healthcheck `rabbitmq-diagnostics ping`, volume `rabbitmq_data:/var/lib/rabbitmq`, порт `127.0.0.1:15672:15672` для Management UI), `line-provider`, `bet-maker`.
  - Порты: line-provider `8000:8000`, bet-maker `8001:8001`. Совпадает с curl-примером в ROADMAP success criteria.
  - PostgreSQL и RabbitMQ AMQP порты НЕ публикуются наружу (только внутри compose network); только Management UI на `127.0.0.1:15672`.
  - `depends_on: { postgres: { condition: service_healthy }, rabbitmq: { condition: service_healthy } }` на обоих app-сервисах.
  - `stop_grace_period: 30s` на обоих app-сервисах.
  - Network: один default network `bsw_default` (compose-managed).
  - `restart: unless-stopped` на app-сервисах; `restart: always` на инфра-сервисах.
  - Healthcheck на app-контейнерах: `curl -fsS http://localhost:8000/health || exit 1` (line-provider) и `http://localhost:8001/health` (bet-maker); `start_period: 10s`, `interval: 5s`, `timeout: 3s`, `retries: 3`.

### CI workflow + pre-commit
- **D-06:** Один CI workflow `.github/workflows/ci.yml`, один job `quality` на `ubuntu-latest`:
  1. `actions/checkout@v4`
  2. `astral-sh/setup-uv@v3` с `enable-cache: true` (cache key на основе `uv.lock`)
  3. `uv python install 3.10.20` (pin)
  4. `uv sync --frozen --all-extras`
  5. `uv run ruff check .`
  6. `uv run ruff format --check .`
  7. `uv run mypy src`
  8. `uv run pytest -q`
- **D-07:** CI триггеры: `on: { push: { branches: ['**'] }, pull_request: { branches: [main] } }` — на любой push и каждый PR в main.
- **D-08:** PG/RabbitMQ как `services:` в CI **не** добавляются в P1 (нет бизнес-логики, требующей их). Появятся в P3 (PG для bet-maker) и P5 (RMQ для consumer тестов).
- **D-09:** Python — single pin 3.10.20 без matrix (TZ фиксирует Python 3.10; matrix добавит шум без пользы).
- **D-10:** Pre-commit (`.pre-commit-config.yaml`) — следующий набор хуков:
  - `ruff check --fix` (locally fixable rules)
  - `ruff format`
  - `mypy --strict src` (local hook через `entry: uv run mypy --strict src`, `pass_filenames: false`, `types_or: [python, pyi]`) — стоит +5-15s на коммит, но ловит type drift до push
  - `check-merge-conflict`
  - `end-of-file-fixer`
  - `trailing-whitespace`
  - `check-yaml`
  - `check-toml`
  - `check-added-large-files`

### Tests scaffold + README
- **D-11:** В P1 один smoke-тест на каждый сервис:
  - `tests/line_provider/test_health.py` — `httpx.AsyncClient(transport=ASGITransport(app=build_app()), base_url="http://test")` → `GET /health` → ассерт `status_code == 200` и `body == {"status": "ok"}`.
  - `tests/bet_maker/test_health.py` — то же самое.
- **D-12:** Структура тестов:
  ```
  tests/
  ├── conftest.py                       # общие фикстуры (event_loop scope)
  ├── line_provider/
  │   ├── __init__.py
  │   ├── conftest.py                   # client_factory fixture
  │   └── test_health.py
  ├── bet_maker/
  │   ├── __init__.py
  │   ├── conftest.py
  │   └── test_health.py
  └── e2e/
      └── __init__.py                   # пусто в P1, заполняется в P6
  ```
- **D-13:** `pyproject.toml` тест-конфиг: `asyncio_mode = "auto"`, `pythonpath = ["src"]`, минимальный pytest-cov не настраивается до P7 (когда появится бизнес-логика для измерения покрытия).
- **D-14:** README в P1 — stub:
  - Заголовок проекта + 1-абзац описание (что это, ссылка на ТЗ)
  - Бейдж CI (статус GitHub Actions)
  - Раздел **Quick start**: `docker compose up` + `curl :8000/health` / `curl :8001/health`
  - Раздел **Architecture** — пустой с TODO ссылкой на `.planning/research/ARCHITECTURE.md`
  - Раздел **Development** — короткий `uv sync`, `uv run pytest`, `uv run ruff check`
  - Раздел **Reliability** — пустой с TODO (заполняется в P7)
  - Финальное расширение — задача P7.

### Settings и env
- **D-15:** Отдельные `Settings`-классы для каждого сервиса, наследуются от `config.settings_base.BaseAppSettings`:
  - `LineProviderSettings(BaseAppSettings)` — env_prefix=`LINE_PROVIDER_`, поля: `rabbitmq_url`, `host`, `port`.
  - `BetMakerSettings(BaseAppSettings)` — env_prefix=`BET_MAKER_`, поля: `postgres_dsn`, `rabbitmq_url`, `line_provider_base_url`, `reconciliation_interval_s` (default 30), `host`, `port`.
- **D-16:** Один корневой `.env.example` со всеми ключами, явно сгруппированный комментариями `# line-provider` / `# bet-maker` / `# shared`. В compose `env_file: .env`. Сам `.env` в `.gitignore`.

### Logging
- **D-17:** structlog настраивается в `lifespan` каждого сервиса вызовом `config.logging.configure_structlog(settings.log_level)`. processors:
  ```python
  [
      structlog.contextvars.merge_contextvars,
      structlog.processors.add_log_level,
      structlog.processors.TimeStamper(fmt="iso", utc=True),
      structlog.processors.dict_tracebacks,
      structlog.processors.JSONRenderer(),
  ]
  ```
- **D-18:** FastAPI middleware `RequestContextMiddleware` (в `entrypoints/middleware.py`) — `bind_contextvars(request_id=uuid4().hex)` на входе, `clear_contextvars()` в `finally`. Обязательно `clear_contextvars` (A7 из PITFALLS.md).

### /health endpoint в P1
- **D-19:** Тонкий handler: возвращает `{"status": "ok"}` со статусом 200 без проверок зависимостей. Сигнатура и место `entrypoints/api/health.py` уже соответствуют P3/P5, где endpoint обогащается ping'ом PG/RMQ. Подмена реализации в P3/P5 не сломает контракт.

### Claude's Discretion
- Точная структура `src/line_provider/` и `src/bet_maker/` следует ARCHITECTURE.md §«paste-ready tree»; planner может корректировать имена файлов и `__init__.py` под конвенции.
- Версия `astral-sh/setup-uv` — последняя стабильная (на момент планирования).
- Точные `interval/timeout/retries` для compose-healthcheck'ов app-сервисов — на усмотрение planner'а, если значения по умолчанию вступают в конфликт с `start_period`.
- Можно ли использовать `tool.uv.dev-dependencies` vs `[dependency-groups] dev` — выбрать актуальный синтаксис uv 0.11.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Проектные документы
- `.planning/PROJECT.md` — Core Value, Constraints, Out of Scope, Key Decisions table.
- `.planning/REQUIREMENTS.md` — 42 v1-требования; для P1 особенно INFR-01..08, QA-02, QA-03, QA-10.
- `.planning/ROADMAP.md` §«Phase 1: Skeleton + Infrastructure» — 6 success criteria, pitfalls preventing.
- `.planning/STATE.md` — текущая позиция, Open Questions, Accumulated Decisions.
- `CLAUDE.md` §«Technology Stack» — фиксация версий и Stack Patterns by Variant.
- `CLAUDE.md` §«Constraints» — ТЗ-фиксированные ограничения (Python 3.10, FastAPI, async, in-memory line-provider, docker compose up).

### Research (исследование выполнено до /gsd-discuss-phase)
- `.planning/research/STACK.md` §«Recommended Stack», §«Installation», §«Stack Patterns by Variant», §«Version Compatibility Matrix» — версии и compatibility.
- `.planning/research/STACK.md` §«FastStream + FastAPI Integration» — лайфспан-автоматизация для `fastapi>=0.112.2` (мы пинуем `>=0.115`).
- `.planning/research/ARCHITECTURE.md` §«Recommended Project Structure» — paste-ready trees для `src/line_provider/` и `src/bet_maker/`.
- `.planning/research/ARCHITECTURE.md` §«Pattern 4: FastAPI + FastStream lifespan composition» — образец `lifespan.py`.
- `.planning/research/ARCHITECTURE.md` §«Suggested Build Order — Phase 1» — детальный чек-лист.
- `.planning/research/PITFALLS.md` §«Docker / docker-compose» (D1, D2, D3, D4, D5, D6, D7, D8) — обязательные превентивные меры для P1.
- `.planning/research/PITFALLS.md` §«Pitfall A7: structlog contextvars cross-task contamination» — `clear_contextvars` шаблон, используется в middleware.
- `.planning/research/PITFALLS.md` §«Pitfall R10: docker compose down -v wipes the durable queue» — обоснование named volumes.
- `.planning/research/PITFALLS.md` §«Looks Done But Isn't» checklist — 18 пунктов, P7 верифицирует, но P1 закладывает фундамент.

### Внешний контекст
- `Тестовое задание Middle Python developer.pdf` (в корне репо) — оригинальное ТЗ.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Нет существующего кода** — это Phase 1, репозиторий пуст кроме `.planning/`, `.claude/`, `.serena/`, `CLAUDE.md`. Всё создаётся с нуля.

### Established Patterns
- Из ARCHITECTURE.md: слоистая архитектура (entrypoints / facades / interactors / selectors / helpers / schemas / infrastructure / repositories для bet-maker / models для bet-maker) — закладывается в P1 как директории-каркас, наполняется в P2-P6.
- `build_app()` factory pattern для FastAPI приложений (см. ARCHITECTURE.md §«Pattern 4»).
- `lifespan` как `@asynccontextmanager` — общая структура для обоих сервисов (заглушки в P1, реальные ресурсы в P3/P5).

### Integration Points
- В P1 ни одной реальной интеграции (PG/RMQ запускаются как контейнеры, но сервисы их не используют — только compose-healthchecks).
- P3 будет добавлять PG-engine в bet-maker `lifespan`.
- P5 будет добавлять `RabbitRouter` + broker connect в оба сервиса.

</code_context>

<specifics>
## Specific Ideas

- **Single root pyproject** — выбор пользователя; распаковано так, что packages = `['line_provider', 'bet_maker', 'config']` под `src/`. `config` — internal-only, не публикуется как distribution, но видим обоим сервисам через одно пакетное дерево.
- **Порты 8000/8001** — выбор пользователя; ровно совпадает с curl-примером в ROADMAP success criteria 2.
- **mypy в pre-commit + CI** — выбор пользователя; ранний catch type drift важнее +5-15s на коммит.
- **CI на любые push + PR в main** — выбор пользователя; полная feedback-loop на feature-ветке без зависимости от наличия PR.

</specifics>

<deferred>
## Deferred Ideas

- **PG/RabbitMQ как CI services в GH Actions** — отложено до P3 (PG для bet-maker integration) и P5 (RMQ для consumer integration). В P1 CI запускает только unit-уровень: ruff + mypy + smoke-тесты health через ASGITransport.
- **pytest-cov coverage gate** — добавляется в P7 (QA-09 ≥80%). В P1 coverage не измеряется (нет бизнес-логики).
- **`alembic upgrade head` на старте bet-maker** — отложено до P3, когда появятся миграции. В P1 `alembic.ini` уже копируется в образ для будущего использования.
- **Pre-commit `pyupgrade` через ruff UP-rules** — уже покрыто `ruff check` (rule set UP включён); отдельный hook не нужен.
- **OpenAPI tags/summaries/examples** — задача P7 (DOC-01..04). В P1 авто-сгенерированный OpenAPI содержит только `GET /health`, дополнительные метаданные не нужны.
- **README разделы Architecture/Development/Reliability полные** — задача P7. В P1 только stubs с TODO-ссылкой на `.planning/research/ARCHITECTURE.md`.
- **Idempotency-Key header на POST /bet** — REL/API-01 deferred per REQUIREMENTS.md (v2). Не в P1.
- **OpenTelemetry tracing, Prometheus metrics, Grafana** — OBS-01..03 deferred per REQUIREMENTS.md (v2). Не в P1.

</deferred>

---

*Phase: 1-Skeleton + Infrastructure*
*Context gathered: 2026-05-13*
