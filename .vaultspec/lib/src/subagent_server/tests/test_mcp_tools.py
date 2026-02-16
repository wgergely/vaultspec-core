"""Comprehensive tests for all MCP tool functions in the subagent server.

Tests all 5 MCP tools: list_agents, dispatch_agent, get_task_status,
cancel_task, and get_locks.  Also covers internal helpers like
_parse_agent_metadata, _parse_tools, and _inject_permission_prompt.
"""

from __future__ import annotations

import json

import pytest
import subagent_server.server as srv
from mcp.server.fastmcp.exceptions import ToolError
from subagent_server.server import (
    _inject_permission_prompt,
    _parse_agent_metadata,
    _parse_tools,
    _prepare_dispatch_kwargs,
    _resolve_effective_mode,
    _strip_quotes,
    cancel_task,
    dispatch_agent,
    get_locks,
    get_task_status,
    initialize_server,
    list_agents,
)

from orchestration.task_engine import (
    LockManager,
    TaskEngine,
    TaskStatus,
)
from protocol.providers.base import ClaudeModels, GeminiModels

from .conftest import TEST_PROJECT

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _init_server():
    """Initialize server with TEST_PROJECT before each test, reset after."""
    initialize_server(root_dir=TEST_PROJECT, ttl_seconds=60.0)
    yield
    srv._agent_cache.clear()
    srv._background_tasks.clear()
    srv._active_clients.clear()


@pytest.fixture
def fresh_task_engine():
    """A clean TaskEngine with a short TTL for testing."""
    lm = LockManager()
    return TaskEngine(ttl_seconds=60.0, lock_manager=lm)


@pytest.fixture
def baker_cache():
    """Agent cache with a single French Baker agent entry."""
    return {
        "simple-executor": {
            "name": "simple-executor",
            "tier": "LOW",
            "description": "A helpful French Baker agent",
            "default_model": None,
            "default_mode": None,
            "tools": ["Read", "Write"],
        },
        "research-analyst": {
            "name": "research-analyst",
            "tier": "HIGH",
            "description": "A thorough research analyst",
            "default_model": ClaudeModels.HIGH,
            "default_mode": "read-only",
            "tools": ["Read", "Grep", "Glob"],
        },
    }


@pytest.fixture
def agent_md_file(tmp_path):
    """Create a temporary agent markdown file with valid frontmatter."""
    content = f"""\
---
tier: LOW
model: {GeminiModels.LOW}
description: "A helpful French Baker agent"
tools: Read, Write, Bash
mode: read-write
---

# Agent Persona
You are a helpful French Baker who writes excellent code.
"""
    agent_file = tmp_path / "boulanger.md"
    agent_file.write_text(content, encoding="utf-8")
    return agent_file


@pytest.fixture
def agent_md_missing_fields(tmp_path):
    """Create an agent markdown file with minimal frontmatter."""
    content = """\
---
tier: MEDIUM
---

# Agent
A minimal agent definition.
"""
    agent_file = tmp_path / "minimal-agent.md"
    agent_file.write_text(content, encoding="utf-8")
    return agent_file


class TestListAgents:
    """Tests for the list_agents MCP tool."""

    @pytest.mark.asyncio
    async def test_populated_cache(self, baker_cache):
        """list_agents returns all agents from the cache."""
        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        result = await list_agents()
        data = json.loads(result)
        assert len(data["agents"]) == 2
        names = {a["name"] for a in data["agents"]}
        assert "simple-executor" in names
        assert "research-analyst" in names

    @pytest.mark.asyncio
    async def test_empty_cache(self):
        """list_agents returns empty list when no agents are cached."""
        srv._agent_cache = {}
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        result = await list_agents()
        data = json.loads(result)
        assert data["agents"] == []

    @pytest.mark.asyncio
    async def test_response_json_structure(self, baker_cache):
        """list_agents response has correct top-level keys and agent fields."""
        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        result = await list_agents()
        data = json.loads(result)
        assert "agents" in data
        assert "hint" in data
        for agent in data["agents"]:
            assert "name" in agent
            assert "tier" in agent
            assert "description" in agent

    @pytest.mark.asyncio
    async def test_refresh_is_triggered(self, baker_cache):
        """list_agents calls _refresh_if_changed before returning."""
        calls = []

        def _tracking_refresh():
            calls.append(1)
            return False

        srv._agent_cache = baker_cache
        srv._refresh_if_changed = _tracking_refresh  # type: ignore[assignment]
        await list_agents()
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_tier_and_description_passthrough(self, baker_cache):
        """Agent tier and description are passed through correctly."""
        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        result = await list_agents()
        data = json.loads(result)
        executor = next(a for a in data["agents"] if a["name"] == "simple-executor")
        assert executor["tier"] == "LOW"
        assert executor["description"] == "A helpful French Baker agent"


class TestDispatchAgent:
    """Tests for the dispatch_agent MCP tool."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_successful_dispatch(self, baker_cache, fresh_task_engine):
        """Successful dispatch returns taskId and 'working' status."""

        async def _noop(**_kw):
            pass

        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        srv.task_engine = fresh_task_engine
        srv._background_tasks = {}
        srv._active_clients = {}
        srv.run_subagent = _noop  # type: ignore[assignment]
        result = await dispatch_agent(
            agent="simple-executor",
            task="Bake a baguette",
        )
        data = json.loads(result)
        assert data["status"] == "working"
        assert data["agent"] == "simple-executor"
        assert "taskId" in data
        assert data["mode"] == "read-write"

    @pytest.mark.asyncio
    async def test_unknown_agent_raises_tool_error(self, baker_cache):
        """Dispatching an unknown agent raises ToolError."""
        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        with pytest.raises(ToolError, match="not found"):
            await dispatch_agent(
                agent="nonexistent-patissier",
                task="Bake a croissant",
            )

    @pytest.mark.asyncio
    async def test_invalid_mode_raises_tool_error(self, baker_cache, fresh_task_engine):
        """Providing an invalid mode raises ToolError."""
        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        srv.task_engine = fresh_task_engine
        with pytest.raises(ToolError, match="Invalid mode"):
            await dispatch_agent(
                agent="simple-executor",
                task="Bake bread",
                mode="execute-only",
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_model_override_passthrough(self, baker_cache, fresh_task_engine):
        """Model override is included in the dispatch response."""

        async def _noop(**_kw):
            pass

        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        srv.task_engine = fresh_task_engine
        srv._background_tasks = {}
        srv._active_clients = {}
        srv.run_subagent = _noop  # type: ignore[assignment]
        result = await dispatch_agent(
            agent="simple-executor",
            task="Bake sourdough",
            model=ClaudeModels.HIGH,
        )
        data = json.loads(result)
        assert data["model"] == ClaudeModels.HIGH

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_task_engine_creates_task(self, baker_cache, fresh_task_engine):
        """dispatch_agent creates a task in the engine."""

        async def _noop(**_kw):
            pass

        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        srv.task_engine = fresh_task_engine
        srv._background_tasks = {}
        srv._active_clients = {}
        srv.run_subagent = _noop  # type: ignore[assignment]
        result = await dispatch_agent(
            agent="simple-executor",
            task="Proof the dough",
        )
        data = json.loads(result)
        task_id = data["taskId"]
        task_obj = fresh_task_engine.get_task(task_id)
        assert task_obj is not None
        assert task_obj.agent == "simple-executor"
        assert task_obj.status == TaskStatus.WORKING

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_default_mode_from_agent_cache(self, baker_cache, fresh_task_engine):
        """When no mode is passed, uses agent's default_mode from cache."""

        async def _noop(**_kw):
            pass

        srv._agent_cache = baker_cache
        srv._refresh_if_changed = lambda: False  # type: ignore[assignment]
        srv.task_engine = fresh_task_engine
        srv._background_tasks = {}
        srv._active_clients = {}
        srv.run_subagent = _noop  # type: ignore[assignment]
        result = await dispatch_agent(
            agent="research-analyst",
            task="Analyze the flour supply chain",
        )
        data = json.loads(result)
        assert data["mode"] == "read-only"


class TestGetTaskStatus:
    """Tests for the get_task_status MCP tool."""

    @pytest.mark.asyncio
    async def test_working_task(self, fresh_task_engine):
        """Returns status 'working' for an active task."""
        fresh_task_engine.create_task("simple-executor", task_id="task-001")
        srv.task_engine = fresh_task_engine
        srv.lock_manager = fresh_task_engine._lock_manager
        result = await get_task_status(task_id="task-001")
        data = json.loads(result)
        assert data["taskId"] == "task-001"
        assert data["status"] == "working"
        assert data["agent"] == "simple-executor"

    @pytest.mark.asyncio
    async def test_completed_task_with_result(self, fresh_task_engine):
        """Returns status 'completed' with result payload."""
        fresh_task_engine.create_task("simple-executor", task_id="task-002")
        fresh_task_engine.complete_task("task-002", {"summary": "Baguettes baked"})
        srv.task_engine = fresh_task_engine
        srv.lock_manager = fresh_task_engine._lock_manager
        result = await get_task_status(task_id="task-002")
        data = json.loads(result)
        assert data["status"] == "completed"
        assert data["result"]["summary"] == "Baguettes baked"

    @pytest.mark.asyncio
    async def test_failed_task_with_error(self, fresh_task_engine):
        """Returns status 'failed' with error message."""
        fresh_task_engine.create_task("simple-executor", task_id="task-003")
        fresh_task_engine.fail_task("task-003", "Oven caught fire")
        srv.task_engine = fresh_task_engine
        srv.lock_manager = fresh_task_engine._lock_manager
        result = await get_task_status(task_id="task-003")
        data = json.loads(result)
        assert data["status"] == "failed"
        assert data["error"] == "Oven caught fire"

    @pytest.mark.asyncio
    async def test_nonexistent_task_raises_tool_error(self, fresh_task_engine):
        """Querying a nonexistent task raises ToolError."""
        srv.task_engine = fresh_task_engine
        with pytest.raises(ToolError, match="not found"):
            await get_task_status(task_id="task-ghost")

    @pytest.mark.asyncio
    async def test_cancelled_task(self, fresh_task_engine):
        """Returns status 'cancelled' for a cancelled task."""
        fresh_task_engine.create_task("simple-executor", task_id="task-004")
        fresh_task_engine.cancel_task("task-004")
        srv.task_engine = fresh_task_engine
        srv.lock_manager = fresh_task_engine._lock_manager
        result = await get_task_status(task_id="task-004")
        data = json.loads(result)
        assert data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_includes_lock_info_when_present(self, fresh_task_engine):
        """Response includes lock details when the task holds a lock."""
        fresh_task_engine.create_task("simple-executor", task_id="task-005")
        lm = fresh_task_engine._lock_manager
        lm.acquire_lock("task-005", {".vault/plan.md"}, "read-only")
        srv.task_engine = fresh_task_engine
        srv.lock_manager = lm
        result = await get_task_status(task_id="task-005")
        data = json.loads(result)
        assert "lock" in data
        assert ".vault/plan.md" in data["lock"]["paths"]
        assert data["lock"]["mode"] == "read-only"


class TestCancelTask:
    """Tests for the cancel_task MCP tool."""

    @pytest.mark.asyncio
    async def test_cancel_working_task(self, fresh_task_engine):
        """Cancelling a working task returns 'cancelled' status."""
        fresh_task_engine.create_task("simple-executor", task_id="task-010")
        srv.task_engine = fresh_task_engine
        srv._active_clients = {}
        srv._background_tasks = {}
        result = await cancel_task(task_id="task-010")
        data = json.loads(result)
        assert data["status"] == "cancelled"
        assert data["taskId"] == "task-010"
        assert data["agent"] == "simple-executor"

    @pytest.mark.asyncio
    async def test_cancel_already_completed_raises_tool_error(self, fresh_task_engine):
        """Cancelling a completed task raises ToolError."""
        fresh_task_engine.create_task("simple-executor", task_id="task-011")
        fresh_task_engine.complete_task("task-011", {"summary": "Done"})
        srv.task_engine = fresh_task_engine
        with pytest.raises(ToolError, match="already completed"):
            await cancel_task(task_id="task-011")

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_raises_tool_error(self, fresh_task_engine):
        """Cancelling a nonexistent task raises ToolError."""
        srv.task_engine = fresh_task_engine
        with pytest.raises(ToolError, match="not found"):
            await cancel_task(task_id="task-phantom")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_cancel_invokes_graceful_cancel(self):
        """Cancellation sends ACP graceful_cancel when client is active.

        Integration: requires real ACP client with graceful_cancel method.
        """
        pytest.skip("requires real ACP client connection")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_cancel_stops_background_task(self):
        """Cancellation calls .cancel() on the background asyncio.Task.

        Integration: requires real asyncio.Task from a running dispatch.
        """
        pytest.skip("requires real background asyncio.Task from dispatch")


class TestGetLocks:
    """Tests for the get_locks MCP tool."""

    @pytest.mark.asyncio
    async def test_no_active_locks(self, fresh_task_engine):
        """Returns empty lock list when no locks are held."""
        srv.lock_manager = fresh_task_engine._lock_manager
        srv.task_engine = fresh_task_engine
        result = await get_locks()
        data = json.loads(result)
        assert data["locks"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_with_active_locks(self, fresh_task_engine):
        """Returns all active locks with correct structure."""
        lm = fresh_task_engine._lock_manager
        fresh_task_engine.create_task("simple-executor", task_id="task-020")
        fresh_task_engine.create_task("research-analyst", task_id="task-021")
        lm.acquire_lock("task-020", {".vault/plan.md"}, "read-write")
        lm.acquire_lock("task-021", {".vault/adr/001.md"}, "read-only")
        srv.lock_manager = lm
        srv.task_engine = fresh_task_engine
        result = await get_locks()
        data = json.loads(result)
        assert data["count"] == 2
        assert len(data["locks"]) == 2

        task_ids = {lock["taskId"] for lock in data["locks"]}
        assert "task-020" in task_ids
        assert "task-021" in task_ids

    @pytest.mark.asyncio
    async def test_lock_structure(self, fresh_task_engine):
        """Each lock entry includes taskId, agent, paths, mode, acquired_at."""
        lm = fresh_task_engine._lock_manager
        fresh_task_engine.create_task("simple-executor", task_id="task-030")
        lm.acquire_lock("task-030", {".vault/exec/log.md"}, "read-write")
        srv.lock_manager = lm
        srv.task_engine = fresh_task_engine
        result = await get_locks()
        data = json.loads(result)
        lock = data["locks"][0]
        assert lock["taskId"] == "task-030"
        assert lock["agent"] == "simple-executor"
        assert ".vault/exec/log.md" in lock["paths"]
        assert lock["mode"] == "read-write"
        assert "acquired_at" in lock

    @pytest.mark.asyncio
    async def test_lock_with_unknown_task(self):
        """Lock entry shows 'unknown' agent when task is missing from engine."""
        lm = LockManager()
        lm.acquire_lock("orphan-task", {".vault/orphan.md"}, "read-only")
        engine = TaskEngine(ttl_seconds=60.0, lock_manager=lm)
        srv.lock_manager = lm
        srv.task_engine = engine
        result = await get_locks()
        data = json.loads(result)
        assert data["locks"][0]["agent"] == "unknown"


class TestAgentCache:
    """Tests for agent cache helpers: parsing, tools, metadata extraction."""

    def test_parse_agent_metadata_valid(self, agent_md_file):
        """Parses full frontmatter into expected metadata dict."""
        meta = _parse_agent_metadata(agent_md_file)
        assert meta["name"] == "boulanger"
        assert meta["tier"] == "LOW"
        assert meta["description"] == "A helpful French Baker agent"
        assert meta["default_model"] == GeminiModels.LOW
        assert meta["default_mode"] == "read-write"
        tools = meta["tools"]
        assert isinstance(tools, list)
        assert "Read" in tools
        assert "Write" in tools
        assert "Bash" in tools

    def test_parse_agent_metadata_missing_fields(self, agent_md_missing_fields):
        """Parses minimal frontmatter with graceful defaults."""
        meta = _parse_agent_metadata(agent_md_missing_fields)
        assert meta["name"] == "minimal-agent"
        assert meta["tier"] == "MEDIUM"
        assert meta["description"] == ""
        assert meta["default_model"] is None
        assert meta["default_mode"] is None
        assert meta["tools"] == []

    def test_parse_tools_csv(self):
        """_parse_tools splits comma-separated tool names correctly."""
        result = _parse_tools("Read, Write, Bash")
        assert result == ["Read", "Write", "Bash"]

    def test_parse_tools_empty_string(self):
        """_parse_tools returns empty list for empty string."""
        result = _parse_tools("")
        assert result == []

    def test_parse_tools_single_tool(self):
        """_parse_tools handles single tool without commas."""
        result = _parse_tools("Read")
        assert result == ["Read"]

    def test_parse_tools_whitespace_handling(self):
        """_parse_tools strips whitespace from each tool name."""
        result = _parse_tools("  Read ,  Write  ,  Bash  ")
        assert result == ["Read", "Write", "Bash"]


class TestPermissionHelpers:
    """Tests for permission enforcement helpers."""

    def test_inject_permission_prompt_readonly(self):
        """Read-only mode prepends permission instructions."""
        result = _inject_permission_prompt("Do the thing", "read-only")
        assert result.startswith("PERMISSION MODE: READ-ONLY")
        assert "Do the thing" in result

    def test_inject_permission_prompt_readwrite(self):
        """Read-write mode passes task content through unchanged."""
        result = _inject_permission_prompt("Do the thing", "read-write")
        assert result == "Do the thing"

    def test_resolve_effective_mode_explicit(self):
        """Explicit mode overrides agent default."""
        assert _resolve_effective_mode("any", "read-only") == "read-only"

    def test_resolve_effective_mode_from_cache(self):
        """When mode is None, uses agent's default_mode from cache."""
        srv._agent_cache = {"analyst": {"default_mode": "read-only"}}
        assert _resolve_effective_mode("analyst", None) == "read-only"

    def test_resolve_effective_mode_fallback(self):
        """When no mode and no agent default, falls back to read-write."""
        srv._agent_cache = {}
        assert _resolve_effective_mode("any", None) == "read-write"

    def test_strip_quotes_basic(self):
        """Strips surrounding double-quotes."""
        assert _strip_quotes('"hello world"') == "hello world"

    def test_strip_quotes_no_quotes(self):
        """Returns value unchanged when no surrounding quotes."""
        assert _strip_quotes("hello world") == "hello world"


class TestDispatchAgentOverrides:
    """Verify _prepare_dispatch_kwargs builds correct kwargs for run_subagent.

    Tests the pure helper function directly instead of the full dispatch_agent
    flow, which depends on server globals and background tasks.
    """

    def test_max_turns_override(self):
        """max_turns override is included in kwargs."""
        kwargs = _prepare_dispatch_kwargs(
            agent_name="simple-executor",
            task="Bake bread",
            root_dir=TEST_PROJECT,
            mode="read-write",
            max_turns=10,
        )
        assert kwargs["max_turns"] == 10

    def test_budget_override(self):
        """budget override is included in kwargs."""
        kwargs = _prepare_dispatch_kwargs(
            agent_name="simple-executor",
            task="Bake bread",
            root_dir=TEST_PROJECT,
            mode="read-write",
            budget=2.5,
        )
        assert kwargs["budget"] == 2.5

    def test_effort_override(self):
        """effort override is included in kwargs."""
        kwargs = _prepare_dispatch_kwargs(
            agent_name="simple-executor",
            task="Bake bread",
            root_dir=TEST_PROJECT,
            mode="read-write",
            effort="high",
        )
        assert kwargs["effort"] == "high"

    def test_output_format_override(self):
        """output_format override is included in kwargs."""
        kwargs = _prepare_dispatch_kwargs(
            agent_name="simple-executor",
            task="Bake bread",
            root_dir=TEST_PROJECT,
            mode="read-write",
            output_format="json",
        )
        assert kwargs["output_format"] == "json"

    def test_no_overrides_passes_none(self):
        """Without overrides, None values are in kwargs."""
        kwargs = _prepare_dispatch_kwargs(
            agent_name="simple-executor",
            task="Bake bread",
            root_dir=TEST_PROJECT,
            mode="read-write",
        )
        assert kwargs["max_turns"] is None
        assert kwargs["budget"] is None
        assert kwargs["effort"] is None
        assert kwargs["output_format"] is None

    def test_all_overrides_combined(self):
        """All overrides are passed together correctly."""
        kwargs = _prepare_dispatch_kwargs(
            agent_name="simple-executor",
            task="Bake bread",
            root_dir=TEST_PROJECT,
            mode="read-only",
            model=ClaudeModels.HIGH,
            max_turns=5,
            budget=1.0,
            effort="low",
            output_format="json",
        )
        assert kwargs["agent_name"] == "simple-executor"
        assert kwargs["initial_task"] == "Bake bread"
        assert kwargs["root_dir"] == TEST_PROJECT
        assert kwargs["mode"] == "read-only"
        assert kwargs["model_override"] == ClaudeModels.HIGH
        assert kwargs["max_turns"] == 5
        assert kwargs["budget"] == 1.0
        assert kwargs["effort"] == "low"
        assert kwargs["output_format"] == "json"
        assert kwargs["interactive"] is False
        assert kwargs["quiet"] is True


class TestParseAgentMetadataExtended:
    """Verify _parse_agent_metadata extracts new optional fields."""

    def test_max_turns_parsed(self, tmp_path):
        agent_file = tmp_path / "test.md"
        agent_file.write_text(
            "---\ndescription: test\nmax_turns: 25\n---\nBody",
            encoding="utf-8",
        )
        meta = _parse_agent_metadata(agent_file)
        assert meta["max_turns"] == 25

    def test_budget_parsed(self, tmp_path):
        agent_file = tmp_path / "test.md"
        agent_file.write_text(
            "---\ndescription: test\nbudget: 1.5\n---\nBody",
            encoding="utf-8",
        )
        meta = _parse_agent_metadata(agent_file)
        assert meta["budget"] == 1.5

    def test_effort_parsed(self, tmp_path):
        agent_file = tmp_path / "test.md"
        agent_file.write_text(
            "---\ndescription: test\neffort: high\n---\nBody",
            encoding="utf-8",
        )
        meta = _parse_agent_metadata(agent_file)
        assert meta["effort"] == "high"

    def test_allowed_tools_parsed(self, tmp_path):
        agent_file = tmp_path / "test.md"
        agent_file.write_text(
            "---\ndescription: test\nallowed_tools: Glob, Read\n---\nBody",
            encoding="utf-8",
        )
        meta = _parse_agent_metadata(agent_file)
        assert meta["allowed_tools"] == ["Glob", "Read"]

    def test_fallback_model_parsed(self, tmp_path):
        agent_file = tmp_path / "test.md"
        agent_file.write_text(
            f"---\ndescription: test\nfallback_model: {ClaudeModels.LOW}\n---\nBody",
            encoding="utf-8",
        )
        meta = _parse_agent_metadata(agent_file)
        assert meta["fallback_model"] == ClaudeModels.LOW

    def test_no_extended_fields_in_minimal(self, tmp_path):
        """Minimal agent with no extended fields doesn't include them."""
        agent_file = tmp_path / "test.md"
        agent_file.write_text(
            "---\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        meta = _parse_agent_metadata(agent_file)
        assert "max_turns" not in meta
        assert "budget" not in meta
        assert "effort" not in meta
        assert "allowed_tools" not in meta
        assert "fallback_model" not in meta
