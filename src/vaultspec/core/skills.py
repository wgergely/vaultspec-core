"""Skills management for vaultspec."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from . import types as _t
from .enums import FileName, Tool
from .helpers import atomic_write, build_file, ensure_dir
from .sync import print_summary
from .sync import sync_skills as _sync_skills
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
                except (OSError, Exception) as e:
                    logger.error("Failed to read/parse %s: %s", skill_md, e)
                    continue
    return sources


def transform_skill(tool: Tool, name: str, _meta: dict[str, Any], body: str) -> str:
    """Transform a skill definition for a specific tool destination.

    Assembles a YAML-frontmattered file containing the skill's name and
    description alongside its Markdown body.

    Args:
        _tool: Target tool name (unused; accepted for interface consistency).
        name: Skill directory name (e.g. ``"vaultspec-execute"``).
        meta: Parsed frontmatter dict; may contain ``"description"``.
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


def skills_list(_args: argparse.Namespace) -> None:
    """Print a tabular list of all available skills with their descriptions.

    Args:
        _args: Parsed CLI arguments (unused).
    """
    sources = collect_skills()
    if not sources:
        print("No managed skills found.")
        return

    print(f"{'Name':<30} {'Description':<60}")
    print("-" * 90)
    for name, meta_tuple in sources.items():
        _path, meta, _body = meta_tuple
        desc = meta.get("description", "")
        if len(desc) > 57:
            desc = desc[:57] + "..."
        print(f"{name:<30} {desc:<60}")


def skills_add(args: argparse.Namespace) -> None:
    """Scaffold a new skill directory with a SKILL.md and open it in the user's editor.

    The skill name is automatically prefixed with ``vaultspec-`` if not already.
    When running interactively (TTY), opens the editor after writing the scaffold.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``name``, ``description``
            (optional), ``template`` (optional path relative to templates dir),
            and ``force`` (bool to allow overwriting an existing skill).
    """
    ensure_dir(_t.SKILLS_SRC_DIR)

    skill_name = args.name
    if not skill_name.startswith("vaultspec-"):
        skill_name = f"vaultspec-{skill_name}"

    skill_dir = _t.SKILLS_SRC_DIR / skill_name
    file_path = skill_dir / "SKILL.md"

    if skill_dir.exists() and not getattr(args, "force", False):
        logger.error("Error: Skill '%s' exists. Use --force to overwrite.", skill_name)
        return

    ensure_dir(skill_dir)

    description = getattr(args, "description", "") or ""
    default_body = f"# {skill_name}\n\nDefine your skill instructions here.\n"
    body = default_body
    if getattr(args, "template", None):
        tmpl_path = _t.TEMPLATES_DIR / args.template
        if not tmpl_path.suffix:
            tmpl_path = tmpl_path.with_suffix(".md")
        if tmpl_path.exists():
            body = tmpl_path.read_text(encoding="utf-8")
        else:
            logger.warning(
                "Warning: Template '%s' not found at %s", args.template, tmpl_path
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


def skills_sync(args: argparse.Namespace) -> None:
    """Sync all skill definitions to every configured tool destination.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``dry_run`` and ``prune``.
    """
    sources = collect_skills()
    dry_run = getattr(args, "dry_run", False)
    prune = getattr(args, "prune", False)

    total = SyncResult()
    for tool_type, cfg in _t.TOOL_CONFIGS.items():
        if cfg.skills_dir is None:
            continue
        result = _sync_skills(
            sources=sources,
            skills_dir=cfg.skills_dir,
            transform_fn=lambda _tool, n, m, b, _tt=tool_type: transform_skill(
                _tt, n, m, b
            ),
            prune=prune,
            dry_run=dry_run,
            label=f"skills -> {tool_type.value}",
        )
        total.added += result.added
        total.updated += result.updated
        total.pruned += result.pruned
        total.skipped += result.skipped
        total.errors.extend(result.errors)

    print_summary("Skills", total)
