"""Tests for MCP vault tools (find + create) using a real FastMCP server."""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from vaultspec_core.config import reset_config
from vaultspec_core.core.types import init_paths
from vaultspec_core.mcp_server.app import create_server
from vaultspec_core.vaultcore.models import DocType


def _vault_doc(doc_type: str, feature: str, date: str, heading: str = "") -> str:
    text = (
        "---\n"
        f"tags:\n  - '#{doc_type}'\n  - '#{feature}'\n"
        f"date: '{date}'\n"
        "related: []\n"
        "---\n"
    )
    if heading:
        text += f"{heading}\n"
    return text


def _data(result) -> Any:
    """Extract Python object from a CallToolResult."""
    error_texts = [c.text for c in result.content if hasattr(c, "text")]
    assert not result.isError, f"Tool returned error: {error_texts}"
    if result.structuredContent is not None:
        sc = result.structuredContent
        if isinstance(sc, dict) and list(sc.keys()) == ["result"]:
            return sc["result"]
        return sc
    import json

    texts = [c.text for c in result.content if hasattr(c, "text")]
    if len(texts) == 1:
        return json.loads(texts[0])
    return [json.loads(t) for t in texts]


@pytest.fixture
def vault_root(tmp_path):
    """Create a minimal vault + vaultspec structure, init global paths."""
    reset_config()

    vault_dir = tmp_path / ".vault"
    for dt in DocType:
        (vault_dir / dt.value).mkdir(parents=True)

    templates_dir = tmp_path / ".vaultspec" / "rules" / "templates"
    templates_dir.mkdir(parents=True)

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

    for subdir in ("agents", "rules", "skills"):
        (tmp_path / ".vaultspec" / "rules" / subdir).mkdir(parents=True, exist_ok=True)

    init_paths(tmp_path)
    yield tmp_path
    reset_config()


@pytest.mark.asyncio
async def test_find_lists_features_when_no_args(vault_root):
    (vault_root / ".vault" / "adr" / "2026-03-06-feat-a-adr.md").write_text(
        _vault_doc("adr", "feat-a", "2026-03-06", "# ADR A")
    )
    (vault_root / ".vault" / "plan" / "2026-03-06-feat-a-plan.md").write_text(
        _vault_doc("plan", "feat-a", "2026-03-06", "# Plan A")
    )
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("find", {})
        features = _data(result)
        assert isinstance(features, list)
        assert len(features) >= 1
        feat_a = next((f for f in features if f["name"] == "feat-a"), None)
        assert feat_a is not None
        assert feat_a["doc_count"] >= 2
        assert "weight" in feat_a


@pytest.mark.asyncio
async def test_find_json_returns_enriched_metadata(vault_root):
    (vault_root / ".vault" / "adr" / "2026-03-06-rich-feat-adr.md").write_text(
        _vault_doc("adr", "rich-feat", "2026-03-06", "# ADR")
    )
    (vault_root / ".vault" / "plan" / "2026-03-06-rich-feat-plan.md").write_text(
        _vault_doc("plan", "rich-feat", "2026-03-06", "# Plan")
    )
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("find", {"json": True})
        features = _data(result)
        feat = next((f for f in features if f["name"] == "rich-feat"), None)
        assert feat is not None
        assert feat["status"] == "Planned"
        assert "adr" in feat["types"]
        assert "plan" in feat["types"]


@pytest.mark.asyncio
async def test_find_by_feature(vault_root):
    (vault_root / ".vault" / "adr" / "2026-03-06-my-feat-adr.md").write_text(
        _vault_doc("adr", "my-feat", "2026-03-06", "# ADR")
    )
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("find", {"feature": "my-feat"})
        docs = _data(result)
        assert len(docs) >= 1
        assert all(d["feature"] == "my-feat" for d in docs)


@pytest.mark.asyncio
async def test_find_by_type(vault_root):
    (vault_root / ".vault" / "adr" / "2026-03-06-typed-feat-adr.md").write_text(
        _vault_doc("adr", "typed-feat", "2026-03-06")
    )
    (vault_root / ".vault" / "plan" / "2026-03-06-typed-feat-plan.md").write_text(
        _vault_doc("plan", "typed-feat", "2026-03-06")
    )
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("find", {"type": ["plan"]})
        docs = _data(result)
        assert all(d["type"] == "plan" for d in docs)


@pytest.mark.asyncio
async def test_find_excludes_exec_by_default(vault_root):
    (vault_root / ".vault" / "adr" / "2026-03-06-exc-feat-adr.md").write_text(
        _vault_doc("adr", "exc-feat", "2026-03-06")
    )
    (vault_root / ".vault" / "exec" / "2026-03-06-exc-feat-exec-step1.md").write_text(
        _vault_doc("exec", "exc-feat", "2026-03-06")
    )
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("find", {"feature": "exc-feat"})
        docs = _data(result)
        types = {d["type"] for d in docs}
        assert "exec" not in types
        assert "adr" in types


@pytest.mark.asyncio
async def test_find_includes_exec_when_explicit(vault_root):
    (vault_root / ".vault" / "exec" / "2026-03-06-exp-feat-exec-step1.md").write_text(
        _vault_doc("exec", "exp-feat", "2026-03-06")
    )
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("find", {"type": ["exec"]})
        docs = _data(result)
        assert len(docs) >= 1
        assert all(d["type"] == "exec" for d in docs)


@pytest.mark.asyncio
async def test_find_with_body(vault_root):
    (vault_root / ".vault" / "adr" / "2026-03-06-body-feat-adr.md").write_text(
        _vault_doc("adr", "body-feat", "2026-03-06", "# Body Test")
        + "\nSome body content.\n"
    )
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("find", {"feature": "body-feat", "body": True})
        docs = _data(result)
        assert len(docs) >= 1
        assert "body" in docs[0]
        assert "Some body content" in docs[0]["body"]


@pytest.mark.asyncio
async def test_find_respects_limit(vault_root):
    adr_dir = vault_root / ".vault" / "adr"
    (adr_dir / "2026-03-06-lim-a-adr.md").write_text(
        _vault_doc("adr", "lim-a", "2026-03-06")
    )
    (adr_dir / "2026-03-06-lim-b-adr.md").write_text(
        _vault_doc("adr", "lim-b", "2026-03-06")
    )
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("find", {"type": ["adr"], "limit": 1})
        docs = _data(result)
        assert len(docs) == 1


@pytest.mark.asyncio
async def test_create_document(vault_root):
    today = datetime.date.today().isoformat()
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(
            "create",
            {"feature": "new-feat", "type": "adr", "title": "new-architecture"},
        )
        data = _data(result)
        assert data["success"] is True
        assert (vault_root / ".vault" / "adr" / f"{today}-new-feat-adr.md").exists()


@pytest.mark.asyncio
async def test_create_defaults_to_research(vault_root):
    today = datetime.date.today().isoformat()
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool("create", {"feature": "default-type-feat"})
        data = _data(result)
        assert data["success"] is True
        assert (
            vault_root
            / ".vault"
            / "research"
            / f"{today}-default-type-feat-research.md"
        ).exists()


@pytest.mark.asyncio
async def test_create_duplicate_fails(vault_root):
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        await client.call_tool(
            "create", {"feature": "dup-feat", "type": "adr", "title": "dup"}
        )
        result = await client.call_tool(
            "create",
            {"feature": "dup-feat", "type": "adr", "title": "dup"},
        )
        data = _data(result)
        assert data["success"] is False
        assert "already exists" in data["message"]


@pytest.mark.asyncio
async def test_create_invalid_type(vault_root):
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(
            "create",
            {"feature": "feat", "type": "invalid", "title": "title"},
        )
        data = _data(result)
        assert data["success"] is False
        assert "Invalid document type" in data["message"]


@pytest.mark.asyncio
async def test_create_with_content(vault_root):
    today = datetime.date.today().isoformat()
    mcp = create_server()
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(
            "create",
            {
                "feature": "content-feat",
                "type": "adr",
                "title": "with-content",
                "content": "Extra context here.",
            },
        )
        data = _data(result)
        assert data["success"] is True
        path = vault_root / ".vault" / "adr" / f"{today}-content-feat-adr.md"
        text = path.read_text(encoding="utf-8")
        assert "Extra context here." in text
