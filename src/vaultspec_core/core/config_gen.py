"""Generate top-level tool configuration files from framework-managed sources.

This module merges internal framework configuration, optional project-local
configuration, and generated rule references into the config files consumed by
supported tools. It also distinguishes CLI-managed files from custom files so
sync operations can avoid unsafe overwrites.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from . import types as _t
from .enums import Tool
from .helpers import atomic_write, ensure_dir
from .sync import print_summary
from .types import SyncResult, ToolConfig

logger = logging.getLogger(__name__)

CODEX_CONFIG_BEGIN = "# BEGIN VAULTSPEC MANAGED CODEX CONFIG"
CODEX_CONFIG_END = "# END VAULTSPEC MANAGED CODEX CONFIG"


def _is_cli_managed(path_or_content: str | Path) -> bool:
    """Return True if the file content contains the AUTO-GENERATED header."""
    if isinstance(path_or_content, Path):
        if not path_or_content.exists():
            return False
        try:
            content = path_or_content.read_text(encoding="utf-8")
        except Exception:
            return False
    else:
        content = path_or_content
    return _t.CONFIG_HEADER in content


def _collect_rule_refs(cfg: ToolConfig) -> list[str]:
    """Scan the configured rule-reference directory for markdown rule files.

    Args:
        cfg: Configuration for the target tool.

    Returns:
        List of include strings (e.g. ``"@rules/my-rule.md"``) for every file
        found in the rule-reference directory.
    """
    rule_ref_dir = cfg.rule_ref_dir or cfg.rules_dir
    if rule_ref_dir is None or cfg.config_file is None:
        return []
    if not rule_ref_dir.exists():
        return []

    config_dir = cfg.config_file.parent
    refs = []
    for rule_file in sorted(rule_ref_dir.glob("*.md")):
        try:
            rel = rule_file.relative_to(config_dir)
            refs.append(str(rel).replace("\\", "/"))
        except ValueError:
            ref = rule_file.relative_to(_t.TARGET_DIR)
            refs.append(str(ref).replace("\\", "/"))
    return refs


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _strip_managed_codex_config_block(content: str) -> str:
    pattern = re.compile(
        rf"\n?{re.escape(CODEX_CONFIG_BEGIN)}\n.*?\n{re.escape(CODEX_CONFIG_END)}\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", content).strip()


def _read_framework_project_parts() -> tuple[
    dict[str, object], str, dict[str, object], str
]:
    from ..vaultcore import parse_frontmatter

    internal_meta: dict[str, object] = {}
    internal_body = ""
    if _t.FRAMEWORK_CONFIG_SRC.exists():
        internal_meta, internal_body = parse_frontmatter(
            _t.FRAMEWORK_CONFIG_SRC.read_text(encoding="utf-8")
        )
        internal_body = internal_body.strip()

    project_meta: dict[str, object] = {}
    custom_body = ""
    if _t.PROJECT_CONFIG_SRC.exists():
        project_meta, custom_body = parse_frontmatter(
            _t.PROJECT_CONFIG_SRC.read_text(encoding="utf-8")
        )
        custom_body = custom_body.strip()

    return internal_meta, internal_body, project_meta, custom_body


def _merge_codex_config_meta(
    internal_meta: dict[str, object],
    project_meta: dict[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = {}
    supported_keys = [
        "codex_model",
        "codex_model_provider",
        "codex_approval_policy",
        "codex_sandbox_mode",
        "codex_model_reasoning_effort",
        "codex_model_reasoning_summary",
        "codex_model_supports_reasoning_summaries",
        "codex_model_verbosity",
        "codex_service_tier",
        "codex_project_doc_max_bytes",
        "codex_project_doc_fallback_filenames",
        "codex_project_root_markers",
    ]
    for key in supported_keys:
        value = project_meta.get(key, internal_meta.get(key))
        if value is not None:
            merged[key] = value
    return merged


def _render_codex_config_lines(meta: dict[str, object]) -> list[str]:
    rendered: list[str] = []
    string_keys = {
        "codex_model": "model",
        "codex_model_provider": "model_provider",
        "codex_approval_policy": "approval_policy",
        "codex_sandbox_mode": "sandbox_mode",
        "codex_model_reasoning_effort": "model_reasoning_effort",
        "codex_model_reasoning_summary": "model_reasoning_summary",
        "codex_model_verbosity": "model_verbosity",
        "codex_service_tier": "service_tier",
    }
    for source_key, target_key in string_keys.items():
        value = meta.get(source_key)
        if isinstance(value, str) and value.strip():
            rendered.append(f"{target_key} = {_toml_quote(value.strip())}")

    bool_value = meta.get("codex_model_supports_reasoning_summaries")
    if isinstance(bool_value, bool):
        rendered.append(
            "model_supports_reasoning_summaries = "
            + ("true" if bool_value else "false")
        )

    int_value = meta.get("codex_project_doc_max_bytes")
    if isinstance(int_value, int):
        rendered.append(f"project_doc_max_bytes = {int_value}")

    list_keys = {
        "codex_project_doc_fallback_filenames": "project_doc_fallback_filenames",
        "codex_project_root_markers": "project_root_markers",
    }
    for source_key, target_key in list_keys.items():
        value = meta.get(source_key)
        if isinstance(value, list):
            items = [
                item.strip() for item in value if isinstance(item, str) and item.strip()
            ]
            if items:
                rendered_items = ", ".join(_toml_quote(item) for item in items)
                rendered.append(f"{target_key} = [{rendered_items}]")

    return rendered


def _generate_codex_native_config() -> str | None:
    (
        internal_meta,
        _internal_body,
        project_meta,
        _custom_body,
    ) = _read_framework_project_parts()
    merged = _merge_codex_config_meta(internal_meta, project_meta)
    lines = _render_codex_config_lines(merged)
    if not lines:
        return None
    return f"{CODEX_CONFIG_BEGIN}\n" + "\n".join(lines) + f"\n{CODEX_CONFIG_END}"


def _generate_config(cfg: ToolConfig) -> str | None:
    """Assemble the complete configuration file for a tool destination."""

    if cfg.config_file is None:
        return None

    if not _t.FRAMEWORK_CONFIG_SRC.exists():
        return None

    (
        _internal_meta,
        internal_body,
        _project_meta,
        custom_body,
    ) = _read_framework_project_parts()

    body_parts = [internal_body]

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


def _generate_codex_agents_md() -> str | None:
    """Assemble the managed root AGENTS.md content for Codex."""
    if not _t.FRAMEWORK_CONFIG_SRC.exists():
        return None

    (
        _internal_meta,
        internal_body,
        _project_meta,
        custom_body,
    ) = _read_framework_project_parts()

    body_parts = [internal_body]
    if custom_body:
        body_parts.append("")
        body_parts.append(custom_body)

    return f"{_t.CONFIG_HEADER}\n{'\n'.join(body_parts)}"


def config_show() -> None:
    """Print the generated configuration content for every active tool destination."""
    import typer

    for tool_type, cfg in _t.TOOL_CONFIGS.items():
        typer.echo(f"--- {tool_type.value} config ---")
        content = _generate_config(cfg)
        if content:
            typer.echo(content)
        else:
            typer.echo("(No internal framework config found)")
        typer.echo()


def config_sync(dry_run: bool = False, force: bool = False) -> None:
    """Sync tool configuration files (CLAUDE.md, etc.) to their destinations.

    Args:
        dry_run: If ``True``, log planned actions without writing.
        force: If ``True``, overwrite non-managed files.
    """
    result = SyncResult()

    for _tool_type, cfg in _t.TOOL_CONFIGS.items():
        if not cfg.config_file:
            continue

        content = _generate_config(cfg)
        if not content:
            continue

        action = "[SKIP]"
        if not cfg.config_file.exists():
            action = "[ADD]"
        elif _is_cli_managed(cfg.config_file):
            action = "[UPDT]"
        elif force:
            action = "[FORC]"

        if action != "[SKIP]":
            logger.info("%s %s", action, cfg.config_file)
            if not dry_run:
                ensure_dir(cfg.config_file.parent)
                atomic_write(cfg.config_file, content)

        if action == "[ADD]":
            result.added += 1
        elif action != "[SKIP]":
            result.updated += 1

    codex_path = _t.TARGET_DIR / "AGENTS.md"
    codex_content = _generate_codex_agents_md()
    if codex_content:
        action = "[SKIP]"
        if not codex_path.exists():
            action = "[ADD]"
        elif _is_cli_managed(codex_path):
            action = "[UPDT]"
        elif force:
            action = "[FORC]"

        if action != "[SKIP]":
            logger.info("%s %s", action, codex_path)
            if not dry_run:
                atomic_write(codex_path, codex_content)

        if action == "[ADD]":
            result.added += 1
        elif action != "[SKIP]":
            result.updated += 1

    codex_native_path = _t.TOOL_CONFIGS[Tool.CODEX].native_config_file
    codex_native_content = _generate_codex_native_config()
    if codex_native_path is not None and codex_native_content is not None:
        existing = (
            codex_native_path.read_text(encoding="utf-8")
            if codex_native_path.exists()
            else ""
        )
        preserved = _strip_managed_codex_config_block(existing)
        parts = [part for part in [preserved, codex_native_content] if part]
        merged_content = "\n\n".join(parts).strip()
        if merged_content:
            merged_content += "\n"

        action = "[SKIP]"
        if not codex_native_path.exists():
            action = "[ADD]"
        elif existing != merged_content:
            action = "[UPDT]"

        if action != "[SKIP]":
            logger.info("%s %s", action, codex_native_path)
            if not dry_run:
                ensure_dir(codex_native_path.parent)
                atomic_write(codex_native_path, merged_content)

        if action == "[ADD]":
            result.added += 1
        elif action == "[UPDT]":
            result.updated += 1

    print_summary("Config", result)
