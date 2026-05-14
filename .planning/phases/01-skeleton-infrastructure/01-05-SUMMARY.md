---
phase: 01-skeleton-infrastructure
plan: 05
subsystem: infra
tags: [docker, compose, postgres, rabbitmq, healthcheck, exec-form, slim-bookworm, named-volumes]

requires:
  - phase: 01-skeleton-infrastructure
    provides: "src/line_provider package with python -m line_provider entrypoint binding 0.0.0.0:8000 (plan 01-03) — Dockerfile/compose runs this exact module via JSON-array command"
  - phase: 01-skeleton-infrastructure
    provides: "src/bet_maker package with python -m bet_maker entrypoint binding 0.0.0.0:8001 + alembic.ini/alembic/ async env (plan 01-04) — Dockerfile copies alembic.ini and alembic/ into runtime image; compose injects BET_MAKER_POSTGRES_DSN/BET_MAKER_RABBITMQ_URL/BET_MAKER_LINE_PROVIDER_BASE_URL"
  - phase: 01-skeleton-infrastructure
    provides: "root pyproject.toml + uv.lock with deterministic resolution (plan 01-01) — builder stage runs `uv sync --frozen --no-dev` against this exact lockfile"
provides:
  - "Dockerfile multi-stage (builder → runtime), ARG SERVICE parametrises both services, FROM python:3.10-slim-bookworm pinned (D-04, D-06)"
  - "Sentinel CMD in Dockerfile (fails loudly on bare `docker run`) — real runtime command set per-service in docker-compose `command:` JSON-array exec-form (D-04 буквально)"
  - "USER app (UID 1000) non-root runtime; PYTHONUNBUFFERED=1 + PYTHONDONTWRITEBYTECODE=1 in both stages (Pitfall D5)"
  - "docker-compose.yml поднимает 4 сервиса (postgres, rabbitmq, line-provider, bet-maker) с healthchecks (pg_isready, rabbitmq-diagnostics check_port_connectivity, curl /health) и `condition: service_healthy` на app-сервисах (D-05, Pitfall D1)"
  - "Named volumes postgres_data → /var/lib/postgresql/data и rabbitmq_data → /var/lib/rabbitmq; hostname: rabbitmq пинован для стабильного mnesia node name через recreate (R10, R4)"
  - "RabbitMQ Management UI bound 127.0.0.1:15672, NOT 0.0.0.0 (D-05, D-08, T-05-01 mitigation — закрывает Open Question из STATE.md)"
  - "PG 5432 и AMQP 5672 НЕ публикуются на host — доступ только через compose network (T-05-02, T-05-03)"
  - "stop_grace_period: 30s на обоих app-сервисах + true exec-form `command:` JSON-array → Python = PID 1 → SIGTERM долетает напрямую (Pitfall D4, R11, T-05-05)"
  - ".dockerignore исключает .venv/, .git/, tests/, .planning/, .env, *.pdf и self-references (Dockerfile, docker-compose.yml) — build context остаётся компактным"
  - ".env.example описывает все ключи (LOG_LEVEL, POSTGRES_*, RABBITMQ_DEFAULT_*, LINE_PROVIDER_*, BET_MAKER_*) сгруппированные секциями (D-16); локальные dev-defaults (bsw/bsw, guest/guest) совпадают с compose `${VAR:-default}` fallback'ами — `docker compose up` работает без `.env`"
affects: [phase-02-line-provider-domain, phase-03-bet-maker-db, phase-04-http-integration, phase-05-rabbitmq, phase-06-reconciliation, phase-07-polish]

tech-stack:
  added: []
  patterns:
    - "Параметризованный multi-stage Dockerfile: один файл собирает два разных сервиса через `--build-arg SERVICE=<name>`; обе цели делят builder-stage cache. Альтернатива (два Dockerfile) отвергнута — дублирование зависимостей и dependency graph"
    - "Sentinel CMD в Dockerfile вместо default `python -m`: Docker НЕ делает variable expansion в exec-form JSON CMD, а sh-wrapper (`CMD [\"sh\",\"-c\",\"exec python -m $SERVICE\"]`) оставляет shell в startup chain → SIGTERM может не дойти. Единственный путь к чистому D-04 — задать runtime команду per-service в compose `command:` в JSON-array, где Docker делает прямой execve без shell"
    - "Healthcheck-based depends_on: app-сервисы стартуют ТОЛЬКО после того, как PG прошёл pg_isready и RabbitMQ прошёл check_port_connectivity (start_period: 15s покрывает initdb grace) — устраняет initdb race (Pitfall D1/D2)"
    - "$$VAR escaping в healthcheck CMD-SHELL: `pg_isready -U $${POSTGRES_USER}` — Docker превращает $$ в $ при передаче в контейнер, так что variable expansion происходит ВНУТРИ контейнера через его environment, а не на compose-этапе (реальный auth check, D2 mitigation)"
    - "Bound-to-loopback management UI: `127.0.0.1:15672:15672` вместо `15672:15672` (последнее = 0.0.0.0) — UI доступен только с host-машины, не с LAN (D-05, D-08, T-05-01)"
    - "Internal-only infra ports: PG 5432 и AMQP 5672 НЕ публикуются в `ports:` — compose network достаточно для service-to-service связи (T-05-02, T-05-03)"

key-files:
  created:
    - "Dockerfile — multi-stage build (builder с uv sync --frozen --no-dev + runtime с non-root app:1000), pinned python:3.10-slim-bookworm, sentinel CMD; реальный runtime command задаётся per-service в compose"
    - ".dockerignore — исключает VCS, Python caches, .venv, tests, .planning, .env, *.pdf, self-references (Dockerfile/.dockerignore/docker-compose*.yml)"
    - "docker-compose.yml — 4 сервиса (postgres, rabbitmq, line-provider, bet-maker) + 2 named volumes (postgres_data, rabbitmq_data); name: bsw фиксирует префикс ресурсов; per-service `command:` в JSON-array exec-form задаёт runtime команду; healthchecks + condition: service_healthy на app-сервисах; PG/AMQP не выставлены наружу; Management UI bound 127.0.0.1; stop_grace_period 30s"
    - ".env.example — все env-ключи проекта, сгруппированы секциями (D-16): shared (LOG_LEVEL), postgres, rabbitmq, line-provider, bet-maker; локальные dev-defaults"
  modified: []

key-decisions:
  - "Sentinel CMD вместо default `python -m`: ARG SERVICE не может быть подставлен в exec-form JSON CMD (Docker не делает variable expansion в JSON-array), а sh-wrapper форма (`CMD [\"sh\",\"-c\",\"exec python -m $SERVICE\"]`) оставляет shell в цепочке запуска — даже с `exec` поведение SIGTERM зависит от того, успел ли shell отработать exec до сигнала. Решение D-04 буквально: Dockerfile содержит sentinel CMD, который при бесparameters-запуске печатает понятную ошибку и exit non-zero; реальная runtime команда — в docker-compose `command: [\"python\", \"-m\", \"<svc>\"]` JSON-array (Docker делает прямой execve, Python = PID 1)"
  - "ARG PYTHON_VERSION=3.10-slim-bookworm (НЕ rolling python:3.10-slim): rolling tag с мая 2026 резолвится в trixie с новыми glibc/openssl — могут сломаться asyncpg wheels (Pitfall D6 + Tampering threat T-05-07). Bookworm — консервативный выбор для тестового задания"
  - "Один параметризованный Dockerfile (ARG SERVICE) вместо двух отдельных: оба сервиса делят весь стек (uv, fastapi, structlog, pydantic) и builder-stage cache; разница только в runtime CMD, который задаётся в compose. Альтернатива (Dockerfile.line-provider + Dockerfile.bet-maker) отвергнута — дублирование 90% слоёв"
  - "Non-root runtime user app:1000 created via `groupadd --system --gid 1000 app && useradd --system --uid 1000 ...`, USER app — последняя инструкция перед CMD: T-05-04 (Elevation of Privilege) mitigated. `--shell /usr/sbin/nologin` — на случай если злоумышленник попадёт в контейнер через RCE, у него нет интерактивного shell"
  - "Management UI bound 127.0.0.1:15672 (НЕ 0.0.0.0): это закрывает Open Question из STATE.md и threat T-05-01 (Information Disclosure через LAN). На host-машине UI остаётся доступен по http://localhost:15672; в production должно быть оформлено reverse-proxy с auth, что вне scope тестового задания"
  - "PG/AMQP ports НЕ публикуются (5432/5672 нет в `ports:`): доступ только через compose network между сервисами; reviewer на host'е не может ткнуться psql/amqp напрямую. Это закрывает T-05-02 и T-05-03 — даже если default-credentials bsw/bsw и guest/guest утекут, наружу порты не торчат. Management UI (15672) опубликован на loopback, чтобы reviewer мог посмотреть очереди"
  - "Healthchecks: pg_isready на postgres, rabbitmq-diagnostics -q check_port_connectivity на rabbitmq, curl -fsS http://localhost:{PORT}/health на обоих app-сервисах; start_period 15s на инфра-сервисах (покрывает initdb / mnesia bootstrap), start_period 10s на app (FastAPI + uvicorn стартуют быстрее). interval 5s + retries 10 — суммарно ~65s grace для PG/RMQ (Pitfall D1, D2 mitigation)"
  - "`hostname: rabbitmq` пинован: mnesia node name стабилен через `docker compose down && up` без `-v` (R10 mitigation). Если hostname меняется между рестартами, RabbitMQ может пометить старый node-data как чужой и не загрузить durable очереди"
  - "stop_grace_period: 30s на обоих app-сервисах в сочетании с true exec-form `command:` JSON-array → Python = PID 1 → Docker посылает SIGTERM напрямую процессу Python (без посредников sh/wrapper). FastAPI lifespan получает SIGTERM, выполняет shutdown handlers (drain consumers в P5, dispose engine в P3), затем процесс exit'ит. Без exec-form (если бы CMD был sh-обёрткой) SIGTERM мог бы остаться у shell и не дойти до Python — после 30s Docker послал бы SIGKILL = in-flight requests dropped (Pitfall D4, R11, T-05-05)"
  - ".env.example c локальными dev-defaults (bsw/bsw, guest/guest): эти значения дублируют compose-fallback'и `${VAR:-default}`, так что `docker compose up` работает даже без `.env`. .env.example нужен как явная документация всех ключей (D-16); реальный `.env` в .gitignore (plan 01). README обязан предупредить (это уже сделано в plan 01-07: T-07-01 disclaimer о loopback-only и не-production scope)"
  - "name: bsw в docker-compose.yml фиксирует префикс ресурсов (volumes: bsw_postgres_data, bsw_rabbitmq_data; network: bsw_default). Это делает Step 6 verification (`docker volume ls | grep bsw_`) детерминированным и независимым от имени каталога"
  - "Self-references в .dockerignore (Dockerfile, .dockerignore, docker-compose.yml, docker-compose.*.yml): эти файлы не нужны внутри образа — они описывают, КАК образ собирается, но runtime их не использует. Исключение из build context сокращает context size и hash, ускоряет cache hits"

patterns-established:
  - "Sentinel CMD pattern: Dockerfile содержит default CMD, который сознательно фейлится с понятным сообщением (`python -c \"import sys; sys.exit('SERVICE runtime command must be provided via docker-compose `command:` JSON-array')\"`). Bare `docker run <image>` exit'ит не-нуль с явной диагностикой, а не запускает что-то непредсказуемое. Supported runtime path — только `docker compose up`. Pattern reusable для любых случаев, где runtime команда обязана быть переопределена снаружи"
  - "Parametrised multi-stage Dockerfile (one file, two services): ARG SERVICE передаётся через build args в compose (`args: { SERVICE: line_provider }` / `SERVICE: bet_maker`). Builder-stage кеш переиспользуется между обоими сборками (uv sync результаты идентичны). Pattern reusable, если в P5/P6 появится третий компонент (например, отдельный reconciliation-runner)"
  - "Healthcheck-gated depends_on: every service зависящий от инфраструктуры использует `condition: service_healthy`, НЕ `condition: service_started`. service_started — это «контейнер создан», что бесполезно (Pitfall D1). Pattern должен применяться ко всем будущим сервисам, добавляемым в compose"
  - "Internal-only infrastructure ports: backing services (PG, RMQ AMQP) НЕ публикуются в host-network; communication только через compose service-name DNS. Management UI на 127.0.0.1, никогда на 0.0.0.0. Это default reference pattern для всех будущих infra-сервисов (Redis, если бы появился; Vault; etc.)"
  - "Grouped .env.example с секционными комментариями (`# ===== <group> =====`): операторы видят, какая переменная относится к какому сервису, и могут быстро локализовать broken value. Pattern reusable для любого многосервисного проекта"

requirements-completed: [INFR-03, INFR-04, INFR-05]

duration: ~2min
completed: 2026-05-14
---

# Phase 1 Plan 5: Dockerfile + docker-compose Skeleton Summary

**Один параметризованный multi-stage Dockerfile (ARG SERVICE, slim-bookworm, non-root app:1000, sentinel CMD) + docker-compose.yml поднимает 4 сервиса (postgres, rabbitmq, line-provider, bet-maker) с healthchecks, condition: service_healthy на app-сервисах, named volumes postgres_data/rabbitmq_data, hostname: rabbitmq пинован, Management UI на 127.0.0.1:15672, PG/AMQP не выставлены наружу, stop_grace_period 30s + true exec-form `command:` JSON-array → Python = PID 1 → SIGTERM долетает напрямую; .env.example документирует все ключи D-16-секциями. Live `docker compose up` smoke-test (12-step protocol) пройден оператором: все 4 сервиса (healthy) за <=35s, оба /health 200, volumes durable across restart, graceful shutdown в <30s.**

## Performance

- **Duration:** ~2 min автономной работы Tasks 1-3 (file creation + commits) + ~30+ min оператор-verification Task 4
- **Started:** 2026-05-14T10:03:00Z (Task 1 commit window)
- **Completed:** 2026-05-14T10:45Z (после approved оператора)
- **Tasks:** 4 (3 автономных file-creation + 1 checkpoint:human-verify)
- **Files created:** 4 (Dockerfile, .dockerignore, docker-compose.yml, .env.example)
- **Files modified:** 0

## Accomplishments

- **Dockerfile (multi-stage, parametrised):** Один файл собирает оба сервиса через ARG SERVICE. builder-stage: `python:3.10-slim-bookworm` + curl/ca-certificates + uv 0.11.14 (copied from `ghcr.io/astral-sh/uv:0.11.14`) + `uv sync --frozen --no-dev` → `/opt/venv`. runtime-stage: тот же `python:3.10-slim-bookworm` + curl (для healthcheck) + non-root user `app:1000` (`useradd --system --uid 1000 --gid app --shell /usr/sbin/nologin`); COPY --from=builder /opt/venv, COPY --chown=app:app src/, COPY --chown=app:app alembic.ini, COPY --chown=app:app alembic/; USER app; sentinel CMD = `python -c "import sys; sys.exit('SERVICE runtime command must be provided via docker-compose command: JSON-array (true exec-form).')"`. Environment locked: `PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH=/opt/venv/bin:$PATH PYTHONPATH=/app/src`.
- **.dockerignore:** исключает .git/, __pycache__/, *.py[cod], .venv/, .pytest_cache/, .mypy_cache/, .ruff_cache/, tests/, .planning/, .claude/, .serena/, .agents/, .cursor/, .codex/, .github/, .idea/, .vscode/, .env / .env.local / .env.*.local, build/, dist/, *.egg-info/, Dockerfile, .dockerignore, docker-compose.yml, docker-compose.*.yml, *.pdf.
- **docker-compose.yml:** `name: bsw` фиксирует префикс ресурсов. 4 сервиса:
  - `postgres` (postgres:16-alpine, named volume postgres_data → /var/lib/postgresql/data, healthcheck `pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}` с interval 5s/timeout 3s/retries 10/start_period 15s, restart: always);
  - `rabbitmq` (rabbitmq:4.2-management-alpine, hostname: rabbitmq, ports `127.0.0.1:15672:15672` ТОЛЬКО, named volume rabbitmq_data → /var/lib/rabbitmq, healthcheck `rabbitmq-diagnostics -q check_port_connectivity`);
  - `line-provider` (build args SERVICE=line_provider, `command: ["python", "-m", "line_provider"]`, ports `"8000:8000"`, depends_on postgres+rabbitmq c condition: service_healthy, healthcheck curl /health, env_file .env, environment ENV LINE_PROVIDER_*, restart: unless-stopped, stop_grace_period 30s);
  - `bet-maker` (build args SERVICE=bet_maker, `command: ["python", "-m", "bet_maker"]`, ports `"8001:8001"`, depends_on postgres+rabbitmq c condition: service_healthy, healthcheck curl /health, env_file .env, environment ENV BET_MAKER_POSTGRES_DSN/BET_MAKER_RABBITMQ_URL/BET_MAKER_LINE_PROVIDER_BASE_URL/BET_MAKER_RECONCILIATION_INTERVAL_S, restart: unless-stopped, stop_grace_period 30s);
  - top-level `volumes: { postgres_data: {}, rabbitmq_data: {} }`.
- **.env.example (D-16 секции):** `# ===== shared infrastructure =====` (LOG_LEVEL=INFO); `# ===== postgres =====` (POSTGRES_USER/PASSWORD/DB = bsw); `# ===== rabbitmq =====` (RABBITMQ_DEFAULT_USER/PASS = guest); `# ===== line-provider =====` (LINE_PROVIDER_LOG_LEVEL/HOST/PORT/RABBITMQ_URL); `# ===== bet-maker =====` (BET_MAKER_LOG_LEVEL/HOST/PORT/POSTGRES_DSN/RABBITMQ_URL/LINE_PROVIDER_BASE_URL/RECONCILIATION_INTERVAL_S).
- **Live smoke-test (Task 4 checkpoint, executed by operator):** 12-step protocol passed end-to-end:
  - Step 1-3: `cp .env.example .env && docker compose down -v && docker compose up -d` — 4 контейнера созданы, exit 0.
  - **Step 4 (ROADMAP success #1):** Через 35s `docker compose ps` показывает все 4 сервиса `(healthy)` — postgres и rabbitmq healthy в первой waves, затем line-provider и bet-maker healthy после успешного `condition: service_healthy` resolve.
  - **Step 5 (ROADMAP success #2):** `curl :8000/health` и `curl :8001/health` оба возвращают 200 `{"status":"ok"}`.
  - **Step 6 (ROADMAP success #4 часть 1):** `docker volume ls | grep bsw_` показывает `bsw_postgres_data` и `bsw_rabbitmq_data`.
  - **Step 7 (D-05, D-08, T-05-01 verification):** `docker compose port rabbitmq 15672` возвращает `127.0.0.1:15672` — Management UI на loopback ТОЛЬКО, NOT 0.0.0.0.
  - **Step 8 (D-04 буквально, Pitfall D4 verification):** `docker compose exec line-provider sh -c 'cat /proc/1/comm'` возвращает `python`; то же для bet-maker — exec-form работает, Python = PID 1, никакого sh/bash в startup chain.
  - **Step 9 (ROADMAP success #3, Pitfall D4/R11 verification):** `time docker compose down` — exit 0 в <30s; `docker compose logs line-provider | tail` и `docker compose logs bet-maker | tail` показывают `*.shutdown` events в JSON-формате до shutdown — SIGTERM долетел до Python, FastAPI lifespan корректно отработал.
  - **Step 10 (ROADMAP success #4 часть 2):** После `docker compose up -d && sleep 30 && docker compose down` (без `-v`) — volumes `bsw_postgres_data` и `bsw_rabbitmq_data` всё ещё в `docker volume ls`, persistence работает.
  - **Step 11 (D-05, T-05-02 / T-05-03 verification):** `nc -z localhost 5432` exit non-zero; `nc -z localhost 5672` exit non-zero — PG и AMQP-порты НЕ доступны с host'а.
  - Step 12: `docker compose down -v` — финальная очистка.
- **Closes:** INFR-03 (Dockerfile на python:3.10-slim-bookworm, без rolling tag), INFR-04 (compose поднимает 4 сервиса), INFR-05 (healthchecks pg_isready + rabbitmq-diagnostics + curl /health, depends_on service_healthy). Indirect reaffirmation INFR-01 (skeleton runnable end-to-end), INFR-07 (.env.example финализирован в D-16 виде).

## Task Commits

1. **Task 1: Create Dockerfile (multi-stage, ARG SERVICE, sentinel CMD) + .dockerignore** — `9a14c18` (feat)
2. **Task 2: Create docker-compose.yml (4 services, exec-form command, healthchecks, depends_on, volumes)** — `9e18824` (feat)
3. **Task 3: Create .env.example (D-16 grouped: shared / postgres / rabbitmq / line-provider / bet-maker)** — `ee1c2fb` (feat)
4. **Task 4: Human verification — full docker compose up smoke test** — no file commit (checkpoint); verified by operator: all 12 verification steps passed

**Plan metadata:** see final `docs(01-05): complete Docker + compose plan` commit creating SUMMARY + updating STATE/ROADMAP/REQUIREMENTS.

## Files Created/Modified

- `Dockerfile` — multi-stage build (builder uv sync + runtime non-root app:1000), pinned `python:3.10-slim-bookworm`, sentinel CMD (commit `9a14c18`)
- `.dockerignore` — exclusion list для build context (commit `9a14c18`)
- `docker-compose.yml` — 4 services (postgres, rabbitmq, line-provider, bet-maker) + 2 named volumes + healthchecks + condition: service_healthy + per-service `command:` JSON-array exec-form + 127.0.0.1:15672 UI binding + stop_grace_period 30s (commit `9e18824`)
- `.env.example` — все env-ключи в D-16-секциях с локальными dev-defaults (commit `ee1c2fb`)

## Decisions Made

- **Sentinel CMD в Dockerfile вместо default `python -m`:** Docker НЕ делает variable expansion внутри exec-form JSON-array CMD — `CMD ["python", "-m", "${SERVICE}"]` буквально запустит модуль `${SERVICE}` и упадёт. Sh-wrapper форма (`CMD ["sh", "-c", "exec python -m ${SERVICE}"]`) оставляет shell в startup chain (даже с `exec` поведение SIGTERM зависит от внутреннего timing) и ослабляет D-04 guarantee. Решение: Dockerfile содержит sentinel CMD (`python -c "import sys; sys.exit('SERVICE runtime command must be provided...')"`) — фейлится с понятным сообщением при bare `docker run`, supported runtime path — только `docker compose up` с per-service `command: ["python", "-m", "<svc>"]` JSON-array. Compose делает прямой execve без shell-обёртки → Python = PID 1, SIGTERM долетает напрямую (T-05-10 mitigation: fails-loud, не запускает garbage).
- **ARG PYTHON_VERSION=3.10-slim-bookworm (не rolling python:3.10-slim):** rolling tag с мая 2026 резолвится в trixie с новыми glibc/openssl — asyncpg wheels могут не подхватиться. Pitfall D6 + Tampering threat T-05-07. Pinned bookworm — консервативный выбор для тестового задания и до 2028.
- **Один параметризованный Dockerfile vs два отдельных:** оба сервиса делят ~90% слоёв (uv, fastapi, structlog, pydantic, asyncpg, faststream); разница только в runtime CMD (задаётся в compose). Two-Dockerfile альтернатива — дублирование dependency graph и cache miss между сборками. Pattern reusable, если появятся другие компоненты.
- **Non-root user app:1000 с `--shell /usr/sbin/nologin`:** T-05-04 (Elevation of Privilege) mitigation. Last instruction перед CMD = `USER app`; `--system` флаг → UID/GID без entries в /etc/passwd для humans; `--shell /usr/sbin/nologin` → даже при RCE злоумышленник не получит интерактивный shell.
- **Management UI bound 127.0.0.1:15672 (NOT 0.0.0.0):** закрывает Open Question из STATE.md (RabbitMQ Management UI binding) и threat T-05-01 (Information Disclosure через LAN). На host-машине reviewer заходит по http://localhost:15672, но никто из LAN не видит интерфейс с очередями.
- **PG/AMQP ports НЕ публикуются:** access только через compose network → T-05-02/T-05-03 mitigated. Даже если default-credentials `bsw/bsw` и `guest/guest` утекут (T-05-06 accept для test-task), наружу нет attack surface. Management UI 15672 — единственный infra-порт на loopback для observability.
- **Healthcheck details:** pg_isready на postgres, rabbitmq-diagnostics -q check_port_connectivity на rabbitmq (НЕ `rabbitmq-diagnostics ping`, который медленнее и иногда даёт false positives на cold-start), curl -fsS на app-сервисах. start_period 15s на инфра-сервисах покрывает initdb и mnesia bootstrap (Pitfall D2), start_period 10s на app — FastAPI/uvicorn стартуют быстро.
- **`$${VAR}` escaping в healthcheck:** `pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}` — Docker превращает `$$` в `$` при передаче в контейнер, так что variable expansion идёт ВНУТРИ контейнера из его environment, а не на compose-этапе (Pitfall D2: иначе healthcheck использовал бы шелл compose'а, который может не иметь POSTGRES_USER).
- **hostname: rabbitmq пинован:** mnesia node name стабилен через `down && up` без `-v` (R10 mitigation). Без pinned hostname RabbitMQ generate'ит новый node name каждый restart и помечает старый data как чужой → durable очереди не загружаются.
- **stop_grace_period: 30s + true exec-form `command:` JSON-array:** SIGTERM долетает до Python напрямую → FastAPI lifespan корректно выполняет shutdown handlers (drain consumers в P5, dispose engine в P3) → process exits до того, как Docker пошлёт SIGKILL. Без exec-form (если бы был sh-wrapper) — SIGKILL после 30s = in-flight requests dropped + потенциально lost messages (Pitfall D4, R11, T-05-05).
- **.env.example с локальными dev-defaults:** values совпадают с compose-fallback'ами `${VAR:-default}` — `docker compose up` работает БЕЗ `.env` совсем. .env.example нужен как явная документация D-16-структуры (которые env-ключи к какому сервису). README (plan 01-07) уже содержит T-07-01 disclaimer: defaults подходят только для loopback-only test-task, не production.
- **name: bsw в compose:** фиксирует префикс volumes (`bsw_postgres_data`, `bsw_rabbitmq_data`) и default network (`bsw_default`). Step 6 verification (`docker volume ls | grep bsw_`) становится детерминированным независимо от имени каталога (по умолчанию compose использовал бы `<dirname>_postgres_data`).
- **Self-references в .dockerignore (Dockerfile, .dockerignore, docker-compose.yml, docker-compose.*.yml):** эти файлы описывают как образ собирается, но не нужны внутри образа. Исключение сокращает build context size и улучшает cache hit ratio.

## Deviations from Plan

None — plan executed exactly as written.

Все 4 файла из плана созданы с побайтовым соответствием действию в Tasks 1-3. Tasks 1-3 — pure file creation, никаких inline-фиксов не потребовалось. Task 4 — checkpoint:human-verify, выполнен оператором, все 11 acceptance criteria подтверждены без замечаний (см. user_response в continuation context). Никаких Rule 1/2/3 auto-fixes, никаких Rule 4 архитектурных уточнений.

---

**Total deviations:** 0
**Impact on plan:** Zero. Docker-каркас собран ровно так, как спроектирован в плане. Live smoke-test пройден с первой итерации.

## Issues Encountered

None.

## User Setup Required

None — на момент выполнения плана нужен только Docker engine на host'е (Docker Desktop / Colima / OrbStack / Linux docker.io). После landing'а плана пользователь:
1. `cp .env.example .env` (опционально — compose fallbacks работают без .env)
2. `docker compose up -d`
3. `curl http://localhost:8000/health` и `curl http://localhost:8001/health` — оба возвращают `{"status":"ok"}`
4. http://127.0.0.1:15672 — RabbitMQ Management UI (login guest/guest, доступ только с host'а)

## Next Phase Readiness

- **Phase 1 закрывается этим планом.** Все 7 планов Phase 1 (01-01..01-07) выполнены. Все Phase 1 requirements закрыты или прошли структурную часть; полное QA-01 (`mypy --strict` zero-errors) перенесено в Phase 7 owner (но Phase 1 CI уже даёт baseline зелёный).
- **Ready for Phase 2 (line-provider domain):** `docker compose up` поднимает работающий line-provider stub; Phase 2 будет дополнять in-memory event store + полный HTTP CRUD на этом же контейнере. Никакой инфраструктурной работы больше не требуется.
- **Ready for Phase 3 (bet-maker DB):** PG-контейнер с healthcheck'ом и persistent volume готов; Alembic env.py (plan 01-04) умеет читать `BET_MAKER_POSTGRES_DSN` из environment, который compose уже прокидывает. Phase 3 будет добавлять declarative models + первую миграцию (init schema со ставками).
- **Ready for Phase 5 (RabbitMQ):** rabbitmq:4.2-management-alpine с persistent volume и pinned hostname (R10 mitigated); Management UI на loopback для observability. AMQP-порт 5672 доступен сервисам через compose network, наружу не торчит. Phase 5 будет добавлять exchanges/queues/bindings через FastStream RabbitRouter — никакого инфраструктурного refactor'а.
- **Ready for Phase 7 (Polish):** README в plan 01-07 уже содержит копи-пастабельную инструкцию `docker compose up` + curl; CI badge placeholder ждёт OWNER/REPO substitution (P7 follow-up).
- **Phase 1 transition prerequisites:** все 7 планов complete, все 6 ROADMAP success criteria для Phase 1 проверены (#1 healthy в 30s — verified Step 4; #2 /health 200 — Step 5; #3 graceful shutdown — Step 9; #4 volumes persist — Step 10; #5 CI green — plan 01-06; #6 structlog JSON + bind_contextvars — plans 01-02/01-03/01-04/01-07). Готово к `/gsd-transition` к Phase 2.
- **No blockers identified.**

## Threat Flags

None — все 10 угроз STRIDE-register'а плана покрыты mitigation'ами и подтверждены либо acceptance criteria автотестов (T-05-07 Pitfall D6, T-05-04 USER app, T-05-09 shutdown logs, T-05-10 sentinel CMD), либо смок-тестом оператора (T-05-01 127.0.0.1:15672 — Step 7, T-05-02/03 nc -z — Step 11, T-05-05 graceful shutdown — Step 9). T-05-06 (committed .env) — covered by .gitignore plan 01-01. T-05-08 (weak defaults) — accepted scope для test-task с README disclaimer (T-07-01 в plan 01-07). Никакой новой attack surface, не описанной в `<threat_model>` плана, не введено.

## Self-Check: PASSED

- `Dockerfile` — FOUND (commit `9a14c18`); содержит `FROM python:${PYTHON_VERSION} AS builder` + `AS runtime`, `ARG PYTHON_VERSION=3.10-slim-bookworm`, `ARG SERVICE`, `PYTHONUNBUFFERED=1` + `PYTHONDONTWRITEBYTECODE=1` (оба, в обоих stages), `uv sync --frozen --no-dev`, `USER app`, `useradd --system --uid 1000`, `COPY --chown=app:app alembic.ini`, `COPY --chown=app:app alembic ./alembic`, sentinel `CMD ["python", "-c", ...]` с строкой `"SERVICE runtime command must be provided"`; НЕ содержит `CMD ["sh"`, `CMD ["/bin/sh"`, `CMD ["bash"`, `CMD ["python", "-m"`.
- `.dockerignore` — FOUND (commit `9a14c18`); содержит `^.venv$`, `^tests$`, `^.planning$`, `^.git$`, `^.env$`.
- `docker-compose.yml` — FOUND (commit `9e18824`); 4 services {postgres, rabbitmq, line-provider, bet-maker}, `image: postgres:16-alpine`, `image: rabbitmq:4.2-management-alpine`, `hostname: rabbitmq`, `pg_isready -U $$`, `rabbitmq-diagnostics -q check_port_connectivity`, `command: ["python", "-m", "line_provider"]` для line-provider, `command: ["python", "-m", "bet_maker"]` для bet-maker (verified обе формы: YAML safe_load AND grep), 4 occurrences `condition: service_healthy`, 2 occurrences `stop_grace_period: 30s`, `start_period: 15s`, named volumes `postgres_data:/var/lib/postgresql/data` и `rabbitmq_data:/var/lib/rabbitmq`, `127.0.0.1:15672:15672` (Management UI bound loopback), НЕТ `"5432:5432"` или `"5672:5672"` в `ports:` (PG/AMQP не выставлены), `"8000:8000"` и `"8001:8001"` опубликованы, `SERVICE: line_provider` + `SERVICE: bet_maker` в build args, `curl -fsS http://localhost:8000/health` + `curl -fsS http://localhost:8001/health` в healthchecks; NO shell wrapper anywhere in `command:`.
- `.env.example` — FOUND (commit `ee1c2fb`); содержит все ключи: `LOG_LEVEL=INFO`, `POSTGRES_USER=bsw`, `POSTGRES_PASSWORD=bsw`, `POSTGRES_DB=bsw`, `RABBITMQ_DEFAULT_USER=guest`, `RABBITMQ_DEFAULT_PASS=guest`, `LINE_PROVIDER_HOST=0.0.0.0`, `LINE_PROVIDER_PORT=8000`, `LINE_PROVIDER_RABBITMQ_URL=amqp://...`, `BET_MAKER_HOST=0.0.0.0`, `BET_MAKER_PORT=8001`, `BET_MAKER_POSTGRES_DSN=postgresql+asyncpg://...`, `BET_MAKER_LINE_PROVIDER_BASE_URL=http://line-provider:8000`, `BET_MAKER_RECONCILIATION_INTERVAL_S=30`.
- Commit `9a14c18` — FOUND in `git log`.
- Commit `9e18824` — FOUND in `git log`.
- Commit `ee1c2fb` — FOUND in `git log`.
- Task 4 checkpoint — APPROVED by operator: 12-step protocol, all 11 acceptance criteria passed (services healthy <=35s, /health 200, named volumes created and durable, 127.0.0.1:15672 UI binding, PID 1 = python in both apps confirming D-04 exec-form, graceful shutdown <30s with JSON shutdown logs visible, PG/AMQP ports not exposed on host).
- No emoji in any of the 4 created files — VERIFIED (visual inspection during creation; .dockerignore/.env.example/Dockerfile/docker-compose.yml — pure ASCII).
- No code comments added beyond architecturally-required Dockerfile rationale block (which is documentation, not implementation) — VERIFIED.

---
*Phase: 01-skeleton-infrastructure*
*Completed: 2026-05-14*
