"""Integration tests for full team lifecycle through MCP tools and server wiring.

Verifies the end-to-end chain:
  form_team → persist session → restore → dispatch → dissolve

Also validates that the unified server exposes team tools alongside subagent
tools, and that ClaudeA2AExecutor accepts mcp_servers configuration for team
tool injection.

ADR: .vault/adr/2026-02-21-claude-a2a-overhaul-adr.md
Plan: .vault/plan/2026-02-21-claude-a2a-overhaul-impl-plan.md (Phase 5)
"""

from __future__ import annotations

import json

import httpx
import pytest
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from ...mcp_server.team_tools import (
    _load_session,
    _save_session,
    list_teams,
    set_root_dir,
    team_status,
)
from ...protocol.a2a.tests.helpers import EchoExecutor
from ..team import (
    TeamCoordinator,
    TeamStatus,
    extract_artifact_text,
)

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_card(name: str, port: int) -> AgentCard:
    return AgentCard(
        name=name,
        url=f"http://localhost:{port}/",
        version="0.1.0",
        description=f"Integration test {name}",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="echo", name="Echo", description="Echoes input", tags=["test"]
            )
        ],
    )


def _build_a2a_app(executor, card: AgentCard):
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    a2a_app = A2AStarletteApplication(agent_card=card, http_handler=handler)
    return a2a_app.build()


class _MuxTransport(httpx.AsyncBaseTransport):
    """Route requests to the correct in-process ASGI app by base URL."""

    def __init__(self, routes: dict[str, object]) -> None:
        self._transports: dict[str, httpx.ASGITransport] = {}
        for base_url, app in routes.items():
            self._transports[base_url] = httpx.ASGITransport(app=app)  # ty: ignore[invalid-argument-type]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        base = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        transport = self._transports.get(base)
        if transport is None:
            raise httpx.ConnectError(f"No route for {base}")
        return await transport.handle_async_request(request)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """Clean workspace root with team_tools configured."""
    set_root_dir(tmp_path)
    yield tmp_path
    set_root_dir(tmp_path)


@pytest.fixture
def mux_transport():
    """Mux transport routing to two in-process echo agents."""
    app_a = _build_a2a_app(EchoExecutor(), _make_card("alpha", 10300))
    app_b = _build_a2a_app(EchoExecutor(), _make_card("beta", 10301))
    return _MuxTransport(
        {"http://localhost:10300": app_a, "http://localhost:10301": app_b}
    )


# ---------------------------------------------------------------------------
# Test 1: Full lifecycle — form → persist → restore → dispatch → dissolve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle_with_session_persistence(workspace, mux_transport):
    """End-to-end: form team, persist, restore from disk, dispatch, dissolve.

    This exercises the complete data path that MCP tools use internally:
    TeamCoordinator.form_team() → _save_session() → _load_session() →
    restore_session() → dispatch_parallel() → dissolve_team().
    """
    # Step 1: Form team with two echo agents
    coordinator = TeamCoordinator()
    async with coordinator:
        coordinator._http_client = httpx.AsyncClient(transport=mux_transport)
        session = await coordinator.form_team(
            name="lifecycle-integ",
            agent_urls=["http://localhost:10300/", "http://localhost:10301/"],
        )

    assert session.status == TeamStatus.ACTIVE
    assert len(session.members) == 2
    # Members are keyed by URL after the M1 URL-keying fix; check display names.
    member_display_names = {m.display_name for m in session.members.values()}
    assert "alpha" in member_display_names
    assert "beta" in member_display_names

    # Step 2: Persist session to disk (same path MCP create_team uses)
    _save_session(workspace, session)

    # Step 3: Verify via MCP tool functions that the session is visible
    teams_result = json.loads(await list_teams())
    assert "lifecycle-integ" in teams_result["teams"]

    status_result = json.loads(await team_status(name="lifecycle-integ"))
    assert status_result["name"] == "lifecycle-integ"
    assert status_result["status"] == "active"
    assert len(status_result["members"]) == 2

    # Step 4: Load session from disk and restore coordinator
    loaded = _load_session(workspace, "lifecycle-integ")
    assert loaded.team_id == session.team_id

    restored = TeamCoordinator()
    restored.restore_session(loaded)
    async with restored:
        restored._http_client = httpx.AsyncClient(transport=mux_transport)

        # Step 5: Dispatch task to one agent (result keyed by canonical URL).
        results = await restored.dispatch_parallel({"alpha": "ping from lifecycle"})
        assert len(results) == 1
        text = extract_artifact_text(next(iter(results.values())))
        assert "Echo: ping from lifecycle" in text

        # Step 6: Dispatch to both agents (broadcast-style)
        all_results = await restored.dispatch_parallel(
            {"alpha": "broadcast msg", "beta": "broadcast msg"}
        )
        assert len(all_results) == 2
        for _agent_name, task_result in all_results.items():
            assert "Echo: broadcast msg" in extract_artifact_text(task_result)

    # Step 7: Dissolve
    restored2 = TeamCoordinator()
    restored2.restore_session(loaded)
    async with restored2:
        restored2._http_client = httpx.AsyncClient(transport=mux_transport)
        await restored2.dissolve_team()

    assert restored2.session.status == TeamStatus.DISSOLVED


# ---------------------------------------------------------------------------
# Test 2: Unified server exposes team tools
# ---------------------------------------------------------------------------


def test_unified_server_registers_team_tools():
    """Verify create_server() registers team tools alongside subagent tools."""
    from ...mcp_server.app import create_server

    mcp = create_server()

    tool_manager = mcp._tool_manager
    tool_names = {t.name for t in tool_manager.list_tools()}

    expected_team_tools = {
        "create_team",
        "team_status",
        "list_teams",
        "dispatch_task",
        "broadcast_message",
        "send_message",
        "spawn_agent",
        "dissolve_team",
    }

    expected_subagent_tools = {
        "list_agents",
        "dispatch_agent",
        "get_task_status",
        "cancel_task",
        "get_locks",
    }

    for tool in expected_team_tools:
        assert tool in tool_names, f"Team tool {tool!r} missing from unified server"
    for tool in expected_subagent_tools:
        assert tool in tool_names, f"Subagent tool {tool!r} missing from unified server"


# ---------------------------------------------------------------------------
# Test 3: ClaudeA2AExecutor accepts mcp_servers config
# ---------------------------------------------------------------------------


def test_executor_accepts_mcp_servers_config():
    """ClaudeA2AExecutor stores mcp_servers config correctly on construction.

    The executor passes mcp_servers through to ClaudeAgentOptions, allowing
    the Claude subprocess to connect to team tools. This test verifies the
    configuration is accepted and stored without starting a real Claude
    process.
    """
    from ...protocol.a2a.executors import ClaudeA2AExecutor

    team_tools_config = {
        "vaultspec-team": {
            "command": "uv",
            "args": ["run", "vaultspec-mcp"],
            "env": {"VAULTSPEC_MCP_ROOT_DIR": "/workspace"},
        }
    }

    executor = ClaudeA2AExecutor(
        model="claude-sonnet-4-20250514",
        root_dir="/workspace",
        mode="read-write",
        mcp_servers=team_tools_config,
    )

    assert executor._mcp_servers == team_tools_config
    assert executor._model == "claude-sonnet-4-20250514"
    assert executor._root_dir == "/workspace"
    assert executor._mode == "read-write"
