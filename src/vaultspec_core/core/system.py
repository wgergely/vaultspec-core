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
from .types import SyncResult, ToolConfig

logger = logging.getLogger(__name__)

#: Filename of the synthesized system-rule artifact emitted by
#: :func:`system_sync` into each provider's rules directory.
SYSTEM_BUILTIN_RULE = "vaultspec-system.builtin.md"


def collect_system_parts(
    warnings: list[str] | None = None,
) -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect system prompt parts from .vaultspec/rules/system/.

    Args:
        warnings: Optional list to append parse-error messages to, so callers
            can propagate them into :class:`~vaultspec_core.core.types.SyncResult`.

    Returns:
        A mapping of file stem (e.g. ``"01-core"``) to a three-tuple of
        ``(source_path, frontmatter_dict, body_text)``.
    """
    from ..vaultcore import parse_frontmatter

    sources: dict[str, tuple[Path, dict[str, Any], str]] = {}
    system_src_dir = _t.get_context().system_src_dir
    if not system_src_dir.exists():
        return sources
    for f in sorted(system_src_dir.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            sources[f.stem] = (f, meta, body)
        except (OSError, Exception) as e:
            logger.error("Failed to read/parse %s: %s", f, e)
            if warnings is not None:
                warnings.append(f"Failed to read/parse {f}: {e}")
            continue
    return sources


def _collect_skill_listing() -> str:
    """Build a section listing all available skills."""
    skills = collect_skills()
    if not skills:
        return ""

    lines = [
        "## Vaultspec Skills",
        "",
    ]
    for name, meta_tuple in skills.items():
        _path, meta, _body = meta_tuple
        description = meta.get("description", "")
        lines.append(f"- **{name}**: {description}")
    return "\n".join(lines)


def _generate_system_prompt(cfg: ToolConfig) -> str | None:
    """Assemble a complete system prompt for a tool with a dedicated system_file."""
    if cfg.system_file is None:
        return None

    parts = collect_system_parts()
    if not parts:
        return None

    assembled: list[str] = [_t.CONFIG_HEADER]

    for _name, (_path, meta, body) in sorted(parts.items()):
        tool_filter = meta.get("tool")
        if tool_filter is not None and tool_filter == cfg.name:
            assembled.append(body)

    skill_listing = _collect_skill_listing()
    if skill_listing:
        assembled.append(skill_listing)

    shared = [
        (name, _path, meta, body)
        for name, (_path, meta, body) in parts.items()
        if meta.get("tool") is None and meta.get("pipeline") != "config"
    ]
    shared.sort(key=lambda t: (t[2].get("order", 50), t[0]))
    for _name, _path, _meta, body in shared:
        assembled.append(body)

    return "\n\n".join(assembled)


def _generate_system_rules(cfg: ToolConfig) -> str | None:
    """Assemble shared behavioral content as a rule file."""
    if cfg.rules_dir is None or not cfg.emit_system_rule:
        return None

    parts = collect_system_parts()
    if not parts:
        return None

    assembled: list[str] = []

    shared = [
        (name, _path, meta, body)
        for name, (_path, meta, body) in parts.items()
        if meta.get("tool") is None and meta.get("pipeline") != "config"
    ]
    shared.sort(key=lambda t: (t[2].get("order", 50), t[0]))
    for _name, _path, _meta, body in shared:
        assembled.append(body)

    if not assembled:
        return None

    content = "\n\n".join(assembled)
    fm = {"name": "vaultspec-system", "trigger": "always_on"}
    return f"{_t.CONFIG_HEADER}\n{build_file(fm, content)}"


def system_show() -> dict[str, Any]:
    """Return structured data about system prompt parts and targets.

    Returns:
        A dict with keys:
        - ``"parts"``: list of dicts with ``"name"``, ``"tool_filter"``, ``"lines"``.
        - ``"targets"``: list of dicts with ``"tool"``, ``"path"``, ``"managed"``.
    """
    parts = collect_system_parts()
    parts_list = []
    for name, (_path, meta, body) in sorted(parts.items()):
        tool_filter = meta.get("tool", "-")
        line_count = len(body.strip().splitlines()) if body.strip() else 0
        parts_list.append(
            {"name": name, "tool_filter": tool_filter, "lines": line_count}
        )

    ctx = _t.get_context()
    targets_list = []
    for tool_type, cfg in ctx.tool_configs.items():
        system_file = cfg.system_file
        if system_file is None:
            continue
        rel = str(system_file.relative_to(ctx.target_dir))
        managed = "CLI-managed" if _is_cli_managed(system_file) else "custom"
        targets_list.append({"tool": tool_type.value, "path": rel, "managed": managed})

    return {"parts": parts_list, "targets": targets_list}


def system_sync(dry_run: bool = False, force: bool = False) -> SyncResult:
    """Sync assembled system prompts and behavioral rules to tool destinations.

    For tools with a dedicated ``system_file`` (e.g. Gemini's
    ``.gemini/SYSTEM.md``), writes the assembled prompt.  For tools with
    ``emit_system_rule=True`` (e.g. Claude), emits a
    ``vaultspec-system.builtin.md`` rule file in the rules directory.
    Skips files with user-authored content unless *force* is set.

    Args:
        dry_run: Log planned actions without writing any files.
        force: Overwrite user-authored system files.

    Returns:
        A :class:`SyncResult` tallying added, updated, and skipped files.
    """
    from .manifest import installed_tool_configs

    result = SyncResult()

    for _tool_type, cfg in installed_tool_configs().items():
        tool_result = SyncResult()
        system_file = cfg.system_file
        if system_file is not None:
            content = _generate_system_prompt(cfg)
            if content is None:
                tool_result.skipped += 1
            else:
                rel = system_file.relative_to(_t.get_context().target_dir)

                if (
                    system_file.exists()
                    and not _is_cli_managed(system_file)
                    and not force
                ):
                    logger.warning(
                        "    [SKIP] %s - file exists with custom content.", rel
                    )
                    tool_result.warnings.append(
                        f"Skipped {rel} (user-authored content, "
                        f"use --force to overwrite)"
                    )
                    tool_result.skipped += 1
                else:
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
                        abs_path = str(system_file).replace("\\", "/")
                        if dry_run:
                            tool_result.items.append((abs_path, action))
                        else:
                            ensure_dir(system_file.parent)
                            atomic_write(system_file, content)

                        if action == "[ADD]":
                            tool_result.added += 1
                        else:
                            tool_result.updated += 1
                    else:
                        tool_result.skipped += 1

        elif cfg.rules_dir is not None and cfg.emit_system_rule:
            content = _generate_system_rules(cfg)
            if content is not None:
                rule_path = cfg.rules_dir / SYSTEM_BUILTIN_RULE

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
                    abs_path = str(rule_path).replace("\\", "/")
                    if dry_run:
                        tool_result.items.append((abs_path, action))
                    else:
                        ensure_dir(cfg.rules_dir)
                        atomic_write(rule_path, content)

                    if action == "[ADD]":
                        tool_result.added += 1
                    else:
                        tool_result.updated += 1
                else:
                    tool_result.skipped += 1

        result.merge(tool_result)
        result.per_tool[cfg.name] = tool_result

    return result
