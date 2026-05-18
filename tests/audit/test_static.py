"""Phase 7 D-19 static audit tests.

Each test asserts a single ``Looks Done But Isn't`` invariant from
``.planning/research/PITFALLS.md``. The tests are pure file-content checks
(``Path.read_text()`` + regex/substring) so they run in CI without spinning
up Docker, RabbitMQ, or PostgreSQL.

A failing test here means a refactor silently undid a Phase 1-6 invariant
(e.g. someone re-formatted ``@router.subscriber(...)`` and dropped
``ack_policy=AckPolicy.MANUAL``). The grep-style style is deliberate:
Pitfall 6 (RESEARCH.md) warns formatting drift can break a regex, so the
patterns anchor on stable substrings rather than full multi-line shapes.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def test_subscribers_have_manual_ack() -> None:
    """R1 / F1: every @router.subscriber must declare ack_policy=AckPolicy.MANUAL.

    Default AckPolicy.REJECT_ON_ERROR would silently drop messages on
    any handler exception — breaks the Core Value invariant (no stuck PENDING bets).
    """
    src = (SRC / "bet_maker" / "entrypoints" / "messaging.py").read_text()
    subscribers = re.findall(r"@router\.subscriber\s*\(", src)
    manual_ack_kwargs = re.findall(r"ack_policy\s*=\s*AckPolicy\.MANUAL", src)
    assert subscribers, "no @router.subscriber decorator found — wrong file?"
    assert len(manual_ack_kwargs) >= len(subscribers), (
        f"{len(subscribers)} @router.subscriber decorators found, "
        f"but only {len(manual_ack_kwargs)} mentions of "
        f"ack_policy=AckPolicy.MANUAL — see ARCHITECTURE.md R1/F1"
    )


def test_repositories_use_for_update_skip_locked() -> None:
    """R3: BetRepository.get_pending_locked must use with_for_update(skip_locked=True).

    The row lock plus skip_locked=True is what makes consumer + reconciler
    concurrent settle idempotent against the same event_id.
    """
    src = (SRC / "bet_maker" / "repositories" / "bets.py").read_text()
    assert "with_for_update(skip_locked=True)" in src, (
        "BetRepository.get_pending_locked must use "
        "with_for_update(skip_locked=True) — see ARCHITECTURE.md R3."
    )


def test_async_sessionmaker_expire_on_commit_false() -> None:
    """A1 (Pitfall): async_sessionmaker must declare expire_on_commit=False.

    Without this, any access to ORM attributes after commit raises
    MissingGreenlet (the async session would try to lazy-reload, which
    requires greenlet). Plan 03-07 place_bet interactor depends on this.
    """
    src = (SRC / "bet_maker" / "infrastructure" / "db" / "engine.py").read_text()
    assert re.search(
        r"async_sessionmaker\s*\([^)]*expire_on_commit\s*=\s*False",
        src,
        re.DOTALL,
    ), "async_sessionmaker must declare expire_on_commit=False — see ARCHITECTURE.md A1."


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
    """D-20: Dockerfile must pin python:3.10-slim-bookworm.

    Rolling tag 3.10-slim resolves to trixie (since May 2026) which
    ships glibc/openssl changes that may break asyncpg wheels.
    """
    src = (REPO_ROOT / "Dockerfile").read_text()
    assert "3.10-slim-bookworm" in src, (
        "Dockerfile must pin python:3.10-slim-bookworm explicitly "
        "(not rolling 3.10-slim) — see CLAUDE.md Stack Patterns."
    )


def test_pythonunbuffered_set() -> None:
    """D-04: PYTHONUNBUFFERED=1 must be set so stdout flushes immediately.

    Without this, structlog logs are buffered in Docker and only appear
    after the process exits — invisible during steady-state run.
    """
    src = (REPO_ROOT / "Dockerfile").read_text()
    assert re.search(r"PYTHONUNBUFFERED\s*=\s*1", src), (
        "Dockerfile must declare PYTHONUNBUFFERED=1."
    )


def test_durable_queue_and_exchange() -> None:
    """R4 / R10: RabbitQueue and RabbitExchange must declare durable=True.

    Non-durable queues/exchanges are deleted on RabbitMQ restart and
    silently lose the EventFinishedMessage stream. Combined with named
    volume on /var/lib/rabbitmq, durability is what makes the stack
    survive a broker restart.
    """
    src = (SRC / "bet_maker" / "entrypoints" / "messaging.py").read_text()
    assert re.search(r"RabbitQueue\([^)]*durable\s*=\s*True", src, re.DOTALL), (
        "RabbitQueue must declare durable=True — see ARCHITECTURE.md R4/R10."
    )
    assert re.search(r"RabbitExchange\([^)]*durable\s*=\s*True", src, re.DOTALL), (
        "RabbitExchange must declare durable=True — see ARCHITECTURE.md R4/R10."
    )
