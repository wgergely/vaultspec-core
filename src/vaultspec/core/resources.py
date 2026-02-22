"""Resource show/edit/remove/rename operations for vaultspec."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from . import types as _t
from .helpers import _launch_editor, ensure_dir
from .skills import skill_dest_path

logger = logging.getLogger(__name__)


def resource_show(args: argparse.Namespace, src_dir: Path, label: str) -> None:
    """Display a single resource file.

    Args:
        args: Parsed CLI arguments. Expected attribute: ``name`` (resource name
            or filename stem).
        src_dir: Source directory where the resource file lives.
        label: Human-readable resource type label (e.g. ``"Rule"``, ``"Agent"``,
            or ``"Skill"``), used in error messages and path resolution.
    """
    from ..vaultcore import parse_frontmatter

    name = args.name

    if label == "Skill":
        file_path = src_dir / name / "SKILL.md"
    else:
        file_name = name if name.endswith(".md") else f"{name}.md"
        file_path = src_dir / file_name

    if not file_path.exists():
        logger.error("Error: %s '%s' not found at %s", label, name, file_path)
        return
    content = file_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)
    if meta:
        print("--- Metadata ---")
        for k, v in meta.items():
            print(f"  {k}: {v}")
        print("---")
    print(body)


def resource_edit(args: argparse.Namespace, src_dir: Path, label: str) -> None:
    """Open a resource file in the user's editor.

    Args:
        args: Parsed CLI arguments. Expected attribute: ``name`` (resource name
            or filename stem).
        src_dir: Source directory where the resource file lives.
        label: Human-readable resource type label (e.g. ``"Rule"``, ``"Agent"``,
            or ``"Skill"``), used in error messages and path resolution.
    """
    name = args.name

    if label == "Skill":
        file_path = src_dir / name / "SKILL.md"
    else:
        file_name = name if name.endswith(".md") else f"{name}.md"
        file_path = src_dir / file_name

    if not file_path.exists():
        logger.error("Error: %s '%s' not found at %s", label, name, file_path)
        return
    from ..config import get_config

    editor = (
        os.environ.get("VAULTSPEC_EDITOR")
        or os.environ.get("VISUAL")
        or os.environ.get("EDITOR")
        or get_config().editor
    )
    try:
        _launch_editor(editor, str(file_path))
    except Exception as e:
        logger.error("Error opening editor: %s", e)


def resource_remove(args: argparse.Namespace, src_dir: Path, label: str) -> None:
    """Delete a resource file and its synced copies.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``name`` (resource name
            or filename stem) and ``force`` (bool to skip the confirmation prompt).
        src_dir: Source directory where the resource file lives.
        label: Human-readable resource type label (e.g. ``"Rule"``, ``"Agent"``,
            or ``"Skill"``), used in error messages and path resolution.
    """
    import shutil

    name = args.name

    if label == "Skill":
        skill_dir = src_dir / name
        file_path = skill_dir / "SKILL.md"
        target_to_remove = skill_dir
    else:
        file_name = name if name.endswith(".md") else f"{name}.md"
        file_path = src_dir / file_name
        target_to_remove = file_path

    if not file_path.exists():
        logger.error("Error: %s '%s' not found at %s", label, name, file_path)
        return

    if not getattr(args, "force", False):
        confirm = input(f"Remove {label} '{name}'? [y/N] ").strip().lower()
        if confirm != "y":
            logger.info("Cancelled.")
            return

    if label == "Skill":
        shutil.rmtree(target_to_remove)
    else:
        target_to_remove.unlink()
    logger.info("Removed %s", target_to_remove)

    # Prune synced copies
    removed = 0
    # For skills, name is the dir name. For others, stripping .md
    resource_key = name if label == "Skill" or not name.endswith(".md") else name[:-3]

    for _tool_name, cfg in _t.TOOL_CONFIGS.items():
        dest_dir = None
        if label == "Rule" and cfg.rules_dir:
            dest_dir = cfg.rules_dir
        elif label == "Agent" and cfg.agents_dir:
            dest_dir = cfg.agents_dir
        elif label == "Skill" and cfg.skills_dir:
            dest_dir = cfg.skills_dir
        if dest_dir:
            if label == "Skill":
                synced = skill_dest_path(dest_dir, resource_key)
                if synced.exists():
                    synced.unlink()
                # Remove parent dir if empty (skill dirs)
                synced_dir = dest_dir / resource_key
                if synced_dir.exists() and not any(synced_dir.iterdir()):
                    synced_dir.rmdir()
                    removed += 1
            else:
                synced = dest_dir / (resource_key + ".md")
                if synced.exists():
                    synced.unlink()
                    removed += 1

    if removed:
        logger.info("  Pruned %d synced copies.", removed)


def resource_rename(args: argparse.Namespace, src_dir: Path, label: str) -> None:
    """Rename a resource file and update synced copies.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``old_name`` and
            ``new_name`` (resource name or filename stems).
        src_dir: Source directory where the resource file lives.
        label: Human-readable resource type label (e.g. ``"Rule"``, ``"Agent"``,
            or ``"Skill"``), used in error messages and path resolution.
    """
    old_name = args.old_name
    new_name = args.new_name

    if label == "Skill":
        old_path = src_dir / old_name
        new_path = src_dir / new_name
    else:
        old_file = old_name if old_name.endswith(".md") else f"{old_name}.md"
        new_file = new_name if new_name.endswith(".md") else f"{new_name}.md"
        old_path = src_dir / old_file
        new_path = src_dir / new_file

    if not old_path.exists():
        logger.error("Error: %s '%s' not found at %s", label, old_name, old_path)
        return
    if new_path.exists():
        logger.error("Error: %s '%s' already exists at %s", label, new_name, new_path)
        return

    old_path.rename(new_path)
    logger.info("Renamed %s -> %s", old_path.name, new_path.name)

    # Update synced copies
    updated = 0
    old_key = (
        old_name if label == "Skill" or not old_name.endswith(".md") else old_name[:-3]
    )
    new_key = (
        new_name if label == "Skill" or not new_name.endswith(".md") else new_name[:-3]
    )

    for _tool_name, cfg in _t.TOOL_CONFIGS.items():
        dest_dir = None
        if label == "Rule" and cfg.rules_dir:
            dest_dir = cfg.rules_dir
        elif label == "Agent" and cfg.agents_dir:
            dest_dir = cfg.agents_dir
        elif label == "Skill" and cfg.skills_dir:
            dest_dir = cfg.skills_dir
        if dest_dir:
            if label == "Skill":
                old_synced = skill_dest_path(dest_dir, old_key)
                if old_synced.exists():
                    new_parent = dest_dir / new_key
                    ensure_dir(new_parent)
                    old_synced.rename(new_parent / "SKILL.md")
                    # Remove old parent dir if empty
                    if old_synced.parent.exists() and not any(
                        old_synced.parent.iterdir()
                    ):
                        old_synced.parent.rmdir()
                    updated += 1
            else:
                old_synced = dest_dir / (old_key + ".md")
                if old_synced.exists():
                    old_synced.rename(dest_dir / (new_key + ".md"))
                    updated += 1
    if updated:
        logger.info("  Updated %d synced copies.", updated)
    logger.info("Run 'sync-all' to ensure all destinations are current.")
