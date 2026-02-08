from __future__ import annotations

from typing import TYPE_CHECKING

from vault.models import DocType, VaultConstants
from vault.parser import parse_vault_metadata
from vault.scanner import get_doc_type, scan_vault

if TYPE_CHECKING:
    import pathlib


class VerificationError:
    def __init__(self, path: pathlib.Path, message: str):
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def verify_vault_structure(root_dir: pathlib.Path) -> list[VerificationError]:
    """Checks for unsupported directories and files in .docs/ root."""
    errors = VaultConstants.validate_vault_structure(root_dir)
    return [VerificationError(root_dir / VaultConstants.DOCS_DIR, e) for e in errors]


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
        errors.append(VerificationError(path, f"Error reading/parsing: {e}"))

    return errors


def get_malformed(root_dir: pathlib.Path) -> list[VerificationError]:
    """Returns all documents that fail verification."""
    all_errors = verify_vault_structure(root_dir)
    for path in scan_vault(root_dir):
        all_errors.extend(verify_file(path, root_dir))
    return all_errors


def list_features(root_dir: pathlib.Path) -> set[str]:
    """Infers features from tags across all documents."""
    features = set()
    for path in scan_vault(root_dir):
        try:
            content = path.read_text(encoding="utf-8")
            metadata, _ = parse_vault_metadata(content)
            for tag in metadata.tags:
                if not DocType.from_tag(tag):
                    # It's a feature tag
                    features.add(tag.lstrip("#"))
        except Exception:
            continue
    return features


def verify_vertical_integrity(root_dir: pathlib.Path) -> list[VerificationError]:
    """Ensures every feature used has a corresponding plan doc."""
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
        except Exception:
            continue

    missing_plans = features_found - planned_features
    for feature in sorted(missing_plans):
        errors.append(
            VerificationError(
                root_dir / VaultConstants.DOCS_DIR / "plan",
                f"Integrity violation: Feature '#{feature}' is "
                "missing a master plan document.",
            )
        )

    return errors
