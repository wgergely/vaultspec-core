"""Tests for the batch-native MCP ``create`` tool.

Drives the real MCPServer over the in-memory client transport against
a :class:`WorkspaceFactory`-installed vault on the real filesystem.  Covers
the intra-batch lifecycle dependency (an item validated against the vault
state including earlier same-batch items), the partial-failure envelope (a
good and a bad item aggregate to ``mixed`` while later items still apply),
and the automatic feature-index regeneration side effect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client

from vaultspec_core.mcp_server.app import create_server

from .conftest import data_of

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _create(client: Client, documents: list[dict[str, Any]]) -> Any:
    result = await client.call_tool("create", {"documents": documents})
    return data_of(result)


async def test_create_batch_intra_batch_lifecycle_dependency(vault_root: Path) -> None:
    """A single batch scaffolds research -> ADR -> plan -> audit coherently.

    ``audit`` requires the artifacts it reviews; because items apply
    sequentially and validation runs against the on-disk vault, the earlier
    same-batch items satisfy the later item without a second call.
    """
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [
                {"feature": "lifecycle-feat", "type": "research"},
                {"feature": "lifecycle-feat", "type": "adr"},
                {"feature": "lifecycle-feat", "type": "plan"},
                {"feature": "lifecycle-feat", "type": "audit"},
            ],
        )
        assert payload["status"] == "ok"
        statuses = [item["status"] for item in payload["items"]]
        assert statuses == ["created", "created", "created", "created"]
        assert (
            vault_root / ".vault" / "adr" / "2026-07-09-lifecycle-feat-adr.md"
        ).exists() or any(
            (vault_root / ".vault" / "adr").glob("*-lifecycle-feat-adr.md")
        )
        assert any((vault_root / ".vault" / "plan").glob("*-lifecycle-feat-plan.md"))
        # Every created item returns a post-write blob hash for chaining.
        assert all(item["blob_hash"] for item in payload["items"])


async def test_create_exec_is_refused_but_later_item_applies(
    vault_root: Path,
) -> None:
    """A bad item fails per-item while good items on both sides still apply.

    ``exec`` is not a scaffold type: execution is logged with the ``log``
    tool. The item fails in place with that message, the batch aggregates to
    ``mixed``, and the item after it is still scaffolded. No exec document
    is written.
    """
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [
                {"feature": "partial-feat", "type": "adr"},
                {"feature": "partial-feat", "type": "exec"},
                {"feature": "other-feat", "type": "research"},
            ],
        )
        assert payload["status"] == "mixed"
        items = payload["items"]
        assert items[0]["status"] == "created"
        assert items[1]["status"] == "failed"
        assert items[1]["error"] is not None
        assert "vault exec log" in items[1]["error"]["message"]
        assert "`log` tool" in items[1]["error"]["message"]
        assert not list((vault_root / ".vault" / "exec").rglob("*partial-feat*"))
        # The item after the failure is still applied.
        assert items[2]["status"] == "created"
        research_dir = vault_root / ".vault" / "research"
        assert any(research_dir.glob("*-other-feat-research.md"))


async def test_create_regenerates_feature_index(vault_root: Path) -> None:
    """Creating documents regenerates the affected feature's index as a side effect."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [
                {"feature": "index-feat", "type": "adr"},
                {"feature": "index-feat", "type": "plan"},
            ],
        )
        assert payload["status"] == "ok"
        index_path = vault_root / ".vault" / "index" / "index-feat.index.md"
        assert index_path.exists()
        index_text = index_path.read_text(encoding="utf-8")
        assert "#index-feat" in index_text


async def test_create_rejects_extra_tags_without_writing(vault_root: Path) -> None:
    """A rejected item writes neither its document nor its feature index."""
    vault = vault_root / ".vault"
    before = {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*.md")}
    async with Client(create_server()) as client:
        payload = await _create(
            client,
            [{"feature": "tag-rejection", "type": "research", "tags": ["review"]}],
        )
    assert payload["status"] == "failed"
    assert "Unsupported tags" in payload["items"][0]["error"]["message"]
    after = {p.relative_to(vault): p.read_bytes() for p in vault.rglob("*.md")}
    assert after == before


async def test_create_rejects_index_type_per_item(vault_root: Path) -> None:
    """An ``index`` spec is a per-item failure, not a whole-call error."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [{"feature": "idx-reject", "type": "index"}],
        )
        assert payload["status"] == "failed"
        assert payload["items"][0]["status"] == "failed"
        assert "auto-generated" in payload["items"][0]["error"]["message"]


async def test_create_rejects_unknown_document_type_per_item(vault_root: Path) -> None:
    """A type outside the taxonomy fails its item with the offending value."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [{"feature": "type-reject", "type": "brief"}],
        )
        assert payload["status"] == "failed"
        item = payload["items"][0]
        assert item["target"] == "brief:type-reject"
        assert item["error"]["message"] == "Invalid document type: brief"


async def test_create_rejects_invalid_plan_tier(vault_root: Path) -> None:
    """A tier outside ``L1``-``L4`` fails the item and writes nothing."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [{"feature": "tier-reject", "type": "plan", "tier": "L5"}],
        )
        assert payload["status"] == "failed"
        assert payload["items"][0]["error"]["message"] == (
            "Invalid tier 'L5'. Allowed values: L1, L2, L3, L4."
        )
        assert not any((vault_root / ".vault" / "plan").glob("*-tier-reject-plan.md"))


async def test_create_reports_unresolvable_related_with_failures(
    vault_root: Path,
) -> None:
    """An unresolvable ``related`` entry fails the item and lists each failure."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [
                {
                    "feature": "related-reject",
                    "type": "research",
                    "related": ["[[no-such-document]]"],
                }
            ],
        )
        assert payload["status"] == "failed"
        error = payload["items"][0]["error"]
        assert error["message"].startswith("Cannot resolve related document(s): ")
        assert error["failures"] == ["[[no-such-document]]"]


async def test_create_empty_batch_raises_protocol_error(vault_root: Path) -> None:
    """An empty batch is a malformed whole-call input surfaced as ``isError``."""
    mcp = create_server()
    async with Client(mcp) as client:
        result = await client.call_tool("create", {"documents": []})
        assert result.is_error


async def test_create_seed_content_appended(vault_root: Path) -> None:
    """Seed content is appended through the shared edit engine as a section."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [
                {
                    "feature": "seed-feat",
                    "type": "adr",
                    "content": "A distinctive seeded paragraph.",
                }
            ],
        )
        assert payload["status"] == "ok"
        adr = next((vault_root / ".vault" / "adr").glob("*-seed-feat-adr.md"))
        text = adr.read_text(encoding="utf-8")
        assert "A distinctive seeded paragraph." in text


async def test_create_topic_infix_scaffolds_second_reference(vault_root: Path) -> None:
    """A topic-infixed spec scaffolds a second same-day reference document."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [
                {"feature": "infix-feat", "type": "reference"},
                {
                    "feature": "infix-feat",
                    "type": "reference",
                    "topic": "engine-wire",
                },
            ],
        )
        assert payload["status"] == "ok"
        ref_dir = vault_root / ".vault" / "reference"
        assert any(ref_dir.glob("*-infix-feat-reference.md"))
        assert any(ref_dir.glob("*-infix-feat-engine-wire-reference.md"))


async def test_create_topic_rejected_for_plan(vault_root: Path) -> None:
    """A topic on a plan spec remains a per-item failure."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [{"feature": "infix-feat", "type": "plan", "topic": "second"}],
        )
        assert payload["status"] == "failed"
        assert "topic is only valid" in payload["items"][0]["error"]["message"]


async def test_create_mixed_batch_accepts_adr_topic_and_rejects_plan_topic(
    vault_root: Path,
) -> None:
    """ADR topics create while plan topics fail without aborting the batch."""
    mcp = create_server()
    async with Client(mcp) as client:
        payload = await _create(
            client,
            [
                {"feature": "mixed-feat", "type": "reference", "topic": "wire"},
                {"feature": "mixed-feat", "type": "adr", "topic": "second"},
                {"feature": "mixed-feat", "type": "plan", "topic": "third"},
                {"feature": "mixed-feat", "type": "research"},
            ],
        )
        assert payload["status"] == "mixed"
        items = payload["items"]
        assert items[0]["status"] == "created"
        assert items[1]["status"] == "created"
        assert items[2]["status"] == "failed"
        assert "topic is only valid" in items[2]["error"]["message"]
        assert items[3]["status"] == "created"
        assert any((vault_root / ".vault" / "adr").glob("*-mixed-feat-second-adr.md"))
