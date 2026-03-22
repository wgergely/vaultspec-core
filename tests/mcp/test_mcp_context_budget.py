"""Test that the MCP tool surface stays within a context budget.

Prevents tool definition bloat from consuming agent working context.
A FastMCP server's tool definitions are serialized into every LLM
request  - keeping them compact is a hard requirement.
"""

from __future__ import annotations

import json

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.core.types import init_paths
from vaultspec_core.mcp_server.app import create_server
from vaultspec_core.vaultcore.models import DocType

# Budget: 2 tools ~ 2K chars.  Ceiling at 10K to catch bloat.
MAX_TOOL_DEFINITION_CHARS = 10_000

# Maximum number of tools.
MAX_TOOL_COUNT = 5

# Exact expected tool surface.
EXPECTED_TOOLS = {"find", "create"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_tool_definition(tool) -> str:
    """Serialize a single FastMCP Tool object to a JSON string."""
    tool_def = {
        "name": tool.name,
        "description": tool.description or "",
        "parameters": tool.parameters or {},
    }
    return json.dumps(tool_def, indent=2)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mcp_tools(tmp_path):
    """Create a minimal workspace, build the MCP server, and return tools."""
    reset_config()

    for dt in DocType:
        (tmp_path / ".vault" / dt.value).mkdir(parents=True)

    for subdir in ("templates", "agents", "rules", "skills"):
        (tmp_path / ".vaultspec" / "rules" / subdir).mkdir(parents=True)

    init_paths(tmp_path)

    mcp = create_server()
    tools = mcp._tool_manager._tools

    yield tools

    reset_config()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_tool_count_within_budget(mcp_tools):
    """The total number of registered tools must not exceed MAX_TOOL_COUNT."""
    count = len(mcp_tools)
    assert count <= MAX_TOOL_COUNT, (
        f"Tool count {count} exceeds budget of {MAX_TOOL_COUNT}. "
        f"Registered tools: {sorted(mcp_tools.keys())}"
    )


def test_tool_surface_is_exact(mcp_tools):
    """The registered tool names must match EXPECTED_TOOLS exactly."""
    actual = set(mcp_tools.keys())
    assert actual == EXPECTED_TOOLS, (
        f"Tool surface mismatch.\n"
        f"  Expected: {sorted(EXPECTED_TOOLS)}\n"
        f"  Actual:   {sorted(actual)}\n"
        f"  Extra:    {sorted(actual - EXPECTED_TOOLS)}\n"
        f"  Missing:  {sorted(EXPECTED_TOOLS - actual)}"
    )


def test_tool_definitions_within_context_budget(mcp_tools):
    """Aggregate serialized tool definitions must stay under the char budget."""
    per_tool: list[tuple[str, int]] = []
    total = 0

    for name, tool in mcp_tools.items():
        serialized = _serialize_tool_definition(tool)
        size = len(serialized)
        per_tool.append((name, size))
        total += size

    if total > MAX_TOOL_DEFINITION_CHARS:
        per_tool.sort(key=lambda t: t[1], reverse=True)
        breakdown = "\n".join(f"  {name}: {size:,} chars" for name, size in per_tool)
        pytest.fail(
            f"Aggregate tool definition size ({total:,} chars) exceeds budget "
            f"of {MAX_TOOL_DEFINITION_CHARS:,} chars.\n"
            f"Per-tool breakdown (largest first):\n{breakdown}"
        )


def test_no_duplicate_tool_names(mcp_tools):
    """All registered tool names must be unique."""
    names = list(mcp_tools.keys())
    seen: set[str] = set()
    duplicates: list[str] = []

    for name in names:
        if name in seen:
            duplicates.append(name)
        seen.add(name)

    assert not duplicates, f"Duplicate tool names found: {duplicates}"


def test_all_tools_have_descriptions(mcp_tools):
    """Every registered tool must have a non-empty description."""
    missing: list[str] = []

    for name, tool in mcp_tools.items():
        desc = (tool.description or "").strip()
        if not desc:
            missing.append(name)

    assert not missing, (
        f"Tools missing descriptions: {missing}. "
        "Every tool must have a description so LLMs understand when to use it."
    )
