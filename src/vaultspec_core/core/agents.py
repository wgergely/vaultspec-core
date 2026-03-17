"""Manage canonical agent definitions and sync them to tool destinations.

This module owns the source-side lifecycle for managed agent documents under
the framework tree. It collects agent markdown, scaffolds new definitions, and
delegates cross-tool propagation to the shared sync engine.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import typer

from . import types as _t
from .enums import Tool
from .helpers import (
    _launch_editor,
    atomic_write,
    build_file,
    collect_md_resources,
    ensure_dir,
)
from .sync import print_summary, sync_files
from .types import SyncResult

logger = logging.getLogger(__name__)


def collect_agents() -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect agent definitions from .vaultspec/rules/agents/.

    Returns:
        A mapping of filename to a three-tuple of
        ``(source_path, frontmatter_dict, body_text)``.
    """
    return collect_md_resources(_t.AGENTS_SRC_DIR)


def transform_agent(_tool: Tool, _name: str, meta: dict[str, Any], body: str) -> str:
    """Transform an agent definition for a specific tool destination.

    Args:
        tool: Target tool enum or string.
        name: Source filename (e.g. ``"my-agent.md"``).
        meta: Parsed source frontmatter.
        body: Markdown body text of the agent instructions.

    Returns:
        Assembled file content string.
    """
    return build_file(meta, body)


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_multiline(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"""', '\\"""')
    return f'"""\n{escaped}\n"""'


def _coerce_codex_model(meta: dict[str, Any]) -> str | None:
    explicit = meta.get("codex_model")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    generic = meta.get("model")
    if isinstance(generic, str):
        model = generic.strip()
        if model.startswith("gpt-") or "codex" in model:
            return model

    return None


def _coerce_codex_string(meta: dict[str, Any], key: str) -> str | None:
    value = meta.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _render_codex_agent(name: str, meta: dict[str, Any], body: str) -> str:
    agent_name = Path(name).stem
    lines = [f"[agents.{_toml_quote(agent_name)}]"]

    description = meta.get("description")
    if isinstance(description, str) and description.strip():
        lines.append(f"description = {_toml_quote(description.strip())}")

    model = _coerce_codex_model(meta)
    if model:
        lines.append(f"model = {_toml_quote(model)}")

    approval_policy = _coerce_codex_string(meta, "codex_approval_policy")
    if approval_policy:
        lines.append(f"approval_policy = {_toml_quote(approval_policy)}")

    sandbox_mode = _coerce_codex_string(meta, "codex_sandbox_mode")
    if sandbox_mode:
        lines.append(f"sandbox_mode = {_toml_quote(sandbox_mode)}")

    tools = _coerce_string_list(meta.get("codex_tools"))
    if tools:
        rendered_tools = ", ".join(_toml_quote(tool) for tool in tools)
        lines.append(f"tools = [{rendered_tools}]")

    nickname_candidates = _coerce_string_list(meta.get("codex_nickname_candidates"))
    if nickname_candidates:
        rendered_nicknames = ", ".join(
            _toml_quote(candidate) for candidate in nickname_candidates
        )
        lines.append(f"nickname_candidates = [{rendered_nicknames}]")

    lines.append(f"prompt = {_toml_multiline(body.strip())}")
    return "\n".join(lines)


def _build_codex_agents_body(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
) -> str:
    """Render Codex agent definitions as TOML content (body only)."""
    rendered_agents = []
    for name, (_path, meta, body) in sorted(sources.items()):
        rendered_agents.append(_render_codex_agent(name, meta, body))
    if not rendered_agents:
        return ""
    return "\n\n".join(rendered_agents)


def _sync_codex_agents(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
    prune: bool = False,
    dry_run: bool = False,
) -> SyncResult:
    from .tags import TagError, has_block, strip_block, upsert_block

    result = SyncResult()
    codex_cfg = _t.TOOL_CONFIGS.get(Tool.CODEX)
    if codex_cfg is None or codex_cfg.native_config_file is None:
        return result

    path = codex_cfg.native_config_file
    existed = path.exists()
    existing = path.read_text(encoding="utf-8") if existed else ""
    body = _build_codex_agents_body(sources)

    abs_path = str(path).replace("\\", "/")

    if not body:
        # No agents to sync. If pruning, strip any existing block.
        if prune and existed and has_block(existing, "agents"):
            try:
                new_content = strip_block(existing, "agents")
            except TagError as e:
                logger.warning("Cannot prune agents from %s: %s", path, e)
                result.errors.append(str(e))
                return result
            if dry_run:
                result.items.append((abs_path, "[DELETE]"))
            else:
                atomic_write(path, new_content)
            result.pruned = 1
        else:
            result.skipped = 1
        return result

    try:
        new_content = upsert_block(existing, "agents", body, comment_prefix="# ")
    except TagError as e:
        logger.warning("Cannot sync agents to %s: %s", path, e)
        result.errors.append(str(e))
        return result

    if existing == new_content:
        result.skipped = len(sources) if sources else 1
        return result

    action = "[UPDATE]" if existed else "[ADD]"
    if dry_run:
        result.items.append((abs_path, action))
    else:
        ensure_dir(path.parent)
        atomic_write(path, new_content)

    if existed:
        result.updated = 1
    else:
        result.added = 1
    return result


def agents_list() -> None:
    """Print a tabular list of all available agents with their descriptions."""
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console

    sources = collect_agents()
    if not sources:
        get_console().print("No managed agents found.")
        return

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Description", max_width=50, overflow="ellipsis")

    for name, (_path, meta, _body) in sources.items():
        table.add_row(name, meta.get("description", ""))

    get_console().print(table)


def agents_add(
    name: str,
    description: str = "",
    force: bool = False,
) -> None:
    """Scaffold a new agent definition.

    Args:
        name: Agent name.
        description: Short description.
        force: Whether to overwrite existing.
    """
    ensure_dir(_t.AGENTS_SRC_DIR)

    file_name = name if name.endswith(".md") else f"{name}.md"
    file_path = _t.AGENTS_SRC_DIR / file_name

    if file_path.exists() and not force:
        logger.error("Error: Agent '%s' exists. Use --force to overwrite.", file_name)
        raise typer.Exit(code=1)

    fm = {"name": name, "description": description}
    body = "# Instructions\n\nAdd agent instructions here.\n"

    if sys.stdin.isatty() and not description:
        from ..config import get_config

        editor = get_config().editor
        content = build_file(fm, body)
        file_path.write_text(content, encoding="utf-8")
        logger.info("Opening editor (%s) for %s...", editor, file_path)
        try:
            _launch_editor(editor, str(file_path))
        except Exception as e:
            logger.error("Error opening editor: %s", e)
    else:
        content = build_file(fm, body)
        file_path.write_text(content, encoding="utf-8")

    logger.info("Created agent: %s", file_path)


def agents_sync(dry_run: bool = False, prune: bool = False) -> SyncResult:
    """Sync all agent definitions to every configured tool destination.

    Args:
        dry_run: If ``True``, log planned actions without writing.
        prune: If ``True``, remove stale agent files.
    """
    sources = collect_agents()
    total = SyncResult()

    def _merge(result: SyncResult) -> None:
        total.added += result.added
        total.updated += result.updated
        total.pruned += result.pruned
        total.skipped += result.skipped
        total.errors.extend(result.errors)
        total.items.extend(result.items)

    from .manifest import installed_tool_configs

    active_configs = installed_tool_configs()
    for tool_type, cfg in active_configs.items():
        if tool_type is Tool.CODEX or cfg.agents_dir is None:
            continue
        result = sync_files(
            sources=sources,
            dest_dir=cfg.agents_dir,
            transform_fn=lambda _tool, n, m, b, _tt=tool_type: transform_agent(
                _tt, n, m, b
            ),
            dest_path_fn=lambda dest_dir, name: dest_dir / name,
            prune=prune,
            dry_run=dry_run,
            label=f"Agents -> {tool_type.value}",
        )
        _merge(result)

    if Tool.CODEX in active_configs:
        codex_result = _sync_codex_agents(sources, prune=prune, dry_run=dry_run)
        _merge(codex_result)
    print_summary("Agents", total)
    return total
