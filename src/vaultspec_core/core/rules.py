"""Manage canonical always-on rule documents for the vaultspec framework.

This module handles source rule collection, custom rule scaffolding, and the
transformation needed to emit tool-consumable rule files with the expected
frontmatter and sync behavior.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from . import types as _t
from .enums import Tool
from .helpers import _launch_editor, build_file, collect_md_resources, ensure_dir
from .sync import sync_to_all_tools

if TYPE_CHECKING:
    from .types import SyncResult

logger = logging.getLogger(__name__)


def collect_rules() -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect rule definitions from .vaultspec/rules/rules/.

    Includes both built-in rules (``*.builtin.md``) and custom user rules
    (``*.md``).

    Returns:
        A mapping of filename to a three-tuple of
        ``(source_path, frontmatter_dict, body_text)``.
    """
    return collect_md_resources(_t.RULES_SRC_DIR)


def transform_rule(tool: Tool, name: str, _meta: dict[str, Any], body: str) -> str:
    """Transform a rule definition for a specific tool destination.

    Adds a YAML frontmatter block with ``trigger: always_on`` and a ``name``
    key derived from the filename stem.

    Args:
        tool: Target tool enum or string.
        name: Source filename (e.g. ``"my-rule.md"``).
        _meta: Parsed source frontmatter (currently unused).
        body: Markdown body text of the rule.

    Returns:
        Assembled file content string with the appropriate frontmatter.
    """
    if isinstance(tool, str):
        tool = Tool(tool)

    fm: dict[str, Any] = {}
    fm["name"] = Path(name).stem
    fm["trigger"] = "always_on"
    return build_file(fm, body)


def rules_list() -> None:
    """Print a tabular list of all available rules, indicating built-in vs. custom."""
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Source")

    if _t.RULES_SRC_DIR.exists():
        for f in sorted(_t.RULES_SRC_DIR.glob("*.md")):
            source = "Built-in" if f.name.endswith(".builtin.md") else "Custom"
            table.add_row(f.name, source)

    get_console().print(table)


def rules_add(
    name: str,
    content: str | None = None,
    force: bool = False,
) -> None:
    """Scaffold a new custom rule file, opening the editor when running interactively.

    When stdin is a TTY, writes a scaffold and opens the configured editor.
    Otherwise, reads content from stdin.

    Args:
        name: Rule name.
        content: Optional rule content.
        force: Whether to overwrite an existing rule.
    """
    ensure_dir(_t.RULES_SRC_DIR)

    file_name = name if name.endswith(".md") else f"{name}.md"
    file_path = _t.RULES_SRC_DIR / file_name

    if file_path.exists() and not force:
        logger.error("Error: Rule '%s' exists. Use --force to overwrite.", file_name)
        raise typer.Exit(code=1)

    rule_content = content

    if not rule_content:
        if sys.stdin.isatty():
            from ..config import get_config

            editor = get_config().editor
            scaffold = f"---\nname: {name}\n---\n\n# Rule content\n"
            file_path.write_text(scaffold, encoding="utf-8")
            logger.info("Opening editor (%s) for %s...", editor, file_path)
            try:
                _launch_editor(editor, str(file_path))
                logger.info("Rule saved to %s", file_path)
            except Exception as e:
                logger.error("Error opening editor: %s", e, exc_info=True)
            return
        else:
            rule_content = sys.stdin.read()

    fm = {"name": name}
    full = build_file(fm, (rule_content or "").lstrip())
    file_path.write_text(full, encoding="utf-8")
    logger.info("Created custom rule: %s", file_path)


def rules_sync(dry_run: bool = False, prune: bool = False) -> SyncResult:
    """Sync all rule definitions to every configured tool destination.

    Args:
        dry_run: If ``True``, log planned actions without writing.
        prune: If ``True``, remove stale rule files.
    """
    return sync_to_all_tools(
        sources=collect_rules(),
        dir_attr="rules_dir",
        transform_fn=transform_rule,
        label="Rules",
        prune=prune,
        dry_run=dry_run,
    )
