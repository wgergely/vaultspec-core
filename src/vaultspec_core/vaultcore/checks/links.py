"""Check and fix wiki-link conventions in vault documents.

Obsidian convention: ``[[note-name]]`` without file extension.
Detects ``[[name.md]]`` patterns in both ``related:`` frontmatter fields
and markdown body text, and normalizes them with ``--fix``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_links"]

# Matches [[target.md]] or [[target.md|display]]
_MD_LINK_PATTERN = re.compile(r"\[\[([^\]|]+)\.md(\|[^\]]+)?\]\]")


def check_links(
    root_dir: Path,
    *,
    feature: str | None = None,
    fix: bool = False,
) -> CheckResult:
    """Check wiki-links follow Obsidian convention (no ``.md`` extension).

    With ``--fix``, rewrites ``[[name.md]]`` → ``[[name]]`` in-place.
    """
    from ..parser import parse_vault_metadata
    from ..scanner import scan_vault

    result = CheckResult(check_name="links", supports_fix=True)

    for doc_path in scan_vault(root_dir):
        try:
            content = doc_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Feature filter
        if feature:
            metadata, _ = parse_vault_metadata(content)
            from ..models import DocType

            feat = feature.lstrip("#")
            type_values = {d.value for d in DocType}
            feature_tags = [
                t.lstrip("#") for t in metadata.tags if t.lstrip("#") not in type_values
            ]
            if feat not in feature_tags:
                continue

        matches = _MD_LINK_PATTERN.findall(content)
        if not matches:
            continue

        rel_path = doc_path.relative_to(root_dir)
        bad_count = len(matches)

        if fix:
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
