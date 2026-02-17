from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vault.models import DocType, VaultConstants
from vault.parser import parse_vault_metadata
from vault.scanner import get_doc_type, scan_vault

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)


class VerificationError:
    """A single vault verification failure tied to a file path."""

    def __init__(self, path: pathlib.Path, message: str) -> None:
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def verify_vault_structure(root_dir: pathlib.Path) -> list[VerificationError]:
    """Checks for unsupported directories and files in .vault/ root."""
    from core.config import get_config

    logger.info("Verifying vault structure at %s", root_dir)
    errors = VaultConstants.validate_vault_structure(root_dir)
    if errors:
        logger.warning("Found %d structural violations", len(errors))
    else:
        logger.debug("Vault structure validation passed")
    return [VerificationError(root_dir / get_config().docs_dir, e) for e in errors]


def verify_file(path: pathlib.Path, root_dir: pathlib.Path) -> list[VerificationError]:
    """Performs all checks on a single file."""
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
    """Returns all documents that fail verification."""
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
    """Infers features from tags across all documents."""
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
            logger.debug("Failed to read feature tags from %s", path.name)
            continue
    logger.info(
        "Feature extraction complete: found %d features, skipped %d files",
        len(features),
        skip_count,
    )
    return features


def verify_vertical_integrity(root_dir: pathlib.Path) -> list[VerificationError]:
    """Ensures every feature used has a corresponding plan doc."""
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
            logger.debug("Failed to parse vertical integrity from %s", path.name)
            continue

    from core.config import get_config

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
