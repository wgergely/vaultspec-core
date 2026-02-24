"""Config file generation for vaultspec tool configurations."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from . import types as _t
from .enums import FileName, Tool
from .helpers import atomic_write, ensure_dir
from .rules import collect_rules
from .sync import print_summary
from .types import SyncResult, ToolConfig

logger = logging.getLogger(__name__)


def _collect_rule_refs(cfg: ToolConfig) -> list[str]:
    """Collect relative rule file reference strings for a tool's config file.

    Handles the special ``agents`` tool by sourcing rules from the first peer
    tool that has a ``rules_dir``, and also includes the generated
    ``vaultspec-system.builtin.md`` rule when present.

    Args:
        cfg: Tool configuration describing destination directories and files.

    Returns:
        A sorted list of forward-slash paths suitable for embedding as
        ``@rule/path`` references in a config file.
    """
    if cfg.rules_dir is None or cfg.config_file is None:
        if cfg.name == Tool.AGENTS.value and cfg.config_file:
            config_dir = cfg.config_file.parent
            sources = collect_rules()
            # Also include the generated system rule (vaultspec-system.builtin.md),
            # which system_sync writes to peer tools' rules_dir (e.g. .claude/rules/).
            # Find it from the first peer tool that has rules_dir and the file present.
            system_rule_name = "vaultspec-system.builtin.md"
            for peer_cfg in _t.TOOL_CONFIGS.values():
                if peer_cfg.rules_dir is None:
                    continue
                candidate = peer_cfg.rules_dir / system_rule_name
                if candidate.exists() and system_rule_name not in sources:
                    sources[system_rule_name] = (candidate, {}, "")
                    break
            refs = []
            for name in sorted(sources.keys()):
                src_path, _meta, _body = sources[name]
                try:
                    rel = src_path.relative_to(config_dir)
                    refs.append(str(rel).replace("\\", "/"))
                except ValueError:
                    ref = src_path.relative_to(_t.ROOT_DIR)
                    refs.append(str(ref).replace("\\", "/"))
            return refs
        return []
    if not cfg.rules_dir.exists():
        return []

    config_dir = cfg.config_file.parent
    refs = []
    for rule_file in sorted(cfg.rules_dir.glob("*.md")):
        try:
            rel = rule_file.relative_to(config_dir)
            refs.append(str(rel).replace("\\", "/"))
        except ValueError:
            ref = rule_file.relative_to(_t.ROOT_DIR)
            refs.append(str(ref).replace("\\", "/"))
    return refs


def _xml_to_heading(text: str) -> str:
    """Convert XML tag blocks to Markdown level-2 headings.

    Transforms ``<tag>`` / ``</tag>`` patterns (optionally surrounded by
    backticks) into ``## Tag`` Markdown section headers.

    Args:
        text: Raw text that may contain XML-like tag blocks.

    Returns:
        The transformed text with XML tags replaced by ``##`` headings.
    """
    # Replace opening tags with headings (handle optional surrounding backticks)
    text = re.sub(
        r"`?<(\w+)>`?\s*",
        lambda m: f"## {m.group(1).replace('_', ' ').title()}\n\n",
        text,
    )
    # Remove closing tags (handle optional surrounding backticks)
    text = re.sub(r"`?</\w+>`?\s*", "\n", text)
    return text.strip()


def _generate_agents_md(cfg: ToolConfig) -> str | None:
    """Generate AGENTS.md in plain Markdown (no YAML frontmatter).

    The AGENTS.md spec does not support frontmatter, so the output starts
    with the AUTO-GENERATED comment followed directly by the Markdown body:
    framework content (XML tags converted to headings), optional project
    content, and rule references.

    Args:
        cfg: Tool configuration for the ``agents`` target, used to resolve
            rule reference paths relative to the config file location.

    Returns:
        The assembled AGENTS.md content string, or ``None`` if the framework
        config source does not exist.
    """
    from ..vaultcore import parse_frontmatter

    if not _t.FRAMEWORK_CONFIG_SRC.exists():
        return None

    _meta, internal_body = parse_frontmatter(
        _t.FRAMEWORK_CONFIG_SRC.read_text(encoding="utf-8")
    )
    internal_body = internal_body.strip()

    body_content = _xml_to_heading(internal_body)

    custom_body = ""
    if _t.PROJECT_CONFIG_SRC.exists():
        _meta, custom_body = parse_frontmatter(
            _t.PROJECT_CONFIG_SRC.read_text(encoding="utf-8")
        )
        custom_body = custom_body.strip()

    # Assemble body (no frontmatter — AGENTS.md spec does not support it)
    body_parts = [body_content]

    if custom_body:
        body_parts.append("")
        body_parts.append(custom_body)

    # Add rules
    refs = _collect_rule_refs(cfg)
    if refs:
        body_parts.append("")
        body_parts.append("## Rules")
        body_parts.append("")
        body_parts.append("You MUST respect these rules at all times:")
        body_parts.append("")
        for ref in refs:
            body_parts.append(f"@{ref}")

    body = "\n".join(body_parts)
    return f"{_t.CONFIG_HEADER}\n{body}"


def _generate_config(cfg: ToolConfig) -> str | None:
    """Generate CLAUDE.md / GEMINI.md config file content as plain Markdown.

    Assembles framework content (with XML tags converted to headings), optional
    project-level content, and rule ``@``-references into a single string
    prefixed by the auto-generated header sentinel.

    Args:
        cfg: Tool configuration used to resolve rule references.

    Returns:
        The complete file content string, or ``None`` if the framework config
        source does not exist.
    """
    from ..vaultcore import parse_frontmatter

    if not _t.FRAMEWORK_CONFIG_SRC.exists():
        return None

    _meta, internal_body = parse_frontmatter(
        _t.FRAMEWORK_CONFIG_SRC.read_text(encoding="utf-8")
    )
    internal_body = internal_body.strip()
    custom_body = ""
    if _t.PROJECT_CONFIG_SRC.exists():
        _meta, custom_body = parse_frontmatter(
            _t.PROJECT_CONFIG_SRC.read_text(encoding="utf-8")
        )
        custom_body = custom_body.strip()

    body_content = _xml_to_heading(internal_body)

    # Body starts with framework content (XML tags converted to headings)
    body_parts = [body_content]

    if custom_body:
        body_parts.append("")
        body_parts.append(custom_body)

    # Add rules
    refs = _collect_rule_refs(cfg)
    if refs:
        body_parts.append("")
        body_parts.append("## Rules")
        body_parts.append("")
        body_parts.append("You MUST respect these rules at all times:")
        body_parts.append("")
        for ref in refs:
            body_parts.append(f"@{ref}")

    body = "\n".join(body_parts)
    return f"{_t.CONFIG_HEADER}\n{body}"


def _is_cli_managed(path: Path) -> bool:
    """Return True if the file at *path* was generated by the vaultspec CLI.

    Detection is based on the presence of the ``CONFIG_HEADER`` sentinel at
    the start of the file.

    Args:
        path: Filesystem path to check.

    Returns:
        ``True`` if the file exists and starts with the auto-generated header,
        ``False`` otherwise.
    """
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8")
        return content.startswith(_t.CONFIG_HEADER)
    except Exception as exc:
        logger.warning("Failed to check CLI management for %s: %s", path, exc)
        return False


def config_show(_args: argparse.Namespace) -> None:
    """Print framework config, project config, and per-tool rule references.

    Args:
        _args: Parsed CLI arguments (unused).
    """
    from ..vaultcore import parse_frontmatter

    if not _t.FRAMEWORK_CONFIG_SRC.exists():
        rel = _t.FRAMEWORK_CONFIG_SRC.relative_to(_t.ROOT_DIR)
        logger.error("No framework config found at %s", rel)
        return

    print(f"Framework: {_t.FRAMEWORK_CONFIG_SRC.relative_to(_t.ROOT_DIR)}")
    print("-" * 60)
    _meta, fw_body = parse_frontmatter(
        _t.FRAMEWORK_CONFIG_SRC.read_text(encoding="utf-8")
    )
    print(fw_body.strip())
    print("-" * 60)

    if _t.PROJECT_CONFIG_SRC.exists():
        print(f"Project: {_t.PROJECT_CONFIG_SRC.relative_to(_t.ROOT_DIR)}")
        print("-" * 60)
        _meta, proj_body = parse_frontmatter(
            _t.PROJECT_CONFIG_SRC.read_text(encoding="utf-8")
        )
        print(proj_body.strip())
        print("-" * 60)

    print("Generated references per tool:")
    for tool_type, cfg in _t.TOOL_CONFIGS.items():
        if cfg.config_file is None:
            continue
        refs = _collect_rule_refs(cfg)
        dest_rel = cfg.config_file.relative_to(_t.ROOT_DIR)
        managed = "CLI-managed" if _is_cli_managed(cfg.config_file) else "custom"
        print(f"\n  {tool_type.value} ({dest_rel}) [{managed}]:")
        if refs:
            for ref in refs:
                print(f"    @{ref}")
        else:
            print("    (no rules synced yet)")


def config_sync(args: argparse.Namespace) -> None:
    """Write generated config files to all configured tool destinations.

    Skips files that were not previously managed by the CLI unless ``--force``
    is supplied, to avoid overwriting user-customised configs.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``dry_run`` and ``force``.
    """
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    if not _t.FRAMEWORK_CONFIG_SRC.exists():
        rel = _t.FRAMEWORK_CONFIG_SRC.relative_to(_t.ROOT_DIR)
        logger.error("  Error: No framework config found at %s", rel)
        return

    result = SyncResult()

    for _tool_type, cfg in _t.TOOL_CONFIGS.items():
        if cfg.config_file is None:
            continue

        # Use agents.md standard format for AGENTS.md
        if cfg.name == Tool.AGENTS.value:
            content = _generate_agents_md(cfg)
        else:
            content = _generate_config(cfg)
        if content is None:
            result.skipped += 1
            continue

        rel = cfg.config_file.relative_to(_t.ROOT_DIR)

        # Safety guard
        if (
            cfg.config_file.exists()
            and not _is_cli_managed(cfg.config_file)
            and not force
        ):
            logger.warning("    [SKIP] %s - file exists with custom content.", rel)
            proj_rel = _t.PROJECT_CONFIG_SRC.relative_to(_t.ROOT_DIR)
            msg = f"           Migrate to {proj_rel}, then --force."
            logger.warning(msg)
            result.skipped += 1
            continue

        action = "[UPDATE]" if cfg.config_file.exists() else "[ADD]"

        if dry_run:
            logger.info("    %s %s", action, rel)
        else:
            ensure_dir(cfg.config_file.parent)
            atomic_write(cfg.config_file, content)

        if action == "[ADD]":
            result.added += 1
        else:
            result.updated += 1

    print_summary("Config", result)
