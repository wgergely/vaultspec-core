"""Register vault-domain MCP tools on a FastMCP instance.

Exposes two tools: ``find`` for vault document discovery and feature listing
(with graph-based weight scoring), and ``create`` for document authoring from
templates. Delegates to the vault query engine and
:class:`~vaultspec_core.graph.VaultGraph`.

Call :func:`register_tools` to attach these tools to a ``FastMCP`` instance
before serving the MCP endpoint.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from ..core import types as _t
from ..core.helpers import atomic_write
from ..vaultcore.models import DocType, VaultConstants

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]

_DEFAULT_TYPES = ["adr", "plan", "research", "reference"]


def _infer_status(types: set[str]) -> str:
    """Infer lifecycle status from the set of document types present."""
    if "exec" in types:
        return "In Progress"
    if "plan" in types:
        return "Planned"
    if "adr" in types:
        return "Specified"
    if "research" in types:
        return "Researching"
    return "Unknown"


def register_tools(mcp: FastMCP) -> None:
    """Register vault tools on the given FastMCP instance."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def find(
        ctx: Context,
        feature: str | None = None,
        type: list[str] | None = None,
        date: str | None = None,
        body: bool = False,
        json: bool = False,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find vault documents or list features.

        With no arguments, returns all features with document count and
        graph weight score.  Add filters to narrow to specific documents.

        The ``type`` filter defaults to adr, plan, research, reference.
        Exec and audit entries are excluded unless explicitly requested.
        """
        from ..graph import VaultGraph
        from ..vaultcore.query import list_documents, list_feature_details

        await ctx.info(
            f"find: feature={feature!r} type={type!r} date={date!r} "
            f"body={body} json={json} limit={limit}"
        )

        # --- Feature listing mode (no filters) ---
        if not feature and not type and not date:
            features = list_feature_details(_t.TARGET_DIR)
            try:
                graph = VaultGraph(_t.TARGET_DIR)
                rankings = dict(graph.get_feature_rankings(limit=100))
            except Exception:
                rankings = {}

            results = []
            for feat in features[:limit]:
                entry: dict[str, Any] = {
                    "name": feat["name"],
                    "doc_count": feat["doc_count"],
                    "weight": rankings.get(feat["name"], 0),
                }
                if json:
                    entry["status"] = _infer_status(set(feat["types"]))
                    entry["types"] = feat["types"]
                    entry["earliest_date"] = feat["earliest_date"]
                    entry["has_plan"] = feat["has_plan"]
                results.append(entry)

            await ctx.debug(f"Listed {len(results)} features.")
            return results

        # --- Document search mode ---
        effective_types = type if type else _DEFAULT_TYPES

        all_docs = []
        for dt in effective_types:
            docs = list_documents(
                _t.TARGET_DIR,
                doc_type=dt,
                feature=feature,
                date=date,
            )
            all_docs.extend(docs)

        results = []
        for doc in all_docs[:limit]:
            entry: dict[str, Any] = {
                "name": doc.name,
                "type": doc.doc_type,
                "feature": doc.feature,
                "date": doc.date,
                "path": str(doc.path.relative_to(_t.TARGET_DIR)),
            }
            if body:
                try:
                    entry["body"] = doc.path.read_text(encoding="utf-8")
                except Exception:
                    entry["body"] = ""
            results.append(entry)

        await ctx.debug(f"Found {len(results)} documents.")
        return results

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def create(
        ctx: Context,
        feature: str,
        type: str | None = None,
        date: str | None = None,
        title: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        """Create a new vault document from a template.

        ``feature`` is required.  ``type`` defaults to ``research``.
        ``date`` defaults to today.
        """
        doc_type_str = type or "research"
        today = date or datetime.date.today().isoformat()
        title_clean = (title or feature).strip().lower().replace(" ", "-")

        await ctx.info(
            f"create: feature={feature!r} type={doc_type_str!r} "
            f"date={today!r} title={title_clean!r}"
        )

        try:
            doc_type = DocType(doc_type_str)
        except ValueError:
            return {
                "success": False,
                "message": f"Invalid document type: {doc_type_str}",
            }

        # Load template
        template_path = _t.TEMPLATES_DIR / f"{doc_type_str}.md"
        if not template_path.exists():
            return {
                "success": False,
                "message": f"Template not found: {template_path}",
            }

        template = template_path.read_text(encoding="utf-8")

        # Clean feature
        feature_clean = feature.lstrip("#").strip().lower()

        # Replace placeholders
        rendered = template.replace("{feature}", feature_clean)
        rendered = rendered.replace("{yyyy-mm-dd}", today)
        rendered = rendered.replace("{topic}", title_clean)
        rendered = rendered.replace("{title}", title_clean)

        if content:
            rendered += f"\n\n## Context\n\n{content}\n"

        # Generate filename
        filename = f"{today}-{feature_clean}-{doc_type_str}.md"
        if doc_type == DocType.EXEC:
            filename = f"{today}-{feature_clean}-exec-{title_clean}.md"

        # Validate filename
        errors = VaultConstants.validate_filename(filename, doc_type)
        if errors:
            return {
                "success": False,
                "message": f"Filename validation failed: {errors}",
            }

        # Write file
        out_dir = _t.TARGET_DIR / ".vault" / doc_type_str
        if not out_dir.exists():
            return {"success": False, "message": f"Directory not found: {out_dir}"}

        out_path = out_dir / filename
        if out_path.exists():
            return {"success": False, "message": f"File already exists: {out_path}"}

        try:
            atomic_write(out_path, rendered)
            await ctx.info(f"Created: {out_path.name}")
            return {
                "success": True,
                "path": str(out_path.relative_to(_t.TARGET_DIR)),
                "message": "Document created successfully.",
            }
        except Exception as e:
            await ctx.error(f"Failed to write document: {e}")
            return {"success": False, "message": f"Write failed: {e}"}
