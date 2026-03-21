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

from . import types as _t
from .enums import Tool
from .exceptions import ResourceExistsError
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
        tool: Target :class:`~vaultspec_core.core.enums.Tool`.
        name: Source filename (stem used as rule name).
        _meta: Original frontmatter dict (unused; overridden by generated meta).
        body: Markdown body of the rule source file.

    Returns:
        Rendered file content with generated YAML frontmatter prepended.
    """
    if isinstance(tool, str):
        tool = Tool(tool)

    fm: dict[str, Any] = {}
    fm["name"] = Path(name).stem
    fm["trigger"] = "always_on"
    return build_file(fm, body)


def rules_list() -> list[dict[str, str]]:
    """Return a list of rule metadata dicts.

    Each dict contains ``"name"`` and ``"source"`` (``"Built-in"`` or
    ``"Custom"``).
    """
    items: list[dict[str, str]] = []
    if _t.RULES_SRC_DIR.exists():
        for f in sorted(_t.RULES_SRC_DIR.glob("*.md")):
            source = "Built-in" if f.name.endswith(".builtin.md") else "Custom"
            items.append({"name": f.name, "source": source})
    return items


def rules_add(
    name: str,
    content: str | None = None,
    force: bool = False,
    *,
    interactive: bool | None = None,
) -> Path:
    """Scaffold a new custom rule file.

    Args:
        name: Rule name.
        content: Optional rule content.  When ``None`` and *interactive* is
            ``True``, opens the configured editor.  When ``None`` and
            *interactive* is ``False``, reads from stdin.
        force: Whether to overwrite an existing rule.
        interactive: Override TTY detection.  ``None`` means auto-detect via
            ``sys.stdin.isatty()``.

    Returns:
        Path to the created rule file.

    Raises:
        ResourceExistsError: If the rule exists and *force* is ``False``.
    """
    ensure_dir(_t.RULES_SRC_DIR)

    file_name = name if name.endswith(".md") else f"{name}.md"
    file_path = _t.RULES_SRC_DIR / file_name

    if file_path.exists() and not force:
        raise ResourceExistsError(
            f"Rule '{file_name}' exists. Use --force to overwrite."
        )

    rule_content = content

    is_interactive = interactive if interactive is not None else sys.stdin.isatty()

    if not rule_content:
        if is_interactive:
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
            return file_path
        else:
            rule_content = sys.stdin.read()

    fm = {"name": name}
    full = build_file(fm, (rule_content or "").lstrip())
    file_path.write_text(full, encoding="utf-8")
    logger.info("Created custom rule: %s", file_path)
    return file_path


def rules_sync(dry_run: bool = False, prune: bool = False) -> SyncResult:
    """Sync all rule definitions to every configured tool destination.

    Args:
        dry_run: If ``True``, log planned actions without writing files.
        prune: If ``True``, delete destination ``.md`` files not in sources.

    Returns:
        Accumulated :class:`~vaultspec_core.core.types.SyncResult` across
        all active tool destinations.
    """
    return sync_to_all_tools(
        sources=collect_rules(),
        dir_attr="rules_dir",
        transform_fn=transform_rule,
        label="Rules",
        prune=prune,
        dry_run=dry_run,
    )
