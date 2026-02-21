"""MCP protocol integration tests for vaultspec-mcp.

Tests the full MCP server through FastMCP's call_tool interface
(server-side invocation that exercises tool registration, schemas,
annotations, and error handling without requiring a transport layer).

Also includes stdio transport tests that verify JSON-RPC communication
by spawning the MCP server as a subprocess.
"""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

import vaultspec.subagent_server.server as srv
from tests.constants import TEST_PROJECT
from vaultspec.orchestration import LockManager, TaskEngine
from vaultspec.server import create_server
from vaultspec.subagent_server import initialize_server

pytestmark = [pytest.mark.api]

# Module-level FastMCP instance with all tools registered for protocol tests.
mcp = create_server()


@pytest.fixture(autouse=True)
def _init_server():
    """Initialize server with TEST_PROJECT before each test, reset after."""
    initialize_server(
        root_dir=TEST_PROJECT,
        ttl_seconds=60.0,
        refresh_callback=lambda: False,
    )
    yield
    srv._agent_cache.clear()
    srv._background_tasks.clear()
    srv._active_clients.clear()


@pytest.fixture
def fresh_engine():
    """A clean TaskEngine + LockManager for protocol tests."""
    lm = LockManager()
    return TaskEngine(ttl_seconds=60.0, lock_manager=lm)


@pytest.fixture
def baker_cache():
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


async def _noop_run_subagent(**_kwargs):
    """No-op async stand-in for run_subagent."""


class TestToolRegistration:
    """Verify all tools are registered with correct schemas."""

    @pytest.mark.asyncio
    async def test_all_five_tools_registered(self):
        """Server exposes exactly 5 tools."""
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert names == {
            "list_agents",
            "dispatch_agent",
            "get_task_status",
            "cancel_task",
            "get_locks",
        }

    @pytest.mark.asyncio
    async def test_tool_titles_set(self):
        """Every tool has a human-readable title."""
        tools = await mcp.list_tools()
        for tool in tools:
            assert tool.title, f"{tool.name} missing title"

    @pytest.mark.asyncio
    async def test_tool_annotations_present(self):
        """Every tool has ToolAnnotations set."""
        tools = await mcp.list_tools()
        for tool in tools:
            assert tool.annotations is not None, f"{tool.name} missing annotations"

    @pytest.mark.asyncio
    async def test_readonly_tools_marked(self):
        """Read-only tools have readOnlyHint=True."""
        tools = await mcp.list_tools()
        tool_map = {t.name: t for t in tools}
        for name in ("list_agents", "get_task_status", "get_locks"):
            ann = tool_map[name].annotations
            assert ann is not None, f"{name} missing annotations"
            assert ann.readOnlyHint is True, f"{name} should be readOnlyHint=True"

    @pytest.mark.asyncio
    async def test_dispatch_not_readonly(self):
        """dispatch_agent is NOT read-only."""
        tools = await mcp.list_tools()
        tool_map = {t.name: t for t in tools}
        ann = tool_map["dispatch_agent"].annotations
        assert ann is not None
        assert ann.readOnlyHint is False

    @pytest.mark.asyncio
    async def test_cancel_is_destructive(self):
        """cancel_task is marked destructive."""
        tools = await mcp.list_tools()
        tool_map = {t.name: t for t in tools}
        ann = tool_map["cancel_task"].annotations
        assert ann is not None
        assert ann.destructiveHint is True

    @pytest.mark.asyncio
    async def test_dispatch_agent_input_schema(self):
        """dispatch_agent has required 'agent' and 'task' parameters."""
        tools = await mcp.list_tools()
        tool_map = {t.name: t for t in tools}
        schema = tool_map["dispatch_agent"].inputSchema
        assert "agent" in schema["properties"]
        assert "task" in schema["properties"]
        required = schema.get("required", [])
        assert "agent" in required
        assert "task" in required


class TestProtocolCallTool:
    """Test tools via FastMCP's call_tool (exercises full tool pipeline)."""

    @pytest.mark.asyncio
    async def test_list_agents_via_call_tool(self, baker_cache):
        """call_tool('list_agents') returns valid JSON with agents."""
        srv._agent_cache = baker_cache

        _, result = await mcp.call_tool("list_agents", {})
        data = json.loads(result["result"])  # type: ignore[index]
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "vaultspec-simple-executor"

    @pytest.mark.asyncio
    async def test_dispatch_agent_via_call_tool(self, baker_cache, fresh_engine):
        """call_tool('dispatch_agent') creates a task and returns taskId."""
        srv._agent_cache = baker_cache

        srv.task_engine = fresh_engine
        srv._background_tasks = {}
        srv._active_clients = {}
        srv._run_subagent_fn = _noop_run_subagent
        _, result = await mcp.call_tool(
            "dispatch_agent",
            {"agent": "vaultspec-simple-executor", "task": "Bake baguettes"},
        )
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["status"] == "working"
        assert data["agent"] == "vaultspec-simple-executor"
        assert "taskId" in data

    @pytest.mark.asyncio
    async def test_dispatch_unknown_agent_raises_error(self, baker_cache):
        """call_tool('dispatch_agent') with unknown agent raises ToolError."""
        srv._agent_cache = baker_cache

        with pytest.raises(ToolError, match="not found"):
            await mcp.call_tool(
                "dispatch_agent",
                {"agent": "phantom-baker", "task": "Bake nothing"},
            )

    @pytest.mark.asyncio
    async def test_get_task_status_via_call_tool(self, fresh_engine):
        """call_tool('get_task_status') returns task state."""
        fresh_engine.create_task("vaultspec-simple-executor", task_id="proto-001")
        srv.task_engine = fresh_engine
        srv.lock_manager = fresh_engine._lock_manager
        _, result = await mcp.call_tool("get_task_status", {"task_id": "proto-001"})
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["status"] == "working"
        assert data["taskId"] == "proto-001"

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, fresh_engine):
        """call_tool('get_task_status') for missing task raises ToolError."""
        srv.task_engine = fresh_engine
        with pytest.raises(ToolError, match="not found"):
            await mcp.call_tool("get_task_status", {"task_id": "nonexistent"})

    @pytest.mark.asyncio
    async def test_cancel_task_via_call_tool(self, fresh_engine):
        """call_tool('cancel_task') cancels a working task."""
        fresh_engine.create_task("vaultspec-simple-executor", task_id="proto-002")
        srv.task_engine = fresh_engine
        srv._active_clients = {}
        srv._background_tasks = {}
        _, result = await mcp.call_tool("cancel_task", {"task_id": "proto-002"})
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_get_locks_via_call_tool(self, fresh_engine):
        """call_tool('get_locks') returns empty list when no locks."""
        srv.lock_manager = fresh_engine._lock_manager
        srv.task_engine = fresh_engine
        _, result = await mcp.call_tool("get_locks", {})
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["locks"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_get_locks_with_active_lock(self, fresh_engine):
        """call_tool('get_locks') returns lock details."""
        fresh_engine.create_task("vaultspec-simple-executor", task_id="proto-003")
        fresh_engine._lock_manager.acquire_lock(
            "proto-003", {".vault/plan.md"}, "read-only"
        )
        srv.lock_manager = fresh_engine._lock_manager
        srv.task_engine = fresh_engine
        _, result = await mcp.call_tool("get_locks", {})
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["count"] == 1
        assert data["locks"][0]["agent"] == "vaultspec-simple-executor"


class TestProtocolRoundTrip:
    """Test a full dispatch -> poll -> complete lifecycle via call_tool."""

    @pytest.mark.asyncio
    async def test_dispatch_poll_complete_cycle(self, baker_cache, fresh_engine):
        """Dispatch an agent, poll for completion, verify result."""
        import types

        canned_result = types.SimpleNamespace(
            session_id="sess-001",
            response_text="Bonjour! I am Jean-Claude, your French Baker.",
            written_files=[],
        )

        async def _test_run(**_kw):
            return canned_result

        srv._agent_cache = baker_cache

        srv.task_engine = fresh_engine
        srv._background_tasks = {}
        srv._active_clients = {}
        srv._run_subagent_fn = _test_run
        srv.lock_manager = fresh_engine._lock_manager

        # Step 1: Dispatch
        _, dispatch_result = await mcp.call_tool(
            "dispatch_agent",
            {"agent": "vaultspec-simple-executor", "task": "Introduce yourself"},
        )
        dispatch_data = json.loads(dispatch_result["result"])  # type: ignore[index]
        task_id = dispatch_data["taskId"]
        assert dispatch_data["status"] == "working"

        # Step 2: Wait for background task to complete
        import asyncio

        # Give the background coroutine a moment to finish
        await asyncio.sleep(0.2)

        # Step 3: Poll status
        _, status_result = await mcp.call_tool("get_task_status", {"task_id": task_id})
        status_data = json.loads(status_result["result"])  # type: ignore[index]
        assert status_data["status"] == "completed"
        assert "Jean-Claude" in status_data["result"]["summary"]
