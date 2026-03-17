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
from typing import TYPE_CHECKING, Any

from . import types as _t
from .enums import FileName, Tool
from .exceptions import ResourceExistsError
from .helpers import _launch_editor, build_file, ensure_dir
from .sync import sync_to_all_tools

if TYPE_CHECKING:
    from .types import SyncResult

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
    """Transform a skill definition for a specific tool destination."""
    description = _meta.get("description", "")
    fm = {"name": name, "description": description}
    return build_file(fm, body)


def skill_dest_path(dest_dir: Path, name: str) -> Path:
    """Return the destination path for a skill's SKILL.md file."""
    return dest_dir / name / FileName.SKILL.value


def skills_list() -> list[dict[str, str]]:
    """Return a list of skill metadata dicts.

    Each dict contains ``"name"`` and ``"description"``.
    """
    sources = collect_skills()
    items: list[dict[str, str]] = []
    for name, meta_tuple in sources.items():
        _path, meta, _body = meta_tuple
        items.append({"name": name, "description": meta.get("description", "")})
    return items


def skills_add(
    name: str,
    description: str = "",
    force: bool = False,
    template: str | None = None,
    *,
    interactive: bool | None = None,
) -> Path:
    """Scaffold a new skill directory with a SKILL.md.

    Args:
        name: Skill name.
        description: Optional skill description.
        force: Whether to overwrite an existing skill.
        template: Optional template name to pre-populate.
        interactive: Override TTY detection.  ``None`` means auto-detect.

    Returns:
        Path to the created SKILL.md file.

    Raises:
        ResourceExistsError: If the skill exists and *force* is ``False``.
    """
    ensure_dir(_t.SKILLS_SRC_DIR)

    skill_name = name
    if not skill_name.startswith("vaultspec-"):
        skill_name = f"vaultspec-{skill_name}"

    skill_dir = _t.SKILLS_SRC_DIR / skill_name
    file_path = skill_dir / "SKILL.md"

    if skill_dir.exists() and not force:
        raise ResourceExistsError(
            f"Skill '{skill_name}' exists. Use --force to overwrite."
        )

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

    is_interactive = interactive if interactive is not None else sys.stdin.isatty()

    if is_interactive:
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

    return file_path


def skills_sync(dry_run: bool = False, prune: bool = False) -> SyncResult:
    """Sync all skill definitions to every configured tool destination."""
    return sync_to_all_tools(
        sources=collect_skills(),
        dir_attr="skills_dir",
        transform_fn=transform_skill,
        label="Skills",
        prune=prune,
        dry_run=dry_run,
        dest_path_fn=skill_dest_path,
        is_skill=True,
    )
