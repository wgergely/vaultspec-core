"""Register the current vault/spec-core MCP tool surface.

This module binds vault queries, document creation, resource introspection,
workspace status, and vault audit operations onto a FastMCP instance. It is the
MCP adapter for the present vault/spec-core product boundary rather than a
broader orchestration surface.

Usage:
    Call `register_tools(mcp)` to attach the current vault/spec-core tools to a
    FastMCP instance before serving the MCP endpoint.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import Context

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from ..core import types as _t
from ..core.helpers import atomic_write
from ..vaultcore.models import DocType, VaultConstants
from ..vaultcore.parser import parse_vault_metadata
from ..vaultcore.scanner import scan_vault

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]


def register_tools(mcp: FastMCP) -> None:
    """Register vault tools on the given FastMCP instance.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def query_vault(
        ctx: Context,
        query: str | None = None,
        feature: str | None = None,
        type: str | None = None,
        related_to: str | None = None,
        recent: bool = False,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query vault documents by text search, feature, type, related links,
        or recency.

        Provide one or more filters to narrow results. Omitting all filters
        returns all documents up to ``limit``.

        Args:
            ctx: MCP context for logging.
            query: Text to search for in document content or title.
            feature: Filter by feature tag (e.g. "editor-demo").
            type: Filter by document type (e.g. "adr", "plan", "research").
            related_to: Relative path to a document — returns documents linked
                from its ``related:`` frontmatter field.
            recent: If True, return the most recently modified documents
                (one per feature, sorted by date descending).
            limit: Maximum number of results to return (default 20).

        Returns:
            List of matching documents with path, title, type, feature, and date.
        """
        await ctx.info(
            f"query_vault: query={query!r} feature={feature!r} type={type!r} "
            f"related_to={related_to!r} recent={recent} limit={limit}"
        )

        # --- related_to mode ---
        if related_to:
            full_path = _t.TARGET_DIR / related_to
            if not full_path.exists():
                await ctx.warning(f"File not found: {related_to}")
                return []
            try:
                content = full_path.read_text(encoding="utf-8")
                metadata, _ = parse_vault_metadata(content)
            except Exception as e:
                await ctx.error(f"Failed to parse metadata from {related_to}: {e}")
                return []
            link_names = {link.strip("[]") for link in (metadata.related or [])}
            results = []
            for p in scan_vault(_t.TARGET_DIR):
                if p.stem in link_names:
                    try:
                        meta, _ = parse_vault_metadata(p.read_text(encoding="utf-8"))
                        feature_tag = next(
                            (t for t in meta.tags if not DocType.from_tag(t)), None
                        )
                        doc_type = next(
                            (t for t in meta.tags if DocType.from_tag(t)), None
                        )
                        results.append(
                            {
                                "path": str(p.relative_to(_t.TARGET_DIR)),
                                "title": p.stem,
                                "type": doc_type,
                                "feature": feature_tag,
                                "date": meta.date,
                            }
                        )
                    except Exception:
                        continue
            await ctx.debug(f"Found {len(results)} related documents.")
            return results[:limit]

        # --- recent mode ---
        if recent:
            activities = []
            for path in scan_vault(_t.TARGET_DIR):
                try:
                    content = path.read_text(encoding="utf-8")
                    metadata, _ = parse_vault_metadata(content)
                    if not metadata.date:
                        continue
                    feature_tag = next(
                        (t for t in metadata.tags if not DocType.from_tag(t)), None
                    )
                    if not feature_tag:
                        continue
                    doc_type = next(
                        (t for t in metadata.tags if DocType.from_tag(t)), None
                    )
                    activities.append(
                        {
                            "date": metadata.date,
                            "feature": feature_tag,
                            "type": doc_type,
                            "path": str(path.relative_to(_t.TARGET_DIR)),
                        }
                    )
                except Exception:
                    continue
            activities.sort(key=lambda x: x["date"], reverse=True)
            seen: set[str] = set()
            unique: list[dict[str, Any]] = []
            for act in activities:
                if act["feature"] not in seen:
                    seen.add(act["feature"])
                    unique.append(act)
                    if len(unique) >= limit:
                        break
            await ctx.debug(f"Found {len(unique)} recently active features.")
            return unique

        # --- search / filter mode ---
        target_type = f"#{type}" if type and not type.startswith("#") else type
        target_feature = (
            f"#{feature}" if feature and not feature.startswith("#") else feature
        )
        results = []
        for path in scan_vault(_t.TARGET_DIR):
            try:
                content = path.read_text(encoding="utf-8")
                metadata, _body = parse_vault_metadata(content)

                if target_type and target_type not in metadata.tags:
                    continue
                if target_feature and target_feature not in metadata.tags:
                    continue
                if query and query.lower() not in content.lower():
                    continue

                feature_tag = next(
                    (t for t in metadata.tags if not DocType.from_tag(t)), None
                )
                doc_type = next((t for t in metadata.tags if DocType.from_tag(t)), None)
                results.append(
                    {
                        "path": str(path.relative_to(_t.TARGET_DIR)),
                        "title": path.stem,
                        "type": doc_type,
                        "feature": feature_tag,
                        "date": metadata.date,
                    }
                )
            except Exception as e:
                await ctx.error(f"Failed to process {path.name}: {e}")

        await ctx.debug(f"query_vault complete. Found {len(results)} matches.")
        return results[:limit]

    @mcp.tool()
    async def feature_status(feature: str, ctx: Context) -> dict[str, Any]:
        """Get the lifecycle status of a feature based on its vault documents.

        Args:
            feature: Feature name (e.g. "editor-demo").
            ctx: MCP context for logging.

        Returns:
            Status object with determined phase (Unknown/Researching/Specified/
            Planned/In Progress) and document list grouped by type.
        """
        await ctx.info(f"Deriving status for feature: {feature}")
        feature_tag = f"#{feature}" if not feature.startswith("#") else feature
        docs: dict[str, list[str]] = {dt.value: [] for dt in DocType}

        for path in scan_vault(_t.TARGET_DIR):
            try:
                content = path.read_text(encoding="utf-8")
                metadata, _ = parse_vault_metadata(content)

                if feature_tag in metadata.tags:
                    # Determine type
                    for tag in metadata.tags:
                        dt = DocType.from_tag(tag)
                        if dt:
                            docs[dt.value].append(str(path.relative_to(_t.TARGET_DIR)))
            except Exception:
                continue

        # Determine status
        status = "Unknown"
        if docs[DocType.EXEC]:
            status = "In Progress"
        elif docs[DocType.PLAN]:
            status = "Planned"
        elif docs[DocType.ADR]:
            status = "Specified"
        elif docs[DocType.RESEARCH]:
            status = "Researching"

        await ctx.debug(f"Feature '{feature}' status: {status}")
        return {
            "feature": feature,
            "status": status,
            "documents": docs,
        }

    @mcp.tool()
    async def create_vault_document(
        type: str,
        feature: str,
        title: str,
        ctx: Context,
        extra_context: str = "",
    ) -> dict[str, Any]:
        """Create a new vault document from a template.

        Args:
            type: Document type ("adr", "plan", "research", "audit").
            feature: Feature name (kebab-case).
            title: Document title/topic (kebab-case).
            ctx: MCP context for logging.
            extra_context: Optional context to append or inject.

        Returns:
            Result with path and status.
        """
        await ctx.info(f"Creating new {type} for feature: {feature} (title: {title})")
        try:
            doc_type = DocType(type)
        except ValueError:
            return {"success": False, "message": f"Invalid document type: {type}"}

        # Load template
        template_path = _t.TEMPLATES_DIR / f"{type}.md"
        if not template_path.exists():
            return {
                "success": False,
                "message": f"Template not found: {template_path}",
            }

        template = template_path.read_text(encoding="utf-8")

        # Prepare variables
        today = datetime.date.today().isoformat()
        # Clean inputs
        feature_clean = feature.lstrip("#").strip().lower()
        title_clean = title.strip().lower().replace(" ", "-")

        # Replace placeholders
        content = template.replace("{feature}", feature_clean)
        content = content.replace("{yyyy-mm-dd}", today)
        content = content.replace("{topic}", title_clean)  # For research
        content = content.replace("{title}", title_clean)

        if extra_context:
            content += f"\n\n## Extra Context\n\n{extra_context}\n"

        # Generate filename
        filename = f"{today}-{feature_clean}-{type}.md"
        if type == DocType.EXEC:
            # Special handling for exec might be needed, but for now standard pattern
            filename = f"{today}-{feature_clean}-exec-{title_clean}.md"

        # Validate filename
        errors = VaultConstants.validate_filename(filename, doc_type)
        if errors:
            return {
                "success": False,
                "message": f"Filename validation failed: {errors}",
            }

        # Write file
        out_dir = _t.TARGET_DIR / ".vault" / type
        if not out_dir.exists():
            return {"success": False, "message": f"Directory not found: {out_dir}"}

        out_path = out_dir / filename
        if out_path.exists():
            return {"success": False, "message": f"File already exists: {out_path}"}

        try:
            atomic_write(out_path, content)
            await ctx.info(f"Successfully created: {out_path.name}")
            return {
                "success": True,
                "path": str(out_path.relative_to(_t.TARGET_DIR)),
                "message": "Document created successfully.",
            }
        except Exception as e:
            await ctx.error(f"Failed to write document: {e}")
            return {"success": False, "message": f"Write failed: {e}"}

    @mcp.tool()
    async def list_spec_resources(
        resource: Literal["rules", "skills", "agents"],
        ctx: Context,
    ) -> list[dict[str, Any]]:
        """List available spec resources of the given type.

        Args:
            resource: Resource type to list ("rules", "skills", or "agents").
            ctx: MCP context for logging.

        Returns:
            List of resources with name, path, and frontmatter metadata.
        """
        from ..core.agents import collect_agents
        from ..core.rules import collect_rules
        from ..core.skills import collect_skills

        await ctx.info(f"Listing {resource}...")
        collectors = {
            "rules": collect_rules,
            "skills": collect_skills,
            "agents": collect_agents,
        }
        try:
            sources = collectors[resource]()
        except Exception as e:
            await ctx.error(f"Failed to collect {resource}: {e}")
            return []

        results = []
        for name, (path, meta, _body) in sources.items():
            results.append(
                {
                    "name": name,
                    "path": str(path),
                    "metadata": meta,
                }
            )
        await ctx.debug(f"Found {len(results)} {resource}.")
        return results

    @mcp.tool()
    async def get_spec_resource(
        resource: Literal["rules", "skills", "agents"],
        name: str,
        ctx: Context,
    ) -> dict[str, Any]:
        """Get the full content of a named spec resource.

        Args:
            resource: Resource type ("rules", "skills", or "agents").
            name: Resource filename (with or without .md extension).
            ctx: MCP context for logging.

        Returns:
            Resource details including name, path, metadata, and full content.
        """
        from ..core.agents import collect_agents
        from ..core.rules import collect_rules
        from ..core.skills import collect_skills

        await ctx.info(f"Fetching {resource}/{name}...")
        collectors = {
            "rules": collect_rules,
            "skills": collect_skills,
            "agents": collect_agents,
        }
        try:
            sources = collectors[resource]()
        except Exception as e:
            await ctx.error(f"Failed to collect {resource}: {e}")
            return {"error": str(e)}

        key = name if name.endswith(".md") else f"{name}.md"
        if key not in sources:
            await ctx.warning(f"{resource}/{name} not found.")
            return {"error": f"{resource}/{name} not found"}

        path, meta, body = sources[key]
        return {
            "name": key,
            "path": str(path),
            "metadata": meta,
            "content": body,
        }

    @mcp.tool()
    async def workspace_status(
        ctx: Context,
    ) -> dict[str, Any]:
        """Run vault health checks and return structured results.

        Args:
            ctx: MCP context for logging.

        Returns:
            Health check results with pass/fail status and issue details.
        """
        from ..vaultcore.checks import Severity, run_all_checks

        await ctx.info("Running workspace health checks")

        try:
            check_results = run_all_checks(_t.TARGET_DIR)
            diags = []
            for cr in check_results:
                for d in cr.diagnostics:
                    if d.severity != Severity.INFO:
                        diags.append(
                            {
                                "check": cr.check_name,
                                "path": str(d.path) if d.path else None,
                                "message": d.message,
                                "severity": d.severity.value,
                            }
                        )
            return {
                "passed": len(diags) == 0,
                "issues": diags,
            }
        except Exception as e:
            await ctx.error(f"Health check failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def audit_vault(
        ctx: Context,
        summary: bool = True,
        verify: bool = False,
        fix: bool = False,
    ) -> dict[str, Any]:
        """Run audit operations on the .vault directory.

        Args:
            ctx: MCP context for logging.
            summary: Include summary metrics (total docs, features).
            verify: Run consistency and integrity checks.
            fix: Automatically repair common violations.

        Returns:
            Audit results including metrics and any discovered errors or fixes.
        """
        from ..vaultcore.checks import Severity, run_all_checks

        await ctx.info("Running vault audit...")
        results: dict[str, Any] = {}

        if summary:
            from ..metrics import get_vault_metrics

            metrics = get_vault_metrics(_t.TARGET_DIR)
            results["summary"] = {
                "total_docs": metrics.total_docs,
                "total_features": metrics.total_features,
                "counts_by_type": {
                    dt.value: count for dt, count in metrics.counts_by_type.items()
                },
            }

        if verify or fix:
            check_results = run_all_checks(_t.TARGET_DIR, fix=fix)

            all_diags = []
            total_fixed = 0
            for cr in check_results:
                total_fixed += cr.fixed_count
                for d in cr.diagnostics:
                    if d.severity != Severity.INFO:
                        all_diags.append(
                            {
                                "check": cr.check_name,
                                "path": str(d.path) if d.path else None,
                                "message": d.message,
                                "severity": d.severity.value,
                            }
                        )

            results["verification"] = {
                "passed": len(all_diags) == 0,
                "errors": all_diags,
            }

            if fix and total_fixed:
                results["fixed_count"] = total_fixed

        return results
