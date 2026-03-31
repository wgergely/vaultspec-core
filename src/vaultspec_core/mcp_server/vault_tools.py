"""Register vault-domain MCP tools on a FastMCP instance.

Exposes two tools: ``find`` for vault document discovery and feature listing
(with graph-based weight scoring), and ``create`` for document authoring from
templates. Delegates to the vault query engine and
:class:`~vaultspec_core.graph.VaultGraph`.

Call :func:`register_tools` to attach these tools to a ``FastMCP`` instance
before serving the MCP endpoint.
"""

from __future__ import annotations

import contextvars
import datetime
import functools
import logging
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from mcp.server.fastmcp import FastMCP

from ..core.helpers import atomic_write
from ..core.types import get_context as _get_ctx
from ..vaultcore.models import DocType, VaultConstants

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]


def _isolated_context(
    fn: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Wrap an async tool handler so it runs in a copied context.

    Each invocation snapshots all :mod:`contextvars` state via
    :func:`contextvars.copy_context` and invokes the handler inside that
    snapshot.  This prevents mutations from leaking between concurrent
    MCP requests without the race-prone manual save/restore pattern.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx_copy = contextvars.copy_context()
        coro = ctx_copy.run(fn, *args, **kwargs)
        return await coro

    return wrapper


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
    """Register the ``find`` and ``create`` vault tools on *mcp*.

    ``find``  - read-only, idempotent tool for feature listing and document
    search with graph-weight scoring via :class:`~vaultspec_core.graph.VaultGraph`.

    ``create``  - idempotent, non-destructive tool that scaffolds a new vault
    document from a type template, replacing ``{feature}``, ``{yyyy-mm-dd}``,
    and ``{title}`` placeholders.

    Args:
        mcp: :class:`~mcp.server.fastmcp.FastMCP` instance to decorate.
    """

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    @_isolated_context
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
            features = list_feature_details(_get_ctx().target_dir)
            graph_unavailable = False
            try:
                graph = VaultGraph(_get_ctx().target_dir)
                rankings = dict(graph.get_feature_rankings(limit=100))
            except (OSError, ValueError) as exc:
                logger.warning("Failed to load vault graph rankings: %s", exc)
                rankings = {}
                graph_unavailable = True

            results = []
            for feat in features[:limit]:
                entry: dict[str, Any] = {
                    "name": feat["name"],
                    "doc_count": feat["doc_count"],
                    "weight": rankings.get(feat["name"], 0),
                }
                if graph_unavailable:
                    entry["_note"] = "graph ranking unavailable"
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
                _get_ctx().target_dir,
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
                "path": str(doc.path.relative_to(_get_ctx().target_dir)),
            }
            if body:
                try:
                    entry["body"] = doc.path.read_text(encoding="utf-8")
                except Exception:
                    logger.warning(
                        "Failed to read body of %s",
                        entry.get("name", "unknown"),
                    )
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
    @_isolated_context
    async def create(
        ctx: Context,
        feature: str,
        type: str | None = None,
        date: str | None = None,
        title: str | None = None,
        content: str | None = None,
        related: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new vault document from a template.

        ``feature`` is required.  ``type`` defaults to ``research``.
        ``date`` defaults to today.

        ``related`` accepts document references in any format (absolute path,
        relative path, filename, stem, or ``[[wiki-link]]``) and resolves
        them to valid ``[[wiki-link]]`` entries in the ``related:``
        frontmatter field.

        ``tags`` adds additional freeform tags beyond the required directory
        and feature tags.

        Feature lifecycle dependencies are validated before creation:
        exec requires plan and ADR, plan warns without ADR, etc.
        """
        import re

        from ..vaultcore.hydration import hydrate_template
        from ..vaultcore.parser import parse_vault_metadata
        from ..vaultcore.resolve import (
            RelatedResolutionError,
            resolve_related_inputs,
            validate_feature_dependencies,
        )

        doc_type_str = type or "research"
        today = date or datetime.date.today().isoformat()
        title_raw = (title or feature).strip().lower().replace(" ", "-")
        title_clean = re.sub(r"[/\\]", "-", title_raw).replace("..", "")
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", title_clean):
            return {
                "success": False,
                "message": (
                    f"Invalid title '{title_raw}'. "
                    "Must be kebab-case (lowercase, digits, hyphens)."
                ),
            }

        await ctx.info(
            f"create: feature={feature!r} type={doc_type_str!r} "
            f"date={today!r} title={title_clean!r} "
            f"related={related!r} tags={tags!r}"
        )

        try:
            doc_type = DocType(doc_type_str)
        except ValueError:
            return {
                "success": False,
                "message": f"Invalid document type: {doc_type_str}",
            }

        # Clean feature and reject path traversal characters
        feature_clean = feature.lstrip("#").strip().lower()
        feature_clean = re.sub(r"[/\\]", "-", feature_clean).replace("..", "")
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", feature_clean):
            return {
                "success": False,
                "message": (
                    f"Invalid feature '{feature}'. "
                    "Must be kebab-case (lowercase, digits, hyphens)."
                ),
            }

        # Validate extra tags
        extra_tags: list[str] | None = None
        if tags:
            extra_tags = []
            for tag in tags:
                normalized = tag.lstrip("#").strip()
                if not re.match(r"^[a-z0-9][a-z0-9-]*$", normalized):
                    return {
                        "success": False,
                        "message": (
                            f"Invalid tag '{tag}'. "
                            "Must be kebab-case (lowercase, digits, hyphens)."
                        ),
                    }
                extra_tags.append(f"#{normalized}")

        # Resolve related paths to wiki-links
        resolved_related: list[str] | None = None
        if related:
            try:
                resolved_related = resolve_related_inputs(
                    related, _get_ctx().target_dir
                )
            except RelatedResolutionError as exc:
                return {
                    "success": False,
                    "message": (
                        "Cannot resolve related document(s): "
                        + ", ".join(exc.failures)
                        + ". Accepted formats: absolute path, relative path, "
                        "filename, stem, or [[wiki-link]]."
                    ),
                }

        # Validate feature dependencies (lifecycle rules)
        dep_diagnostics = validate_feature_dependencies(
            _get_ctx().target_dir, doc_type, feature_clean
        )
        warnings: list[str] = []
        for diag in dep_diagnostics:
            if diag.startswith("ERROR:"):
                return {"success": False, "message": diag}
            elif diag.startswith("WARNING:"):
                warnings.append(diag)

        # Load template
        template_path = _get_ctx().templates_dir / f"{doc_type.value}.md"
        if not template_path.exists():
            return {
                "success": False,
                "message": f"Template not found: {template_path}",
            }

        template = template_path.read_text(encoding="utf-8")

        # Hydrate template with all parameters
        rendered = hydrate_template(
            template,
            feature_clean,
            today,
            title_clean,
            related=resolved_related if resolved_related is not None else [],
            extra_tags=extra_tags,
        )

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
        out_dir = _get_ctx().target_dir / ".vault" / doc_type_str
        if not out_dir.exists():
            return {"success": False, "message": f"Directory not found: {out_dir}"}

        out_path = out_dir / filename
        if out_path.exists():
            return {"success": False, "message": f"File already exists: {out_path}"}

        try:
            atomic_write(out_path, rendered)
            await ctx.info(f"Created: {out_path.name}")

            # Post-creation self-validation
            validation_warnings: list[str] = []
            try:
                doc_content = out_path.read_text(encoding="utf-8")
                metadata, _ = parse_vault_metadata(doc_content)
                validation_warnings = metadata.validate()
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning(
                    "Post-creation validation failed for %s: %s",
                    out_path.name,
                    exc,
                )

            parts = ["Document created successfully."]
            if warnings:
                parts.append(" ".join(warnings))
            if validation_warnings:
                parts.append(f"Validation: {'; '.join(validation_warnings)}")
            message = " ".join(parts)

            return {
                "success": True,
                "path": str(out_path.relative_to(_get_ctx().target_dir)),
                "message": message,
            }
        except Exception as e:
            await ctx.error(f"Failed to write document: {e}")
            return {"success": False, "message": f"Write failed: {e}"}
