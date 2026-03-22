"""Check and fix wiki-link conventions in vault documents.

Obsidian convention: ``[[note-name]]`` without file extension.
Detects ``[[name.md]]`` patterns in both ``related:`` frontmatter fields
and markdown body text, and normalizes them with ``--fix``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity, VaultSnapshot

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_links"]

# Matches [[target.md]] or [[target.md|display]]
_MD_LINK_PATTERN = re.compile(r"\[\[([^\]|]+)\.md(\|[^\]]+)?\]\]")


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
            try:
                content = doc_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fixed_content = _MD_LINK_PATTERN.sub(
                lambda m: f"[[{m.group(1)}{m.group(2) or ''}]]",
                content,
            )
            doc_path.write_text(fixed_content, encoding="utf-8")
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
                    fix_description="Run with --fix to normalize wiki-links",
                )
            )

    return result
