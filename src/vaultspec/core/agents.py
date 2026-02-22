"""Agents management for vaultspec."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import types as _t
from .helpers import _launch_editor, build_file, ensure_dir, resolve_model
from .sync import print_summary, sync_files
from .types import SyncResult

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def collect_agents() -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect agent definitions from .vaultspec/rules/agents/.

    Returns:
        A mapping of filename (e.g. ``"my-agent.md"``) to a three-tuple of
        ``(source_path, frontmatter_dict, body_text)``.
    """
    from ..vaultcore import parse_frontmatter

    sources: dict[str, tuple[Path, dict[str, Any], str]] = {}
    if not _t.AGENTS_SRC_DIR.exists():
        return sources
    for f in sorted(_t.AGENTS_SRC_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)
        sources[f.name] = (f, meta, body)
    return sources


def transform_agent(
    tool: str,
    name: str,
    meta: dict[str, Any],
    body: str,
    *,
    resolve_fn: Callable[..., str | None] | None = None,
) -> str | None:
    """Transform an agent definition for a specific tool destination.

    Resolves the agent's capability tier to a model string and assembles the
    final file content with YAML frontmatter.

    Args:
        tool: Target tool name (e.g. ``"claude"`` or ``"gemini"``).
        name: Source filename (e.g. ``"my-agent.md"``).
        meta: Parsed frontmatter dict; must contain ``"tier"`` and optionally
            ``"description"``.
        body: Markdown body text of the agent definition.
        resolve_fn: Optional override for the model-resolution callable. If
            ``None``, the default ``resolve_model`` function is used.

    Returns:
        Assembled file content string, or ``None`` if the agent should be
        skipped (missing tier or no model found for the given tool/tier pair).
    """
    agent_name = Path(name).stem
    description = meta.get("description", "")
    tier = meta.get("tier", "")

    if not tier:
        logger.warning("  Warning: Agent '%s' missing tier.", agent_name)
        return None

    _resolve = resolve_fn or resolve_model
    model = _resolve(tool, tier)
    if model is None:
        msg = f"  Warning: No model for {tool}/{tier}. Skipping {agent_name}."
        logger.warning(msg)
        return None

    fm = {
        "name": agent_name,
        "description": description,
        "kind": "local",
        "model": model,
    }
    return build_file(fm, body)


def agents_list(_args: argparse.Namespace) -> None:
    """Print a tabular list of all available agents with their tier and resolved models.

    Args:
        _args: Parsed CLI arguments (unused).
    """
    sources = collect_agents()
    if not sources:
        print("No agents found.")
        return

    print(f"{'Name':<25} {'Tier':<8} {'Claude':<25} {'Gemini':<25}")
    print("-" * 83)
    for name, meta_tuple in sources.items():
        _path, meta, _body = meta_tuple
        agent_name = Path(name).stem
        tier = meta.get("tier", "?")
        claude_model = resolve_model("claude", tier) or "?"
        gemini_model = resolve_model("gemini", tier) or "?"
        print(f"{agent_name:<25} {tier:<8} {claude_model:<25} {gemini_model:<25}")


def agents_add(args: argparse.Namespace) -> None:
    """Scaffold a new agent definition file and open it in the user's editor.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``name``, ``description``
            (optional), ``tier`` (optional, defaults to ``MEDIUM``), ``template``
            (optional path relative to templates dir), and ``force`` (optional bool
            to allow overwriting an existing file).
    """
    ensure_dir(_t.AGENTS_SRC_DIR)

    file_name = args.name if args.name.endswith(".md") else f"{args.name}.md"
    file_path = _t.AGENTS_SRC_DIR / file_name

    if file_path.exists() and not getattr(args, "force", False):
        logger.error("Error: Agent '%s' exists. Use --force to overwrite.", file_name)
        return

    description = getattr(args, "description", "") or ""
    tier = getattr(args, "tier", "MEDIUM") or "MEDIUM"

    default_body = f"# Persona: {args.name}\n\nDefine your agent persona here.\n"
    body = default_body
    if getattr(args, "template", None):
        tmpl_path = _t.TEMPLATES_DIR / args.template
        if not tmpl_path.suffix:
            tmpl_path = tmpl_path.with_suffix(".md")
        if tmpl_path.exists():
            body = tmpl_path.read_text(encoding="utf-8")
        else:
            logger.warning(
                "Warning: Template '%s' not found at %s", args.template, tmpl_path
            )

    fm = {"description": description, "tier": tier.upper()}
    scaffold = build_file(fm, body)

    if sys.stdin.isatty():
        file_path.write_text(scaffold, encoding="utf-8")
        from ..config import get_config

        editor = get_config().editor
        logger.info("Opening editor (%s) for %s...", editor, file_path)
        try:
            _launch_editor(editor, str(file_path))
            logger.info("Agent saved to %s", file_path)
        except Exception as e:
            logger.error("Error opening editor: %s", e)
    else:
        file_path.write_text(scaffold, encoding="utf-8")
        logger.info("Created agent: %s", file_path)


def agents_set_tier(args: argparse.Namespace) -> None:
    """Update the tier of an agent in its source file.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``name`` (agent filename
            stem) and ``tier`` (one of ``LOW``, ``MEDIUM``, or ``HIGH``).
    """
    from ..vaultcore import parse_frontmatter

    agent_name = args.name
    new_tier = args.tier.upper()

    if new_tier not in ("LOW", "MEDIUM", "HIGH"):
        logger.error("Error: Invalid tier '%s'.", new_tier)
        return

    file_name = agent_name if agent_name.endswith(".md") else f"{agent_name}.md"
    file_path = _t.AGENTS_SRC_DIR / file_name

    if not file_path.exists():
        logger.error("Error: Agent '%s' not found at %s", agent_name, file_path)
        return

    from .helpers import atomic_write

    content = file_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    old_tier = meta.get("tier", "?")
    meta["tier"] = new_tier

    atomic_write(file_path, build_file(meta, body))
    logger.info("Updated %s: tier %s -> %s", agent_name, old_tier, new_tier)

    # Show resolved models
    for tool_name in ["claude", "gemini"]:
        model = resolve_model(tool_name, new_tier)
        if model:
            logger.info("  %s: %s", tool_name, model)

    logger.info("Run 'agents sync' to propagate changes.")


def agents_sync(
    args: argparse.Namespace,
    *,
    resolve_fn: Callable[..., str | None] | None = None,
) -> None:
    """Sync all agent definitions to every configured tool destination.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``dry_run`` and ``prune``.
        resolve_fn: Optional override for model resolution, replacing the default
            ``resolve_model`` function. Useful in tests.
    """
    sources = collect_agents()
    dry_run = getattr(args, "dry_run", False)
    prune = getattr(args, "prune", False)

    total = SyncResult()
    for tool_name, cfg in _t.TOOL_CONFIGS.items():
        if cfg.agents_dir is None:
            continue
        result = sync_files(
            sources=sources,
            dest_dir=cfg.agents_dir,
            transform_fn=lambda _tool, n, m, b, _tn=tool_name: transform_agent(
                _tn, n, m, b, resolve_fn=resolve_fn
            ),
            dest_path_fn=lambda dest_dir, name: dest_dir / name,
            prune=prune,
            dry_run=dry_run,
            label=f"agents -> {tool_name}",
        )
        total.added += result.added
        total.updated += result.updated
        total.pruned += result.pruned
        total.skipped += result.skipped
        total.errors.extend(result.errors)

    print_summary("Agents", total)
