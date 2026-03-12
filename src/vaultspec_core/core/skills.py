"""Manage canonical skill definitions and sync them into tool-specific layouts.

The module treats skills as directory-shaped resources rooted at
``.vaultspec/rules/skills``. It collects their ``SKILL.md`` entrypoints,
scaffolds new skill directories, and adapts them to destination layouts used
by external tools.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import typer

from . import types as _t
from .enums import FileName, Tool
from .helpers import _launch_editor, build_file, ensure_dir
from .sync import sync_to_all_tools

logger = logging.getLogger(__name__)


def collect_skills() -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect vaultspec-* skill definitions from .vaultspec/rules/skills/*/SKILL.md.

    Returns:
        A mapping of skill directory name (e.g. ``"vaultspec-execute"``) to a
        three-tuple of ``(skill_md_path, frontmatter_dict, body_text)``.
    """
    from ..vaultcore import parse_frontmatter

    sources: dict[str, tuple[Path, dict[str, Any], str]] = {}
    if not _t.SKILLS_SRC_DIR.exists():
        return sources
    for path in sorted(_t.SKILLS_SRC_DIR.iterdir()):
        if path.is_dir() and path.name.startswith("vaultspec-"):
            skill_md = path / "SKILL.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding="utf-8")
                    meta, body = parse_frontmatter(content)
                    sources[path.name] = (skill_md, meta, body)
                except Exception as e:
                    logger.error("Failed to read/parse %s: %s", skill_md, e)
                    continue
    return sources


def transform_skill(_tool: Tool, name: str, _meta: dict[str, Any], body: str) -> str:
    """Transform a skill definition for a specific tool destination.

    Assembles a YAML-frontmattered file containing the skill's name and
    description alongside its Markdown body.

    Args:
        _tool: Target tool name (unused; accepted for interface consistency).
        name: Skill directory name (e.g. ``"vaultspec-execute"``).
        _meta: Parsed frontmatter dict; may contain ``"description"``.
        body: Markdown body text of the skill definition.

    Returns:
        Assembled file content string with YAML frontmatter.
    """
    description = _meta.get("description", "")
    fm = {"name": name, "description": description}
    return build_file(fm, body)


def skill_dest_path(dest_dir: Path, name: str) -> Path:
    """Return the destination path for a skill's SKILL.md file.

    Args:
        dest_dir: Base skills directory for the target tool.
        name: Skill directory name (e.g. ``"vaultspec-execute"``).

    Returns:
        The full path ``dest_dir / name / SKILL.md``.
    """
    return dest_dir / name / FileName.SKILL.value


def skills_list() -> None:
    """Print a tabular list of all available skills with their descriptions."""
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console

    sources = collect_skills()
    if not sources:
        get_console().print("No managed skills found.")
        return

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Description", max_width=60, overflow="ellipsis")

    for name, meta_tuple in sources.items():
        _path, meta, _body = meta_tuple
        table.add_row(name, meta.get("description", ""))

    get_console().print(table)


def skills_add(
    name: str,
    description: str = "",
    force: bool = False,
    template: str | None = None,
) -> None:
    """Scaffold a new skill directory with a SKILL.md and open it in the user's editor.

    The skill name is automatically prefixed with ``vaultspec-`` if not already.
    When running interactively (TTY), opens the editor after writing the scaffold.

    Args:
        name: Skill name.
        description: Optional skill description.
        force: Whether to overwrite an existing skill.
        template: Optional template name to pre-populate.
    """
    ensure_dir(_t.SKILLS_SRC_DIR)

    skill_name = name
    if not skill_name.startswith("vaultspec-"):
        skill_name = f"vaultspec-{skill_name}"

    skill_dir = _t.SKILLS_SRC_DIR / skill_name
    file_path = skill_dir / "SKILL.md"

    if skill_dir.exists() and not force:
        logger.error("Error: Skill '%s' exists. Use --force to overwrite.", skill_name)
        raise typer.Exit(code=1)

    ensure_dir(skill_dir)

    body = f"# {skill_name}\n\nDefine your skill instructions here.\n"
    if template:
        tmpl_path = _t.TEMPLATES_DIR / template
        if not tmpl_path.suffix:
            tmpl_path = tmpl_path.with_suffix(".md")
        if tmpl_path.exists():
            body = tmpl_path.read_text(encoding="utf-8")
        else:
            logger.warning(
                "Warning: Template '%s' not found at %s", template, tmpl_path
            )

    fm = {"name": skill_name, "description": description}
    scaffold = build_file(fm, body)

    if sys.stdin.isatty():
        file_path.write_text(scaffold, encoding="utf-8")
        from ..config import get_config

        editor = get_config().editor
        logger.info("Opening editor (%s) for %s...", editor, file_path)
        try:
            _launch_editor(editor, str(file_path))
            logger.info("Skill saved to %s", file_path)
        except Exception as e:
            logger.error("Error opening editor: %s", e, exc_info=True)
    else:
        file_path.write_text(scaffold, encoding="utf-8")
        logger.info("Created skill: %s", file_path)


def skills_sync(dry_run: bool = False, prune: bool = False) -> None:
    """Sync all skill definitions to every configured tool destination.

    Args:
        dry_run: If ``True``, log planned actions without writing.
        prune: If ``True``, remove stale skill files.
    """
    sync_to_all_tools(
        sources=collect_skills(),
        dir_attr="skills_dir",
        transform_fn=transform_skill,
        label="Skills",
        prune=prune,
        dry_run=dry_run,
        dest_path_fn=skill_dest_path,
        is_skill=True,
    )
