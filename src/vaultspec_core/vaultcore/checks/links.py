"""Check and fix wiki-link conventions in vault documents.

Obsidian convention: ``[[note-name]]`` without file extension.
Detects ``[[name.md]]`` patterns in both ``related:`` frontmatter fields
and markdown body text, and normalizes them with ``--fix``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...core.helpers import atomic_write
from ._base import CheckDiagnostic, CheckResult, Severity, VaultSnapshot

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_links"]

# Matches [[target.md]] or [[target.md|display]]
_MD_LINK_PATTERN = re.compile(r"\[\[([^\]|]+)\.md(\|[^\]]+)?\]\]")


def _rewrite_md_links(doc_path: Path, root_dir: Path) -> bool:
    """Strip ``.md`` from every wiki-link in *doc_path*, under its own lock.

    The read and the write are one critical section on *doc_path*'s
    per-document advisory lock - the same sentinel ``execute_edit`` takes.
    The substitution is computed from bytes read inside that section, so a
    concurrent editor cannot land a revision between the read and the write
    and have it silently overwritten by a replacement derived from the
    superseded bytes.

    Args:
        doc_path: The document to rewrite.
        root_dir: Project root owning the document's ``.vault/``.

    Returns:
        ``True`` when the document was rewritten, ``False`` when it could
        not be read or carried no ``.md`` wiki-link once the lock was held
        (another writer may have fixed or removed it in the interim).
    """
    from ..edit_engine import document_write_lock

    with document_write_lock(doc_path, root_dir):
        try:
            # Read as bytes and decode without universal newlines so CRLF
            # endings survive the regex substitution; the pattern is
            # line-internal and does not touch newlines, so reading bytes is
            # sufficient to preserve the source convention.
            content = doc_path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        fixed_content = _MD_LINK_PATTERN.sub(
            lambda m: f"[[{m.group(1)}{m.group(2) or ''}]]",
            content,
        )
        if fixed_content == content:
            # The finding came from the pre-lock snapshot; re-derived under
            # the lock there is nothing left to change. Reporting a fix that
            # did not happen would be a false count.
            return False
        atomic_write(doc_path, fixed_content)
        return True


def check_links(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    feature: str | None = None,
    fix: bool = False,
) -> CheckResult:
    """Check wiki-links follow Obsidian convention (no ``.md`` extension).

    Detects ``[[name.md]]`` patterns in both frontmatter ``related:`` fields
    and markdown body text.

    Args:
        root_dir: Project root directory.
        snapshot: Pre-built snapshot mapping document paths to parsed data.
        feature: Restrict checks to documents with this feature tag
            (without ``#``).
        fix: When ``True``, rewrites ``[[name.md]]`` to ``[[name]]`` in-place.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"links"``.
    """
    from ._base import extract_feature_tags

    result = CheckResult(check_name="links", supports_fix=True)

    for doc_path, (metadata, body) in snapshot.items():
        if feature:
            feat = feature.lstrip("#")
            if feat not in extract_feature_tags(metadata.tags):
                continue

        # Check both related fields and body for .md wiki-links
        related_str = " ".join(metadata.related) if metadata.related else ""
        combined = related_str + "\n" + body
        matches = _MD_LINK_PATTERN.findall(combined)
        if not matches:
            continue

        rel_path = doc_path.relative_to(root_dir)
        bad_count = len(matches)

        if fix:
            if not _rewrite_md_links(doc_path, root_dir):
                continue
            result.fixed_count += 1
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=(
                        f"Fixed: removed .md extension from {bad_count} wiki-link(s)"
                    ),
                    severity=Severity.INFO,
                )
            )
        else:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=(
                        f"{bad_count} wiki-link(s) use .md extension "
                        f"(Obsidian convention: no file extension in wiki-links)"
                    ),
                    severity=Severity.WARNING,
                    fixable=True,
                )
            )

    return result
