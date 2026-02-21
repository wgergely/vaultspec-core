"""Vault audit and management MCP tools.

Phase 3 will surface the following CLI functionality as MCP tools:
- vault_audit: Run vault audit with summary/features/verify/graph/fix modes
- create_document: Create a new vault document from a template
- index_vault: Build or rebuild the RAG index (GPU required)
- search_vault: Semantic search across indexed vault documents

See :mod:`vaultspec.vault_cli` for the corresponding CLI implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["register_tools"]

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP) -> None:
    """Register vault tools on the given FastMCP instance.

    Currently a no-op stub.  Implementation deferred to Phase 3.
    """
