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
from .helpers import (
    atomic_write,
    atomic_write_bytes,
    build_file,
    collect_md_resources,
    ensure_dir,
    launch_editor,
)
from .sync import sync_to_all_tools

if TYPE_CHECKING:
    from .types import SyncResult

logger = logging.getLogger(__name__)


def collect_rules(
    warnings: list[str] | None = None,
) -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect rule definitions from .vaultspec/rules/.

    Includes both built-in rules (``*.builtin.md``) and custom user rules
    (``*.md``).

    Args:
        warnings: Optional list to append parse-error messages to, so callers
            can propagate them into :class:`~vaultspec_core.core.types.SyncResult`.

    Returns:
        A mapping of filename to a three-tuple of
        ``(source_path, frontmatter_dict, body_text)``.
    """
    rules_src_dir = _t.get_context().rules_src_dir
    flatten_nested_custom_rules(rules_src_dir)
    raw_sources = collect_md_resources(rules_src_dir, warnings=warnings)
    # Rule sources are flat after sanitization; reduce any residual nested key
    # (e.g. a basename collision the flattener could not resolve) to its
    # basename so the collected name is always the flat rule name.
    sources: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for k, v in raw_sources.items():
        sources[k.replace("\\", "/").rsplit("/", 1)[-1]] = v
    return sources


def transform_rule(
    tool: Tool | str, name: str, _meta: dict[str, Any], body: str
) -> str:
    """Transform a rule definition for a specific tool destination.

    Adds a YAML frontmatter block with ``trigger: always_on`` and a ``name``
    key derived from the filename stem.

    Args:
        tool: Target :class:`~vaultspec_core.core.enums.Tool`, or its ``.value``
            string (the ``transform_fn`` callback contract this satisfies
            passes an untyped first argument; accept either shape).
        name: Source filename (stem used as rule name).
        _meta: Original frontmatter dict (unused; overridden by generated meta).
        body: Markdown body of the rule source file.

    Returns:
        Rendered file content with generated YAML frontmatter prepended.
    """
    # ``Tool`` is a ``StrEnum``, so a caller-supplied ``Tool`` member already
    # satisfies ``isinstance(tool, str)`` - normalising unconditionally is
    # equivalent to the old guarded form and covers a raw ``.value`` string.
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
    rules_src_dir = _t.get_context().rules_src_dir
    if rules_src_dir.exists():
        flatten_nested_custom_rules(rules_src_dir)
        for f in sorted(rules_src_dir.glob("**/*.md")):
            rel_name = f.relative_to(rules_src_dir).as_posix()
            source = "Built-in" if f.name.endswith(".builtin.md") else "Custom"
            items.append({"name": rel_name, "source": source})
    return items


def rules_add(
    name: str,
    content: str | None = None,
    force: bool = False,
    *,
    dry_run: bool = False,
    interactive: bool | None = None,
) -> Path:
    """Scaffold a new custom rule file.

    Args:
        name: Rule name.
        content: Optional rule content.  When ``None`` and *interactive* is
            ``True``, opens the configured editor.  When ``None`` and
            *interactive* is ``False``, reads from stdin.
        force: Whether to overwrite an existing rule.
        dry_run: If ``True``, return the target path without writing.
        interactive: Override TTY detection.  ``None`` means auto-detect via
            ``sys.stdin.isatty()``.

    Returns:
        Path to the created (or would-be-created) rule file.

    Raises:
        ResourceExistsError: If the rule exists and *force* is ``False``.
    """
    rules_src_dir = _t.get_context().rules_src_dir
    ensure_dir(rules_src_dir)

    # Custom rules live flat directly under the rules root alongside the
    # ``*.builtin.md`` builtins; nested rule folders are not supported. Reduce
    # the requested name to its basename so any directory components (including
    # a legacy ``project/`` prefix) are sanitized away rather than creating a
    # nested rule.
    base_name = Path(name.replace("\\", "/")).name
    file_name = base_name if base_name.endswith(".md") else f"{base_name}.md"
    rule_stem = file_name[:-3]
    file_path = rules_src_dir / file_name

    if file_path.exists() and not force:
        raise ResourceExistsError(
            f"Rule '{file_name}' exists.",
            hint="Use --force to overwrite, or --dry-run to preview",
        )

    if dry_run:
        return file_path

    rule_content = content

    is_interactive = interactive if interactive is not None else sys.stdin.isatty()

    if not rule_content:
        if is_interactive:
            from ..config import get_config

            editor = get_config().editor
            scaffold = f"---\nname: {rule_stem}\n---\n\n# Rule content\n"
            atomic_write(file_path, scaffold)
            logger.info("Opening editor (%s) for %s...", editor, file_path)
            try:
                launch_editor(editor, str(file_path))
                logger.info("Rule saved to %s", file_path)
            except Exception as e:
                logger.error("Error opening editor: %s", e, exc_info=True)
            return file_path
        else:
            rule_content = sys.stdin.read()

    fm = {"name": rule_stem}
    full = build_file(fm, (rule_content or "").lstrip())
    atomic_write(file_path, full)
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
    parse_warnings: list[str] = []
    if not dry_run:
        try:
            rules_src_dir = _t.get_context().rules_src_dir
        except (LookupError, AttributeError):
            rules_src_dir = None
        if rules_src_dir is not None:
            converge_spec_layer_gitignore(Path(rules_src_dir))
    result = sync_to_all_tools(
        sources=collect_rules(warnings=parse_warnings),
        dir_attr="rules_dir",
        transform_fn=transform_rule,
        label="Rules",
        prune=prune,
        dry_run=dry_run,
    )
    result.warnings.extend(parse_warnings)
    return result


# Active (non-comment, non-blank) lines of the pre-0.1.20 nested rules
# .gitignore that un-tracked project-authored rule sources. Convergence only
# rewrites a file whose active policy is a subset of these, so an operator's
# hand-authored nested .gitignore is never clobbered (issue #124).
_STALE_RULES_GITIGNORE_POLICY: frozenset[str] = frozenset({"*.md", "!*.builtin.md"})


def converge_spec_layer_gitignore(rules_src_dir: Path) -> bool:
    """Refresh the nested ``rules/.gitignore`` to the shipped team-shared policy.

    Pre-0.1.20 installs left a ``*.md`` / ``!*.builtin.md`` policy in
    ``.vaultspec/rules/.gitignore`` that silently un-tracks the
    project-authored rule sources now relocated under ``project/`` - the exact
    failure the ``gitignore_reversal`` migration was meant to end. Only
    ``install --force`` previously refreshed it; this convergence lets ``sync``
    (and the migration) repair the drift idempotently.

    Conservative, like the migration: a file whose active lines fall outside the
    known stale policy is treated as operator-customised and left untouched.

    Returns:
        ``True`` if the file was rewritten, ``False`` otherwise.
    """
    from vaultspec_core.builtins import builtins_root

    template = builtins_root() / "rules" / ".gitignore"
    try:
        want = template.read_bytes()
    except OSError:
        return False

    dest = rules_src_dir / ".gitignore"
    if dest.exists():
        try:
            current = dest.read_bytes()
        except OSError:
            return False
        if current == want:
            return False
        active = {
            line.strip()
            for line in current.decode("utf-8", errors="replace").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        if not active <= _STALE_RULES_GITIGNORE_POLICY:
            logger.debug(
                "Nested rules .gitignore at %s carries custom entries; "
                "leaving untouched",
                dest,
            )
            return False

    try:
        rules_src_dir.mkdir(parents=True, exist_ok=True)
        # Through the shared atomic writer rather than `write_bytes`: a
        # symlink at this path would otherwise be followed and whatever it
        # names overwritten with the shipped policy. The writer refuses a
        # symlinked destination outright, and this convergence runs on every
        # `sync`.
        atomic_write_bytes(dest, want)
    except OSError as exc:
        logger.error("Failed to converge nested rules .gitignore at %s: %s", dest, exc)
        return False
    logger.info("Converged nested rules .gitignore at %s to shipped policy", dest)
    return True


def flatten_nested_custom_rules(rules_src_dir: Path) -> None:
    """Flatten any nested custom rule to the rules root; sanitize nesting.

    Custom rules are team-shared markdown files that live FLAT directly under
    ``.vaultspec/rules/`` alongside the ``*.builtin.md`` builtins; nested
    rule folders (notably the historical ``project/`` subdir) are not
    supported. This heals the source tree idempotently: every non-builtin
    ``*.md`` found below the rules root is moved up to ``<root>/<basename>`` and
    the emptied subdirectories are removed. A basename collision with an
    existing flat rule is left in place and logged rather than overwriting the
    operator's file. Runs on every collect / sync so authored or previously
    migrated nesting is sanitized automatically.
    """
    if not rules_src_dir.exists():
        return
    import shutil

    for f in sorted(rules_src_dir.glob("**/*.md")):
        if not f.is_file() or f.parent == rules_src_dir:
            continue  # already flat
        if f.name.endswith(".builtin.md"):
            continue  # builtins are flat by contract
        dest_file = rules_src_dir / f.name
        if dest_file.exists():
            logger.warning(
                "Cannot flatten nested rule %s: %s already exists; leaving nested",
                f,
                dest_file,
            )
            continue
        try:
            shutil.move(str(f), str(dest_file))
            logger.info("Flattened nested custom rule %s to %s", f, dest_file)
        except OSError as e:
            logger.error("Failed to flatten nested custom rule %s: %s", f, e)

    # Remove now-empty nested directories (e.g. the legacy ``project/`` subdir),
    # deepest first so parents empty out after their children.
    nested_dirs = sorted(
        (p for p in rules_src_dir.glob("**/*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for d in nested_dirs:
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass


def rule_promote(
    from_audit: str,
    rule_name: str,
    force: bool = False,
    dry_run: bool = False,
) -> Path:
    """Promote an audit finding to a team-shared rule.

    Scaffolds a new rule flat under `.vaultspec/rules/` and appends
    the rule to the originating audit's ``promoted_to`` frontmatter field.

    Args:
        from_audit: The audit document stem (e.g., '2026-05-17-cli-simplification').
        rule_name: The kebab-case name of the new rule to scaffold.
        force: Whether to overwrite the rule file if it already exists.
        dry_run: If True, preview the action without writing any changes.

    Returns:
        The Path to the scaffolded rule file.
    """
    import re

    from ..config import get_config
    from ..vaultcore import (
        parse_vault_metadata,
        refresh_modified_stamp,
        vault_today,
    )
    from .exceptions import ResourceExistsError, ResourceNotFoundError, VaultSpecError

    # 1. Locate the originating audit document
    target_dir = _t.get_context().target_dir
    audit_stem = from_audit[:-3] if from_audit.endswith(".md") else from_audit
    docs_dir = get_config().docs_dir
    audit_file = target_dir / docs_dir / "audit" / f"{audit_stem}.md"
    if not audit_file.exists():
        raise ResourceNotFoundError(
            f"Audit document '{docs_dir}/audit/{audit_stem}.md' not found."
        )

    # 2. Validate that rule_name is kebab-case
    rule_name_stem = rule_name[:-3] if rule_name.endswith(".md") else rule_name
    if not re.match(r"^[a-z0-9-]+$", rule_name_stem):
        raise VaultSpecError(
            f"Rule name '{rule_name_stem}' must be in kebab-case "
            "(lowercase letters, numbers, and hyphens)."
        )

    # 3. Define target rule file path (flat; nested rule folders unsupported)
    rules_src_dir = _t.get_context().rules_src_dir
    rule_file = rules_src_dir / f"{rule_name_stem}.md"

    if rule_file.exists() and not force:
        raise ResourceExistsError(
            f"Rule '{rule_name_stem}' already exists.",
            hint="Use --force to overwrite, or --dry-run to preview.",
        )

    # 4. Form the rule scaffold content
    scaffold_content = f"""---
derived_from:
  - "audit:{audit_stem}"
---

# Rule

<!-- Describe the positive or negative obligation in one sentence. -->

## Why

<!-- Explain the constraint's origin in 2-3 sentences. -->

## How

<!-- Provide concrete examples of the rule applied and the rule violated. -->
"""

    # 5. Read audit content, update its frontmatter: promoted_to: ['rule:<rule-name>']
    raw_bytes = audit_file.read_bytes()
    raw_content = raw_bytes.decode("utf-8")
    source_newline = "\r\n" if "\r\n" in raw_content else "\n"
    normalized_content = raw_content.replace("\r\n", "\n")

    # Let's parse metadata
    meta, _body = parse_vault_metadata(normalized_content)

    # Append to promoted_to
    new_rule_ref = f"rule:{rule_name_stem}"
    if new_rule_ref not in meta.promoted_to:
        meta.promoted_to.append(new_rule_ref)

    # Rebuild the audit's frontmatter to update promoted_to, preserving rest
    match = re.match(
        r"^---\s*\n(.*?)\n---\s*\n?(.*)$", normalized_content.lstrip(), re.DOTALL
    )
    if not match:
        raise VaultSpecError(
            f"Could not parse frontmatter of audit file '{audit_file}'."
        )

    yaml_block = match.group(1)
    audit_body = match.group(2)
    leading_whitespace = normalized_content[
        : len(normalized_content) - len(normalized_content.lstrip())
    ]

    # Rebuild frontmatter keys
    lines = ["---"]
    if meta.tags:
        lines.append("tags:")
        for tag in meta.tags:
            lines.append(f'  - "{tag}"')
    if meta.date:
        lines.append(f"date: '{meta.date}'")
    if meta.related:
        lines.append("related:")
        for link in meta.related:
            lines.append(f'  - "{link}"')
    if meta.supersedes:
        lines.append("supersedes:")
        for stem in meta.supersedes:
            lines.append(f"  - '{stem}'")
    if meta.superseded_by:
        lines.append(f"superseded_by: '{meta.superseded_by}'")
    if meta.derived_from:
        lines.append("derived_from:")
        for stem in meta.derived_from:
            lines.append(f"  - '{stem}'")
    if meta.promoted_to:
        lines.append("promoted_to:")
        for rule in meta.promoted_to:
            lines.append(f"  - '{rule}'")
    if meta.archived:
        lines.append(f"archived: '{meta.archived}'")

    # Preserve any unknown keys
    known_keys = {
        "tags",
        "date",
        "related",
        "feature",
        "supersedes",
        "superseded_by",
        "derived_from",
        "promoted_to",
        "archived",
    }
    in_unknown_key = False
    for line in yaml_block.split("\n"):
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith("-"):
            key = stripped.split(":", 1)[0].strip()
            in_unknown_key = key not in known_keys
            if in_unknown_key:
                lines.append(line)
        elif stripped.startswith("-"):
            if in_unknown_key:
                lines.append(line)
        else:
            if in_unknown_key and stripped:
                lines.append(line)
            in_unknown_key = False

    lines.append("---")
    if audit_body:
        lines.append(audit_body)

    rendered_audit = leading_whitespace + "\n".join(lines)
    final_audit_content = (
        rendered_audit
        if source_newline == "\n"
        else rendered_audit.replace("\n", source_newline)
    )

    # Vault-orientation ADR (decision D3): promote rewrites the source
    # audit's frontmatter (appending the promoted rule reference), so the
    # audit is mutated and its modified stamp is refreshed. The rule file
    # is freshly scaffolded with its own stamp and needs no refresh here.
    final_audit_content = refresh_modified_stamp(final_audit_content, vault_today())

    if not dry_run:
        # Write rule file
        ensure_dir(rule_file.parent)
        atomic_write(rule_file, scaffold_content)
        # Write updated audit file
        atomic_write(audit_file, final_audit_content)

    return rule_file
