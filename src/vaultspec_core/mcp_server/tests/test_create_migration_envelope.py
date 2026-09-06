"""A failed convergence must refuse the ``create`` call *and say why*.

``create`` decides where it writes from the schema, so it converges the
workspace through ``ensure_migrated`` before its first write. That hook
deliberately propagates: writing some documents into a layout the schema no
longer describes and reporting partial success is the split brain the hook
exists to prevent, and a partial write is harder to recover from than a clean
refusal. So the *shape* is settled - a whole-call protocol error, no ``items``,
matching the CLI and matching every other whole-call refusal on this surface.

What was not settled is that the refusal has to carry its diagnosis. The MCP
SDK forwards a ``ToolError``'s own text and discards the message of anything
else, so an unwrapped ``VaultSpecError`` arrives as the bare string "Error
executing tool create" - issue #330's failure mode, one layer up, and the one
copy of the diagnosis otherwise goes to the server's own stderr where no client
reads it.

The failing convergence here is real, not simulated: a truncated
``providers.json`` is exactly what the driver's ``strict=True`` read refuses
(issue #455), because a manifest whose recorded version is unknown cannot
decide which migrations are pending.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mcp.types import TextContent

from vaultspec_core.mcp_server.app import create_server

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_create_refuses_the_whole_call_when_convergence_fails(
    vault_root: Path,
) -> None:
    """The call fails as a protocol error carrying the real cause."""
    manifest = vault_root / ".vaultspec" / "providers.json"
    manifest.write_text('{"installed": ["claude"', encoding="utf-8")

    mcp = create_server()
    async with Client(mcp) as client:
        result = await client.call_tool(
            "create", {"documents": [{"feature": "envelope-feat", "type": "research"}]}
        )

    assert result.is_error
    # No per-item envelope: the call never reached the item loop.
    assert result.structured_content is None
    texts = " ".join(c.text for c in result.content if isinstance(c, TextContent))
    assert "could not converge" in texts, texts
    assert "Corrupt provider manifest" in texts, texts
    # The manifest's own path is what the operator has to act on.
    assert "providers.json" in texts, texts


async def test_create_writes_nothing_when_convergence_fails(
    vault_root: Path,
) -> None:
    """A refused call leaves the corpus exactly as it was."""
    manifest = vault_root / ".vaultspec" / "providers.json"
    manifest.write_text('{"installed": ["claude"', encoding="utf-8")
    before = sorted(p.name for p in (vault_root / ".vault").rglob("*.md"))

    mcp = create_server()
    async with Client(mcp) as client:
        result = await client.call_tool(
            "create", {"documents": [{"feature": "envelope-feat", "type": "research"}]}
        )

    assert result.is_error
    assert sorted(p.name for p in (vault_root / ".vault").rglob("*.md")) == before
