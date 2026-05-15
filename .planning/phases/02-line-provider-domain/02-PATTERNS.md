# Phase 2: line-provider domain — Pattern Map

**Mapped:** 2026-05-14
**Files to deliver / modify:** 21 (3 modifications + 18 new)
**Analogs found:** 21 / 21 (все имеют P1-аналог либо прямой code-example из RESEARCH.md, который сам ссылается на P1-конвенции)

Главный источник стилистики — P1 (`src/line_provider/*`, `src/config/*`, `tests/line_provider/*`). Все новые файлы следуют тем же конвенциям: `from __future__ import annotations` в шапке, абсолютные импорты `line_provider.*` / `config.*`, без `__init__.py`-экспортов (пустые `__init__.py`), без комментариев. Слоистая иерархия фиксирована в `ARCHITECTURE.md §«src/line_provider/ — paste-ready tree»` и `02-RESEARCH.md §«Recommended Project Structure»` — НЕ выдумывать новые слои.

---

## §1 File-to-analog mapping

### Modified files (P1 in place)

| Файл | Роль | P1-аналог (тот же файл) | Что переиспользовать / куда направлять diff |
|------|------|-------------------------|---------------------------------------------|
| `src/line_provider/app.py` | factory | `src/line_provider/app.py:1-19` | Добавить второй `app.include_router(events.router)` сразу после health-router (строка 17). Сохранить `add_middleware(RequestContextMiddleware)` до роутеров. Никаких новых аргументов в `FastAPI(...)`. |
| `src/line_provider/entrypoints/lifespan.py` | lifespan | `src/line_provider/entrypoints/lifespan.py:1-24` | Между `app.state.settings = settings` (строка 19) и `try: yield` создать `app.state.event_store = InMemoryEventStore()` и `app.state.event_bus: EventBus = NoopEventBus()`. Сохранить структуру `try/finally` + лог `line_provider.startup/shutdown`. D-14. |
| `tests/line_provider/conftest.py` | test fixture | `tests/line_provider/conftest.py:1-16` | **Upgrade in place** (Pitfall 1 / Pattern 7): обернуть `build_app()` в `async with LifespanManager(app):` ДО `AsyncClient`. Сохранить shape `pytest_asyncio.fixture` + `AsyncIterator[AsyncClient]` + `base_url="http://test"`. Требует dev-dep `asgi-lifespan>=2.1,<3`. |

### New files — domain core

| Новый файл | Роль | Ближайший аналог | Что переиспользовать |
|------------|------|------------------|----------------------|
| `src/line_provider/schemas/__init__.py` | package marker | `src/line_provider/entrypoints/__init__.py` (1-line empty) | Пустой файл, ровно 1 строка. |
| `src/line_provider/schemas/events.py` | schema | `src/line_provider/settings/config.py:1-22` (Pydantic + `from __future__ import annotations`) | `from __future__ import annotations`, `from pydantic import BaseModel, ConfigDict, Field` — стиль уже зафиксирован в settings/config. Дополнительно — `AwareDatetime` (Pydantic v2) + `AfterValidator` через `config.time.utc_now`. Полная структура — RESEARCH.md §«Pattern 6». |
| `src/line_provider/schemas/messages.py` | schema (AMQP body, frozen) | `src/line_provider/schemas/events.py` (этот же план) | Тот же стиль Pydantic v2, но `ConfigDict(frozen=True, extra="forbid")`. `schema_version: Annotated[int, Field(ge=1)] = 1`. D-13. |
| `src/line_provider/helpers/__init__.py` | package marker | пустые `__init__.py` в P1 | Пустой файл. |
| `src/line_provider/helpers/state_machine.py` | helper (pure function) | `src/config/time.py:1-7` (one-liner pure function) | `from __future__ import annotations`, без классов и DI, единственная экспортируемая функция. `frozenset[tuple[EventState, EventState]]` на module level. D-08. |
| `src/line_provider/infrastructure/__init__.py` | package marker | пустые `__init__.py` в P1 | Пустой файл. |
| `src/line_provider/infrastructure/store/__init__.py` | package marker | пустые `__init__.py` в P1 | Пустой файл. |
| `src/line_provider/infrastructure/store/in_memory.py` | store + domain errors | `src/line_provider/settings/config.py` (для class-shape) + RESEARCH.md §«Pattern 1» | `from __future__ import annotations`, `asyncio.Lock()` инстансово, два доменных Exception-класса в одном файле, `update()` возвращает `(new_event, previous_state)`. D-15/D-16. |
| `src/line_provider/facades/__init__.py` | package marker | пустые `__init__.py` в P1 | Пустой файл. |
| `src/line_provider/facades/event_bus.py` | facade (Protocol + Noop) | `src/line_provider/entrypoints/middleware.py:1-27` (структура `class … :` + structlog) | `typing.Protocol`, `class NoopEventBus:` с `structlog.get_logger().info(...)`. D-11. |
| `src/line_provider/facades/deps.py` | DI providers | `src/line_provider/entrypoints/api/health.py:1-10` (структура thin router-module) + RESEARCH.md §«Pattern 3» | `from fastapi import Depends, Request`. Synchronous Depends-providers читают `request.app.state.*` (A5). `StoreDep`/`EventBusDep` — `Annotated[…, Depends(…)]`. |
| `src/line_provider/interactors/__init__.py` | package marker | пустые `__init__.py` в P1 | Пустой файл. |
| `src/line_provider/interactors/create_event.py` | interactor (write, no publish) | RESEARCH.md §«Code Examples → create_event interactor» (lines 834-849) | Thin: построить frozen `Event(state=EventState.NEW)` + `store.add(event)`. Никаких HTTPException — доменное исключение выкидывается store. |
| `src/line_provider/interactors/set_event_state.py` | interactor (write + publish ordering) | RESEARCH.md §«Pattern 4» (lines 440-505) | Commit → publish strict order. Дополнительный `TransitionForbiddenError` в этом же файле. Module-level `_TERMINAL_TO_ROUTING: dict[EventState, str]`. D-12 / Anti-Pattern 2. |
| `src/line_provider/selectors/__init__.py` | package marker | пустые `__init__.py` в P1 | Пустой файл. |
| `src/line_provider/selectors/get_event_by_id.py` | selector (pure read) | `src/config/time.py:1-7` (one-liner pure function) | Просто `return await store.get_by_id(event_id)`. Без DI, без lock'ов. |
| `src/line_provider/selectors/list_active_events.py` | selector (filter read) | RESEARCH.md §«Code Examples → list_active_events selector» (lines 855-869) | `now = utc_now()` через `from config.time import utc_now` — тот же импорт, что и P1 (settings и middleware ничего другого не делают). Filter `e.state == EventState.NEW and e.deadline > now`. LP-05. |
| `src/line_provider/entrypoints/api/events.py` | route module | `src/line_provider/entrypoints/api/health.py:1-10` (структура: `router = APIRouter(tags=...)`) + RESEARCH.md §«Pattern 5» | `router = APIRouter(tags=["events"])`. Тонкие хендлеры: вызов interactor/selector, перевод доменных исключений в `HTTPException(status, detail)`. 4 роута: `POST /event`, `PUT /event/{event_id}`, `GET /event/{event_id}`, `GET /events`. D-01..D-04, D-06..D-10. |

### New files — tests

| Новый файл | Роль | Ближайший аналог | Что переиспользовать |
|------------|------|------------------|----------------------|
| `tests/line_provider/test_state_machine.py` | unit test (helper) | `tests/line_provider/test_health.py:1-29` (docstring со ссылкой на REQ-ID; `from __future__ import annotations`) | `pytest.mark.parametrize` + REQ-ID в docstring (LP-08). Без `client` fixture — pure-функция. RESEARCH.md §«Pattern 8» (lines 873-898). |
| `tests/line_provider/test_in_memory_store.py` | unit test (infrastructure) | `tests/line_provider/test_health.py:1-29` | Async-tests без HTTP (использует store напрямую). `asyncio.gather(*[store.add(...)])` сценарий + проверка `EventAlreadyExistsError`. REQ-ID в docstring (LP-01). |
| `tests/line_provider/test_create_event.py` | unit test (interactor + fake bus) | `tests/line_provider/test_health.py:1-29` | Fake `EventBus` (либо `unittest.mock.AsyncMock`, либо list-based fake). Проверка состояния store ПОСЛЕ вызова. REQ-ID в docstring. |
| `tests/line_provider/test_set_event_state.py` | unit test (interactor with publish ordering + TOCTOU) | `tests/line_provider/test_health.py:1-29` | FakeEventBus собирает вызовы; concurrent `asyncio.gather` на reverse transitions; проверка что publish вызван ровно 1 раз при двух concurrent PUT'ах (Pitfall 5). REQ-ID LP-08, D-12. |
| `tests/line_provider/test_selectors.py` | unit test (selectors) | `tests/line_provider/test_health.py:1-29` + RESEARCH.md §«Validation Architecture» | `monkeypatch.setattr("line_provider.selectors.list_active_events.utc_now", lambda: ...)` для контроля времени. Без `freezegun`. REQ-ID LP-05. |
| `tests/line_provider/test_event_routes.py` | integration test (API через httpx) | `tests/line_provider/test_health.py:1-29` (уже использует client fixture с `AsyncClient`) | Использует **обновлённую** `client` fixture (LifespanManager). Покрывает 4-route matrix: 201/200/404/409/422. Опционально — `event_store` fixture для arrange-setup напрямую через store. REQ-ID LP-03, LP-04, LP-05, LP-08, QA-05. |

---

## §2 Code excerpts (что копировать)

Все excerpts ниже — реально существующий P1-код. Применяй буквально (стиль, импорты, форматирование) с поправкой на новую семантику P2.

---

### Excerpt A — `src/line_provider/app.py:1-19` (текущий P1)

```python
from __future__ import annotations

from fastapi import FastAPI

from line_provider.entrypoints.api import health
from line_provider.entrypoints.lifespan import lifespan
from line_provider.entrypoints.middleware import RequestContextMiddleware


def build_app() -> FastAPI:
    app = FastAPI(
        title="line-provider",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    return app
```

**Применить так в P2 (`app.py`, T-XX «wire events router»):**

- Добавить импорт `from line_provider.entrypoints.api import events` рядом с импортом `health` (одна линия выше или ниже).
- Внутри `build_app()` после `app.include_router(health.router)` добавить `app.include_router(events.router)`.
- Не менять порядок `add_middleware` ↔ `include_router` (middleware регистрируется ДО роутеров — это P1-соглашение, важно для A7 double-clear).

**Diff direction:**
```diff
 from line_provider.entrypoints.api import health
+from line_provider.entrypoints.api import events
 ...
     app.include_router(health.router)
+    app.include_router(events.router)
     return app
```

---

### Excerpt B — `src/line_provider/entrypoints/lifespan.py:1-24` (текущий P1)

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from config.logging import configure_structlog
from line_provider.settings.config import LineProviderSettings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = LineProviderSettings()
    configure_structlog(settings.log_level)
    log = structlog.get_logger()
    log.info("line_provider.startup", service=settings.service_name)
    app.state.settings = settings
    try:
        yield
    finally:
        log.info("line_provider.shutdown")
```

**Применить так в P2 (`lifespan.py`, T-XX «wire event_store/event_bus singletons»):**

- Импортировать `InMemoryEventStore` и `NoopEventBus`.
- Между `app.state.settings = settings` и `try:` создать два singleton'а и положить на app.state. P5 будет менять только `event_bus`-строку.
- Сохранить структуру `try/yield/finally` и `log.info("line_provider.startup", ...)` — это P1-инвариант.

**Diff direction (T-XX from P2 plan):**
```diff
 from config.logging import configure_structlog
 from line_provider.settings.config import LineProviderSettings
+from line_provider.facades.event_bus import EventBus, NoopEventBus
+from line_provider.infrastructure.store.in_memory import InMemoryEventStore
 ...
     log.info("line_provider.startup", service=settings.service_name)
     app.state.settings = settings
+    app.state.event_store = InMemoryEventStore()
+    app.state.event_bus: EventBus = NoopEventBus()
     try:
         yield
     finally:
         log.info("line_provider.shutdown")
```

D-14 — `app.state.event_bus` устанавливается после `configure_structlog`. Порядок здесь уже корректный.

---

### Excerpt C — `tests/line_provider/conftest.py:1-16` (текущий P1, **требует upgrade in place**)

```python
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from line_provider.app import build_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**Что не так:** `ASGITransport` не триггерит ASGI lifespan-события (FastAPI docs, RESEARCH.md Pitfall 1 / Pattern 7). `test_health.py` сейчас зелёный только потому, что `/health` не читает `app.state`. Как только P2-routes начнут читать `request.app.state.event_store`, fixture упадёт с `AttributeError: 'State' object has no attribute 'event_store'`.

**Применить так в P2 (T-01 / Wave 0 — ДО любых route-тестов):**

```python
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from line_provider.app import build_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = build_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
```

Также: `uv add --dev "asgi-lifespan>=2.1,<3"` + коммит обновлённого `uv.lock`. Без этого все integration-тесты P2 не запустятся.

**Optional addition** (для arrange-setup через store напрямую, см. RESEARCH.md §«Pattern 7» / Open Question 5):

```python
@pytest_asyncio.fixture
async def event_store(client: AsyncClient) -> InMemoryEventStore:
    """Direct access to the same store the client uses."""
    return client._transport.app.state.event_store  # type: ignore[attr-defined]
```

(planner выберет: оставить private attribute access, либо рефакторить `client` fixture на yield-tuple — оба валидны).

---

### Excerpt D — `src/line_provider/entrypoints/api/health.py:1-10` (route-module shape для `events.py`)

```python
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

**Применить так в P2 (`src/line_provider/entrypoints/api/events.py`):**

- Одинаковая шапка: `from __future__ import annotations` + `from fastapi import APIRouter, HTTPException, status`.
- `router = APIRouter(tags=["events"])` — одна на все 4 хендлера.
- Каждый хендлер — `async def`-функция, явный `response_model=EventRead`, явный `status_code=` где не дефолт.
- Импорты — абсолютные `line_provider.*` (тот же стиль, что и `app.py`/`lifespan.py`).
- Никаких комментариев и docstring'ов (P1 convention, см. health.py).

Полный шаблон в RESEARCH.md §«Pattern 5» (строки 513-578).

---

### Excerpt E — `src/line_provider/entrypoints/middleware.py:1-27` (для `event_bus.py` — structlog use pattern)

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        structlog.contextvars.clear_contextvars()
        request_id = request.headers.get("X-Request-ID", uuid4().hex)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
```

**Применить так в P2 (`src/line_provider/facades/event_bus.py`):**

- Импорт `import structlog` (без `from structlog import get_logger` — стиль P1).
- В `NoopEventBus.publish`: `structlog.get_logger().info("event_bus.publish.noop", routing_key=..., event_id=..., new_state=..., schema_version=...)` — каждая строка лога с dot-namespaced ключом и kwargs (P1 convention из `lifespan.py:18`: `log.info("line_provider.startup", service=...)`).
- **Pitfall 7:** НЕ делать `bind_contextvars` в interactor'ах — only middleware binds. `log.info(..., event_id=...)` без bind — корректный путь.

---

### Excerpt F — `src/config/time.py:1-7` (для pure-function helpers и selectors)

```python
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
```

**Применить так в P2:**

- **`src/line_provider/helpers/state_machine.py`** — тот же стиль one-liner-модуля: одна экспортируемая функция, без классов, `from __future__ import annotations` в шапке. Тип-сигнатура + плоское тело.
- **`src/line_provider/selectors/get_event_by_id.py`** — то же: `async def get_event_by_id(store, *, event_id): return await store.get_by_id(event_id)`.
- **`src/line_provider/selectors/list_active_events.py`** — `from config.time import utc_now` (тот же import, что используют `lifespan.py`/`settings/config.py` для config-пакета). Никакого DI-параметра `now: datetime | None = None` — тесты monkey-patch модульный атрибут (RESEARCH.md Open Question 4).
- **Pydantic validator `FutureDeadline`** в `schemas/events.py` — тоже `from config.time import utc_now`. **Не использовать `datetime.utcnow()`** (deprecated since Python 3.12, см. RESEARCH.md State of the Art).

---

### Excerpt G — `src/line_provider/settings/config.py:1-22` (для Pydantic-модели схем)

```python
from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from config.settings_base import BaseAppSettings


class LineProviderSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LINE_PROVIDER_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = Field(default="line-provider")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    rabbitmq_url: str = Field(default="amqp://guest:guest@rabbitmq:5672/")
```

**Применить так в P2 (`schemas/events.py` и `schemas/messages.py`):**

- Шапка `from __future__ import annotations` обязательна.
- Импорты Pydantic — на отдельной строке (`from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, AfterValidator`).
- `model_config = ConfigDict(...)` как первый class-level statement (тот же layout, что в settings).
- Для `Event`: `ConfigDict(frozen=True, extra="forbid")` (D-17).
- Для `EventCreate`/`EventUpdate`: `ConfigDict(extra="forbid")` (D-04 защита от лишних полей).
- Для `EventFinishedMessage`: `ConfigDict(frozen=True, extra="forbid")` (D-13).

**Поля — Pydantic v2 Annotated style** (RESEARCH.md «Don't Hand-Roll»):
```python
Coefficient = Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)]
```
Не использовать deprecated `condecimal`.

---

### Excerpt H — `tests/line_provider/test_health.py:1-29` (для всех test-файлов P2)

```python
"""Smoke tests for line_provider /health endpoint.

QA-10: pytest must collect and pass green.
INFR-08: HTTP-level E2E proof of structlog request-id propagation via
RequestContextMiddleware — X-Request-ID is echoed back in response headers
(logging-side INFR-08 validated unit-wise in plan 02).
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_status_ok(client: AsyncClient) -> None:
    """QA-10: /health returns 200 with {"status": "ok"}."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_echoes_request_id_header(client: AsyncClient) -> None:
    """INFR-08 (HTTP-level E2E): RequestContextMiddleware binds request_id via
    bind_contextvars and echoes X-Request-ID header on response. Without correct
    middleware wiring (bind_contextvars + finally clear_contextvars), this fails.
    """
    response = await client.get("/health")
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0
```

**Применить так в каждом P2-тестовом файле:**

- Module docstring со списком REQ-ID, которые покрывает файл (например, `LP-08, QA-04` — для `test_state_machine.py`).
- `from __future__ import annotations` обязательно.
- Каждая тест-функция — REQ-ID в первой строке docstring (`"""LP-03: POST /event creates with 201."""`). Это grep-traceability convention из P1.
- `async def test_...` — без `@pytest.mark.asyncio` (pyproject `asyncio_mode = "auto"` уже стоит).
- Integration-тесты — параметр `client: AsyncClient`. Unit-тесты — без client fixture, либо собственные локальные `pytest_asyncio.fixture` на `InMemoryEventStore`.

---

### Excerpt I — `src/line_provider/settings/config.py` + `src/config/logging.py` (импорты `config.*`)

В `lifespan.py:9`:
```python
from config.logging import configure_structlog
from line_provider.settings.config import LineProviderSettings
```

**Применить так в P2:**

- `src/config/time.py` импортируется как `from config.time import utc_now` (НЕ `from line_provider.helpers.time import ...`; helpers/time.py НЕ создавать — `config.time.utc_now` достаточно, см. CONTEXT.md `code_context.Reusable Assets`).
- Все интра-сервисные импорты — `line_provider.*` (абсолютные); shared utilities — `config.*`. **Не использовать relative imports** (`from .schemas import …`) — P1 не делает relative imports нигде.

---

## §3 Shared Patterns

### A. `from __future__ import annotations` everywhere
**Source:** Все P1-файлы (`app.py`, `lifespan.py`, `middleware.py`, `health.py`, `settings/config.py`, `config/*.py`, `tests/line_provider/*.py`).
**Apply to:** Каждый новый `.py`-файл P2 (включая тесты).
**Why:** PEP 563 deferred evaluation + ruff `from __future__` rule (UP) — P1 invariant.

### B. Абсолютные импорты + конкретный module-path
**Source:** `src/line_provider/app.py:5-7`, `src/line_provider/entrypoints/lifespan.py:9-10`.
**Apply to:** Все новые модули P2.
```python
from line_provider.facades.event_bus import EventBus, NoopEventBus
from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from config.time import utc_now
```
Никаких `from . import x` / `from line_provider.schemas import *` — конкретный путь до файла, конкретный список имён.

### C. structlog usage (без `bind_contextvars` вне middleware)
**Source:** `src/line_provider/entrypoints/lifespan.py:17-18` (`log = structlog.get_logger(); log.info("line_provider.startup", service=...)`).
**Apply to:** `facades/event_bus.py` (NoopEventBus.publish), `interactors/*` (если нужны логи). **Pitfall 7 / A7:** middleware уже binds request_id; в interactor'ах — только `log.info(..., event_id=..., new_state=...)` без `bind_contextvars`.

### D. Pydantic v2 ConfigDict layout
**Source:** `src/line_provider/settings/config.py:10-16`.
**Apply to:** Все `schemas/*.py` модели. `model_config = ConfigDict(...)` — первый class-level statement.

### E. Pure-function helpers
**Source:** `src/config/time.py:1-7`.
**Apply to:** `helpers/state_machine.py`, `selectors/*.py`. Без классов, без DI, без `__init__.py` экспортов.

### F. APIRouter с tags
**Source:** `src/line_provider/entrypoints/api/health.py:5` (`router = APIRouter(tags=["health"])`).
**Apply to:** `entrypoints/api/events.py` — `router = APIRouter(tags=["events"])`.

### G. Test docstring с REQ-ID
**Source:** `tests/line_provider/test_health.py:14, 22-25`.
**Apply to:** Все новые тест-функции P2. Первая строка docstring — `"""<REQ-ID>: <one-line behavior>."""`.

### H. `from __future__` в lifespan/тестах + `AsyncIterator` typing
**Source:** `src/line_provider/entrypoints/lifespan.py:3, 14`, `tests/line_provider/conftest.py:3, 12`.
**Apply to:** Любая новая lifespan-вставка / новые fixtures.

---

## §4 No analog found

Не применимо. Все 21 файл имеют либо прямой P1-аналог (модификации), либо аналогичный pattern в P1 (новые файлы домена), либо явный code-example в RESEARCH.md, опирающийся на P1-конвенции.

Замечание для планировщика: **`asgi-lifespan`** — единственная новая зависимость P2. Установка — `uv add --dev "asgi-lifespan>=2.1,<3"`. Без этого все integration-тесты P2 (включая Wave 0 smoke) не запустятся. Этот шаг должен быть первым T-task в плане.

---

## Metadata

**Analog search scope:**
- `/Users/dmitrydankov/Personal/BSW/src/line_provider/**` (8 files P1)
- `/Users/dmitrydankov/Personal/BSW/src/config/**` (4 files P1)
- `/Users/dmitrydankov/Personal/BSW/tests/line_provider/**` (4 files P1)
- `/Users/dmitrydankov/Personal/BSW/src/bet_maker/**` (для сравнения структуры — но bet-maker файлы НЕ применимы как аналоги к line-provider P2, т.к. они одного уровня P1-скелета и не содержат domain-layer).

**Files scanned:** 22 P1-файла (полностью прочитаны).
**Pattern extraction date:** 2026-05-14.
**Overrides:** все противоречия между `REQUIREMENTS.md LP-02 (event_id str)`, `ARCHITECTURE.md Pattern 2 (event_id int)` и `CONTEXT.md D-05 (event_id UUID4)` разрешены в пользу CONTEXT.md (D-05). Первый task плана P2 — синхронизировать `REQUIREMENTS.md LP-02` (см. CONTEXT.md D-05).
