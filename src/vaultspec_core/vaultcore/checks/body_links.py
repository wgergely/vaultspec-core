"""Check for wiki-links and markdown links in document body text.

Body text is prose after the YAML frontmatter closing ``---``.  File
references in body should use backtick code spans, not links.  Wiki-links
belong exclusively in the ``related:`` frontmatter field.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...core.helpers import atomic_write
from ..links import extract_wiki_links, rewrite_wiki_links_as_code_spans
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


def _rewrite_body_wiki_links(
    doc_path: Path, root_dir: Path, wanted_feature: str | None
) -> int:
    """Rewrite *doc_path*'s body wiki-links under its per-document lock.

    The read, the rewrite, and the write are one critical section on the same
    sentinel ``execute_edit`` takes.  The snapshot the checker scanned to find
    this document is deliberately not consulted here: it was parsed a whole
    corpus scan ago, so a replacement composed from it would overwrite
    anything committed since with bytes that never saw the newer revision -
    the silent lost update that locking the write alone does not prevent.

    Args:
        doc_path: The document to re-read and rewrite.
        root_dir: The project root whose ``.vault/`` holds the document.
        wanted_feature: The feature tag the pass is restricted to (already
            stripped of ``#``), or ``None`` for the whole corpus.  Re-checked
            under the lock because the revision found there may no longer be
            the one the snapshot matched.

    Returns:
        The number of body wiki-links rewritten as code spans; ``0`` when the
        document could not be read, no longer carries the feature tag, or has
        no body wiki-link left.
    """
    from ..edit_engine import document_write_lock

    with document_write_lock(doc_path, root_dir):
        return _rewrite_body_wiki_links_locked(doc_path, wanted_feature)


def _rewrite_body_wiki_links_locked(doc_path: Path, wanted_feature: str | None) -> int:
    """Perform the body-link rewrite under *doc_path*'s already-held lock.

    Args:
        doc_path: The document to re-read and rewrite.
        wanted_feature: The feature tag the pass is restricted to, or ``None``.

    Returns:
        The number of body wiki-links rewritten; ``0`` when nothing was
        written.
    """
    from ..parser import parse_vault_metadata
    from ._base import extract_feature_tags

    try:
        raw_content = doc_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    metadata, raw_body = parse_vault_metadata(raw_content)
    if wanted_feature is not None and wanted_feature not in extract_feature_tags(
        metadata.tags
    ):
        return 0

    fixed_body, replaced = rewrite_wiki_links_as_code_spans(raw_body)
    if replaced == 0 or fixed_body == raw_body:
        # The finding came from the pre-lock snapshot; re-derived under the
        # lock there is no body wiki-link left.  Writing would overwrite a
        # revision committed in between, and counting it would report a fix
        # that never happened.
        return 0

    prefix = raw_content[: len(raw_content) - len(raw_body)]
    atomic_write(doc_path, prefix + fixed_body)
    return replaced


def check_body_links(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    feature: str | None = None,
    fix: bool = False,
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
        fix: When ``True``, rewrite prose wiki-links as backtick code spans.
            The snapshot only nominates candidates: each rewrite is
            re-derived from a fresh read under the document's advisory lock
            (see :func:`_rewrite_body_wiki_links`), so a document another
            writer has since changed is re-judged rather than overwritten.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"body-links"``.
    """
    from ._base import extract_feature_tags

    result = CheckResult(check_name="body-links", supports_fix=True)
    wanted_feature = feature.lstrip("#") if feature else None

    for doc_path, (metadata, body) in snapshot.items():
        # Skip generated index files
        if is_generated_index(doc_path):
            continue

        if wanted_feature and wanted_feature not in extract_feature_tags(metadata.tags):
            continue

        rel_path = doc_path.relative_to(root_dir)

        # Strip code blocks and inline code before scanning
        prose = _strip_non_prose(body)

        wiki_links = extract_wiki_links(body)
        if fix and wiki_links:
            replaced = _rewrite_body_wiki_links(doc_path, root_dir, wanted_feature)
            if replaced:
                result.fixed_count += 1
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message=f"Fixed {replaced} body wiki-link(s) as code spans",
                        severity=Severity.INFO,
                    )
                )
        else:
            for target, count in wiki_links.items():
                for _occurrence in range(count):
                    result.diagnostics.append(
                        CheckDiagnostic(
                            path=rel_path,
                            message=(
                                f"Wiki-link in body text: [[{target}]] "
                                "- move to related: frontmatter or use backtick "
                                "code span"
                            ),
                            severity=Severity.ERROR,
                            fixable=True,
                            fix_description=(
                                "Run body-links check with --fix to convert it "
                                "to a code span"
                            ),
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
