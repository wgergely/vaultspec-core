"""Assemble shared system prompt and behavioral rule surfaces for each tool.

This module composes the framework's system prompt fragments, skill listings,
and shared behavioral sections into the generated files consumed by supported
tool targets. It is the bridge between canonical system-part sources and the
final prompt or rule artifacts emitted during sync.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import types as _t
from .config_gen import _is_cli_managed
from .helpers import atomic_write, build_file, ensure_dir
from .skills import collect_skills
from .sync import print_summary
from .types import SyncResult, ToolConfig

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


def _collect_skill_listing() -> str:
    """Build a section listing all available skills.

    Returns:
        A string containing the skills listing, or an empty string if no
        skills are found.
    """
    skills = collect_skills()
    if not skills:
        return ""

    # Use Markdown list
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

    Combines the ``base.md`` body, tool-specific parts, auto-generated skill
    listings, and remaining shared parts (ordered by ``order``
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

    # 3. Auto-generated skill listing
    skill_listing = _collect_skill_listing()
    if skill_listing:
        assembled.append(skill_listing)

    # 4. Remaining shared parts (no "tool" key, not "base", not config-only)
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
    if cfg.rules_dir is None or not cfg.emit_system_rule:
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


def system_show() -> None:
    """Print a table of system prompt parts and their generation targets to stdout."""
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console

    console = get_console()

    parts = collect_system_parts()
    if not parts:
        logger.warning("No system parts found in .vaultspec/rules/system/")
        return

    parts_table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    parts_table.add_column("Name", no_wrap=True)
    parts_table.add_column("Tool Filter")
    parts_table.add_column("Lines", justify="right")

    for name, (_path, meta, body) in sorted(parts.items()):
        tool_filter = meta.get("tool", "-")
        line_count = len(body.strip().splitlines()) if body.strip() else 0
        parts_table.add_row(name, tool_filter, str(line_count))

    console.print(parts_table)

    targets = [
        (tool_type, cfg)
        for tool_type, cfg in _t.TOOL_CONFIGS.items()
        if cfg.system_file is not None
    ]
    if targets:
        console.print()
        console.print("Generation targets:", style="bold")
        targets_table = Table(
            box=None, show_header=False, show_edge=False, padding=(0, 1)
        )
        targets_table.add_column("Tool")
        targets_table.add_column("Path")
        targets_table.add_column("Status", style="dim")
        for tool_type, cfg in targets:
            system_file = cfg.system_file
            if system_file is None:
                continue
            rel = system_file.relative_to(_t.TARGET_DIR)
            managed = "CLI-managed" if _is_cli_managed(system_file) else "custom"
            targets_table.add_row(tool_type.value, str(rel), f"[{managed}]")
        console.print(targets_table)


def system_sync(dry_run: bool = False, force: bool = False) -> None:
    """Sync assembled system prompts and behavioral rules to tool destinations.

    Args:
        dry_run: If ``True``, log planned actions without writing.
        force: If ``True``, overwrite non-managed files.
    """
    result = SyncResult()

    for _tool_type, cfg in _t.TOOL_CONFIGS.items():
        # Path A: Tool has a system_file -> generate assembled SYSTEM.md
        system_file = cfg.system_file
        if system_file is not None:
            content = _generate_system_prompt(cfg)
            if content is None:
                result.skipped += 1
                continue

            rel = system_file.relative_to(_t.TARGET_DIR)

            # Safety guard
            if (
                system_file.exists()
                and not _is_cli_managed(system_file)
                and not force
            ):
                logger.warning("    [SKIP] %s - file exists with custom content.", rel)
                logger.warning("           Use --force to overwrite.")
                result.skipped += 1
                continue

            action = "[SKIP]"
            if not system_file.exists():
                action = "[ADD]"
            else:
                try:
                    if system_file.read_text(encoding="utf-8") != content:
                        action = "[UPDATE]"
                except Exception:
                    action = "[UPDATE]"

            if action != "[SKIP]":
                if dry_run:
                    logger.info("    %s %s", action, rel)
                else:
                    ensure_dir(system_file.parent)
                    atomic_write(system_file, content)

                if action == "[ADD]":
                    result.added += 1
                else:
                    result.updated += 1
            else:
                result.skipped += 1

        # Path B: Tool has rules_dir but no system_file -> generate behavioral rule
        elif cfg.rules_dir is not None and cfg.emit_system_rule:
            content = _generate_system_rules(cfg)
            if content is None:
                continue

            rule_path = cfg.rules_dir / "vaultspec-system.builtin.md"
            rel = rule_path.relative_to(_t.TARGET_DIR)

            action = "[SKIP]"
            if not rule_path.exists():
                action = "[ADD]"
            else:
                try:
                    if rule_path.read_text(encoding="utf-8") != content:
                        action = "[UPDATE]"
                except Exception:
                    action = "[UPDATE]"

            if action != "[SKIP]":
                if dry_run:
                    logger.info("    %s %s", action, rel)
                else:
                    ensure_dir(cfg.rules_dir)
                    atomic_write(rule_path, content)

                if action == "[ADD]":
                    result.added += 1
                else:
                    result.updated += 1
            else:
                result.skipped += 1

    print_summary("System", result)
