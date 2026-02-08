"""Gemini & Claude MCP Client Integration Tests.

Real end-to-end integration tests that validate the MCP tool call sequences
a team lead would invoke when coordinating sub-agents via the pp-dispatch
MCP server. No mocking -- all tests dispatch real agents via real API calls.

Requires API keys:
  - GEMINI_API_KEY for Gemini-backed tests
  - ANTHROPIC_API_KEY for Claude-backed tests

Run with::

    pytest -m "integration and gemini_mcp" -v
    pytest -m "integration and claude_mcp" -v
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

import pytest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import mcp_dispatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def has_gemini_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


async def _poll_until_terminal(task_id: str, timeout: float = 180.0) -> dict:
    """Poll get_task_status until the task reaches a terminal state.

    Returns the parsed status dict. Raises TimeoutError if the task
    does not complete within ``timeout`` seconds.
    """
    elapsed = 0.0
    interval = 1.0
    while elapsed < timeout:
        raw = await mcp_dispatch.get_task_status(task_id)
        status = json.loads(raw)
        if status.get("status") != "working":
            return status
        await asyncio.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Task {task_id} did not reach terminal state within {timeout}s")


# ---------------------------------------------------------------------------
# Gemini MCP Team-Lead Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not has_gemini_key(), reason="GEMINI_API_KEY not set")
class TestGeminiMcpTeamLead:
    """Real integration: Gemini sub-agents dispatched through the MCP layer."""

    pytestmark = [pytest.mark.integration, pytest.mark.gemini_mcp]

    @pytest.mark.asyncio
    async def test_list_agents(self):
        """list_agents returns real agent definitions from .rules/agents/."""
        result = await mcp_dispatch.list_agents()
        data = json.loads(result)
        assert "agents" in data
        assert len(data["agents"]) > 0

        names = [a["name"] for a in data["agents"]]
        assert "french-croissant" in names

        for agent in data["agents"]:
            assert "name" in agent
            assert "tier" in agent
            assert "description" in agent

    @pytest.mark.asyncio
    async def test_dispatch_and_poll(self):
        """Dispatch french-croissant via Gemini, poll until completed."""
        result = await mcp_dispatch.dispatch_agent(
            "french-croissant",
            "Say bonjour in one sentence.",
            model="gemini-2.5-flash",
            mode="read-only",
        )
        data = json.loads(result)
        assert data["status"] == "working"
        task_id = data["taskId"]

        status = await _poll_until_terminal(task_id)
        assert status["status"] == "completed"
        assert "result" in status
        assert status["result"]["agent"] == "french-croissant"

    @pytest.mark.asyncio
    async def test_dispatch_and_cancel(self):
        """Dispatch a long task then cancel it before completion."""
        result = await mcp_dispatch.dispatch_agent(
            "french-croissant",
            "Write a 5000-word essay about the history of French pastry.",
            model="gemini-2.5-flash",
        )
        data = json.loads(result)
        task_id = data["taskId"]
        assert data["status"] == "working"

        # Give it a moment to start, then cancel.
        await asyncio.sleep(3.0)
        cancel_raw = await mcp_dispatch.cancel_task(task_id)
        cancel = json.loads(cancel_raw)
        assert cancel["status"] == "cancelled"

        # Verify the terminal state persists.
        await asyncio.sleep(0.5)
        final = json.loads(await mcp_dispatch.get_task_status(task_id))
        assert final["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_locks_visible_during_dispatch(self):
        """Advisory locks are held while a real task is running."""
        result = await mcp_dispatch.dispatch_agent(
            "french-croissant",
            "Describe a croissant in one paragraph.",
            model="gemini-2.5-flash",
            mode="read-only",
        )
        data = json.loads(result)
        task_id = data["taskId"]

        # Locks should be visible while working.
        locks_raw = await mcp_dispatch.get_locks()
        locks = json.loads(locks_raw)
        assert locks["count"] >= 1

        # Wait for completion, then verify lock released.
        await _poll_until_terminal(task_id)
        await asyncio.sleep(0.2)

        locks_after = json.loads(await mcp_dispatch.get_locks())
        task_locks = [
            lk for lk in locks_after.get("locks", [])
            if lk.get("taskId") == task_id
        ]
        assert len(task_locks) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_agent_fails(self):
        """Dispatching a nonexistent agent produces a failed task."""
        result = await mcp_dispatch.dispatch_agent(
            "agent-that-does-not-exist",
            "This should fail.",
        )
        data = json.loads(result)
        task_id = data["taskId"]

        status = await _poll_until_terminal(task_id, timeout=30.0)
        assert status["status"] == "failed"
        assert status.get("error")


# ---------------------------------------------------------------------------
# Claude MCP Team-Lead Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not has_anthropic_key(), reason="ANTHROPIC_API_KEY not set")
class TestClaudeMcpTeamLead:
    """Real integration: Claude sub-agents dispatched through the MCP layer."""

    pytestmark = [pytest.mark.integration, pytest.mark.claude_mcp]

    @pytest.mark.asyncio
    async def test_list_agents(self):
        """list_agents returns real agent definitions."""
        result = await mcp_dispatch.list_agents()
        data = json.loads(result)
        assert len(data["agents"]) > 0
        names = [a["name"] for a in data["agents"]]
        assert "french-croissant" in names

    @pytest.mark.asyncio
    async def test_dispatch_and_poll(self):
        """Dispatch french-croissant via Claude, poll until completed."""
        result = await mcp_dispatch.dispatch_agent(
            "french-croissant",
            "Say bonjour in one sentence.",
            model="claude-haiku-4-5",
            mode="read-only",
        )
        data = json.loads(result)
        assert data["status"] == "working"
        task_id = data["taskId"]

        status = await _poll_until_terminal(task_id)
        assert status["status"] == "completed"
        assert "result" in status
        assert status["result"]["agent"] == "french-croissant"

    @pytest.mark.asyncio
    async def test_dispatch_and_cancel(self):
        """Dispatch a long Claude task then cancel it."""
        result = await mcp_dispatch.dispatch_agent(
            "french-croissant",
            "Write a 5000-word essay about the history of French pastry.",
            model="claude-haiku-4-5",
        )
        data = json.loads(result)
        task_id = data["taskId"]

        await asyncio.sleep(3.0)
        cancel = json.loads(await mcp_dispatch.cancel_task(task_id))
        assert cancel["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_nonexistent_agent_fails(self):
        """Dispatching a nonexistent agent produces a failed task."""
        result = await mcp_dispatch.dispatch_agent(
            "agent-that-does-not-exist",
            "This should fail.",
            model="claude-haiku-4-5",
        )
        data = json.loads(result)
        task_id = data["taskId"]

        status = await _poll_until_terminal(task_id, timeout=30.0)
        assert status["status"] == "failed"
        assert status.get("error")
