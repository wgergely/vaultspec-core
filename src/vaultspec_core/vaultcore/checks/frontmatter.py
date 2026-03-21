"""Check and optionally fix vault document frontmatter.

Validates every document against DocumentMetadata.validate() rules:
- At least 2 tags (one directory tag, one feature tag; extra tags allowed)
- Valid date format (YYYY-MM-DD)
- Valid related link format ([[wiki-link]])
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_frontmatter"]


def _fix_frontmatter(doc_path: Path, root_dir: Path) -> str | None:
    """Attempt to fix common frontmatter issues. Returns fix description or None."""
    from ..scanner import get_doc_type

    try:
        content = doc_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content.lstrip(), re.DOTALL)
    if not match:
        return None

    yaml_block = match.group(1)
    body = match.group(2)
    leading_whitespace = content[: len(content) - len(content.lstrip())]
    fixes_applied = []

    # Parse current state
    from ..parser import parse_vault_metadata

    metadata, _ = parse_vault_metadata(content)
    doc_type = get_doc_type(doc_path, root_dir)

    # Fix 1: Normalize tags
    new_tags = []
    tags_changed = False
    for tag in metadata.tags:
        if not tag.startswith("#"):
            new_tags.append(f"#{tag}")
            tags_changed = True
        else:
            new_tags.append(tag)

    # Fix 2: If no tags but has feature: field, construct tags
    if not metadata.tags:
        feature_match = re.search(r"^feature:\s*(.+)$", yaml_block, re.MULTILINE)
        if feature_match and doc_type:
            feature_val = feature_match.group(1).strip().strip("\"'")
            if not feature_val.startswith("#"):
                feature_val = f"#{feature_val}"
            new_tags = [doc_type.tag, feature_val]
            tags_changed = True
            fixes_applied.append("constructed tags from feature field")

    if tags_changed and not fixes_applied:
        fixes_applied.append("normalized tag # prefixes")

    # Fix 3: Date format normalization
    date_val = metadata.date
    if date_val:
        date_str = str(date_val).strip()
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", date_str)
        if date_match and date_str != date_match.group(1):
            date_val = date_match.group(1)
            fixes_applied.append("normalized date format")

    if not fixes_applied:
        return None

    # Rebuild frontmatter
    lines = ["---"]
    if new_tags or tags_changed:
        lines.append("tags:")
        for tag in new_tags if new_tags else metadata.tags:
            lines.append(f'  - "{tag}"')
    else:
        for line in yaml_block.split("\n"):
            stripped = line.strip()
            if stripped.startswith("tags") or (
                stripped.startswith("-") and "#" in stripped
            ):
                lines.append(line)

    if date_val:
        lines.append(f"date: {date_val}")
    elif metadata.date:
        lines.append(f"date: {metadata.date}")

    if metadata.related:
        lines.append("related:")
        for link in metadata.related:
            lines.append(f'  - "{link}"')

    known_keys = {"tags", "date", "related", "feature"}
    for line in yaml_block.split("\n"):
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith("-"):
            key = stripped.split(":", 1)[0].strip()
            if key not in known_keys:
                lines.append(line)

    lines.append("---")
    if body:
        lines.append(body)

    new_content = leading_whitespace + "\n".join(lines)
    doc_path.write_text(new_content, encoding="utf-8")
    return "; ".join(fixes_applied)


def check_frontmatter(
    root_dir: Path,
    *,
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
    from ..scanner import get_doc_type, scan_vault

    result = CheckResult(check_name="frontmatter", supports_fix=True)

    for doc_path in scan_vault(root_dir):
        if doc_type_filter:
            dt = get_doc_type(doc_path, root_dir)
            if dt and dt.value != doc_type_filter:
                continue

        try:
            content = doc_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        metadata, _ = parse_vault_metadata(content)

        if feature:
            from ..models import DocType

            feat = feature.lstrip("#")
            type_values = {d.value for d in DocType}
            feature_tags = [
                t.lstrip("#") for t in metadata.tags if t.lstrip("#") not in type_values
            ]
            if feat not in feature_tags:
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
                    fix_description="Run with --fix to attempt auto-correction",
                )
            )

    return result
