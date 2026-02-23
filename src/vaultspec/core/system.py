"""System prompt generation for vaultspec."""

from __future__ import annotations

import argparse
import html
import logging
from pathlib import Path
from typing import Any

from . import types as _t
from .agents import collect_agents
from .config_gen import _is_cli_managed
from .helpers import atomic_write, build_file, ensure_dir
from .skills import collect_skills
from .sync import print_summary
from .types import SyncResult, ToolConfig

try:
    from skills_ref.prompt import to_prompt
except ImportError:
    to_prompt = None

logger = logging.getLogger(__name__)


def collect_system_parts() -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect system prompt parts from .vaultspec/rules/system/.

    Returns:
        A mapping of file stem (e.g. ``"base"``) to a three-tuple of
        ``(source_path, frontmatter_dict, body_text)``.
    """
    from ..vaultcore import parse_frontmatter

    sources: dict[str, tuple[Path, dict[str, Any], str]] = {}
    if not _t.SYSTEM_SRC_DIR.exists():
        return sources
    for f in sorted(_t.SYSTEM_SRC_DIR.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            sources[f.stem] = (f, meta, body)
        except (OSError, Exception) as e:
            logger.error("Failed to read/parse %s: %s", f, e)
            continue
    return sources


def _collect_agent_listing() -> str:
    """Build an XML-formatted section listing all available sub-agents.

    Returns:
        A Markdown string containing an ``<available_subagents>`` XML block,
        or an empty string if no agents are found.
    """
    agents = collect_agents()
    if not agents:
        return ""

    lines = [
        "## Available Sub-Agents",
        "",
        "Sub-agents are specialized expert agents.",
        "Dispatch them using the `vaultspec-subagent` skill.",
        "",
        "<available_subagents>",
    ]

    for name, meta_tuple in agents.items():
        _path, meta, _body = meta_tuple
        agent_name = Path(name).stem
        description = meta.get("description", "")

        lines.append("  <subagent>")
        lines.append("    <name>")
        lines.append(html.escape(agent_name))
        lines.append("    </name>")
        lines.append("    <description>")
        lines.append(html.escape(description))
        lines.append("    </description>")
        lines.append("  </subagent>")

    lines.append("</available_subagents>")
    return "\n".join(lines)


def _collect_skill_listing() -> str:
    """Build a section listing all available skills.

    Uses the ``skills_ref`` XML format when the optional ``skills_ref``
    package is installed; falls back to a plain Markdown bullet list.

    Returns:
        A string containing the skills listing, or an empty string if no
        skills are found.
    """
    skills = collect_skills()
    if not skills:
        return ""

    # Use skills-ref XML format if available
    if to_prompt:
        skill_dirs = [path.parent for path, _, _ in skills.values()]
        try:
            return to_prompt(skill_dirs)
        except Exception as exc:
            logger.warning(
                "skills_ref.to_prompt failed, using Markdown fallback: %s", exc
            )

    # Fallback to Markdown list
    lines = [
        "## Available Skills",
        "",
    ]
    for name, meta_tuple in skills.items():
        _path, meta, _body = meta_tuple
        description = meta.get("description", "")
        lines.append(f"- **{name}**: {description}")
    return "\n".join(lines)


def _generate_system_prompt(cfg: ToolConfig) -> str | None:
    """Assemble a complete system prompt for a tool with a dedicated system_file.

    Combines the ``base.md`` body, tool-specific parts, auto-generated agent
    and skill listings, and remaining shared parts (ordered by ``order``
    frontmatter key).

    Args:
        cfg: Tool configuration; must have ``system_file`` set.

    Returns:
        The assembled system prompt string (newline-separated sections with
        the auto-generated header prepended), or ``None`` if no system parts
        exist or the tool has no ``system_file``.
    """
    if cfg.system_file is None:
        return None

    parts = collect_system_parts()
    if not parts:
        return None

    assembled: list[str] = [_t.CONFIG_HEADER]

    # 1. base.md body first
    if "base" in parts:
        _path, _meta, body = parts["base"]
        assembled.append(body)

    # 2. Tool-specific parts (where meta "tool" matches cfg.name)
    for name, (_path, meta, body) in sorted(parts.items()):
        if name == "base":
            continue
        tool_filter = meta.get("tool")
        if tool_filter is not None and tool_filter == cfg.name:
            assembled.append(body)

    # 3. Auto-generated agent listing
    agent_listing = _collect_agent_listing()
    if agent_listing:
        assembled.append(agent_listing)

    # 4. Auto-generated skill listing
    skill_listing = _collect_skill_listing()
    if skill_listing:
        assembled.append(skill_listing)

    # 5. Remaining shared parts (no "tool" key, not "base", not config-only)
    #    Sorted by order frontmatter (default 50), then by name.
    shared = [
        (name, _path, meta, body)
        for name, (_path, meta, body) in parts.items()
        if name != "base"
        and meta.get("tool") is None
        and meta.get("pipeline") != "config"
    ]
    shared.sort(key=lambda t: (t[2].get("order", 50), t[0]))
    for _name, _path, _meta, body in shared:
        assembled.append(body)

    return "\n\n".join(assembled)


def _generate_system_rules(cfg: ToolConfig) -> str | None:
    """Assemble shared behavioral content as a rule file for tools without system_file.

    Combines the ``base.md`` body and all shared system parts into a single
    ``vaultspec-system.builtin.md`` rule file, formatted with YAML frontmatter
    and the auto-generated header sentinel.

    Args:
        cfg: Tool configuration; must have ``rules_dir`` set.

    Returns:
        The assembled rule file content string, or ``None`` if no system parts
        exist or the tool has no ``rules_dir``.
    """
    if cfg.rules_dir is None:
        return None

    parts = collect_system_parts()
    if not parts:
        return None

    assembled: list[str] = []

    # 1. base.md body first
    if "base" in parts:
        _path, _meta, body = parts["base"]
        assembled.append(body)

    # 2. Shared parts only (no "tool" key, not "base", not config-only)
    #    Sorted by order frontmatter (default 50), then by name.
    shared = [
        (name, _path, meta, body)
        for name, (_path, meta, body) in parts.items()
        if name != "base"
        and meta.get("tool") is None
        and meta.get("pipeline") != "config"
    ]
    shared.sort(key=lambda t: (t[2].get("order", 50), t[0]))
    for _name, _path, _meta, body in shared:
        assembled.append(body)

    if not assembled:
        return None

    content = "\n\n".join(assembled)
    fm = {"name": "vaultspec-system", "trigger": "always_on"}
    return f"{_t.CONFIG_HEADER}\n{build_file(fm, content)}"


def system_show(_args: argparse.Namespace) -> None:
    """Print a table of system prompt parts and their generation targets to stdout.

    Args:
        _args: Parsed CLI arguments (unused).
    """
    parts = collect_system_parts()
    if not parts:
        logger.warning("No system parts found in .vaultspec/rules/system/")
        return

    print(f"{'Name':<25} {'Tool Filter':<15} {'Lines':<8}")
    print("-" * 48)
    for name, (_path, meta, body) in sorted(parts.items()):
        tool_filter = meta.get("tool", "-")
        line_count = len(body.strip().splitlines()) if body.strip() else 0
        print(f"{name:<25} {tool_filter:<15} {line_count:<8}")

    print("\nGeneration targets:")
    for tool_name, cfg in _t.TOOL_CONFIGS.items():
        if cfg.system_file is None:
            continue
        rel = cfg.system_file.relative_to(_t.ROOT_DIR)
        managed = "CLI-managed" if _is_cli_managed(cfg.system_file) else "custom"
        print(f"  {tool_name}: {rel} [{managed}]")


def system_sync(args: argparse.Namespace) -> None:
    """Sync assembled system prompts and behavioral rules to tool destinations.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``dry_run`` and
            ``force`` (bool to overwrite files not previously managed by the CLI).
    """
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    result = SyncResult()

    for _tool_name, cfg in _t.TOOL_CONFIGS.items():
        # Path A: Tool has a system_file -> generate assembled SYSTEM.md
        if cfg.system_file is not None:
            content = _generate_system_prompt(cfg)
            if content is None:
                result.skipped += 1
                continue

            rel = cfg.system_file.relative_to(_t.ROOT_DIR)

            # Safety guard
            if (
                cfg.system_file.exists()
                and not _is_cli_managed(cfg.system_file)
                and not force
            ):
                logger.warning("    [SKIP] %s - file exists with custom content.", rel)
                logger.warning("           Use --force to overwrite.")
                result.skipped += 1
                continue

            action = "[UPDATE]" if cfg.system_file.exists() else "[ADD]"

            if dry_run:
                logger.info("    %s %s", action, rel)
            else:
                ensure_dir(cfg.system_file.parent)
                atomic_write(cfg.system_file, content)

            if action == "[ADD]":
                result.added += 1
            else:
                result.updated += 1

        # Path B: Tool has rules_dir but no system_file -> generate behavioral rule
        elif cfg.rules_dir is not None:
            content = _generate_system_rules(cfg)
            if content is None:
                continue

            rule_path = cfg.rules_dir / "vaultspec-system.builtin.md"
            rel = rule_path.relative_to(_t.ROOT_DIR)
            action = "[UPDATE]" if rule_path.exists() else "[ADD]"

            if dry_run:
                logger.info("    %s %s", action, rel)
            else:
                ensure_dir(cfg.rules_dir)
                atomic_write(rule_path, content)

            if action == "[ADD]":
                result.added += 1
            else:
                result.updated += 1

    print_summary("System", result)
