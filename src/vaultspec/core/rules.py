"""Rules management for vaultspec."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from . import types as _t
from .enums import Tool
from .helpers import _launch_editor, build_file, ensure_dir
from .sync import print_summary, sync_files
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
    from ..vaultcore import parse_frontmatter

    sources: dict[str, tuple[Path, dict[str, Any], str]] = {}

    if not _t.RULES_SRC_DIR.exists():
        return sources
    for f in sorted(_t.RULES_SRC_DIR.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            sources[f.name] = (f, meta, body)
        except (OSError, Exception) as e:
            logger.error("Failed to read/parse %s: %s", f, e)
            continue

    return sources


def transform_rule(tool: Tool, name: str, _meta: dict[str, Any], body: str) -> str:
    """Transform a rule definition for a specific tool destination.

    Adds a YAML frontmatter block with ``trigger: always_on`` and, for
    non-antigravity tools, a ``name`` key derived from the filename stem.

    Args:
        tool: Target tool enum. When ``ToolType.ANTIGRAVITY``, the
            ``name`` key is omitted from the frontmatter.
        name: Source filename (e.g. ``"my-rule.md"``).
        _meta: Parsed source frontmatter (currently unused).
        body: Markdown body text of the rule.

    Returns:
        Assembled file content string with the appropriate frontmatter.
    """
    fm: dict[str, Any] = {}
    if tool != Tool.ANTIGRAVITY:
        fm["name"] = Path(name).stem
    fm["trigger"] = "always_on"
    return build_file(fm, body)


def rules_list(_args: argparse.Namespace) -> None:
    """Print a tabular list of all available rules, indicating built-in vs. custom.

    Args:
        _args: Parsed CLI arguments (unused).
    """
    print(f"{'Name':<40} {'Source':<15}")
    print("-" * 55)

    if _t.RULES_SRC_DIR.exists():
        for f in sorted(_t.RULES_SRC_DIR.glob("*.md")):
            source = "Built-in" if f.name.endswith(".builtin.md") else "Custom"
            print(f"{f.name:<40} {source:<15}")


def rules_add(args: argparse.Namespace) -> None:
    """Scaffold a new custom rule file, opening the editor when running interactively.

    When stdin is a TTY, writes a scaffold and opens the configured editor.
    Otherwise, reads content from stdin.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``name``, ``content``
            (optional), and ``force`` (bool to allow overwriting an existing file).
    """
    ensure_dir(_t.RULES_SRC_DIR)

    file_name = args.name if args.name.endswith(".md") else f"{args.name}.md"
    file_path = _t.RULES_SRC_DIR / file_name

    if file_path.exists() and not args.force:
        logger.error("Error: Rule '%s' exists. Use --force to overwrite.", file_name)
        return

    content = args.content

    if not content:
        if sys.stdin.isatty():
            from ..config import get_config

            editor = get_config().editor
            scaffold = f"---\nname: {args.name}\n---\n\n# Rule content\n"
            file_path.write_text(scaffold, encoding="utf-8")
            logger.info("Opening editor (%s) for %s...", editor, file_path)
            try:
                _launch_editor(editor, str(file_path))
                logger.info("Rule saved to %s", file_path)
            except Exception as e:
                logger.error("Error opening editor: %s", e, exc_info=True)
            return
        else:
            content = sys.stdin.read()

    fm = {"name": args.name}
    full = build_file(fm, (content or "").lstrip())
    file_path.write_text(full, encoding="utf-8")
    logger.info("Created custom rule: %s", file_path)


def rules_sync(args: argparse.Namespace) -> None:
    """Sync all rule definitions to every configured tool destination.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``dry_run`` and ``prune``.
    """
    sources = collect_rules()
    dry_run = getattr(args, "dry_run", False)
    prune = getattr(args, "prune", False)

    total = SyncResult()
    for tool_type, cfg in _t.TOOL_CONFIGS.items():
        if cfg.rules_dir is None:
            continue
        result = sync_files(
            sources=sources,
            dest_dir=cfg.rules_dir,
            transform_fn=lambda _tool, n, m, b, _tt=tool_type: transform_rule(
                _tt, n, m, b
            ),
            dest_path_fn=lambda dest_dir, name: dest_dir / name,
            prune=prune,
            dry_run=dry_run,
            label=f"rules -> {tool_type.value}",
        )
        total.added += result.added
        total.updated += result.updated
        total.pruned += result.pruned
        total.skipped += result.skipped
        total.errors.extend(result.errors)

    print_summary("Rules", total)
