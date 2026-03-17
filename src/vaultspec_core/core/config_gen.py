"""Generate top-level tool configuration files from framework-managed sources.

This module merges internal framework configuration, optional project-local
configuration, and generated rule references into the config files consumed by
supported tools.  It uses ``<vaultspec>`` managed content blocks to co-exist
with user-authored content in shared files like CLAUDE.md, GEMINI.md, and
AGENTS.md.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import types as _t
from .enums import Tool
from .helpers import atomic_write, ensure_dir
from .sync import print_summary
from .tags import TagError, has_block, upsert_block
from .types import SyncResult, ToolConfig

logger = logging.getLogger(__name__)


def _is_cli_managed(path_or_content: str | Path) -> bool:
    """Return True if the content contains a vaultspec managed block.

    Detects both old-style ``AUTO-GENERATED`` headers and new-style
    ``<vaultspec>`` tags for backward compatibility.
    """
    if isinstance(path_or_content, Path):
        if not path_or_content.exists():
            return False
        try:
            content = path_or_content.read_text(encoding="utf-8")
        except Exception:
            return False
    else:
        content = path_or_content
    # Check for both old header and new tag system.
    return "<vaultspec " in content or _t.CONFIG_HEADER in content


def _collect_rule_refs(cfg: ToolConfig) -> list[str]:
    """Scan the configured rule-reference directory for markdown rule files.

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


def _read_codex_config_meta() -> dict[str, object]:
    """Read Codex-relevant settings from system parts that have pipeline: config."""
    from ..vaultcore import parse_frontmatter

    merged: dict[str, object] = {}
    if not _t.SYSTEM_SRC_DIR.exists():
        return merged
    for f in sorted(_t.SYSTEM_SRC_DIR.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            meta, _body = parse_frontmatter(content)
            if meta.get("pipeline") == "config":
                merged.update(meta)
        except Exception:
            continue
    return merged


def _filter_codex_config_meta(
    meta: dict[str, object],
) -> dict[str, object]:
    filtered: dict[str, object] = {}
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
        value = meta.get(key)
        if value is not None:
            filtered[key] = value
    return filtered


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


# ---------------------------------------------------------------------------
# Content generators — produce the managed block body (without tags).
# ---------------------------------------------------------------------------


def _generate_config_body(cfg: ToolConfig) -> str | None:
    """Assemble the managed block body for a tool's root config file."""
    if cfg.config_file is None:
        return None

    body_parts: list[str] = []

    refs = _collect_rule_refs(cfg)
    if refs:
        body_parts.append("## Rules")
        body_parts.append("")
        body_parts.append("You MUST respect these rules at all times:")
        body_parts.append("")
        for ref in refs:
            body_parts.append(f"@{ref}")

    if not body_parts:
        return None

    return "\n".join(body_parts)


def _generate_rule_ref_body(cfg: ToolConfig) -> str | None:
    """Generate body for a secondary config with rule references only."""
    if cfg.rule_ref_config_file is None:
        return None

    refs = _collect_rule_refs(cfg)
    if not refs:
        return None

    body_parts = [
        "## Rules",
        "",
        "You MUST respect these rules at all times:",
        "",
    ]
    for ref in refs:
        body_parts.append(f"@{ref}")

    return "\n".join(body_parts)


def _generate_codex_native_config_body() -> str | None:
    """Generate body for Codex config.toml managed settings block."""
    raw_meta = _read_codex_config_meta()
    filtered = _filter_codex_config_meta(raw_meta)
    lines = _render_codex_config_lines(filtered)
    if not lines:
        return None
    return "\n".join(lines)


def _generate_codex_agents_body() -> str | None:
    """Generate body for Codex config.toml managed agents block."""
    from .agents import collect_agents

    sources = collect_agents()
    if not sources:
        return None

    lines = []
    for filename, (_path, meta, body) in sorted(sources.items()):
        agent_name = meta.get("name", filename.removesuffix(".md"))
        description = meta.get(
            "description",
            body.strip().split("\n")[0] if body.strip() else "",
        )
        lines.append(f"[agents.{_toml_quote(str(agent_name))}]")
        lines.append(f"description = {_toml_quote(str(description))}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sync helpers — write managed blocks into files.
# ---------------------------------------------------------------------------


def _sync_managed_md(
    path: Path,
    block_type: str,
    body: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> str:
    """Upsert a ``<vaultspec>`` block into a markdown file.

    Returns the action taken: ``"[ADD]"``, ``"[UPDT]"``, or ``"[SKIP]"``.
    """
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if has_block(existing, block_type):
            # Block exists — check if content actually changed.
            updated = upsert_block(existing, block_type, body)
            if updated == existing:
                return "[SKIP]"
            if not dry_run:
                atomic_write(path, updated)
            return "[UPDT]"
        if _is_cli_managed(existing) or force:
            # File is ours or force — upsert (append block).
            updated = upsert_block(existing, block_type, body)
            if updated == existing:
                return "[SKIP]"
            if not dry_run:
                atomic_write(path, updated)
            return "[UPDT]"
        # File exists with user content, no managed block, no force.
        # Append our block without destroying user content.
        if not dry_run:
            updated = upsert_block(existing, block_type, body)
            atomic_write(path, updated)
        return "[ADD]"
    else:
        # New file — create with managed block only.
        if not dry_run:
            ensure_dir(path.parent)
            content = upsert_block("", block_type, body)
            atomic_write(path, content)
        return "[ADD]"


def _sync_managed_toml(
    path: Path,
    block_type: str,
    body: str,
    *,
    dry_run: bool = False,
) -> str:
    """Upsert a ``# <vaultspec>`` block into a TOML file.

    Returns the action taken.
    """
    existed = path.exists()
    existing = path.read_text(encoding="utf-8") if existed else ""

    try:
        updated = upsert_block(existing, block_type, body, comment_prefix="# ")
    except TagError as e:
        logger.warning("Cannot update %s: %s", path, e)
        return "[SKIP]"

    if updated == existing:
        return "[SKIP]"

    if not dry_run:
        ensure_dir(path.parent)
        atomic_write(path, updated)

    return "[UPDT]" if existed else "[ADD]"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def config_show() -> None:
    """Print the generated configuration content for every active tool."""
    import typer

    for tool_type, cfg in _t.TOOL_CONFIGS.items():
        typer.echo(f"--- {tool_type.value} config ---")
        content = _generate_config_body(cfg)
        if content:
            typer.echo(content)
        else:
            typer.echo("(No internal framework config found)")
        typer.echo()


def config_sync(dry_run: bool = False, force: bool = False) -> SyncResult:
    """Sync tool configuration files using ``<vaultspec>`` managed blocks.

    For markdown files (CLAUDE.md, GEMINI.md, AGENTS.md), inserts or
    updates a ``<vaultspec type="config">`` block.  User content outside
    the block is preserved.

    For TOML files (.codex/config.toml), inserts or updates
    ``# <vaultspec type="...">`` blocks.
    """
    from .manifest import installed_tool_configs

    result = SyncResult()
    active_configs = installed_tool_configs()

    def _record(path: Path, action: str) -> None:
        abs_path = str(path).replace("\\", "/")
        if action == "[ADD]":
            result.added += 1
            if dry_run:
                result.items.append((abs_path, "[ADD]"))
        elif action == "[UPDT]":
            result.updated += 1
            if dry_run:
                result.items.append((abs_path, "[UPDATE]"))

    # --- Markdown root config files ---
    # Aggregate rule refs from all providers sharing the same config_file
    # to avoid last-writer-wins conflicts (e.g. gemini + antigravity → GEMINI.md).
    config_refs: dict[Path, list[str]] = {}
    for _tool_type, cfg in active_configs.items():
        if not cfg.config_file:
            continue
        refs = _collect_rule_refs(cfg)
        config_refs.setdefault(cfg.config_file, []).extend(refs)

    seen_config_files: set[Path] = set()
    for _tool_type, cfg in active_configs.items():
        if not cfg.config_file or cfg.config_file in seen_config_files:
            continue
        seen_config_files.add(cfg.config_file)

        all_refs = config_refs.get(cfg.config_file, [])
        if not all_refs:
            continue

        # Deduplicate while preserving order
        seen_refs: list[str] = []
        seen_ref_set: set[str] = set()
        for ref in all_refs:
            if ref not in seen_ref_set:
                seen_ref_set.add(ref)
                seen_refs.append(ref)

        body_parts = [
            "## Rules",
            "",
            "You MUST respect these rules at all times:",
            "",
        ]
        for ref in seen_refs:
            body_parts.append(f"@{ref}")
        body = "\n".join(body_parts)

        action = _sync_managed_md(
            cfg.config_file,
            "config",
            body,
            dry_run=dry_run,
            force=force,
        )
        logger.info("%s %s", action, cfg.config_file)
        _record(cfg.config_file, action)

    # --- Secondary rule-reference config files (.gemini/GEMINI.md) ---
    for _tool_type, cfg in active_configs.items():
        ref_body = _generate_rule_ref_body(cfg)
        if not ref_body or cfg.rule_ref_config_file is None:
            continue

        action = _sync_managed_md(
            cfg.rule_ref_config_file,
            "rules",
            ref_body,
            dry_run=dry_run,
            force=force,
        )
        logger.info("%s %s", action, cfg.rule_ref_config_file)
        _record(cfg.rule_ref_config_file, action)

    # --- Codex native config (TOML) ---
    codex_cfg = active_configs.get(Tool.CODEX)
    codex_native_path = codex_cfg.native_config_file if codex_cfg else None
    if codex_native_path is not None:
        config_body = _generate_codex_native_config_body()
        if config_body:
            action = _sync_managed_toml(
                codex_native_path,
                "config",
                config_body,
                dry_run=dry_run,
            )
            if action != "[SKIP]":
                logger.info("%s %s", action, codex_native_path)
            _record(codex_native_path, action)

        # NOTE: Codex agents block is managed by agents_sync/_sync_codex_agents,
        # not here, to avoid conflicting writes to the same TOML block.

    print_summary("Config", result)
    return result
