"""Check and optionally fix vault document frontmatter.

Validates every document against DocumentMetadata.validate() rules:
- At least 2 tags (one directory tag, one feature tag; extra tags allowed)
- Valid date format (YYYY-MM-DD)
- Valid related link format ([[wiki-link]])
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...core.helpers import atomic_write
from ._base import (
    CheckDiagnostic,
    CheckResult,
    Severity,
    VaultSnapshot,
    extract_feature_tags,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ..models import DocType, DocumentMetadata

__all__ = ["check_frontmatter"]


_KNOWN_KEYS = frozenset(
    {
        "tags",
        "date",
        "modified",
        "body_schema",
        "body_hash",
        "related",
        "feature",
        "supersedes",
        "superseded_by",
        "derived_from",
        "promoted_to",
        "archived",
    }
)


def _read_source_text(doc_path: Path) -> tuple[str, str] | None:
    """Return ``(lf_content, source_newline)`` for *doc_path*, or None.

    Reads as bytes so the source CRLF/LF convention is observable;
    ``read_text`` collapses everything to ``\\n`` via universal newlines,
    which would silently strip CRLF before we ever see it and bake LF back
    into a previously-CRLF file. The content is normalized to LF for the
    regex/manipulation passes; the caller restores the source newline
    convention on the rendered output so files that arrived as CRLF leave
    as CRLF.
    """
    try:
        raw_content = doc_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    source_newline = "\r\n" if "\r\n" in raw_content else "\n"
    return raw_content.replace("\r\n", "\n"), source_newline


def _normalized_tags(
    metadata: DocumentMetadata, yaml_block: str, doc_type: DocType | None
) -> tuple[list[str], bool, str | None]:
    """Normalize ``#`` prefixes, or construct tags from a bare ``feature:``.

    Returns the tag list, whether it differs from the parsed tags, and the
    fix description to record (``None`` when nothing changed).
    """
    new_tags = [tag if tag.startswith("#") else f"#{tag}" for tag in metadata.tags]
    if metadata.tags:
        if new_tags == list(metadata.tags):
            return new_tags, False, None
        return new_tags, True, "normalized tag # prefixes"

    feature_match = re.search(r"^feature:\s*(.+)$", yaml_block, re.MULTILINE)
    if not feature_match or not doc_type:
        return new_tags, False, None

    feature_val = feature_match.group(1).strip().strip("\"'")
    if not feature_val.startswith("#"):
        feature_val = f"#{feature_val}"
    return [doc_type.tag, feature_val], True, "constructed tags from feature field"


def _normalized_date(date_val: str | None) -> tuple[str | None, bool]:
    """Trim a date value down to its leading ``YYYY-MM-DD`` component."""
    if not date_val:
        return date_val, False
    date_str = str(date_val).strip()
    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", date_str)
    if not date_match or date_str == date_match.group(1):
        return date_val, False
    return date_match.group(1), True


def _existing_tag_lines(yaml_block: str) -> list[str]:
    """Return the verbatim ``tags:`` lines already present in *yaml_block*."""
    lines: list[str] = []
    for line in yaml_block.split("\n"):
        stripped = line.strip()
        if stripped.startswith("tags") or (
            stripped.startswith("-") and "#" in stripped
        ):
            lines.append(line)
    return lines


def _unknown_key_lines(yaml_block: str) -> list[str]:
    """Return the verbatim lines of every key outside :data:`_KNOWN_KEYS`."""
    lines: list[str] = []
    in_unknown_key = False
    for line in yaml_block.split("\n"):
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith("-"):
            in_unknown_key = stripped.split(":", 1)[0].strip() not in _KNOWN_KEYS
        elif not stripped.startswith("-"):
            if in_unknown_key and stripped:
                lines.append(line)
            in_unknown_key = False
            continue
        if in_unknown_key:
            lines.append(line)
    return lines


def _render_frontmatter_lines(
    metadata: DocumentMetadata,
    new_tags: list[str],
    date_val: str | None,
    yaml_block: str,
    *,
    tags_changed: bool,
) -> list[str]:
    """Rebuild the frontmatter block in canonical field order."""
    lines = ["---"]
    if new_tags:
        lines.append("tags:")
        lines.extend(f'  - "{tag}"' for tag in new_tags)
    elif not tags_changed:
        lines.extend(_existing_tag_lines(yaml_block))

    if date_val:
        lines.append(f"date: {date_val}")
    elif metadata.date:
        lines.append(f"date: {metadata.date}")

    if metadata.modified:
        lines.append(f"modified: '{metadata.modified}'")

    if metadata.body_schema:
        lines.append(f"body_schema: '{metadata.body_schema}'")

    # Carried through verbatim: the canonical rebuild only reorders and
    # re-quotes frontmatter, so the body this fingerprint attests is
    # untouched and dropping the field would silently retract a valid
    # attestation.
    if metadata.body_hash:
        lines.append(f"body_hash: '{metadata.body_hash}'")

    if metadata.related:
        lines.append("related:")
        lines.extend(f'  - "{link}"' for link in metadata.related)

    if metadata.supersedes:
        lines.append("supersedes:")
        lines.extend(f"  - '{stem}'" for stem in metadata.supersedes)

    if metadata.superseded_by:
        lines.append(f"superseded_by: '{metadata.superseded_by}'")

    if metadata.derived_from:
        lines.append("derived_from:")
        lines.extend(f"  - '{stem}'" for stem in metadata.derived_from)

    if metadata.promoted_to:
        lines.append("promoted_to:")
        lines.extend(f"  - '{rule}'" for rule in metadata.promoted_to)

    if metadata.archived:
        lines.append(f"archived: '{metadata.archived}'")

    lines.extend(_unknown_key_lines(yaml_block))
    lines.append("---")
    return lines


def _fix_frontmatter(doc_path: Path, root_dir: Path) -> str | None:
    """Attempt to fix common frontmatter issues. Returns fix description or None.

    The read, the recomposition, and the write all run inside *doc_path*'s
    per-document advisory lock, so the frontmatter this pass rewrites is the
    frontmatter it actually read. Composing outside the lock would let a
    concurrent ``vault edit`` land between the read and the write, and the
    replacement - individually atomic, derived from bytes that no longer
    exist - would silently discard that edit.
    """
    from ..edit_engine import document_write_lock

    with document_write_lock(doc_path, root_dir):
        return _fix_frontmatter_locked(doc_path, root_dir)


def _fix_frontmatter_locked(doc_path: Path, root_dir: Path) -> str | None:
    """Recompose and rewrite *doc_path*'s frontmatter under its held lock.

    Args:
        doc_path: The document being fixed; its per-document lock is already
            held by :func:`_fix_frontmatter`.
        root_dir: Project root, used to derive the document's type.

    Returns:
        A ``"; "``-joined description of the fixes applied, or ``None`` when
        the document is unreadable, carries no frontmatter fence, or needs
        no fix.
    """
    from ..scanner import get_doc_type

    source = _read_source_text(doc_path)
    if source is None:
        return None
    content, source_newline = source

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content.lstrip(), re.DOTALL)
    if not match:
        return None

    yaml_block = match.group(1)
    body = match.group(2)
    leading_whitespace = content[: len(content) - len(content.lstrip())]
    fixes_applied: list[str] = []

    # Parse current state
    from ..parser import parse_vault_metadata

    metadata, _ = parse_vault_metadata(content)
    doc_type = get_doc_type(doc_path, root_dir)

    # Fix 1 and 2: normalize tag prefixes, or construct tags from feature:
    new_tags, tags_changed, tag_fix = _normalized_tags(metadata, yaml_block, doc_type)
    if tag_fix:
        fixes_applied.append(tag_fix)

    # Fix 3: Date format normalization
    date_val, date_fixed = _normalized_date(metadata.date)
    if date_fixed:
        fixes_applied.append("normalized date format")

    if not fixes_applied:
        return None

    lines = _render_frontmatter_lines(
        metadata, new_tags, date_val, yaml_block, tags_changed=tags_changed
    )
    if body:
        lines.append(body)

    rendered = leading_whitespace + "\n".join(lines)
    # Restore the source file's newline convention. Internal LFs that
    # came from the body group also need promoting so the file does
    # not end up with mixed endings. ``atomic_write`` writes bytes
    # (via ``Path.write_bytes`` of the UTF-8-encoded payload), so the
    # ``\r\n`` sequences below land on disk byte-for-byte; switching to
    # ``Path.write_text`` would re-enable Python's universal-newline
    # translation on Windows and corrupt CRLF runs into ``\r\r\n``.
    new_content = (
        rendered if source_newline == "\n" else rendered.replace("\n", source_newline)
    )
    atomic_write(doc_path, new_content)
    return "; ".join(fixes_applied)


def check_frontmatter(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    feature: str | None = None,
    doc_type_filter: str | None = None,
    fix: bool = False,
) -> CheckResult:
    """Validate frontmatter of all vault documents.

    Enforces :meth:`~vaultspec_core.vaultcore.models.DocumentMetadata.validate`
    rules: at least two tags (one directory, one feature; extras allowed),
    valid ISO 8601 date, and ``[[wiki-link]]`` format for ``related`` entries.

    Args:
        root_dir: Project root directory.
        snapshot: Pre-built snapshot mapping document paths to parsed data.
        feature: Restrict checks to documents with this feature tag
            (without ``#``).
        doc_type_filter: Restrict checks to documents of this type
            (e.g. ``"adr"``).
        fix: When ``True``, attempt to auto-correct tag prefixes,
            reconstruct tags from a bare ``feature:`` field, and
            normalize date formats.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"frontmatter"``.
    """
    from ..parser import parse_vault_metadata
    from ..scanner import get_doc_type

    result = CheckResult(check_name="frontmatter", supports_fix=True)

    for doc_path, (metadata, _body) in snapshot.items():
        # Indexes used to carry a non-standard one-tag frontmatter and
        # were exempted here; post-#91 they carry the standard two-tag
        # shape (``#index`` directory tag plus the feature tag) and run
        # through the same validator as every other document. The ADR
        # commits to "no more exemptions" at the frontmatter layer.
        if doc_type_filter:
            dt = get_doc_type(doc_path, root_dir)
            if dt and dt.value != doc_type_filter:
                continue

        if feature:
            feat = feature.lstrip("#")
            if feat not in extract_feature_tags(metadata.tags):
                continue

        errors = metadata.validate()
        if not errors:
            continue

        rel_path = doc_path.relative_to(root_dir)

        if fix:
            fix_desc = _fix_frontmatter(doc_path, root_dir)
            if fix_desc:
                result.fixed_count += 1
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message=f"Fixed: {fix_desc}",
                        severity=Severity.INFO,
                    )
                )
                new_content = doc_path.read_text(encoding="utf-8")
                new_metadata, _ = parse_vault_metadata(new_content)
                remaining_errors = new_metadata.validate()
                for msg in remaining_errors:
                    severity = (
                        Severity.ERROR
                        if "required" in msg.lower()
                        else Severity.WARNING
                    )
                    result.diagnostics.append(
                        CheckDiagnostic(
                            path=rel_path,
                            message=msg,
                            severity=severity,
                        )
                    )
                continue

        for msg in errors:
            severity = Severity.ERROR if "required" in msg.lower() else Severity.WARNING
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=msg,
                    severity=severity,
                    fixable=True,
                )
            )

    return result
