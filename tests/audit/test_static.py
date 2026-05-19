"""Static audit tests.

Each test asserts a single ``Looks Done But Isn't`` invariant about the
codebase. The tests are pure file-content checks (``Path.read_text()`` +
regex/substring) so they run in CI without spinning up Docker, RabbitMQ,
or PostgreSQL.

A failing test here means a refactor silently undid a load-bearing
invariant (e.g. someone re-formatted ``@router.subscriber(...)`` and
dropped ``ack_policy=AckPolicy.MANUAL``). The grep-style is deliberate:
formatting drift can break a regex, so the patterns anchor on stable
substrings rather than full multi-line shapes.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def test_subscribers_have_manual_ack() -> None:
    """Every @router.subscriber must declare ack_policy=AckPolicy.MANUAL.

    Default AckPolicy.REJECT_ON_ERROR would silently drop messages on
    any handler exception — breaks the Core Value invariant (no stuck PENDING bets).
    """
    src = (SRC / "bet_maker" / "api" / "messaging.py").read_text()
    subscribers = re.findall(r"@router\.subscriber\s*\(", src)
    manual_ack_kwargs = re.findall(r"ack_policy\s*=\s*AckPolicy\.MANUAL", src)
    assert subscribers, "no @router.subscriber decorator found — wrong file?"
    assert len(manual_ack_kwargs) >= len(subscribers), (
        f"{len(subscribers)} @router.subscriber decorators found, "
        f"but only {len(manual_ack_kwargs)} mentions of "
        f"ack_policy=AckPolicy.MANUAL"
    )


def test_pending_locked_selector_uses_for_update_skip_locked() -> None:
    """selectors/get_pending_locked must use with_for_update(skip_locked=True).

    The row lock plus ``skip_locked=True`` is what makes consumer and
    reconciler concurrent settle idempotent against the same event_id.
    """
    src = (SRC / "bet_maker" / "selectors" / "get_pending_locked.py").read_text()
    assert "with_for_update(skip_locked=True)" in src, (
        "selectors/get_pending_locked must use with_for_update(skip_locked=True)."
    )


def test_async_sessionmaker_expire_on_commit_false() -> None:
    """async_sessionmaker must declare expire_on_commit=False.

    Without this, any access to ORM attributes after commit raises
    MissingGreenlet (the async session would try to lazy-reload, which
    requires greenlet). The ``place_bet`` interactor depends on this.
    """
    src = (SRC / "bet_maker" / "infrastructure" / "db" / "engine.py").read_text()
    assert re.search(
        r"async_sessionmaker\s*\([^)]*expire_on_commit\s*=\s*False",
        src,
        re.DOTALL,
    ), "async_sessionmaker must declare expire_on_commit=False."


def test_compose_command_exec_form() -> None:
    """docker-compose service 'command:' entries must be JSON arrays (exec-form).

    Exec-form passes SIGTERM directly to the process; shell-form wraps
    in /bin/sh which traps SIGTERM and forces docker to SIGKILL after
    stop_grace_period. The Dockerfile has no CMD; the runtime command
    lives in docker-compose.yml for each service.
    """
    src = (REPO_ROOT / "docker-compose.yml").read_text()
    command_lines = [line for line in src.splitlines() if line.lstrip().startswith("command:")]
    assert command_lines, "docker-compose.yml has no command: entry"
    for line in command_lines:
        assert re.search(r"command:\s*\[", line), (
            f'non-exec-form command found: {line!r} — use command: ["python", "..."]'
        )


def test_dockerfile_pinned_python_bookworm() -> None:
    """Dockerfile must pin python:3.10-slim-bookworm.

    Rolling tag 3.10-slim resolves to trixie (since May 2026) which
    ships glibc/openssl changes that may break asyncpg wheels.
    """
    src = (REPO_ROOT / "Dockerfile").read_text()
    assert "3.10-slim-bookworm" in src, (
        "Dockerfile must pin python:3.10-slim-bookworm explicitly (not rolling 3.10-slim)."
    )


def test_pythonunbuffered_set() -> None:
    """PYTHONUNBUFFERED=1 must be set so stdout flushes immediately.

    Without this, structlog logs are buffered in Docker and only appear
    after the process exits — invisible during steady-state run.
    """
    src = (REPO_ROOT / "Dockerfile").read_text()
    assert re.search(r"PYTHONUNBUFFERED\s*=\s*1", src), (
        "Dockerfile must declare PYTHONUNBUFFERED=1."
    )


def test_durable_queue_and_exchange() -> None:
    """RabbitQueue and RabbitExchange must declare durable=True.

    Non-durable queues/exchanges are deleted on RabbitMQ restart and
    silently lose the EventFinishedMessage stream. Combined with the
    named volume on /var/lib/rabbitmq, durability is what makes the
    stack survive a broker restart.
    """
    src = (SRC / "bet_maker" / "api" / "messaging.py").read_text()
    assert re.search(r"RabbitQueue\([^)]*durable\s*=\s*True", src, re.DOTALL), (
        "RabbitQueue must declare durable=True."
    )
    assert re.search(r"RabbitExchange\([^)]*durable\s*=\s*True", src, re.DOTALL), (
        "RabbitExchange must declare durable=True."
    )


def test_no_entrypoints_dir() -> None:
    """src/<svc>/entrypoints/ must not exist for either service.

    HTTP routers + FastStream RabbitRouter live under ``src/<svc>/api/``
    and ``lifespan.py`` + ``middleware.py`` sit at the service-package
    root. The legacy ``entrypoints/`` directory was deleted for both
    services; this audit fails if a future commit recreates either one.
    """
    bm = SRC / "bet_maker" / "entrypoints"
    lp = SRC / "line_provider" / "entrypoints"
    assert not bm.exists(), f"{bm} re-introduced — entrypoints/ has been flattened into api/."
    assert not lp.exists(), f"{lp} re-introduced — entrypoints/ has been flattened into api/."
