"""Define the core domain model for `.vault/` documents and metadata.

This module captures document types, frontmatter structure, tag constraints,
filename validation, and related structural rules. It is the semantic heart of
the vault model on which parsing, scanning, verification, and higher-level
analysis depend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

__all__ = ["DocType", "DocumentMetadata", "VaultConstants"]

if TYPE_CHECKING:
    from pathlib import Path


class DocType(StrEnum):
    """Rigidly defined document types corresponding to .vault/ subdirectories."""

    ADR = "adr"
    AUDIT = "audit"
    EXEC = "exec"
    PLAN = "plan"
    REFERENCE = "reference"
    RESEARCH = "research"

    @property
    def tag(self) -> str:
        """The mandatory directory tag associated with this type.

        Returns:
            Hashtag string such as ``#adr`` or ``#exec``.
        """
        return f"#{self.value}"

    @classmethod
    def from_tag(cls, tag: str) -> DocType | None:
        """Return the DocType that owns the given ``#tag`` string.

        Args:
            tag: Hashtag string such as ``#adr`` or ``#exec``.

        Returns:
            Matching ``DocType``, or ``None`` if the tag is not recognised.
        """
        for dt in cls:
            if dt.tag == tag:
                return dt
        return None


@dataclass
class DocumentMetadata:
    """Rigid representation of YAML frontmatter for all .vault/ files.

    Attributes:
        tags: Exactly two tags — one directory tag and one feature tag.
        date: ISO 8601 creation date (``YYYY-MM-DD``).
        related: List of Obsidian-style ``[[wiki-link]]`` strings.
    """

    tags: list[str] = field(default_factory=list)
    date: str | None = None
    related: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Validate the metadata against the vault schema rules.

        Returns:
            A list of human-readable violation messages; empty list means valid.
        """
        errors = []

        #  The "Rule of Two" for Tags
        if len(self.tags) != 2:
            msg = f"Vault violation: Exactly 2 tags required, found {len(self.tags)}"
            errors.append(msg)

        #  Directory Tag (Type)
        dir_tags = [t for t in self.tags if DocType.from_tag(t)]
        if len(dir_tags) != 1:
            msg = (
                "Vault violation: Exactly one directory tag required "
                "(#adr, #audit, #exec, #plan, #reference, #research). "
                f"Found: {dir_tags}"
            )
            errors.append(msg)

        #  Feature Tag (Kind)
        feature_tags = [t for t in self.tags if not DocType.from_tag(t)]
        if len(feature_tags) != 1:
            msg = (
                "Vault violation: Exactly one feature tag (#<feature>) required. "
                f"Found: {feature_tags}"
            )
            errors.append(msg)
        elif feature_tags and not re.match(r"^#[a-z0-9-]+$", feature_tags[0]):
            msg = (
                f"Vault violation: Invalid feature tag format '{feature_tags[0]}'. "
                "Must be kebab-case (e.g., #editor-demo)."
            )
            errors.append(msg)

        #  Date Format
        if not self.date:
            errors.append("Vault violation: 'date' field is required.")
        elif not re.match(r"^\d{4}-\d{2}-\d{2}$", self.date):
            msg = (
                f"Vault violation: Invalid date format '{self.date}'. "
                "Must be YYYY-MM-DD."
            )
            errors.append(msg)

        #  Related Wiki-links
        for link in self.related:
            if not (link.startswith("[[") and link.endswith("]]")):
                msg = (
                    f"Vault violation: Invalid related link '{link}'. "
                    "Must be a quoted [[wiki-link]]."
                )
                errors.append(msg)

        return errors


class VaultConstants:
    """Central configuration for the .vault vault structure."""

    @staticmethod
    def _get_docs_dir() -> str:
        """Return the configured docs directory name (e.g. ``.vault``).

        Returns:
            Directory name string such as ``".vault"``.
        """
        from ..config import get_config

        return get_config().docs_dir

    # Supported directories within .vault/
    SUPPORTED_DIRECTORIES: ClassVar[set[str]] = {dt.value for dt in DocType}

    # Supported directory tags
    SUPPORTED_TAGS: ClassVar[set[str]] = {dt.tag for dt in DocType}

    @classmethod
    def is_supported_directory(cls, dirname: str) -> bool:
        """Return whether *dirname* is a recognized vault subdirectory.

        Args:
            dirname: Bare directory name (e.g. ``"adr"``, ``"exec"``).

        Returns:
            ``True`` if the directory is in ``SUPPORTED_DIRECTORIES``.
        """
        return dirname in cls.SUPPORTED_DIRECTORIES

    @classmethod
    def get_tag_for_directory(cls, dirname: str) -> str | None:
        """Return the ``#tag`` for a directory name, or ``None`` if unsupported.

        Args:
            dirname: Bare directory name (e.g. ``"adr"``, ``"plan"``).

        Returns:
            Hashtag string such as ``"#adr"``, or ``None`` if not recognised.
        """
        try:
            return DocType(dirname).tag
        except ValueError:
            return None

    @classmethod
    def validate_vault_structure(cls, root_dir: Path) -> list[str]:
        """Ensure the docs directory only contains recognised subdirectories.

        Args:
            root_dir: Project root containing the docs directory.

        Returns:
            List of violation message strings; empty when the structure is valid.
        """
        docs_dir_name = cls._get_docs_dir()
        docs_dir = root_dir / docs_dir_name
        if not docs_dir.exists():
            return []

        errors = []
        # Check for unsupported directories
        for item in docs_dir.iterdir():
            if item.is_dir():
                if item.name.startswith("."):
                    # Allow internal hidden folders like .obsidian
                    continue
                if not cls.is_supported_directory(item.name):
                    msg = (
                        "Vault violation: Unsupported directory found in "
                        f"{docs_dir_name}/: '{item.name}'"
                    )
                    errors.append(msg)
            elif item.is_file():
                # Usually we don't expect files in the root of .vault/
                if item.name.lower() != "readme.md":
                    msg = (
                        f"Vault violation: File found in {docs_dir_name}/ root: "
                        f"'{item.name}'. Files should be in subdirectories."
                    )
                    errors.append(msg)

        return errors

    @classmethod
    def validate_filename(
        cls, filename: str, doc_type: DocType | None = None
    ) -> list[str]:
        """Validate a filename against the vault naming convention.

        Expected pattern: ``yyyy-mm-dd-<feature>-<type>.md``.

        Args:
            filename: Bare filename (no directory component) to validate.
            doc_type: When provided, also checks that the filename's type
                suffix matches this ``DocType``.

        Returns:
            List of violation message strings; empty when the filename is valid.
        """
        errors = []

        if not filename.endswith(".md"):
            msg = f"Vault violation: Filename '{filename}' must have .md extension."
            errors.append(msg)
            return errors

        # Basic pattern: 2026-02-07-feature-name-adr.md
        # Or for exec: 2026-02-07-feature-name-phase1-step1.md
        pattern = (
            r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+-"
            r"(adr|audit|exec|plan|reference|research)(-[a-z0-9-]+)*\.md$"
        )
        if not re.match(pattern, filename):
            msg = (
                f"Vault violation: Filename '{filename}' deviates from "
                "standard yyyy-mm-dd-<feature>-<type>.md pattern."
            )
            errors.append(msg)
            return errors

        # If doc_type is provided, ensure it matches the filename suffix
        if doc_type:
            suffix = f"-{doc_type.value}"
            # Special case for exec records
            if doc_type == DocType.EXEC:
                if f"-{DocType.EXEC.value}" not in filename:
                    msg = (
                        f"Vault violation: Filename '{filename}' does not "
                        "contain expected type suffix '-exec'."
                    )
                    errors.append(msg)
            else:
                if not filename.endswith(f"{suffix}.md"):
                    msg = (
                        f"Vault violation: Filename '{filename}' does not "
                        f"match expected type suffix '{suffix}.md'."
                    )
                    errors.append(msg)

        return errors
