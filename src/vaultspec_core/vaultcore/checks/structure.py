"""Check vault directory structure and filename conventions.

Wraps VaultConstants.validate_vault_structure() and validate_filename()
which exist but were never wired to a CLI command.  With ``--fix``,
renames files that have wrong suffixes or missing date prefixes.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
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

__all__ = ["check_structure"]

logger = logging.getLogger(__name__)


def _fix_filename(doc_path: Path, root_dir: Path, result: CheckResult) -> None:
    """Attempt to fix filename issues: wrong suffix, missing date prefix."""
    from ..models import DocType
    from ..scanner import get_doc_type

    doc_type = get_doc_type(doc_path, root_dir)
    if not doc_type:
        return

    filename = doc_path.name
    rel = doc_path.relative_to(root_dir)

    expected_suffix = f"-{doc_type.value}.md"
    needs_rename = False

    if doc_type == DocType.EXEC:
        if f"-{DocType.EXEC.value}" not in filename:
            needs_rename = True
    else:
        if not filename.endswith(expected_suffix):
            needs_rename = True

    if needs_rename:
        match = re.match(
            r"^(\d{4}-\d{2}-\d{2}-.+?)(?:-(?:adr|audit|"
            r"exec|plan|reference|research).*)?\.md$",
            filename,
        )
        if match:
            base = match.group(1)
            new_filename = f"{base}{expected_suffix}"
            new_path = doc_path.parent / new_filename

            if not new_path.exists():
                doc_path.rename(new_path)
                result.fixed_count += 1
                doc_path = new_path
                rel = doc_path.relative_to(root_dir)
                filename = new_filename
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel,
                        message=f"Fixed: renamed to {new_filename}",
                        severity=Severity.INFO,
                    )
                )
                logger.info("Renamed %s -> %s", filename, new_filename)
            else:
                logger.warning("Cannot rename %s: target exists", filename)
                return

    if not re.match(r"^\d{4}-\d{2}-\d{2}-", filename):
        today = datetime.now().strftime("%Y-%m-%d")
        new_filename = f"{today}-{filename}"
        new_path = doc_path.parent / new_filename

        if not new_path.exists():
            doc_path.rename(new_path)
            result.fixed_count += 1
            rel = new_path.relative_to(root_dir)
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel,
                    message=f"Fixed: renamed to {new_filename}",
                    severity=Severity.INFO,
                )
            )
            logger.info("Renamed %s -> %s", filename, new_filename)
        else:
            logger.warning("Cannot rename %s: target exists", filename)


def check_structure(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    fix: bool = False,
) -> CheckResult:
    """Check vault directory structure and filename conventions.

    Detects unsupported subdirectories in ``.vault/``, files placed directly
    in the ``.vault/`` root, and filenames deviating from the
    ``YYYY-MM-DD-<feature>-<type>.md`` convention.

    Args:
        root_dir: Project root directory.
        snapshot: Pre-built snapshot mapping document paths to parsed data.
        fix: When ``True``, renames files with wrong type suffixes or
            missing date prefixes.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"structure"``.
    """
    from ..models import VaultConstants
    from ..scanner import get_doc_type

    result = CheckResult(check_name="structure", supports_fix=True)

    for msg in VaultConstants.validate_vault_structure(root_dir):
        result.diagnostics.append(
            CheckDiagnostic(
                path=None,
                message=msg,
                severity=Severity.ERROR,
            )
        )

    for doc_path in snapshot:
        # Skip generated index files (non-standard naming convention)
        if is_generated_index(doc_path):
            continue

        doc_type = get_doc_type(doc_path, root_dir)
        errors = VaultConstants.validate_filename(doc_path.name, doc_type)

        if errors and fix:
            _fix_filename(doc_path, root_dir, result)
            if doc_path.exists():
                remaining = VaultConstants.validate_filename(doc_path.name, doc_type)
                for msg in remaining:
                    result.diagnostics.append(
                        CheckDiagnostic(
                            path=doc_path.relative_to(root_dir),
                            message=msg,
                            severity=Severity.WARNING,
                        )
                    )
        else:
            for msg in errors:
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=doc_path.relative_to(root_dir),
                        message=msg,
                        severity=Severity.WARNING,
                        fixable=True,
                        fix_description="Run with --fix to attempt auto-rename",
                    )
                )

    return result
