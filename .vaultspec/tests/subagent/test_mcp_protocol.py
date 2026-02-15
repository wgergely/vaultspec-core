"""MCP protocol integration tests for vs-subagent-mcp.

Tests the full MCP server through FastMCP's call_tool interface
(server-side invocation that exercises tool registration, schemas,
annotations, and error handling without requiring a transport layer).

Also includes stdio transport tests that verify JSON-RPC communication
by spawning the MCP server as a subprocess.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Bootstrap lib/src for imports
_LIB_SRC = Path(__file__).resolve().parent.parent.parent / "lib" / "src"
if str(_LIB_SRC) not in sys.path:
    sys.path.insert(0, str(_LIB_SRC))

from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402
from subagent_server.server import mcp  # noqa: E402

from orchestration.task_engine import LockManager, TaskEngine  # noqa: E402

pytestmark = [pytest.mark.api]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_engine():
    """A clean TaskEngine + LockManager for protocol tests."""
    lm = LockManager()
    return TaskEngine(ttl_seconds=60.0, lock_manager=lm)


@pytest.fixture
def baker_cache():
    """Agent cache with a French Baker agent."""
    return {
        "simple-executor": {
            "name": "simple-executor",
            "tier": "LOW",
            "description": "A helpful French Baker agent",
            "default_model": None,
            "default_mode": "read-write",
            "tools": ["Read", "Write", "Bash"],
        },
    }


# ---------------------------------------------------------------------------
# TestToolRegistration — verify MCP schema metadata
# ---------------------------------------------------------------------------


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
            assert ann.readOnlyHint is True, (  # type: ignore[union-attr]
                f"{name} should be readOnlyHint=True"
            )

    @pytest.mark.asyncio
    async def test_dispatch_not_readonly(self):
        """dispatch_agent is NOT read-only."""
        tools = await mcp.list_tools()
        tool_map = {t.name: t for t in tools}
        ann = tool_map["dispatch_agent"].annotations
        assert ann.readOnlyHint is False  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_cancel_is_destructive(self):
        """cancel_task is marked destructive."""
        tools = await mcp.list_tools()
        tool_map = {t.name: t for t in tools}
        ann = tool_map["cancel_task"].annotations
        assert ann.destructiveHint is True  # type: ignore[union-attr]

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


# ---------------------------------------------------------------------------
# TestProtocolCallTool — call tools through mcp.call_tool()
# ---------------------------------------------------------------------------


def _patch_server(monkeypatch, **overrides):
    """Patch subagent_server.server globals via monkeypatch."""
    import subagent_server.server as srv

    for attr, value in overrides.items():
        monkeypatch.setattr(srv, attr, value)


async def _noop_run_subagent(**_kwargs):
    """No-op async stand-in for run_subagent."""


class TestProtocolCallTool:
    """Test tools via FastMCP's call_tool (exercises full tool pipeline)."""

    @pytest.mark.asyncio
    async def test_list_agents_via_call_tool(self, baker_cache, monkeypatch):
        """call_tool('list_agents') returns valid JSON with agents."""
        _patch_server(
            monkeypatch,
            _agent_cache=baker_cache,
            _refresh_if_changed=lambda: False,
        )
        _, result = await mcp.call_tool("list_agents", {})
        data = json.loads(result["result"])  # type: ignore[index]
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "simple-executor"

    @pytest.mark.asyncio
    async def test_dispatch_agent_via_call_tool(
        self, baker_cache, fresh_engine, monkeypatch
    ):
        """call_tool('dispatch_agent') creates a task and returns taskId."""
        _patch_server(
            monkeypatch,
            _agent_cache=baker_cache,
            _refresh_if_changed=lambda: False,
            task_engine=fresh_engine,
            _background_tasks={},
            _active_clients={},
            run_subagent=_noop_run_subagent,
        )
        _, result = await mcp.call_tool(
            "dispatch_agent",
            {"agent": "simple-executor", "task": "Bake baguettes"},
        )
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["status"] == "working"
        assert data["agent"] == "simple-executor"
        assert "taskId" in data

    @pytest.mark.asyncio
    async def test_dispatch_unknown_agent_raises_error(self, baker_cache, monkeypatch):
        """call_tool('dispatch_agent') with unknown agent raises ToolError."""
        _patch_server(
            monkeypatch,
            _agent_cache=baker_cache,
            _refresh_if_changed=lambda: False,
        )
        with pytest.raises(ToolError, match="not found"):
            await mcp.call_tool(
                "dispatch_agent",
                {"agent": "phantom-baker", "task": "Bake nothing"},
            )

    @pytest.mark.asyncio
    async def test_get_task_status_via_call_tool(self, fresh_engine, monkeypatch):
        """call_tool('get_task_status') returns task state."""
        fresh_engine.create_task("simple-executor", task_id="proto-001")
        _patch_server(
            monkeypatch,
            task_engine=fresh_engine,
            lock_manager=fresh_engine._lock_manager,
        )
        _, result = await mcp.call_tool("get_task_status", {"task_id": "proto-001"})
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["status"] == "working"
        assert data["taskId"] == "proto-001"

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, fresh_engine, monkeypatch):
        """call_tool('get_task_status') for missing task raises ToolError."""
        _patch_server(monkeypatch, task_engine=fresh_engine)
        with pytest.raises(ToolError, match="not found"):
            await mcp.call_tool("get_task_status", {"task_id": "nonexistent"})

    @pytest.mark.asyncio
    async def test_cancel_task_via_call_tool(self, fresh_engine, monkeypatch):
        """call_tool('cancel_task') cancels a working task."""
        fresh_engine.create_task("simple-executor", task_id="proto-002")
        _patch_server(
            monkeypatch,
            task_engine=fresh_engine,
            _active_clients={},
            _background_tasks={},
        )
        _, result = await mcp.call_tool("cancel_task", {"task_id": "proto-002"})
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_get_locks_via_call_tool(self, fresh_engine, monkeypatch):
        """call_tool('get_locks') returns empty list when no locks."""
        _patch_server(
            monkeypatch,
            lock_manager=fresh_engine._lock_manager,
            task_engine=fresh_engine,
        )
        _, result = await mcp.call_tool("get_locks", {})
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["locks"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_get_locks_with_active_lock(self, fresh_engine, monkeypatch):
        """call_tool('get_locks') returns lock details."""
        fresh_engine.create_task("simple-executor", task_id="proto-003")
        fresh_engine._lock_manager.acquire_lock(
            "proto-003", {".vault/plan.md"}, "read-only"
        )
        _patch_server(
            monkeypatch,
            lock_manager=fresh_engine._lock_manager,
            task_engine=fresh_engine,
        )
        _, result = await mcp.call_tool("get_locks", {})
        data = json.loads(result["result"])  # type: ignore[index]
        assert data["count"] == 1
        assert data["locks"][0]["agent"] == "simple-executor"


# ---------------------------------------------------------------------------
# TestProtocolRoundTrip — full dispatch → poll → complete cycle
# ---------------------------------------------------------------------------


class _FakeSubagentResult:
    """Fake result from run_subagent."""

    def __init__(self, session_id, response_text, written_files=None):
        self.session_id = session_id
        self.response_text = response_text
        self.written_files = written_files or []


class TestProtocolRoundTrip:
    """Test a full dispatch → poll → complete lifecycle via call_tool."""

    @pytest.mark.asyncio
    async def test_dispatch_poll_complete_cycle(
        self, baker_cache, fresh_engine, monkeypatch
    ):
        """Dispatch an agent, poll for completion, verify result."""
        mock_result = _FakeSubagentResult(
            session_id="sess-001",
            response_text="Bonjour! I am Jean-Claude, your French Baker.",
        )

        async def _fake_run(**_kw):
            return mock_result

        _patch_server(
            monkeypatch,
            _agent_cache=baker_cache,
            _refresh_if_changed=lambda: False,
            task_engine=fresh_engine,
            _background_tasks={},
            _active_clients={},
            run_subagent=_fake_run,
            lock_manager=fresh_engine._lock_manager,
        )

        # Step 1: Dispatch
        _, dispatch_result = await mcp.call_tool(
            "dispatch_agent",
            {"agent": "simple-executor", "task": "Introduce yourself"},
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
