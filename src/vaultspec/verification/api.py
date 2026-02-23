"""Vault document verification, integrity checking, and auto-repair."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ..vaultcore import (
    DocType,
    DocumentMetadata,
    VaultConstants,
    get_doc_type,
    parse_vault_metadata,
    scan_vault,
)

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)

__all__ = [
    "FixResult",
    "VerificationError",
    "fix_violations",
    "get_malformed",
    "list_features",
    "verify_file",
    "verify_vault_structure",
    "verify_vertical_integrity",
]


class VerificationError:
    """A single vault verification failure tied to a file path.

    Attributes:
        path: The file (or directory) where the violation was detected.
        message: Human-readable description of the violation.
    """

    def __init__(self, path: pathlib.Path, message: str) -> None:
        """Initialise a VerificationError.

        Args:
            path: Path associated with the violation.
            message: Description of what went wrong.
        """
        self.path = path
        self.message = message

    def __str__(self) -> str:
        """Return a concise string representation for display."""
        return f"{self.path}: {self.message}"


def verify_vault_structure(root_dir: pathlib.Path) -> list[VerificationError]:
    """Check for unsupported directories and stray files in the docs root.

    Args:
        root_dir: Project root containing the docs directory.

    Returns:
        List of ``VerificationError`` objects for each structural violation.
    """
    from ..config import get_config

    logger.info("Verifying vault structure at %s", root_dir)
    errors = VaultConstants.validate_vault_structure(root_dir)
    if errors:
        logger.warning("Found %d structural violations", len(errors))
    else:
        logger.debug("Vault structure validation passed")
    return [VerificationError(root_dir / get_config().docs_dir, e) for e in errors]


def verify_file(path: pathlib.Path, root_dir: pathlib.Path) -> list[VerificationError]:
    """Run all verification checks against a single vault document.

    Validates the filename pattern, YAML frontmatter schema, and that the
    mandatory directory tag is present.

    Args:
        path: Absolute path to the vault document.
        root_dir: Project root used to infer the document's ``DocType``.

    Returns:
        List of ``VerificationError`` objects; empty when the file is valid.
    """
    errors = []
    doc_type = get_doc_type(path, root_dir)

    # Validate Filename
    filename_errors = VaultConstants.validate_filename(path.name, doc_type)
    for err in filename_errors:
        errors.append(VerificationError(path, err))

    # Validate Content
    try:
        content = path.read_text(encoding="utf-8")
        metadata, _ = parse_vault_metadata(content)
        content_errors = metadata.validate()

        if doc_type:
            dir_tag = doc_type.tag
            if dir_tag not in metadata.tags:
                msg = (
                    f"Vault violation: Missing mandatory directory tag '{dir_tag}' "
                    f"for file in {doc_type.value}/ directory."
                )
                content_errors.append(msg)

        for err in content_errors:
            errors.append(VerificationError(path, err))
    except Exception as e:
        logger.error("Verification failed for %s", path, exc_info=True)
        errors.append(VerificationError(path, f"Error reading/parsing: {e}"))

    return errors


def get_malformed(root_dir: pathlib.Path) -> list[VerificationError]:
    """Return all vault documents and structural issues that fail verification.

    Combines structural checks with per-file verification across the entire
    vault.

    Args:
        root_dir: Project root containing the docs directory.

    Returns:
        Aggregated list of ``VerificationError`` objects.
    """
    logger.info("Starting comprehensive vault verification")
    all_errors = verify_vault_structure(root_dir)
    file_count = 0
    for path in scan_vault(root_dir):
        file_count += 1
        all_errors.extend(verify_file(path, root_dir))
    logger.info(
        "Vault verification complete: scanned %d files, found %d errors",
        file_count,
        len(all_errors),
    )
    return all_errors


def list_features(root_dir: pathlib.Path) -> set[str]:
    """Infer the set of feature names from tags across all vault documents.

    Args:
        root_dir: Project root containing the docs directory.

    Returns:
        Set of feature name strings (without the leading ``#``).
    """
    logger.debug("Extracting features from vault")
    features = set()
    skip_count = 0
    for path in scan_vault(root_dir):
        try:
            content = path.read_text(encoding="utf-8")
            metadata, _ = parse_vault_metadata(content)
            for tag in metadata.tags:
                if not DocType.from_tag(tag):
                    # It's a feature tag
                    features.add(tag.lstrip("#"))
        except (OSError, UnicodeDecodeError):
            skip_count += 1
            logger.warning("Failed to read feature tags from %s", path.name)
            continue
    logger.info(
        "Feature extraction complete: found %d features, skipped %d files",
        len(features),
        skip_count,
    )
    return features


def verify_vertical_integrity(root_dir: pathlib.Path) -> list[VerificationError]:
    """Ensure every feature tag used in the vault has a corresponding plan document.

    Args:
        root_dir: Project root containing the docs directory.

    Returns:
        List of ``VerificationError`` objects for features missing a plan; empty
        when all features are accounted for.
    """
    logger.info("Verifying vertical integrity: feature -> plan mapping")
    features_found = set()
    planned_features = set()
    errors = []

    for path in scan_vault(root_dir):
        try:
            content = path.read_text(encoding="utf-8")
            metadata, _ = parse_vault_metadata(content)

            doc_features = [
                t.lstrip("#") for t in metadata.tags if not DocType.from_tag(t)
            ]
            features_found.update(doc_features)

            doc_type = get_doc_type(path, root_dir)
            if doc_type == DocType.PLAN:
                planned_features.update(doc_features)
        except (OSError, UnicodeDecodeError):
            logger.warning("Failed to parse vertical integrity from %s", path.name)
            continue

    from ..config import get_config

    missing_plans = features_found - planned_features
    for feature in sorted(missing_plans):
        errors.append(
            VerificationError(
                root_dir / get_config().docs_dir / "plan",
                f"Integrity violation: Feature '#{feature}' is "
                "missing a master plan document.",
            )
        )

    logger.info(
        "Vertical integrity check: %d features found, %d plans, %d missing",
        len(features_found),
        len(planned_features),
        len(missing_plans),
    )
    if errors:
        logger.warning("Found %d integrity violations", len(errors))
    return errors


@dataclass
class FixResult:
    """Result of a single auto-repair operation applied to a vault document.

    Attributes:
        path: Path of the file that was modified or renamed.
        action: Short identifier for the fix type (e.g. ``add_date``,
            ``rename_suffix``).
        detail: Human-readable description of what was changed.
    """

    path: pathlib.Path
    action: str
    detail: str

    def __str__(self) -> str:
        """Return a concise string representation for display."""
        return f"{self.path}: {self.action} - {self.detail}"


def fix_violations(root_dir: pathlib.Path) -> list[FixResult]:
    """Auto-repair common vault violations.

    Fixes:
    - Missing doc_type in frontmatter (infer from directory)
    - Missing tags in frontmatter (add empty list)
    - Wrong filename suffix (rename to match doc_type)
    - Missing date prefix (prepend today's date)

    Args:
        root_dir: Project root directory containing the ``.vault/`` subtree.

    Returns:
        List of FixResult objects describing what was repaired.
    """
    logger.info("Starting auto-repair of vault violations")
    results = []
    today = datetime.now().strftime("%Y-%m-%d")

    for path in scan_vault(root_dir):
        try:
            content = path.read_text(encoding="utf-8")
            # Remove BOM if present
            content = content.lstrip("\ufeff")
            metadata, body = parse_vault_metadata(content)
            doc_type = get_doc_type(path, root_dir)

            modified = False

            # Fix 1: Missing tags field entirely
            if not metadata.tags and doc_type:
                modified = True
                results.append(
                    FixResult(
                        path,
                        "add_tags",
                        f"Added tags: [{doc_type.tag}]",
                    )
                )

            # Fix 2: Missing doc_type tag in frontmatter
            if doc_type:
                dir_tag = doc_type.tag
                if dir_tag not in metadata.tags:
                    metadata.tags.insert(0, dir_tag)
                    modified = True
                    results.append(
                        FixResult(
                            path,
                            "add_doc_type_tag",
                            f"Added directory tag '{dir_tag}'",
                        )
                    )

            # Fix 3: Ensure exactly 2 tags (add empty feature if needed)
            if len(metadata.tags) == 1 and doc_type:
                # Only has dir tag, add placeholder feature
                feature_name = "uncategorized"
                metadata.tags.append(f"#{feature_name}")
                modified = True
                results.append(
                    FixResult(
                        path,
                        "add_feature_tag",
                        f"Added placeholder feature tag '#{feature_name}'",
                    )
                )

            # Fix 4: Missing date field
            if not metadata.date:
                metadata.date = today
                modified = True
                results.append(
                    FixResult(path, "add_date", f"Added date field: {today}")
                )

            # Write updated frontmatter if modified
            if modified:
                new_content = _rebuild_frontmatter(metadata, body)
                # Write without BOM
                path.write_text(new_content, encoding="utf-8")
                logger.info("Updated frontmatter in %s", path.name)

            # Fix 5: Wrong filename suffix
            if doc_type:
                filename = path.name
                expected_suffix = f"-{doc_type.value}.md"

                # Check if filename has correct suffix
                needs_rename = False

                if doc_type == DocType.EXEC:
                    # Exec files can have phase/step suffixes
                    if f"-{DocType.EXEC.value}" not in filename:
                        needs_rename = True
                else:
                    # Other types need exact suffix
                    if not filename.endswith(expected_suffix):
                        needs_rename = True

                if needs_rename:
                    # Extract base name and rebuild
                    # Pattern: yyyy-mm-dd-<feature>-<old-suffix>.md
                    match = re.match(
                        r"^(\d{4}-\d{2}-\d{2}-.+?)(?:-(?:adr|audit|"
                        r"exec|plan|reference|research).*)?\.md$",
                        filename,
                    )
                    if match:
                        base = match.group(1)
                        new_filename = f"{base}{expected_suffix}"
                        new_path = path.parent / new_filename

                        if not new_path.exists():
                            path.rename(new_path)
                            results.append(
                                FixResult(
                                    path,
                                    "rename_suffix",
                                    f"Renamed to {new_filename}",
                                )
                            )
                            logger.info("Renamed %s -> %s", filename, new_filename)
                            path = new_path
                        else:
                            logger.warning("Cannot rename %s: target exists", filename)

            # Fix 6: Missing date prefix
            filename = path.name
            if not re.match(r"^\d{4}-\d{2}-\d{2}-", filename):
                # Prepend today's date
                new_filename = f"{today}-{filename}"
                new_path = path.parent / new_filename

                if not new_path.exists():
                    path.rename(new_path)
                    results.append(
                        FixResult(
                            path,
                            "add_date_prefix",
                            f"Renamed to {new_filename}",
                        )
                    )
                    logger.info("Renamed %s -> %s", filename, new_filename)
                else:
                    logger.warning("Cannot rename %s: target exists", filename)

        except Exception as e:
            logger.error("Failed to fix %s: %s", path, e, exc_info=True)
            continue

    logger.info("Auto-repair complete: performed %d fixes", len(results))
    return results


def _rebuild_frontmatter(metadata: DocumentMetadata, body: str) -> str:
    """Rebuild markdown content from updated metadata and original body.

    Serialises ``metadata`` back to a YAML ``---`` fence and prepends it
    to ``body``.

    Args:
        metadata: Updated ``DocumentMetadata`` to serialise.
        body: Markdown body text (everything after the original closing ``---``).

    Returns:
        Full markdown string with refreshed frontmatter.
    """
    lines = ["---"]

    # Tags
    if metadata.tags:
        lines.append("tags:")
        for tag in metadata.tags:
            lines.append(f'  - "{tag}"')

    # Date
    if metadata.date:
        lines.append(f"date: {metadata.date}")

    # Related
    if metadata.related:
        lines.append("related:")
        for link in metadata.related:
            lines.append(f'  - "{link}"')

    lines.append("---")
    lines.append("")

    return "\n".join(lines) + body
