"""Check for wiki-links and markdown links in document body text.

Body text is prose after the YAML frontmatter closing ``---``.  File
references in body should use backtick code spans, not links.  Wiki-links
belong exclusively in the ``related:`` frontmatter field.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ._base import (
    CheckDiagnostic,
    CheckResult,
    Severity,
    VaultSnapshot,
    is_generated_index,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_body_links"]

# [[target]] or [[target|display]]
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# [display](target) where target is NOT a URL or anchor
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!https?://|#|mailto:)([^)]+)\)")

# Fenced code blocks (``` or ~~~, with optional language tag)
_CODE_FENCE_RE = re.compile(
    r"^(?:```|~~~)[^\n]*\n.*?^(?:```|~~~)\s*$",
    re.MULTILINE | re.DOTALL,
)

# Inline code spans (`...`)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")

# HTML comments (<!-- ... -->), may span multiple lines
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_non_prose(body: str) -> str:
    """Remove code blocks, inline code, and HTML comments from body."""
    stripped = _CODE_FENCE_RE.sub("", body)
    stripped = _HTML_COMMENT_RE.sub("", stripped)
    return _INLINE_CODE_RE.sub("", stripped)


def check_body_links(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    feature: str | None = None,
) -> CheckResult:
    """Find wiki-links and markdown path links in document body text.

    Detects ``[[wiki-link]]`` and ``[text](path)`` patterns in the body
    (everything after the YAML frontmatter ``---`` delimiter).  Links in
    ``related:`` frontmatter are not flagged.  Index files
    (``*.index.md``) are skipped because they legitimately list vault
    documents in body text as a generated inventory.

    Args:
        root_dir: Project root directory.
        snapshot: Pre-built snapshot mapping document paths to parsed data.
        feature: Restrict checks to documents with this feature tag
            (without ``#``).

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"body-links"``.
    """
    from ._base import extract_feature_tags

    result = CheckResult(check_name="body-links", supports_fix=False)

    for doc_path, (metadata, body) in snapshot.items():
        # Skip generated index files
        if is_generated_index(doc_path):
            continue

        if feature:
            feat = feature.lstrip("#")
            if feat not in extract_feature_tags(metadata.tags):
                continue

        rel_path = doc_path.relative_to(root_dir)

        # Strip code blocks and inline code before scanning
        prose = _strip_non_prose(body)

        # Detect wiki-links in body
        for match in _WIKI_LINK_RE.finditer(prose):
            target = match.group(1)
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=(
                        f"Wiki-link in body text: [[{target}]] "
                        "- move to related: frontmatter or use backtick code span"
                    ),
                    severity=Severity.ERROR,
                )
            )

        # Detect markdown path links in body
        for match in _MD_LINK_RE.finditer(prose):
            display = match.group(1)
            target = match.group(2)
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=(
                        f"Markdown link in body text: [{display}]({target}) "
                        "- use backtick code span for file references"
                    ),
                    severity=Severity.ERROR,
                )
            )

    return result
