"""Integration tests for TeamCoordinator.spawn_agent() and process lifecycle.

These tests start real subprocesses via asyncio.create_subprocess_exec and
verify the full spawn -> health-check -> team-membership -> dissolve cycle.

ADR: .vault/adr/2026-02-20-a2a-team-adr.md
Plan: .vault/plan/2026-02-21-claude-a2a-overhaul-impl-plan.md (Phase 3)
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from pathlib import Path

from vaultspec.orchestration.team import (
    MemberStatus,
    TeamCoordinator,
    TeamStatus,
)
from vaultspec.protocol.a2a.tests.conftest import (
    EchoExecutor,
    _make_card,
)


def _build_app_transport(name: str, port: int) -> httpx.ASGITransport:
    """Build an in-process ASGI transport for a minimal echo A2A server."""
    from vaultspec.protocol.a2a import create_app

    card = _make_card(name, port)
    app = create_app(EchoExecutor(), card)
    return httpx.ASGITransport(app=app)


# ---------------------------------------------------------------------------
# Helper: write a temporary A2A echo-server script
# ---------------------------------------------------------------------------

_ECHO_SERVER_SCRIPT = textwrap.dedent("""\
    \"\"\"Minimal A2A echo server for spawn_agent integration tests.\"\"\"
    import argparse
    import asyncio
    from a2a.server.agent_execution import AgentExecutor, RequestContext
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.events import EventQueue
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
    from a2a.types import (
        AgentCapabilities,
        AgentCard,
        AgentSkill,
        Part,
        TextPart,
    )
    import uvicorn


    class _EchoExecutor(AgentExecutor):
        async def execute(
            self, context: RequestContext, event_queue: EventQueue,
        ) -> None:
            assert context.task_id is not None
            assert context.context_id is not None
            updater = TaskUpdater(
                event_queue, context.task_id, context.context_id,
            )
            text = context.get_user_input()
            await updater.start_work()
            await updater.complete(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=f"Echo: {text}"))]
                )
            )

        async def cancel(
            self, context: RequestContext, event_queue: EventQueue,
        ) -> None:
            assert context.task_id is not None
            assert context.context_id is not None
            updater = TaskUpdater(
                event_queue, context.task_id, context.context_id,
            )
            await updater.cancel()


    def main() -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--port", type=int, required=True)
        args = parser.parse_args()

        card = AgentCard(
            name="echo-spawned",
            url=f"http://localhost:{args.port}/",
            version="0.1.0",
            description="Spawned echo agent",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=AgentCapabilities(streaming=False),
            skills=[
                AgentSkill(
                id="echo", name="Echo",
                description="Echoes input", tags=["test"],
            )
            ],
        )
        handler = DefaultRequestHandler(
            agent_executor=_EchoExecutor(),
            task_store=InMemoryTaskStore(),
        )
        a2a_app = A2AStarletteApplication(agent_card=card, http_handler=handler)
        app = a2a_app.build()
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


    if __name__ == "__main__":
        main()
""")


@pytest.fixture
def echo_server_script(tmp_path: Path) -> Path:
    """Write the echo server script to a temporary file and return its path."""
    script = tmp_path / "echo_server.py"
    script.write_text(_ECHO_SERVER_SCRIPT, encoding="utf-8")
    return script


def _find_free_port() -> int:
    """Return a free TCP port from the OS."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ===================================================================
# Phase 3 — spawn_agent integration tests
# ===================================================================


@pytest.mark.integration
@pytest.mark.team
@pytest.mark.asyncio
async def test_spawn_agent_starts_process(echo_server_script: Path):
    """Spawn an echo server script and verify the agent joins the team."""
    port = _find_free_port()

    # Bootstrap a coordinator with one in-process agent so we have an active session.
    coordinator = TeamCoordinator()
    in_process_port = _find_free_port()
    transport = _build_app_transport("bootstrap", in_process_port)
    mounts = {
        f"http://localhost:{in_process_port}/": transport,
        f"http://localhost:{in_process_port}": transport,
    }
    coordinator._http_client = httpx.AsyncClient(mounts=mounts)
    await coordinator.form_team(
        "spawn-test-team",
        [f"http://localhost:{in_process_port}/"],
    )

    try:
        # The spawned agent needs a *real* HTTP client (not ASGI-mounted) to reach
        # the subprocess over TCP. Replace the coordinator's httpx client with one
        # that falls through to real networking for the spawned agent's port while
        # still routing the in-process agent through ASGI transport.
        await coordinator._close_http()
        coordinator._http_client = httpx.AsyncClient(mounts=mounts)
        coordinator._clients.clear()

        member = await coordinator.spawn_agent(
            str(echo_server_script), port, "echo-spawned"
        )

        assert member.name == "echo-spawned"
        assert member.url == f"http://localhost:{port}/"
        assert member.status == MemberStatus.IDLE

        # Verify the agent is in the session.
        assert "echo-spawned" in coordinator.session.members

        # Verify the subprocess is tracked and still running.
        assert "echo-spawned" in coordinator._spawned
        proc = coordinator._spawned["echo-spawned"]
        assert proc.returncode is None
    finally:
        await coordinator.dissolve_team()


@pytest.mark.integration
@pytest.mark.team
@pytest.mark.asyncio
async def test_dissolve_terminates_spawned(echo_server_script: Path):
    """Spawn an agent, then dissolve the team. Verify the process is terminated."""
    port = _find_free_port()

    coordinator = TeamCoordinator()
    in_process_port = _find_free_port()
    transport = _build_app_transport("bootstrap", in_process_port)
    mounts = {
        f"http://localhost:{in_process_port}/": transport,
        f"http://localhost:{in_process_port}": transport,
    }
    coordinator._http_client = httpx.AsyncClient(mounts=mounts)
    await coordinator.form_team(
        "dissolve-spawn-team",
        [f"http://localhost:{in_process_port}/"],
    )

    await coordinator._close_http()
    coordinator._http_client = httpx.AsyncClient(mounts=mounts)
    coordinator._clients.clear()

    await coordinator.spawn_agent(str(echo_server_script), port, "echo-spawned")
    proc = coordinator._spawned["echo-spawned"]

    # Process must be alive before dissolve.
    assert proc.returncode is None

    await coordinator.dissolve_team()

    # After dissolve, the process should have been terminated and waited on.
    assert proc.returncode is not None
    assert coordinator._spawned == {}
    assert coordinator.session.status == TeamStatus.DISSOLVED


@pytest.mark.integration
@pytest.mark.team
@pytest.mark.asyncio
async def test_spawn_invalid_script_fails():
    """Spawning a non-existent script must raise RuntimeError."""
    coordinator = TeamCoordinator()
    in_process_port = _find_free_port()
    transport = _build_app_transport("bootstrap", in_process_port)
    mounts = {
        f"http://localhost:{in_process_port}/": transport,
        f"http://localhost:{in_process_port}": transport,
    }
    coordinator._http_client = httpx.AsyncClient(mounts=mounts)
    await coordinator.form_team(
        "invalid-script-team",
        [f"http://localhost:{in_process_port}/"],
    )

    try:
        with pytest.raises(RuntimeError, match="exited with code"):
            await coordinator.spawn_agent(
                "/nonexistent/path/to/script.py",
                _find_free_port(),
                "ghost-agent",
            )
    finally:
        await coordinator.dissolve_team()
