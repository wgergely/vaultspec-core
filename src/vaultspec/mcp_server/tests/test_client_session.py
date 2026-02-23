"""In-memory MCP client session tests for vaultspec-mcp.

Tests the full MCP protocol stack via the SDK's in-memory transport.
Unlike ``test_mcp_protocol.py`` (which uses ``FastMCP.call_tool``),
these tests create a real ``ClientSession`` connected to the server
over in-memory streams -- exercising the MCP handshake, JSON-RPC
serialization, tool/resource discovery, and error propagation
semantics (``CallToolResult.isError`` instead of Python exceptions).

The session context managers are entered/exited within each test
function body (not via ``yield`` fixtures) to avoid the
``pytest-asyncio`` + ``anyio`` cancel-scope cross-task teardown bug.

SDK entry point:
    ``mcp.shared.memory.create_connected_server_and_client_session``
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
from mcp.client.session import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent, TextResourceContents

from tests.constants import PROJECT_ROOT, TEST_PROJECT

from ...orchestration import LockManager, TaskEngine
from .. import subagent_tools as srv
from ..app import create_server
from ..subagent_tools import initialize_server
from ..subagent_tools import register_tools as register_subagent_tools
from ..team_tools import register_tools as register_team_tools
from ..team_tools import set_root_dir

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = [pytest.mark.api]

EXPECTED_SUBAGENT_TOOLS = {
    "list_agents",
    "dispatch_agent",
    "get_task_status",
    "cancel_task",
    "get_locks",
}

EXPECTED_TEAM_TOOLS = {
    "create_team",
    "team_status",
    "list_teams",
    "dispatch_task",
    "broadcast_message",
    "send_message",
    "spawn_agent",
    "dissolve_team",
    "relay_output",
    "get_team_task_status",
}

ALL_EXPECTED_TOOLS = EXPECTED_SUBAGENT_TOOLS | EXPECTED_TEAM_TOOLS


async def _noop_run_subagent(**_kwargs):
    """No-op async stand-in for run_subagent."""


def _baker_cache():
    """Agent cache with a French Baker agent."""
    return {
        "vaultspec-simple-executor": {
            "name": "vaultspec-simple-executor",
            "tier": "LOW",
            "description": "A helpful French Baker agent",
            "default_model": None,
            "default_mode": "read-write",
            "tools": ["Read", "Write", "Bash"],
        },
    }


def _fresh_engine():
    """A clean TaskEngine + LockManager."""
    lm = LockManager()
    return TaskEngine(ttl_seconds=60.0, lock_manager=lm)


def _inject_subagent_globals(
    *,
    agent_cache=None,
    engine=None,
    run_fn=None,
):
    """Inject test state into subagent_tools module globals."""
    if agent_cache is not None:
        srv._agent_cache = agent_cache
    if engine is not None:
        srv.task_engine = engine
        srv.lock_manager = engine._lock_manager
    if run_fn is not None:
        srv._run_subagent_fn = run_fn
    srv._background_tasks = {}
    srv._active_clients = {}


def _reset_subagent_globals():
    """Reset subagent_tools module globals after each test."""
    srv._agent_cache.clear()
    srv._background_tasks.clear()
    srv._active_clients.clear()


def _init_server():
    """Call initialize_server and set_root_dir with test defaults."""
    initialize_server(
        root_dir=TEST_PROJECT,
        ttl_seconds=60.0,
        refresh_callback=lambda: False,
    )
    set_root_dir(TEST_PROJECT)


@asynccontextmanager
async def _connected_session_with_lifespan() -> AsyncIterator[ClientSession]:
    """Create a full server (with lifespan) and yield a connected session.

    The lifespan fires ``_register_agent_resources()`` and starts the
    agent-file poller.  Uses ``PROJECT_ROOT`` (the repository root) so
    that ``AGENTS_DIR`` resolves to real agent ``.md`` files under
    ``.vaultspec/rules/agents/``.
    """
    initialize_server(
        root_dir=PROJECT_ROOT,
        ttl_seconds=60.0,
        refresh_callback=lambda: False,
    )
    set_root_dir(PROJECT_ROOT)
    server = create_server()
    async with create_connected_server_and_client_session(
        server,
        raise_exceptions=True,
    ) as session:
        yield session


@asynccontextmanager
async def _connected_session_no_lifespan() -> AsyncIterator[ClientSession]:
    """Create a bare FastMCP with tools (no lifespan) and yield a session.

    Used for focused tool and error-propagation tests where the agent-file
    poller is unnecessary.
    """
    _init_server()
    mcp = FastMCP(name="test-vaultspec-mcp")
    register_subagent_tools(mcp)
    register_team_tools(mcp)
    async with create_connected_server_and_client_session(
        mcp,
        raise_exceptions=True,
    ) as session:
        yield session


@pytest.fixture(autouse=True)
def _cleanup_globals():
    """Reset module-level state after every test."""
    yield
    _reset_subagent_globals()


class TestProtocolHandshake:
    """Verify the MCP initialize handshake and capability negotiation."""

    async def test_session_connected(self):
        """Session is a connected ClientSession instance."""
        async with _connected_session_no_lifespan() as session:
            assert session is not None
            assert isinstance(session, ClientSession)

    async def test_server_capabilities_include_tools(self):
        """Server advertises tool capabilities after handshake."""
        async with _connected_session_no_lifespan() as session:
            caps = session.get_server_capabilities()
            assert caps is not None
            assert caps.tools is not None

    async def test_server_capabilities_include_resources(self):
        """Server with lifespan advertises resource capabilities."""
        async with _connected_session_with_lifespan() as session:
            caps = session.get_server_capabilities()
            assert caps is not None
            assert caps.resources is not None

    async def test_ping(self):
        """Protocol-level ping succeeds on a connected session."""
        async with _connected_session_no_lifespan() as session:
            result = await session.send_ping()
            assert result is not None


class TestToolDiscovery:
    """Verify tool listing through the MCP protocol."""

    async def test_all_15_tools_listed(self):
        """list_tools() returns all 15 registered tool names."""
        async with _connected_session_no_lifespan() as session:
            tools_result = await session.list_tools()
            names = {t.name for t in tools_result.tools}
            assert names == ALL_EXPECTED_TOOLS

    async def test_tool_schemas_have_required_fields(self):
        """Every tool exposes an inputSchema through the protocol."""
        async with _connected_session_no_lifespan() as session:
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                assert tool.inputSchema is not None, f"{tool.name} missing inputSchema"
                assert isinstance(tool.inputSchema, dict), (
                    f"{tool.name} inputSchema is not a dict"
                )

    async def test_tool_titles_present(self):
        """Every tool has a non-empty title."""
        async with _connected_session_no_lifespan() as session:
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                assert tool.title, f"{tool.name} missing or empty title"

    async def test_tool_annotations_present(self):
        """Every tool has ToolAnnotations set."""
        async with _connected_session_no_lifespan() as session:
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                assert tool.annotations is not None, f"{tool.name} missing annotations"


class TestResourceDiscovery:
    """Verify resource listing and reading via the MCP protocol.

    Uses ``_connected_session_with_lifespan`` so that
    ``_register_agent_resources()`` fires during server startup.
    """

    async def test_agent_resources_listed(self):
        """list_resources() returns agents:// URIs when agent files exist."""
        async with _connected_session_with_lifespan() as session:
            resources_result = await session.list_resources()
            agent_uris = [
                str(r.uri)
                for r in resources_result.resources
                if str(r.uri).startswith("agents://")
            ]
            # test-project has agent .md files under .vaultspec/rules/agents/
            assert len(agent_uris) > 0, "Expected at least one agents:// resource"

    async def test_read_agent_resource_returns_json(self):
        """read_resource() on an agent URI returns parseable JSON metadata."""
        async with _connected_session_with_lifespan() as session:
            resources_result = await session.list_resources()
            agent_resources = [
                r
                for r in resources_result.resources
                if str(r.uri).startswith("agents://")
            ]
            assert len(agent_resources) > 0, "No agent resources to read"

            uri = agent_resources[0].uri
            read_result = await session.read_resource(uri)
            assert read_result.contents, "read_resource returned empty contents"

            content_item = read_result.contents[0]
            assert isinstance(content_item, TextResourceContents)
            data = json.loads(content_item.text)
            assert "name" in data, "Agent resource JSON missing 'name' field"


class TestSubagentToolsRoundTrip:
    """Test subagent tools via the MCP client session protocol."""

    async def test_list_agents_via_protocol(self):
        """list_agents through the protocol returns valid JSON."""
        async with _connected_session_no_lifespan() as session:
            _inject_subagent_globals(agent_cache=_baker_cache())

            result = await session.call_tool("list_agents", {})
            assert result.isError is not True
            content = result.content[0]
            assert isinstance(content, TextContent)
            data = json.loads(content.text)
            assert len(data["agents"]) == 1
            assert data["agents"][0]["name"] == "vaultspec-simple-executor"

    async def test_dispatch_agent_via_protocol(self):
        """dispatch_agent through the protocol returns status and taskId."""
        async with _connected_session_no_lifespan() as session:
            engine = _fresh_engine()
            _inject_subagent_globals(
                agent_cache=_baker_cache(),
                engine=engine,
                run_fn=_noop_run_subagent,
            )

            result = await session.call_tool(
                "dispatch_agent",
                {"agent": "vaultspec-simple-executor", "task": "Bake baguettes"},
            )
            assert result.isError is not True
            content = result.content[0]
            assert isinstance(content, TextContent)
            data = json.loads(content.text)
            assert data["status"] == "working"
            assert data["agent"] == "vaultspec-simple-executor"
            assert "taskId" in data

    async def test_get_task_status_via_protocol(self):
        """get_task_status through the protocol returns task state."""
        async with _connected_session_no_lifespan() as session:
            engine = _fresh_engine()
            engine.create_task(
                "vaultspec-simple-executor",
                task_id="proto-cs-001",
            )
            _inject_subagent_globals(engine=engine)

            result = await session.call_tool(
                "get_task_status",
                {"task_id": "proto-cs-001"},
            )
            assert result.isError is not True
            content = result.content[0]
            assert isinstance(content, TextContent)
            data = json.loads(content.text)
            assert data["status"] == "working"
            assert data["taskId"] == "proto-cs-001"

    async def test_cancel_task_via_protocol(self):
        """cancel_task through the protocol cancels a working task."""
        async with _connected_session_no_lifespan() as session:
            engine = _fresh_engine()
            engine.create_task(
                "vaultspec-simple-executor",
                task_id="proto-cs-002",
            )
            _inject_subagent_globals(engine=engine)

            result = await session.call_tool(
                "cancel_task",
                {"task_id": "proto-cs-002"},
            )
            assert result.isError is not True
            content = result.content[0]
            assert isinstance(content, TextContent)
            data = json.loads(content.text)
            assert data["status"] == "cancelled"

    async def test_get_locks_via_protocol(self):
        """get_locks through the protocol returns empty locks, then populated."""
        async with _connected_session_no_lifespan() as session:
            engine = _fresh_engine()
            _inject_subagent_globals(engine=engine)

            # Empty locks
            result = await session.call_tool("get_locks", {})
            assert result.isError is not True
            content = result.content[0]
            assert isinstance(content, TextContent)
            data = json.loads(content.text)
            assert data["locks"] == []
            assert data["count"] == 0

            # Add a lock and verify
            engine.create_task(
                "vaultspec-simple-executor",
                task_id="proto-cs-003",
            )
            engine._lock_manager.acquire_lock(
                "proto-cs-003",
                {".vault/plan.md"},
                "read-only",
            )

            result = await session.call_tool("get_locks", {})
            assert result.isError is not True
            content = result.content[0]
            assert isinstance(content, TextContent)
            data = json.loads(content.text)
            assert data["count"] == 1
            assert data["locks"][0]["agent"] == "vaultspec-simple-executor"


class TestErrorPropagation:
    """Verify that ToolError becomes CallToolResult(isError=True) via protocol.

    Through the MCP protocol, ToolError does NOT raise a Python exception.
    It is caught by FastMCP and converted to ``isError=True`` with text content.
    """

    async def test_dispatch_unknown_agent_returns_error(self):
        """Dispatching an unknown agent returns isError with 'not found' text."""
        async with _connected_session_no_lifespan() as session:
            _inject_subagent_globals(agent_cache=_baker_cache())

            result = await session.call_tool(
                "dispatch_agent",
                {"agent": "phantom-baker", "task": "Bake nothing"},
            )
            assert result.isError is True
            content = result.content[0]
            assert isinstance(content, TextContent)
            assert "not found" in content.text.lower()

    async def test_get_status_missing_task_returns_error(self):
        """Polling a nonexistent task returns isError."""
        async with _connected_session_no_lifespan() as session:
            engine = _fresh_engine()
            _inject_subagent_globals(engine=engine)

            result = await session.call_tool(
                "get_task_status",
                {"task_id": "nonexistent-task"},
            )
            assert result.isError is True
            content = result.content[0]
            assert isinstance(content, TextContent)
            assert "not found" in content.text.lower()

    async def test_cancel_missing_task_returns_error(self):
        """Cancelling a nonexistent task returns isError."""
        async with _connected_session_no_lifespan() as session:
            engine = _fresh_engine()
            _inject_subagent_globals(engine=engine)

            result = await session.call_tool(
                "cancel_task",
                {"task_id": "nonexistent-task"},
            )
            assert result.isError is True


class TestConcurrentCalls:
    """Verify that concurrent tool calls on a single session all succeed."""

    async def test_parallel_list_agents(self):
        """Fire 5 concurrent list_agents calls; all return valid results."""
        async with _connected_session_no_lifespan() as session:
            _inject_subagent_globals(agent_cache=_baker_cache())

            results = await asyncio.gather(
                *[session.call_tool("list_agents", {}) for _ in range(5)]
            )

            assert len(results) == 5
            for result in results:
                assert result.isError is not True
                data = json.loads(result.content[0].text)
                assert len(data["agents"]) == 1
                assert data["agents"][0]["name"] == "vaultspec-simple-executor"
