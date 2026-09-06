"""Check and strip generated template annotations from vault documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.helpers import atomic_write
from ._base import (
    CheckDiagnostic,
    CheckResult,
    Severity,
    extract_feature_tags,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

PRESERVED_HTML_COMMENT_PREFIXES = ("RETIRED:",)
"""Standalone HTML comment prefixes that sanitizer must preserve.

These are machine-owned vault comments, not generated template guidance.
"""

_FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})")

__all__ = [
    "PRESERVED_HTML_COMMENT_PREFIXES",
    "AnnotationStats",
    "check_annotations",
    "strip_template_annotations",
]


@dataclass(frozen=True)
class AnnotationStats:
    """Counts of annotation syntaxes removed from a vault document."""

    frontmatter_comments: int = 0
    html_comments: int = 0
    malformed_html_comments: int = 0

    @property
    def total(self) -> int:
        """Return total annotations found."""
        return (
            self.frontmatter_comments
            + self.html_comments
            + self.malformed_html_comments
        )

    def describe(self) -> str:
        """Return a compact human-readable annotation count."""
        parts: list[str] = []
        if self.frontmatter_comments:
            suffix = "" if self.frontmatter_comments == 1 else "s"
            parts.append(
                f"{self.frontmatter_comments} frontmatter comment line{suffix}"
            )
        if self.html_comments:
            suffix = "" if self.html_comments == 1 else "s"
            parts.append(f"{self.html_comments} HTML comment block{suffix}")
        if self.malformed_html_comments:
            suffix = "" if self.malformed_html_comments == 1 else "s"
            parts.append(
                f"{self.malformed_html_comments} malformed HTML comment block{suffix}"
            )
        return ", ".join(parts) if parts else "no annotations"


def strip_template_annotations(content: str) -> tuple[str, AnnotationStats]:
    """Remove agent-facing template annotations from a rendered document.

    The sanitizer is intentionally explicit-operation-only: template hydration
    leaves annotations intact for agents, while check and repair surfaces call
    this function only when the operator requests a fix.

    Sanitization policy:
    - remove YAML frontmatter comment-only lines and standalone frontmatter
      annotation comment blocks;
    - remove standalone Markdown HTML comment blocks, including malformed
      ``<-- ... -->`` template annotations;
    - preserve fenced code blocks and inline/prose mentions of comments;
    - preserve machine-owned comments listed in
      :data:`PRESERVED_HTML_COMMENT_PREFIXES`.
    """
    normalized = content.replace("\r\n", "\n")
    frontmatter, body, has_frontmatter = _split_frontmatter(normalized)

    frontmatter_comment_count = 0
    if has_frontmatter:
        frontmatter, frontmatter_comment_count = _strip_frontmatter_comments(
            frontmatter
        )

    body, html_comment_count = _strip_html_comments(body)
    stats = AnnotationStats(
        frontmatter_comments=frontmatter_comment_count,
        html_comments=html_comment_count[0],
        malformed_html_comments=html_comment_count[1],
    )
    return frontmatter + body, stats


def _strip_annotations_in_place(
    doc_path: Path, root_dir: Path, wanted_feature: str | None
) -> AnnotationStats | None:
    """Strip *doc_path*'s annotations under its per-document advisory lock.

    The read the replacement is derived from, the strip, and the write are
    one critical section on the same sentinel ``execute_edit`` takes.  The
    corpus text the checker scanned to find this document is deliberately
    not reused: it was read a whole corpus scan ago, so composing the
    replacement from it would overwrite anything committed since with bytes
    that never saw the newer revision - the silent lost update that locking
    the write alone does not prevent.

    Args:
        doc_path: The document to re-read and rewrite.
        root_dir: The project root whose ``.vault/`` holds the document.
        wanted_feature: The feature tag the pass is restricted to (already
            stripped of ``#``), or ``None`` for the whole corpus.  Re-checked
            under the lock because the revision found there may no longer be
            the one the scan matched.

    Returns:
        The stats describing what was stripped, or ``None`` when the document
        could not be read, no longer carries the feature tag, or has nothing
        left to strip.
    """
    from ..edit_engine import document_write_lock

    with document_write_lock(doc_path, root_dir):
        return _strip_annotations_locked(doc_path, wanted_feature)


def _strip_annotations_locked(
    doc_path: Path, wanted_feature: str | None
) -> AnnotationStats | None:
    """Perform the strip under *doc_path*'s already-held lock.

    Args:
        doc_path: The document to re-read and rewrite.
        wanted_feature: The feature tag the pass is restricted to, or ``None``.

    Returns:
        The stats describing what was stripped, or ``None`` when there was
        nothing to write.
    """
    from ..parser import parse_vault_metadata

    try:
        # Read as bytes and decode without universal newlines so the source
        # CRLF/LF convention is observable and restorable on the output.
        raw_content = doc_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if wanted_feature is not None:
        metadata, _body = parse_vault_metadata(raw_content)
        if wanted_feature not in extract_feature_tags(metadata.tags):
            return None

    source_newline = "\r\n" if "\r\n" in raw_content else "\n"
    cleaned_lf, stats = strip_template_annotations(raw_content)
    if stats.total == 0:
        # The finding came from the pre-lock scan; re-derived under the lock
        # there is nothing left to strip.  Writing would overwrite a revision
        # committed in between, and counting it would report a fix that never
        # happened.
        return None

    cleaned = (
        cleaned_lf
        if source_newline == "\n"
        else cleaned_lf.replace("\n", source_newline)
    )
    atomic_write(doc_path, cleaned)
    return stats


def check_annotations(
    root_dir: Path,
    *,
    feature: str | None = None,
    fix: bool = False,
    dry_run: bool = False,
    raw_texts: Mapping[Path, tuple[str, bool]] | None = None,
) -> CheckResult:
    """Find or remove template annotations from vault documents.

    Args:
        root_dir: Project root directory.
        feature: Restrict checks to documents with this feature tag.
        fix: When ``True``, remove YAML comment-only frontmatter lines and
            Markdown HTML comment blocks from matching documents.  The scan
            only nominates candidates: each strip is re-derived from a fresh
            read under the document's advisory lock (see
            :func:`_strip_annotations_in_place`), so a document another writer
            has since changed is re-judged rather than overwritten.
        dry_run: When ``True``, report the files that would be changed without
            mutating them. Ignored unless ``fix`` is also ``True``.
        raw_texts: The ingress read's per-document ``(text, crlf)`` map (see
            :attr:`~vaultspec_core.graph.api.VaultGraph.raw_texts`).  When
            supplied on a non-mutating pass, documents are validated from it
            instead of re-reading the corpus - the single-ingress contract.
            Ignored when ``fix`` is set: the mutating path reads and rewrites
            the file it is about to change.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with check
        name ``"annotations"``.
    """
    from ..parser import parse_vault_metadata
    from ._base import iter_document_texts

    result = CheckResult(check_name="annotations", supports_fix=True)
    wanted_feature = feature.lstrip("#") if feature else None

    if raw_texts is not None and not fix:
        sources: Iterable[tuple[Path, str, bool]] = (
            (path, text, crlf) for path, (text, crlf) in raw_texts.items()
        )
    else:
        sources = iter_document_texts(root_dir)

    for doc_path, raw_content, _has_crlf in sources:
        metadata, _body = parse_vault_metadata(raw_content)
        if wanted_feature and wanted_feature not in extract_feature_tags(metadata.tags):
            continue

        _cleaned_lf, stats = strip_template_annotations(raw_content)
        if stats.total == 0:
            continue

        rel_path = doc_path.relative_to(root_dir)
        if fix and dry_run:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=f"Would remove template annotations: {stats.describe()}",
                    severity=Severity.WARNING,
                    fixable=True,
                    fix_description="Run without --dry-run to strip them",
                )
            )
            continue

        if fix:
            written = _strip_annotations_in_place(doc_path, root_dir, wanted_feature)
            if written is None:
                continue
            result.fixed_count += 1
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=f"Removed template annotations: {written.describe()}",
                    severity=Severity.INFO,
                )
            )
            continue

        result.diagnostics.append(
            CheckDiagnostic(
                path=rel_path,
                message=f"Template annotations remain: {stats.describe()}",
                severity=Severity.WARNING,
                fixable=True,
                fix_description="Run annotations check with --fix to strip them",
            )
        )

    return result


def _split_frontmatter(content: str) -> tuple[str, str, bool]:
    if not content.startswith("---\n"):
        return "", content, False

    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            split_at = index + 1
            return "".join(lines[:split_at]), "".join(lines[split_at:]), True
    return "", content, False


def _strip_frontmatter_comments(frontmatter: str) -> tuple[str, int]:
    lines = frontmatter.splitlines(keepends=True)
    kept: list[str] = []
    removed = 0
    in_annotation = False
    for line in lines:
        stripped = line.lstrip()
        if in_annotation:
            if "-->" in line:
                in_annotation = False
            continue
        if stripped.startswith("#"):
            removed += 1
            continue
        if stripped.startswith(("<!--", "<--")):
            removed += 1
            if "-->" not in line:
                in_annotation = True
            continue
        kept.append(line)
    return "".join(kept), removed


def _strip_html_comments(markdown: str) -> tuple[str, tuple[int, int]]:
    lines = markdown.splitlines(keepends=True)
    output: list[str] = []
    removed = 0
    malformed_removed = 0
    fence_char: str | None = None
    fence_len = 0
    in_comment = False
    malformed_comment = False

    for line in lines:
        stripped = line.lstrip()
        fence = _markdown_fence(line)
        if not in_comment and fence is not None:
            marker_char, marker_len = fence
            if fence_char is None:
                fence_char = marker_char
                fence_len = marker_len
            elif marker_char == fence_char and marker_len >= fence_len:
                fence_char = None
                fence_len = 0
            output.append(line)
            continue

        if fence_char is not None:
            output.append(line)
            continue

        if in_comment:
            end = line.find("-->")
            if end == -1:
                continue
            in_comment = False
            if malformed_comment:
                malformed_removed += 1
                malformed_comment = False
            else:
                removed += 1
            tail = line[end + 3 :]
            if tail.strip():
                output.append(tail)
            continue

        sequence = _strip_standalone_comment_sequence(line)
        if sequence is not None:
            cleaned_line, html_count, malformed_count = sequence
            removed += html_count
            malformed_removed += malformed_count
            if cleaned_line:
                output.append(cleaned_line)
            continue

        is_html_comment = stripped.startswith("<!--")
        is_malformed_comment = not is_html_comment and stripped.startswith("<--")
        if not is_html_comment and not is_malformed_comment:
            output.append(line)
            continue

        start_len = 4 if is_html_comment else 3
        comment_text = stripped[start_len:].lstrip()
        if is_html_comment and comment_text.startswith(PRESERVED_HTML_COMMENT_PREFIXES):
            output.append(line)
            continue

        end = stripped.find("-->")
        if end == -1:
            in_comment = True
            malformed_comment = is_malformed_comment
            continue

        tail = stripped[end + 3 :]
        if tail.strip():
            output.append(line)
            continue

        if is_malformed_comment:
            malformed_removed += 1
        else:
            removed += 1

    if in_comment and malformed_comment:
        malformed_removed += 1
    elif in_comment:
        removed += 1

    return "".join(output), (removed, malformed_removed)


def _strip_standalone_comment_sequence(line: str) -> tuple[str, int, int] | None:
    """Strip removable same-line comments when the whole line is comments."""
    cursor = 0
    html_comments = 0
    malformed_comments = 0
    saw_comment = False
    kept_comments: list[str] = []
    newline = "\n" if line.endswith("\n") else ""
    content = line[:-1] if newline else line
    indent = content[: len(content) - len(content.lstrip())]

    while cursor < len(content):
        while cursor < len(content) and content[cursor].isspace():
            cursor += 1
        if cursor >= len(content):
            break

        is_html_comment = content.startswith("<!--", cursor)
        is_malformed_comment = not is_html_comment and content.startswith("<--", cursor)
        if not is_html_comment and not is_malformed_comment:
            return None

        start_len = 4 if is_html_comment else 3
        body_start = cursor + start_len
        end = content.find("-->", body_start)
        if end == -1:
            return None

        comment_text = content[body_start:end].lstrip()
        if is_html_comment and comment_text.startswith(PRESERVED_HTML_COMMENT_PREFIXES):
            kept_comments.append(content[cursor : end + 3])
        else:
            saw_comment = True
            if is_malformed_comment:
                malformed_comments += 1
            else:
                html_comments += 1
        cursor = end + 3

    if not saw_comment and not kept_comments:
        return None
    if not kept_comments:
        return "", html_comments, malformed_comments
    return indent + " ".join(kept_comments) + newline, html_comments, malformed_comments


def _markdown_fence(line: str) -> tuple[str, int] | None:
    """Return the opening/closing fence marker char and length, if present."""
    match = _FENCE_RE.match(line)
    if match is None:
        return None
    marker = match.group("fence")
    return marker[0], len(marker)
