"""The gateway cannot reach the hook verbs or ``sync`` (GHSA-w5xf-54cr-fxcq).

The second half of the advisory is a reachability finding, not an argv one. The
gateway's operand and flag validation is sound, and that is precisely why it
does not help here: ``spec hooks add`` followed by ``spec hooks run`` is a pair
of well-formed, fully declared invocations whose declared purpose is to run a
shell command, and ``sync`` fires the lifecycle event that runs one. Because the
model driving ``discover`` and ``invoke`` can have a cloned repository's text in
its context, those verbs must not be callable from the tool surface at all.

These tests drive the real gateway tools over the in-memory client against a
real installed workspace - no stubs and no patched catalog - and assert both
directions: ``invoke`` refuses, and ``discover`` does not advertise. The
read-only hook verbs are asserted to remain reachable, so the denial is a
scalpel rather than a blanket.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from vaultspec_core.mcp_server.catalog import DENYLIST
from vaultspec_core.mcp_server.tools.gateway import register_gateway_tools

from .conftest import data_of, vault_root

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["vault_root"]

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

#: The verbs this advisory closes. Each one either writes a hook, runs one,
#: approves one, or fires the event that runs them.
SHELL_REACHING_VERBS = (
    "sync",
    "spec hooks add",
    "spec hooks run",
    "spec hooks trust",
)


def _gateway_server() -> MCPServer[None]:
    """Build an MCPServer exposing only the two gateway tools."""
    mcp = MCPServer(name="vaultspec-mcp-hook-denial-test")
    register_gateway_tools(mcp)
    return mcp


def _error_text(result: CallToolResult) -> str:
    """Concatenate the text content of a ``CallToolResult`` for assertions."""
    parts = [c.text for c in result.content if isinstance(c, TextContent)]
    return " ".join(parts).lower()


def test_denylist_names_every_shell_reaching_verb() -> None:
    """The static denylist itself carries each verb, before any wiring runs."""
    for verb in SHELL_REACHING_VERBS:
        assert tuple(verb.split()) in DENYLIST, verb


async def test_invoke_refuses_every_shell_reaching_verb(vault_root: Path) -> None:
    """``invoke`` rejects each verb before a process is spawned."""
    mcp = _gateway_server()
    async with Client(mcp) as client:
        for verb in SHELL_REACHING_VERBS:
            result = await client.call_tool("invoke", {"verb": verb})
            assert result.is_error, verb
            text = _error_text(result)
            assert "denylist" in text or "out of scope" in text, verb


async def test_invoke_refuses_the_add_then_run_pair_with_real_arguments(
    vault_root: Path,
) -> None:
    """The two-call chain is refused when spelled exactly as it would be used.

    The arguments are the ones a caller would actually pass, so the refusal is
    proven to come from the verb path rather than from argument validation
    tripping first on a malformed call. The command is inert on purpose.
    """
    mcp = _gateway_server()
    async with Client(mcp) as client:
        added = await client.call_tool(
            "invoke",
            {
                "verb": "spec hooks add",
                "positionals": ["probe"],
                "arguments": {
                    "event": "config.synced",
                    "command": "echo denied-before-spawn",
                },
            },
        )
        assert added.is_error
        assert "out of scope" in _error_text(added)

        ran = await client.call_tool(
            "invoke", {"verb": "spec hooks run", "positionals": ["config.synced"]}
        )
        assert ran.is_error
        assert "out of scope" in _error_text(ran)

    hooks_dir = vault_root / ".vaultspec" / "hooks"
    assert not (hooks_dir / "probe.yaml").exists(), (
        "the refused call still wrote a hook definition"
    )


async def test_discover_never_advertises_a_shell_reaching_verb(
    vault_root: Path,
) -> None:
    """No query surfaces a denied verb, including one that names it directly."""
    mcp = _gateway_server()
    async with Client(mcp) as client:
        for query in ("hooks run shell command", "sync providers", "trust hooks"):
            result = await client.call_tool("discover", {"query": query, "limit": 50})
            payload = data_of(result)
            advertised = {v["verb"] for v in payload["verbs"]}
            for verb in SHELL_REACHING_VERBS:
                assert verb not in advertised, (query, verb)


async def test_read_only_hook_verbs_remain_reachable(vault_root: Path) -> None:
    """Denying the runner must not blind an agent to what a workspace declares."""
    mcp = _gateway_server()
    async with Client(mcp) as client:
        result = await client.call_tool("invoke", {"verb": "spec hooks list"})
        payload = data_of(result)
        assert payload["ok"] is True
        assert payload["exit_code"] == 0
