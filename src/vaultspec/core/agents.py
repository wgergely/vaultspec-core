"""Agents management for vaultspec."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import types as _t
from .enums import ClaudeModels, GeminiModels, Resource, Tool
from .helpers import _launch_editor, atomic_write, build_file, ensure_dir, resolve_model
from .sync import print_summary, sync_files
from .types import SyncResult

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Maps internal tool names (for agents) to external names in tool-specific formats.
_TOOL_MAPS: dict[Tool, dict[str, str]] = {
    Tool.CLAUDE: {
        "Glob": "Glob",
        "Grep": "Grep",
        "Read": "Read",
        "Write": "Write",
        "Edit": "Edit",
        "Bash": "Bash",
        "WebFetch": "WebFetch",
        "WebSearch": "WebSearch",
        "vaultspec-execute": "execute-plan",
    },
    Tool.GEMINI: {
        "Glob": "glob",
        "Grep": "grep_search",
        "Read": "read_file",
        "Write": "write_file",
        "Edit": "replace",
        "Bash": "run_shell_command",
        "WebFetch": "web_fetch",
        "WebSearch": "google_web_search",
        "vaultspec-execute": "execute_plan",
    },
}


def _translate_tools(tools_value: str | list[str], target: Tool | str) -> list[str]:
    """Translate a tools string or list for *target* tool destination."""
    target_enum = target if isinstance(target, Tool) else Tool(target)
    mapping = _TOOL_MAPS.get(target_enum)

    if isinstance(tools_value, str):
        parts = [t.strip() for t in tools_value.split(",")]
    else:
        parts = tools_value

    if not mapping:
        return parts

    return [mapping.get(p, p) for p in parts]


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
        try:
            content = f.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            sources[f.name] = (f, meta, body)
        except (OSError, Exception) as e:
            logger.error("Failed to read/parse %s: %s", f, e)
            continue
    return sources


def transform_agent(
    tool: Tool,
    name: str,
    meta: dict[str, Any],
    body: str,
) -> str:
    """Transform an agent definition for a specific tool destination.

    Resolves the execution model, translates tool names to the tool's native
    format, and injects tool-agnostic system prompts into a final Markdown
    persona.

    Args:
        tool: Target tool enum (e.g. Tool.CLAUDE).
        name: Logical name of the agent.
        meta: Agent frontmatter metadata.
        body: Raw persona Markdown content.

    Returns:
        The transformed persona content string.
    """
    # 1. Resolve model
    model = meta.get("model")
    if model is None:
        # Default models per tool
        if tool == Tool.GEMINI:
            model = GeminiModels.LOW
        else:
            # Claude and others
            model = ClaudeModels.MEDIUM

    # 2. Tool translations
    tool_map = _TOOL_MAPS.get(tool, {})

    fm: dict[str, Any] = {
        "name": Path(name).stem,
        "description": meta.get("description", ""),
        "kind": "local",
        "model": model,
    }

    # Pass through tool-supported fields, translating names per target.
    if "tools" in meta:
        fm["tools"] = _translate_tools(meta["tools"], tool)
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

    print(f"{'Name':<25} {'Description':<50}")
    print("-" * 75)
    for name, meta_tuple in sources.items():
        _path, meta, _body = meta_tuple
        agent_name = Path(name).stem
        description = meta.get("description", "")
        print(f"{agent_name:<25} {description:<50}")


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
            logger.error("Error opening editor: %s", e, exc_info=True)
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

    content = file_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    old_tier = meta.get("tier", "?")
    meta["tier"] = new_tier

    atomic_write(file_path, build_file(meta, body))
    logger.info("Updated %s: tier %s -> %s", agent_name, old_tier, new_tier)

    logger.info("Run 'agents sync' to propagate changes.")


def agents_sync(
    args: argparse.Namespace,
) -> None:
    """Sync all agent definitions to every configured tool destination.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``dry_run`` and ``prune``.
    """
    sources = collect_agents()
    dry_run = getattr(args, "dry_run", False)
    prune = getattr(args, "prune", False)

    total = SyncResult()
    for tool_type, cfg in _t.TOOL_CONFIGS.items():
        if cfg.agents_dir is None:
            continue
        print(f"  {tool_type.value}: {cfg.agents_dir.relative_to(_t.ROOT_DIR)}")
        result = sync_files(
            sources=sources,
            dest_dir=cfg.agents_dir,
            transform_fn=lambda _tool, n, m, b, _tt=tool_type: transform_agent(
                _tt, n, m, b
            ),
            dest_path_fn=lambda dest_dir, name: dest_dir / name,
            prune=prune,
            dry_run=dry_run,
            label=f"agents -> {tool_type.value}",
        )
        total.added += result.added
        total.updated += result.updated
        total.pruned += result.pruned
        total.skipped += result.skipped
        total.errors.extend(result.errors)

    print_summary("Agents", total)
