"""End-to-end tests: MCP server → dispatch_agent → real CLI → response.

Requires:
- Gemini CLI installed and authenticated (``gemini`` on PATH)
- Claude CLI installed and authenticated (``claude`` on PATH)

These tests exercise the full chain: call_tool('dispatch_agent') through
the MCP server, which spawns a real CLI subprocess via ACP, waits for
completion, and verifies the "Jean-Claude" fingerprint in the response.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import TYPE_CHECKING

import pytest

from tests.constants import TEST_PROJECT
from vaultspec.orchestration import LockManager, TaskEngine
from vaultspec.server import create_server

# Module-level FastMCP instance with all tools registered for e2e tests.
mcp = create_server()

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_has_gemini_cli = shutil.which("gemini") is not None
_has_claude_cli = shutil.which("claude") is not None


def _cleanup_test_project(root: Path) -> None:
    """Remove all transient artifacts, preserving .vault/ and README.md."""
    for item in root.iterdir():
        if item.name in (".vault", "README.md", ".gitignore"):
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


@pytest.fixture
def test_project_root() -> Iterator[Path]:
    """Set up test-project as workspace for MCP e2e tests."""
    root = TEST_PROJECT
    (root / ".vaultspec" / "rules" / "agents").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".gemini" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")
    yield root
    _cleanup_test_project(root)


def _write_jean_claude_agent(root: Path) -> None:
    """Write the Jean-Claude test agent to the workspace."""
    (root / ".vaultspec" / "rules" / "agents" / "tester.md").write_text(
        "---\ntier: LOW\n---\n\n# Persona\n"
        "You are Jean-Claude, a helpful French Baker.\n"
        "Your name is Jean-Claude. Always introduce yourself by name.\n"
        "Keep your responses extremely short (one sentence max).\n",
        encoding="utf-8",
    )


@pytest.fixture
def fresh_engine():
    """A clean TaskEngine for MCP e2e tests."""
    lm = LockManager()
    return TaskEngine(ttl_seconds=300.0, lock_manager=lm)


async def _mcp_dispatch_and_wait(
    agent: str,
    task: str,
    root: Path,
    engine: TaskEngine,
    timeout: float = 120.0,
) -> dict:
    """Dispatch an agent via MCP call_tool and poll until completion."""
    import vaultspec.subagent_server.server as _srv
    from vaultspec.subagent_server import initialize_server

    # Initialize server with the test workspace
    initialize_server(
        root_dir=root,
        ttl_seconds=300.0,
        refresh_callback=lambda: False,
    )

    # Build agent cache from disk
    agent_cache: dict = {}
    agents_dir = root / ".vaultspec" / "rules" / "agents"
    if agents_dir.is_dir():
        for md_file in agents_dir.glob("*.md"):
            agent_cache[md_file.stem] = {
                "name": md_file.stem,
                "tier": "LOW",
                "description": "Test agent",
                "default_model": None,
                "default_mode": "read-write",
                "tools": [],
            }

    # Override per-test state
    _srv._agent_cache = agent_cache
    _srv.task_engine = engine
    _srv._background_tasks = {}
    _srv._active_clients = {}
    assert engine._lock_manager is not None
    _srv.lock_manager = engine._lock_manager

    # Dispatch
    _, dispatch_result = await mcp.call_tool(
        "dispatch_agent",
        {"agent": agent, "task": task},
    )
    dispatch_data = json.loads(dispatch_result["result"])  # type: ignore[index]
    task_id = dispatch_data["taskId"]

    # Poll until completed/failed or timeout
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(1.0)
        _, status_result = await mcp.call_tool("get_task_status", {"task_id": task_id})
        status_data = json.loads(status_result["result"])  # type: ignore[index]
        if status_data["status"] in ("completed", "failed"):
            return status_data

    msg = f"Task {task_id} did not complete within {timeout}s"
    raise TimeoutError(msg)


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.skipif(not _has_gemini_cli, reason="Gemini CLI not installed")
@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_mcp_dispatch_gemini(test_project_root, fresh_engine):
    """MCP dispatch_agent → Gemini CLI → Jean-Claude fingerprint."""
    _write_jean_claude_agent(test_project_root)

    result = await _mcp_dispatch_and_wait(
        agent="tester",
        task="What is your name? Reply with only your name.",
        root=test_project_root,
        engine=fresh_engine,
    )

    assert result["status"] == "completed", (
        f"Expected completed, got {result['status']}: {result.get('error', 'no error')}"
    )
    assert "Jean-Claude" in result["result"]["response"], (
        "Gemini agent did not adopt Jean-Claude persona"
    )


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.skipif(not _has_claude_cli, reason="Claude CLI not installed")
@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_mcp_dispatch_claude(test_project_root, fresh_engine):
    """MCP dispatch_agent → Claude CLI → Jean-Claude fingerprint."""
    _write_jean_claude_agent(test_project_root)

    result = await _mcp_dispatch_and_wait(
        agent="tester",
        task="What is your name? Reply with only your name.",
        root=test_project_root,
        engine=fresh_engine,
    )

    assert result["status"] == "completed", (
        f"Expected completed, got {result['status']}: {result.get('error', 'no error')}"
    )
    assert "Jean-Claude" in result["result"]["response"], (
        "Claude agent did not adopt Jean-Claude persona"
    )
