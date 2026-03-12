"""Tests for MCP vault tools using a real FastMCP server + in-memory transport."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from vaultspec_core.config import reset_config
from vaultspec_core.core.types import init_paths
from vaultspec_core.mcp_server.app import create_server
from vaultspec_core.vaultcore.models import DocType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _data(result) -> Any:
    """Extract Python object from a CallToolResult.

    FastMCP wraps list return types as {"result": [...]} in structuredContent.
    For dict return types, structuredContent is the dict directly.
    Falls back to text content if structuredContent is absent.
    """
    assert not result.isError, (
        f"Tool returned error: {[c.text for c in result.content if hasattr(c, 'text')]}"
    )
    if result.structuredContent is not None:
        sc = result.structuredContent
        # list-returning tools are wrapped: {"result": [...]}
        if isinstance(sc, dict) and list(sc.keys()) == ["result"]:
            return sc["result"]
        return sc
    texts = [c.text for c in result.content if hasattr(c, "text")]
    if len(texts) == 1:
        return json.loads(texts[0])
    return [json.loads(t) for t in texts]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault_root(tmp_path):
    """Create a minimal vault + vaultspec structure, init global paths."""
    reset_config()

    # .vault/ subdirectories
    vault_dir = tmp_path / ".vault"
    for dt in DocType:
        (vault_dir / dt.value).mkdir(parents=True)

    # .vaultspec/ templates
    templates_dir = tmp_path / ".vaultspec" / "rules" / "templates"
    templates_dir.mkdir(parents=True)

    today = datetime.date.today().isoformat()

    (templates_dir / "adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#{feature}'\n"
        "date: '{yyyy-mm-dd}'\nrelated: []\n---\n# {title}\n\nContent.\n"
    )
    (templates_dir / "plan.md").write_text(
        "---\ntags:\n  - '#plan'\n  - '#{feature}'\n"
        "date: '{yyyy-mm-dd}'\nrelated: []\n---\n# {title} plan\n\nContent.\n"
    )
    (templates_dir / "research.md").write_text(
        "---\ntags:\n  - '#research'\n  - '#{feature}'\n"
        "date: '{yyyy-mm-dd}'\nrelated: []\n---\n# {topic}\n\nContent.\n"
    )
    (templates_dir / "exec.md").write_text(
        "---\ntags:\n  - '#exec'\n  - '#{feature}'\n"
        "date: '{yyyy-mm-dd}'\nrelated: []\n---\n# {title}\n\nContent.\n"
    )

    # .vaultspec/ agents, rules, skills dirs (for list_spec_resources / get_spec_resource)
    agents_dir = tmp_path / ".vaultspec" / "rules" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "test-agent.md").write_text(
        "---\nname: test-agent\ndescription: A test agent.\n---\n\n# Instructions\n\nDo things.\n"
    )

    rules_dir = tmp_path / ".vaultspec" / "rules" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "test-rule.md").write_text(
        "---\nname: test-rule\n---\n\n# Rule\n\nAlways do this.\n"
    )

    skills_dir = tmp_path / ".vaultspec" / "rules" / "skills" / "vaultspec-test"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: vaultspec-test\ndescription: Test skill.\n---\n\n# Skill\n\nDo this.\n"
    )

    init_paths(tmp_path)

    yield tmp_path

    reset_config()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_vault_by_query(vault_root):
    adr_dir = vault_root / ".vault" / "adr"
    (adr_dir / "2026-03-06-test-feat-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#test-feat'\ndate: '2026-03-06'\nrelated: []\n---\n"
        "# Test Feature ADR\n\nSome searchable content.\n"
    )

    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("query_vault", {"query": "searchable content"})
        docs = _data(result)
        assert isinstance(docs, list)
        assert len(docs) == 1
        assert docs[0]["feature"] == "#test-feat"

        # no match
        result = await client.call_tool("query_vault", {"query": "nonexistent xyz"})
        assert len(_data(result)) == 0


@pytest.mark.asyncio
async def test_query_vault_by_feature(vault_root):
    adr_dir = vault_root / ".vault" / "adr"
    (adr_dir / "2026-03-06-my-feat-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#my-feat'\ndate: '2026-03-06'\nrelated: []\n---\n# ADR\n"
    )

    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("query_vault", {"feature": "my-feat"})
        docs = _data(result)
        assert len(docs) == 1
        assert docs[0]["type"] == "#adr"


@pytest.mark.asyncio
async def test_query_vault_recent(vault_root):
    adr_dir = vault_root / ".vault" / "adr"
    (adr_dir / "2026-03-01-old-feat-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#old-feat'\ndate: '2026-03-01'\nrelated: []\n---\n# Old\n"
    )
    (adr_dir / "2026-03-06-new-feat-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#new-feat'\ndate: '2026-03-06'\nrelated: []\n---\n# New\n"
    )

    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("query_vault", {"recent": True, "limit": 10})
        docs = _data(result)
        assert len(docs) >= 2
        # Sorted descending by date — newest first
        assert docs[0]["date"] >= docs[1]["date"]


@pytest.mark.asyncio
async def test_query_vault_related_to(vault_root):
    adr_dir = vault_root / ".vault" / "adr"
    plan_dir = vault_root / ".vault" / "plan"

    target = adr_dir / "2026-03-06-target-adr.md"
    target.write_text(
        "---\ntags:\n  - '#adr'\n  - '#target'\ndate: '2026-03-06'\n"
        "related:\n  - '[[2026-03-06-target-plan]]'\n---\n# Target\n"
    )
    (plan_dir / "2026-03-06-target-plan.md").write_text(
        "---\ntags:\n  - '#plan'\n  - '#target'\ndate: '2026-03-06'\nrelated: []\n---\n# Plan\n"
    )

    rel = str(target.relative_to(vault_root))
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("query_vault", {"related_to": rel})
        docs = _data(result)
        assert len(docs) == 1
        assert docs[0]["title"] == "2026-03-06-target-plan"


@pytest.mark.asyncio
async def test_feature_status_lifecycle(vault_root):
    mcp = create_server()

    async with create_connected_server_and_client_session(mcp) as client:
        # Unknown
        result = await client.call_tool("feature_status", {"feature": "lifecycle-feat"})
        status = _data(result)
        assert status["status"] == "Unknown"

    # Researching
    (
        vault_root / ".vault" / "research" / "2026-03-06-lifecycle-feat-research.md"
    ).write_text(
        "---\ntags:\n  - '#research'\n  - '#lifecycle-feat'\ndate: '2026-03-06'\nrelated: []\n---\n"
    )
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("feature_status", {"feature": "lifecycle-feat"})
        assert _data(result)["status"] == "Researching"

    # Specified
    (vault_root / ".vault" / "adr" / "2026-03-06-lifecycle-feat-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#lifecycle-feat'\ndate: '2026-03-06'\nrelated: []\n---\n"
    )
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("feature_status", {"feature": "lifecycle-feat"})
        assert _data(result)["status"] == "Specified"

    # Planned
    (vault_root / ".vault" / "plan" / "2026-03-06-lifecycle-feat-plan.md").write_text(
        "---\ntags:\n  - '#plan'\n  - '#lifecycle-feat'\ndate: '2026-03-06'\nrelated: []\n---\n"
    )
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("feature_status", {"feature": "lifecycle-feat"})
        assert _data(result)["status"] == "Planned"

    # In Progress
    (
        vault_root / ".vault" / "exec" / "2026-03-06-lifecycle-feat-exec-step1.md"
    ).write_text(
        "---\ntags:\n  - '#exec'\n  - '#lifecycle-feat'\ndate: '2026-03-06'\nrelated: []\n---\n"
    )
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("feature_status", {"feature": "lifecycle-feat"})
        assert _data(result)["status"] == "In Progress"


@pytest.mark.asyncio
async def test_create_vault_document(vault_root):
    mcp = create_server()
    today = datetime.date.today().isoformat()

    async with create_connected_server_and_client_session(mcp) as client:
        # Success
        result = await client.call_tool(
            "create_vault_document",
            {"type": "adr", "feature": "new-feat", "title": "new-architecture"},
        )
        data = _data(result)
        assert data["success"] is True
        assert (vault_root / ".vault" / "adr" / f"{today}-new-feat-adr.md").exists()

        # Duplicate → fail
        result = await client.call_tool(
            "create_vault_document",
            {"type": "adr", "feature": "new-feat", "title": "new-architecture"},
        )
        data = _data(result)
        assert data["success"] is False
        assert "already exists" in data["message"]

        # Invalid type → fail
        result = await client.call_tool(
            "create_vault_document",
            {"type": "invalid", "feature": "feat", "title": "title"},
        )
        data = _data(result)
        assert data["success"] is False
        assert "Invalid document type" in data["message"]


@pytest.mark.asyncio
async def test_audit_vault_summary(vault_root):
    adr_dir = vault_root / ".vault" / "adr"
    (adr_dir / "2026-03-06-audit-feat-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#audit-feat'\ndate: '2026-03-06'\nrelated: []\n---\n# Title\n"
    )

    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("audit_vault", {"summary": True})
        data = _data(result)
        assert "summary" in data
        assert data["summary"]["total_docs"] >= 1


@pytest.mark.asyncio
async def test_audit_vault_verify_clean(vault_root):
    # Vertical integrity requires every feature to have a plan document.
    (vault_root / ".vault" / "adr" / "2026-03-06-verify-feat-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#verify-feat'\ndate: '2026-03-06'\nrelated: []\n---\n# Title\n"
    )
    (vault_root / ".vault" / "plan" / "2026-03-06-verify-feat-plan.md").write_text(
        "---\ntags:\n  - '#plan'\n  - '#verify-feat'\ndate: '2026-03-06'\nrelated: []\n---\n# Plan\n"
    )

    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("audit_vault", {"verify": True})
        data = _data(result)
        assert "verification" in data
        assert data["verification"]["passed"] is True


@pytest.mark.asyncio
async def test_list_spec_resources_agents(vault_root):
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("list_spec_resources", {"resource": "agents"})
        items = _data(result)
        assert isinstance(items, list)
        assert len(items) == 1
        assert items[0]["name"] == "test-agent.md"


@pytest.mark.asyncio
async def test_list_spec_resources_rules(vault_root):
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("list_spec_resources", {"resource": "rules"})
        items = _data(result)
        assert len(items) == 1
        assert items[0]["name"] == "test-rule.md"


@pytest.mark.asyncio
async def test_list_spec_resources_skills(vault_root):
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("list_spec_resources", {"resource": "skills"})
        items = _data(result)
        assert len(items) == 1
        assert items[0]["name"] == "vaultspec-test"


@pytest.mark.asyncio
async def test_get_spec_resource_agent(vault_root):
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(
            "get_spec_resource", {"resource": "agents", "name": "test-agent"}
        )
        data = _data(result)
        assert "error" not in data
        assert data["name"] == "test-agent.md"
        assert "Instructions" in data["content"]


@pytest.mark.asyncio
async def test_get_spec_resource_not_found(vault_root):
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(
            "get_spec_resource", {"resource": "agents", "name": "nonexistent"}
        )
        data = _data(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_workspace_status_returns_result(vault_root):
    """workspace_status should return a dict with readiness and/or health keys."""
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("workspace_status", {"check": "all"})
        data = _data(result)
        assert isinstance(data, dict)
        assert "readiness" in data or "health" in data
