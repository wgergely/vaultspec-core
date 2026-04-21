"""Check vault directory structure and filename conventions.

Wraps VaultConstants.validate_vault_structure() and validate_filename()
which exist but were never wired to a CLI command.  With ``--fix``,
renames files that have wrong suffixes or missing date prefixes, and
updates incoming ``[[wiki-link]]`` references in the ``related:``
frontmatter of other documents so the rename does not leave dangling
links behind.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ...core.helpers import atomic_write
from ._base import (
    CheckDiagnostic,
    CheckResult,
    Severity,
    VaultSnapshot,
    is_generated_index,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_structure"]

logger = logging.getLogger(__name__)


def _fix_filename(
    doc_path: Path, root_dir: Path, result: CheckResult
) -> list[tuple[str, str]]:
    """Attempt to fix filename issues: wrong suffix, missing date prefix.

    Returns a list of ``(old_stem, new_stem)`` tuples for every successful
    rename performed on *doc_path* (zero, one, or two renames per call).
    Callers use the returned list to drive a follow-up
    :func:`_rewrite_incoming_refs` pass so incoming ``[[wiki-link]]``
    references stay in sync with the new filenames.
    """
    from ..models import DocType
    from ..scanner import get_doc_type

    renames: list[tuple[str, str]] = []

    doc_type = get_doc_type(doc_path, root_dir)
    if not doc_type:
        return renames

    filename = doc_path.name
    rel = doc_path.relative_to(root_dir)

    expected_suffix = f"-{doc_type.value}.md"
    needs_rename = False

    if doc_type == DocType.EXEC:
        if f"-{DocType.EXEC.value}" not in filename:
            needs_rename = True
    else:
        if not filename.endswith(expected_suffix):
            needs_rename = True

    if needs_rename:
        match = re.match(
            r"^(\d{4}-\d{2}-\d{2}-.+?)(?:-(?:adr|audit|"
            r"exec|plan|reference|research).*)?\.md$",
            filename,
        )
        if match:
            base = match.group(1)
            new_filename = f"{base}{expected_suffix}"
            new_path = doc_path.parent / new_filename

            if not new_path.exists():
                old_stem = doc_path.stem
                doc_path.rename(new_path)
                result.fixed_count += 1
                renames.append((old_stem, new_path.stem))
                doc_path = new_path
                rel = doc_path.relative_to(root_dir)
                filename = new_filename
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel,
                        message=f"Fixed: renamed to {new_filename}",
                        severity=Severity.INFO,
                    )
                )
                logger.info("Renamed %s -> %s", filename, new_filename)
            else:
                logger.warning("Cannot rename %s: target exists", filename)
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel,
                        message=(
                            f"Cannot rename to {new_filename}: target already exists"
                        ),
                        severity=Severity.ERROR,
                    )
                )
                return renames

    if not re.match(r"^\d{4}-\d{2}-\d{2}-", filename):
        # UTC date prefix so the rename is deterministic regardless of
        # the runner's local timezone.  Matches the manifest timestamps
        # in ``core/commands.py`` that also use ``datetime.UTC``.
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        new_filename = f"{today}-{filename}"
        new_path = doc_path.parent / new_filename

        if not new_path.exists():
            old_stem = doc_path.stem
            doc_path.rename(new_path)
            result.fixed_count += 1
            renames.append((old_stem, new_path.stem))
            rel = new_path.relative_to(root_dir)
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel,
                    message=f"Fixed: renamed to {new_filename}",
                    severity=Severity.INFO,
                )
            )
            logger.info("Renamed %s -> %s", filename, new_filename)
        else:
            logger.warning("Cannot rename %s: target exists", filename)
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel,
                    message=(f"Cannot rename to {new_filename}: target already exists"),
                    severity=Severity.ERROR,
                )
            )

    return renames


_RELATED_ENTRY_RE = re.compile(r'^(\s*-\s*["\']?\[\[)(.+?)(\]\]["\']?.*)$')
_FRONTMATTER_LINE_BUDGET = 200


def _rewrite_incoming_refs(
    root_dir: Path,
    renames: list[tuple[str, str]],
    result: CheckResult,
) -> None:
    """Rewrite ``[[old_stem]]`` -> ``[[new_stem]]`` in ``related:`` frontmatter.

    Walks every ``*.md`` file under ``root_dir / ".vault"`` directly off
    the filesystem (the renames have already happened on disk; the
    in-memory :class:`VaultSnapshot` is now stale).  Inspects the YAML
    frontmatter ``related:`` list and rewrites any matching wiki-link
    entry.  Only operates on the ``related:`` block - body prose is left
    untouched so free-text mentions of the old filename do not
    accidentally mutate.

    The scanner recognises the block-sequence form
    (``- "[[stem]]"`` / ``- '[[stem]]'`` / ``- [[stem]]``) which is the
    form enforced by the vault template and used throughout this
    project.  YAML flow-style lists (``related: ["[[stem]]"]``) are not
    currently rewritten; ``vault check frontmatter`` enforces block
    style.

    Each rewrite bumps :attr:`CheckResult.fixed_count` and appends an
    INFO diagnostic.  Read/write failures for individual documents log a
    warning and do not abort the pass.

    Args:
        root_dir: Project root (the caller's workspace).
        renames: List of ``(old_stem, new_stem)`` pairs produced by
            :func:`_fix_filename`.
        result: :class:`CheckResult` to accumulate diagnostics and fix
            counts into.
    """
    if not renames:
        return

    raw_map = {old: new for old, new in renames if old != new}
    if not raw_map:
        return

    # Collapse rename chains so [[A]] -> [[C]] when ``A -> B`` and ``B -> C``
    # both happened in the same check run.  Guards against cycles by
    # capping traversal at the number of raw entries and dropping any
    # entry whose terminal value is the original key (self-cycle).
    rename_map: dict[str, str] = {}
    limit = len(raw_map) + 1
    for old in raw_map:
        current = raw_map[old]
        steps = 0
        while current in raw_map and steps < limit:
            current = raw_map[current]
            steps += 1
        if current != old:
            rename_map[old] = current

    vault_root = root_dir / ".vault"
    if not vault_root.is_dir():
        return

    for md_path in sorted(vault_root.rglob("*.md")):
        try:
            # Read as bytes first so CRLF endings survive the decode;
            # ``read_text`` collapses them via universal newlines.
            raw = md_path.read_bytes()
            content = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Failed to read %s for ref rewrite: %s", md_path, exc)
            continue

        # Preserve a UTF-8 BOM if present; the scanner strips it so the
        # opening ``---`` fence matches but the write-back restores it.
        # Use the ``﻿`` escape rather than the literal character so
        # the source is legible in editors that hide zero-width glyphs.
        bom = ""
        if content.startswith("﻿"):
            bom = "﻿"
            content = content[1:]

        # Preserve the file's line-ending convention across the rewrite
        # so we do not ship mixed CRLF/LF endings back to disk.
        newline = "\r\n" if "\r\n" in content else "\n"
        lines = content.splitlines()
        in_frontmatter = False
        in_related = False
        changed = False
        fence_closed = False
        budget_exceeded = False

        for idx, line in enumerate(lines):
            # Guard against a missing closing fence: if the file is not
            # a real vault document, bail out of the scan after a fixed
            # line budget rather than scanning prose forever.
            if in_frontmatter and idx > _FRONTMATTER_LINE_BUDGET:
                budget_exceeded = True
                break

            stripped = line.strip()
            if stripped == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                else:
                    fence_closed = True
                    break
                continue

            if not in_frontmatter:
                continue

            if line.strip().startswith("related:"):
                in_related = True
                continue

            if in_related and line and not line.startswith((" ", "\t", "-")):
                in_related = False

            if not in_related:
                continue

            match = _RELATED_ENTRY_RE.match(line)
            if not match:
                continue

            target = match.group(2)
            if target in rename_map:
                new_target = rename_map[target]
                lines[idx] = f"{match.group(1)}{new_target}{match.group(3)}"
                changed = True
                result.fixed_count += 1
                try:
                    rel = md_path.relative_to(root_dir)
                except ValueError:
                    rel = md_path
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel,
                        message=(
                            f"Updated wiki-link: [[{target}]] -> [[{new_target}]]"
                        ),
                        severity=Severity.INFO,
                    )
                )

        # Surface a warning diagnostic when the frontmatter exceeds the
        # line budget so operators can investigate documents whose
        # frontmatter may have been skipped mid-scan.
        if budget_exceeded:
            try:
                rel_path = md_path.relative_to(root_dir)
            except ValueError:
                rel_path = md_path
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=(
                        "Frontmatter exceeds "
                        f"{_FRONTMATTER_LINE_BUDGET} lines; "
                        "ref rewrite stopped at budget"
                    ),
                    severity=Severity.WARNING,
                )
            )

        if not changed:
            continue

        # If the scan never saw a closing fence we are in unknown
        # territory; skip writing rather than risk corrupting a file
        # whose frontmatter layout we misread.
        if in_frontmatter and not fence_closed:
            logger.warning(
                "Skipping rewrite of %s: closing frontmatter fence not found",
                md_path,
            )
            continue

        new_content = bom + newline.join(lines)
        # Preserve a trailing newline convention: if the original ended
        # with the detected newline, keep it.
        if content.endswith(newline):
            new_content += newline
        try:
            atomic_write(md_path, new_content)
        except OSError as exc:
            logger.warning("Failed to rewrite %s: %s", md_path, exc)


def check_structure(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    fix: bool = False,
) -> CheckResult:
    """Check vault directory structure and filename conventions.

    Detects unsupported subdirectories in ``.vault/``, files placed directly
    in the ``.vault/`` root, and filenames deviating from the
    ``YYYY-MM-DD-<feature>-<type>.md`` convention.

    Args:
        root_dir: Project root directory.
        snapshot: Pre-built snapshot mapping document paths to parsed data.
        fix: When ``True``, renames files with wrong type suffixes or
            missing date prefixes.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"structure"``.
    """
    from ..models import VaultConstants
    from ..scanner import get_doc_type

    result = CheckResult(check_name="structure", supports_fix=True)
    all_renames: list[tuple[str, str]] = []

    for msg in VaultConstants.validate_vault_structure(root_dir):
        result.diagnostics.append(
            CheckDiagnostic(
                path=None,
                message=msg,
                severity=Severity.ERROR,
            )
        )

    for doc_path in snapshot:
        # Skip generated index files (non-standard naming convention)
        if is_generated_index(doc_path):
            continue

        doc_type = get_doc_type(doc_path, root_dir)
        errors = VaultConstants.validate_filename(doc_path.name, doc_type)

        if errors and fix:
            renames = _fix_filename(doc_path, root_dir, result)
            all_renames.extend(renames)
            if doc_path.exists():
                remaining = VaultConstants.validate_filename(doc_path.name, doc_type)
                for msg in remaining:
                    result.diagnostics.append(
                        CheckDiagnostic(
                            path=doc_path.relative_to(root_dir),
                            message=msg,
                            severity=Severity.ERROR,
                        )
                    )
        else:
            for msg in errors:
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=doc_path.relative_to(root_dir),
                        message=msg,
                        severity=Severity.ERROR,
                        fixable=True,
                        fix_description="Run with --fix to attempt auto-rename",
                    )
                )

    if fix and all_renames:
        _rewrite_incoming_refs(root_dir, all_renames, result)

    return result
