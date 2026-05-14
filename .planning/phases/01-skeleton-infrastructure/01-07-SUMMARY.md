---
phase: 01-skeleton-infrastructure
plan: 07
subsystem: testing-docs
tags: [tests, asgi-transport, httpx, pytest-asyncio, readme, infr-08, qa-10]

requires:
  - phase: 01-skeleton-infrastructure
    provides: "build_app() factories for both services (plan 01-03 + 01-04); RequestContextMiddleware echoing X-Request-ID (plan 01-03 + 01-04); pyproject.toml with [tool.pytest.ini_options] asyncio_mode=auto, pythonpath=['src'], testpaths=['tests'] from plan 01-01"
provides:
  - "tests/ tree per D-12: root conftest + line_provider/ + bet_maker/ + e2e/ (empty package, populated in P6)"
  - "Reusable per-service `client` fixture pattern (httpx.AsyncClient + ASGITransport(app=build_app())) — entire test suite from P2 onward will reuse this shape"
  - "test_health_returns_status_ok (×2 services) — QA-10 HTTP smoke proof"
  - "test_health_echoes_request_id_header (×2 services) — INFR-08 HTTP-level E2E proof (only HTTP-level INFR-08 test in P1)"
  - "README.md stub per D-14: Quick start, Development, Architecture/Reliability TODO, CI badge (OWNER/REPO placeholder), explicit guest:guest disclaimer (loopback-only, test-task scope, not for production)"
  - "`uv run pytest -q` exits 0 → CI plan-01-06 pytest step now has 4 green tests to execute (QA-10 closed)"
affects: [phase-02-line-provider-domain, phase-03-bet_maker-domain-and-db, phase-04-http-integration, phase-05-rabbitmq, phase-06-reconciliation, phase-07-polish]

tech-stack:
  added: []
  patterns:
    - "ASGITransport in-process testing: httpx.AsyncClient(transport=ASGITransport(app=build_app()), base_url='http://test') — zero docker, zero live PG/RMQ. The canonical client fixture for the whole project."
    - "Per-service conftest with @pytest_asyncio.fixture async generator yielding AsyncClient — exit-side `async with` cleans up the transport on every test"
    - "Test docstrings cite requirement IDs (QA-10, INFR-08) so traceability survives grep — `grep -q INFR-08 tests/{service}/test_health.py` is part of acceptance criteria"
    - "INFR-08 HTTP-level E2E via response-header assertion — proves both bind_contextvars (request_id flows in) and echo path (response.headers['X-Request-ID']) without coupling tests to structlog internals (those are unit-validated in plan 02 sanity-only)"
    - "guest:guest disclaimer placed immediately after Management UI URL — reviewer sees credentials and constraint together (T-07-01 mitigation)"

key-files:
  created:
    - "tests/__init__.py — empty package marker"
    - "tests/conftest.py — root conftest stub (one-line docstring per D-12; shared fixtures will land here starting P3)"
    - "tests/line_provider/__init__.py — empty package marker"
    - "tests/line_provider/conftest.py — `client` fixture (httpx AsyncClient + ASGITransport) wired to line_provider.app.build_app"
    - "tests/line_provider/test_health.py — 2 tests: test_health_returns_status_ok (QA-10), test_health_echoes_request_id_header (INFR-08)"
    - "tests/bet_maker/__init__.py — empty package marker"
    - "tests/bet_maker/conftest.py — `client` fixture wired to bet_maker.app.build_app (zero-copy from line_provider with import swap)"
    - "tests/bet_maker/test_health.py — 2 tests mirroring line_provider"
    - "tests/e2e/__init__.py — empty E2E package marker (populated in P6 reconciliation E2E tests)"
  modified:
    - "README.md — expanded from a 5-line placeholder (created in plan 01-01 to satisfy `readme = README.md` in pyproject.toml) into the D-14 stub (Quick start, Development, Architecture TODO, Reliability TODO, CI badge, guest:guest disclaimer, Project status table)"

key-decisions:
  - "Two tests per service, not one: the second test (`test_health_echoes_request_id_header`) is the *only* HTTP-level E2E proof of INFR-08 in P1; without it, INFR-08 reduces to a unit-only signal from plan 02 (configure_structlog processors). The plan explicitly separates layers — log structure is unit, X-Request-ID propagation through middleware is E2E."
  - "Reqs-in-docstrings: every test docstring opens with the requirement ID it covers (QA-10 or INFR-08). This is the only zero-config way to keep traceability grep-able as the suite grows (`grep -r 'INFR-08' tests/` will always show all coverage points)."
  - "Empty tests/e2e/__init__.py shipped in P1, not P6: D-12 calls for the structural tree to exist up-front. Adding the directory later would be a Wave-N retrofit; adding it empty now is structural clarity."
  - "README CI-badge uses OWNER/REPO placeholder, not a real owner/repo: this repo is not yet on GitHub (no `git remote add`); the badge URL would 404 anyway. Documenting as a P7 follow-up (1-line search-replace once remote is configured) avoids hiding the badge in a comment and signals intent visually."
  - "README's `docker compose up -d` flow points at .env.example + docker-compose.yml which are being added in parallel plan 01-05 (Wave 4). The two plans are independent waves of the same phase — by Phase 1 close, both will have landed. Documenting the canonical flow now (rather than after 01-05) keeps the README structurally complete."
  - "No emoji enforcement validated programmatically: a regex over the entire emoji block range, not a hand-curated list, runs against every test file and README in self-check. This catches accidental U+1F600-family additions during future edits."

patterns-established:
  - "`client` fixture per-service: every test in this project will import this pattern. P2's line-provider domain tests will add a second fixture (`event_store_seeded`) that wraps `client` — the building-block compounds without forcing a re-architecture."
  - "Requirement IDs in docstrings: a project-wide convention for trace-by-grep. Future plans (P3, P5, P6) MUST cite REQ-IDs in test docstrings."
  - "ASGI in-process only in P1: no docker, no live PG, no live RMQ. Integration tests that DO require live infrastructure (P5 queue contract test, P6 reconciliation race test) will live under tests/e2e/ and be marked `@pytest.mark.integration` to keep `uv run pytest -q` fast (deferred to P5/P6 plans)."

requirements-completed: [QA-10, INFR-08]

duration: 2min
completed: 2026-05-14
---

# Phase 1 Plan 7: Tests Skeleton + README Stub Summary

**Тестовый каркас по D-12 (root conftest + per-service + пустой e2e) и README stub по D-14. Закрывает QA-10 (pytest зелёный — теперь есть что запускать) и INFR-08 (HTTP-level E2E проверка request-id propagation через RequestContextMiddleware: 4 теста, 2 per service, X-Request-ID echo assertion). README — точка входа ревьюера: Quick start с curl на оба /health, guest:guest disclaimer с loopback-binding оговоркой, Architecture/Reliability TODO-ссылки на research/.**

## Performance

- **Duration:** ~2.5 min (~148 s)
- **Started:** 2026-05-14T09:56:22Z
- **Completed:** 2026-05-14T09:58:50Z
- **Tasks:** 2 (atomic-committed)
- **Files created:** 9 (tests/) + 1 README expansion = 10 file touches
- **Files modified:** 1 (README.md — 5-line placeholder → full D-14 stub)

## Accomplishments

- `tests/` дерево создано полностью по D-12: root `conftest.py` (stub с docstring под shared-fixtures P3+), три подпакета `line_provider/`, `bet_maker/`, `e2e/` (последний пустой, заполнится в P6).
- Canonical `client` fixture pattern зафиксирован в обоих per-service conftest'ах:
  ```python
  @pytest_asyncio.fixture
  async def client() -> AsyncIterator[AsyncClient]:
      app = build_app()
      transport = ASGITransport(app=app)
      async with AsyncClient(transport=transport, base_url="http://test") as ac:
          yield ac
  ```
  Этот же паттерн будет переиспользован во всех последующих фазах — единственное отличие per-service это `from {service}.app import build_app`.
- `tests/line_provider/test_health.py` и `tests/bet_maker/test_health.py` идентичны по структуре, по 2 теста каждый:
  - `test_health_returns_status_ok` — QA-10: 200 OK + body `{"status":"ok"}`.
  - `test_health_echoes_request_id_header` — INFR-08 HTTP-level E2E: header `X-Request-ID` присутствует и непустой. **Это единственная HTTP-level E2E проверка INFR-08 в P1**: если кто-то ломает `RequestContextMiddleware` (например, забывает `bind_contextvars` или `response.headers["X-Request-ID"] = ...`), эти два теста краснеют немедленно.
- Каждое test-docstring открывается с требуемого REQ-ID — `grep -r "INFR-08" tests/` и `grep -r "QA-10" tests/` всегда покажут все точки покрытия (трассировка-по-grep, project-wide конвенция).
- `uv run pytest -q` → `4 passed in 0.17s` — все 4 теста зелёные. CI step из plan 01-06 теперь имеет что выполнить (QA-10 closed).
- `uv run mypy --strict tests/` → `Success: no issues found in 9 source files`.
- `uv run ruff check tests/` → `All checks passed!`.
- `uv run ruff format --check tests/` → `9 files already formatted`.
- README.md расширен с 5-строчного плейсхолдера (созданного в plan 01-01 чтобы `readme = README.md` в pyproject.toml не падал) до полноценного D-14 stub:
  - H1 + tagline + ссылки на PROJECT.md / ROADMAP.md.
  - `## Quick start` с `docker compose up -d` + `docker compose ps` + curl на оба `/health` + Management UI URL `http://127.0.0.1:15672`.
  - **Guest:guest disclaimer** (T-07-01 mitigation): отдельный `> Note:` блок прямо после Management UI URL, explicitly указывает: test-credentials only, loopback binding на 127.0.0.1, AMQP-порт 5672 не публикуется наружу, **«НЕ предназначены для production»**.
  - `## Development`: uv sync, uv run для python -m line_provider/bet_maker, ruff/mypy/pytest, pre-commit install, alembic upgrade head.
  - `## Architecture` и `## Reliability`: каждая — explicit TODO с ссылкой на research/ARCHITECTURE.md, как требует D-14.
  - CI badge: `![ci](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)` — OWNER/REPO placeholder; реальные значения подставит автор после `git remote add` (логировано как P7 follow-up).
  - Project status таблица (7 фаз, текущий статус — Phase 1 in progress).
- Никаких emoji в test-файлах или README (regex-проверка над всем Unicode emoji block range — `[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E0-\U0001F1FF]`).
- Никаких комментариев в коде тестов (project hard rule: «DO NOT ADD COMMENTS»); docstrings разрешены и используются для трассировки REQ-ID.

## Task Commits

1. **Task 1: ASGITransport smoke tests for both /health endpoints (9 test files)** — `1a1e2f6` (test)
2. **Task 2: README stub with Quick start, Development, TODO sections + guest:guest disclaimer** — `2994260` (docs)

## Files Created/Modified

- `tests/__init__.py` — empty package marker (Task 1)
- `tests/conftest.py` — root conftest one-line docstring (Task 1, D-12)
- `tests/line_provider/__init__.py` — empty (Task 1)
- `tests/line_provider/conftest.py` — `client` fixture wired to `line_provider.app.build_app` (Task 1, D-11)
- `tests/line_provider/test_health.py` — 2 tests: QA-10 + INFR-08 (Task 1)
- `tests/bet_maker/__init__.py` — empty (Task 1)
- `tests/bet_maker/conftest.py` — `client` fixture wired to `bet_maker.app.build_app` (Task 1, D-11)
- `tests/bet_maker/test_health.py` — 2 tests mirroring line_provider (Task 1)
- `tests/e2e/__init__.py` — empty E2E package (Task 1, D-12; populated in P6)
- `README.md` — 5-line placeholder → full D-14 stub (Task 2)

## Decisions Made

- **Two tests per service (not one)**: `test_health_returns_status_ok` is QA-10; `test_health_echoes_request_id_header` is the *only* HTTP-level E2E proof of INFR-08 in the whole P1. Without the second test, INFR-08 collapses to a unit-level signal (configure_structlog processor order, validated in plan 02 — not E2E). Cost: 4 LoC per service. Reward: requirement gets E2E-grade evidence.
- **Reqs-in-docstrings convention**: each test docstring opens with the requirement ID. Project-wide convention established here; future plans (P3, P5, P6) MUST follow. Trace-by-grep is the cheapest possible coverage matrix.
- **Empty `tests/e2e/__init__.py` shipped now, not later**: D-12 specifies the directory tree up-front. Creating it empty in P1 is structural clarity; creating it in P6 would be a retrofit.
- **README's `docker compose up -d` flow points at .env.example + docker-compose.yml not yet existing locally**: parallel plan 01-05 (Wave 4) is creating them. By Phase 1 close both will have landed. Documenting the canonical Quick start in this plan (rather than waiting for 01-05) keeps the README structurally complete and reviewers happy: by the time anyone clones the repo, both plans are merged.
- **CI badge with OWNER/REPO placeholder**: this repo is local-only (no `git remote add` yet); a real `github.com/<owner>/<repo>` URL would 404. Placeholder is honest, visible (not hidden in HTML comment), and tracked as a 1-line P7 follow-up.
- **Empty `tests/__init__.py`** (not absent): with `pythonpath=['src']` in pyproject.toml and `testpaths=['tests']`, pytest discovers tests by file path, but having `__init__.py` files makes `tests/...` importable as a package — relevant if any future test imports from a sibling test module (e.g. shared helpers). The cost is zero; the future-proofing is real.
- **Conftest doc-strings, not bare comments**: project hard rule "DO NOT ADD COMMENTS". Docstrings are not comments — they are first-class objects (`module.__doc__`). Test-function docstrings double as requirement traces and as pytest verbose-mode output (`pytest -v` prints them).

## Deviations from Plan

None — plan executed exactly as written.

Все 10 файлов из `files_modified` фронтматтера созданы/обновлены. Все acceptance criteria обеих задач выполнены с первой итерации. Никаких Rule 1/2/3 auto-fixes не потребовалось: код тестов прошёл pytest, mypy --strict, ruff check, ruff format --check без замечаний. README прошёл все grep-based acceptance checks (включая case-insensitive вариант для «не предназначены для production» — заглавная «НЕ» в финальном тексте требует `grep -qi`, что плановое acceptance явно допускает как «robust grep alternative»).

---

**Total deviations:** 0
**Impact on plan:** Zero. Каркас тестов сразу готов к P2/P3 — следующие тесты добавляют новые test-файлы рядом с `test_health.py` и переиспользуют `client` fixture.

## Issues Encountered

None.

## User Setup Required

None — `uv run pytest -q` запускается сразу после `uv sync --frozen`; не требует docker/PG/RMQ. README ссылается на docker-compose.yml и .env.example, которые ещё не существуют в этом коммите — они создаются в parallel plan 01-05 (Wave 4 этой же фазы). По завершении Phase 1 оба артефакта на месте, и README Quick start работает end-to-end.

## Next Phase Readiness

- **Phase 1 Wave 4 status:** 01-07 complete; 01-05 (Dockerfile + docker-compose) выполняется параллельно — после её завершения Phase 1 закроется (`/gsd-transition`).
- **Phase 2 (line-provider domain):** ready — есть paзверзутый `client` fixture, который домен-тесты переиспользуют; новые тесты для facades/interactors/selectors добавятся как `tests/line_provider/test_<thing>.py` рядом с `test_health.py`. Конвенция `REQ-ID в docstrings` зафиксирована и должна продолжаться.
- **Phase 3 (bet-maker domain + DB):** ready — нужно будет добавить `tests/conftest.py` fixtures для `AsyncEngine` + `AsyncSession` (с фабрикой PostgreSQL контейнера в docker для CI или sqlite-in-memory для local). Это первая фаза, где root `conftest.py` начнёт реально использоваться.
- **Phase 5 (RabbitMQ):** ready — integration-тесты против `TestRabbitBroker` (in-memory) появятся как новые файлы рядом с handler-кодом; для E2E против реального RabbitMQ — `tests/e2e/` начнёт заполняться (помеченные `@pytest.mark.integration` чтобы не замедлять обычный `uv run pytest -q`).
- **Phase 6 (Reconciliation):** ready — `tests/e2e/test_reconciliation_recovers_pending_bets.py` будет ключевым тестом core-value инварианта; пакет уже на месте.
- **Phase 7 (Polish):** P7 действия по этому плану:
  1. Заменить `OWNER/REPO` в CI badge на реальный GitHub-owner/repo после `git remote add`.
  2. Заменить `## Architecture` TODO на реальный текст (sourced from research/ARCHITECTURE.md), указанное как DOC-01/02.
  3. Заменить `## Reliability` TODO на реальные гарантии (durable, manual ack, DLQ, reconciliation, `FOR UPDATE SKIP LOCKED`) — DOC-03/04.
- **No blockers identified.**

## TDD Gate Compliance

Plan frontmatter is `type: execute`, Task 1 помечен `tdd="true"`, Task 2 `tdd="false"`.

По существу Task 1 — это **GREEN gate first**: production-код (`build_app()`, `RequestContextMiddleware` echo) был написан в планах 01-03 / 01-04 как scaffold с inline ASGI-smoke-проверками. Этот план их **формализует** в proper pytest-suite. RED-фаза де-юре была в момент написания этого плана: до scaffold'а (до коммитов `a8dfc1c` для line_provider и `5f2b74c` для bet_maker) этих тестов невозможно было ни coll'ировать, ни запустить. GREEN gate в этом плане — `uv run pytest -q` → `4 passed`. REFACTOR gate — не нужен (тесты простые, изначально написаны в финальной форме).

Если же требовать строгий гит-уровневый RED-GREEN порядок: gate sequence для этого плана не порождает отдельного `test(...)` коммита перед `feat(...)` — потому что `feat` уже произошёл в плане 01-03/01-04. Коммит `1a1e2f6 test(01-07): ...` следует за двумя `feat`-коммитами из waves 1-3; он удовлетворяет GREEN-проверке сразу.

Task 2 (README) не требует TDD — это документация.

## Known Stubs

- **README CI badge с `OWNER/REPO` placeholder** — будет заменено на реальный GitHub-owner/repo в P7 после `git remote add`. Документировано как P7 follow-up в этом саммари.
- **README `## Architecture` секция** — пока explicit TODO со ссылкой на research/ARCHITECTURE.md. Заполняется в P7 (DOC-01/02).
- **README `## Reliability` секция** — пока explicit TODO. Заполняется в P7 (DOC-03/04).
- **`tests/e2e/__init__.py` пустой** — package marker, контент появится в P6 (reconciliation E2E тест).
- **`tests/conftest.py` — только docstring** — shared fixtures (AsyncEngine, AsyncSession, и т.п.) добавятся начиная с P3.

Все «stubs» — структурные placeholders с явной ссылкой на будущий план/фазу заполнения; ни один не блокирует Phase 1 success criteria.

## Threat Flags

None — поверхность атаки полностью покрыта `<threat_model>` плана и не вводит новых:

- **T-07-01** (Information Disclosure: README leaks `guest/guest` без context): **mitigated** — `> Note:` блок про test-credentials стоит непосредственно после Management UI URL; явно указаны loopback binding, scope=local-dev, прямой запрет на production. Reviewer видит credentials и constraint вместе, разделение невозможно.
- **T-07-02** (Tampering: tests pass локально, fail в CI без env): **mitigated** — ASGITransport не требует env vars; `BetMakerSettings` и `LineProviderSettings` имеют дефолты для всех полей (plan 01-03 / 01-04); CI workflow plan 01-06 запускает `uv run pytest -q` без extra env vars.
- **T-07-03** (Spoofing: CI badge указывает на неверный repo): **accept** — OWNER/REPO placeholder; не security issue, presentation gap; P7 follow-up.
- **T-07-04** (Information Disclosure: tests log structlog events с request_id как PII?): **accept** — request_id это uuid4().hex, никакой identity binding нет; structlog JSONRenderer выводит structured events; в P1 нет запроса с реальными bodies (только /health GET).
- **T-07-05** (Repudiation: INFR-08 X-Request-ID echo silently broken): **mitigated** — `test_health_echoes_request_id_header` per service ассертит presence + non-empty; HTTP-level E2E доказательство, что middleware echo path работает.

## Self-Check: PASSED

- `tests/__init__.py` — FOUND (commit `1a1e2f6`)
- `tests/conftest.py` — FOUND (commit `1a1e2f6`)
- `tests/line_provider/__init__.py` — FOUND (commit `1a1e2f6`)
- `tests/line_provider/conftest.py` — FOUND (commit `1a1e2f6`)
- `tests/line_provider/test_health.py` — FOUND (commit `1a1e2f6`)
- `tests/bet_maker/__init__.py` — FOUND (commit `1a1e2f6`)
- `tests/bet_maker/conftest.py` — FOUND (commit `1a1e2f6`)
- `tests/bet_maker/test_health.py` — FOUND (commit `1a1e2f6`)
- `tests/e2e/__init__.py` — FOUND (commit `1a1e2f6`)
- `README.md` — FOUND (commit `2994260` — modified from plan 01-01 placeholder)
- Commit `1a1e2f6` — FOUND in `git log`
- Commit `2994260` — FOUND in `git log`
- `uv run pytest -q` — `4 passed in 0.17s` — VERIFIED
- `uv run mypy --strict tests/` — `Success: no issues found in 9 source files` — VERIFIED
- `uv run ruff check tests/` — `All checks passed!` — VERIFIED
- `uv run ruff format --check tests/` — `9 files already formatted` — VERIFIED
- `grep -q "ASGITransport" tests/line_provider/conftest.py` — match — VERIFIED
- `grep -q "ASGITransport" tests/bet_maker/conftest.py` — match — VERIFIED
- `grep -q "from line_provider.app import build_app" tests/line_provider/conftest.py` — match — VERIFIED
- `grep -q "from bet_maker.app import build_app" tests/bet_maker/conftest.py` — match — VERIFIED
- `grep -q "INFR-08" tests/line_provider/test_health.py` — match — VERIFIED
- `grep -q "INFR-08" tests/bet_maker/test_health.py` — match — VERIFIED
- `grep -q "test_health_echoes_request_id_header" tests/line_provider/test_health.py` — match — VERIFIED
- `grep -q "test_health_echoes_request_id_header" tests/bet_maker/test_health.py` — match — VERIFIED
- README sections: H1, Quick start, Development, Architecture, Reliability — all present — VERIFIED
- README `docker compose up -d`, `curl -s http://localhost:8000/health`, `curl -s http://localhost:8001/health`, `uv sync`, `uv run ruff check`, `uv run mypy src`, `uv run pytest -q`, `workflows/ci.yml/badge.svg`, `127.0.0.1:15672`, `guest:guest`, `TODO` — all match — VERIFIED
- README guest:guest disclaimer present (case-insensitive «не предназначены для production» + «test-credentials RabbitMQ») — VERIFIED
- No emojis in any test file or README (regex over full Unicode emoji blocks) — VERIFIED
- No code comments in test files (only docstrings, project hard-rule honoured) — VERIFIED

---
*Phase: 01-skeleton-infrastructure*
*Completed: 2026-05-14*
