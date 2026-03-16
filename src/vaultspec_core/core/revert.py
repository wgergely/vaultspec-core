"""Revert mechanism for builtin firmware resources.

Builtin resources (files ending in .builtin.md) are snapshotted during install.
Revert restores the original snapshot content, discarding local edits.
Custom resources cannot be reverted — they have no canonical original.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_BUILTIN_SUFFIX = ".builtin.md"
_SNAPSHOT_DIR = "_snapshots"


def is_builtin(filename: str) -> bool:
    """Check if a filename represents a builtin resource."""
    return filename.endswith(_BUILTIN_SUFFIX)


def snapshot_builtins(vaultspec_dir: Path) -> int:
    """Snapshot all .builtin.md files from .vaultspec/rules/ into _snapshots/.

    Called during install to capture the pristine state. Overwrites any
    existing snapshots.

    Args:
        vaultspec_dir: The .vaultspec directory.

    Returns:
        Number of files snapshotted.
    """
    rules_dir = vaultspec_dir / "rules"
    snapshot_dir = vaultspec_dir / _SNAPSHOT_DIR

    if not rules_dir.exists():
        return 0

    count = 0
    for builtin in rules_dir.rglob(f"*{_BUILTIN_SUFFIX}"):
        rel = builtin.relative_to(rules_dir)
        dest = snapshot_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(builtin), str(dest))
        count += 1
        logger.debug("Snapshotted %s", rel)

    return count


def get_snapshot_content(
    vaultspec_dir: Path, category: str, filename: str
) -> str | None:
    """Retrieve the snapshotted content of a builtin resource.

    Args:
        vaultspec_dir: The .vaultspec directory.
        category: Subdirectory under rules/ (e.g., "rules", "skills", "agents").
        filename: The builtin filename.

    Returns:
        Original content string, or None if no snapshot exists.
    """
    snapshot_path = vaultspec_dir / _SNAPSHOT_DIR / category / filename
    if not snapshot_path.exists():
        return None
    try:
        return snapshot_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read snapshot %s: %s", snapshot_path, e)
        return None


def revert_resource(vaultspec_dir: Path, category: str, filename: str) -> dict:
    """Revert a resource to its snapshotted original.

    Args:
        vaultspec_dir: The .vaultspec directory.
        category: Subdirectory under rules/ (e.g., "rules", "skills", "agents").
        filename: The resource filename (must end in .builtin.md).

    Returns:
        Dict with "reverted" (bool) and "reason" (str).
    """
    if not is_builtin(filename):
        return {
            "reverted": False,
            "reason": "Not a builtin resource. Only .builtin.md files can be reverted.",
        }

    original = get_snapshot_content(vaultspec_dir, category, filename)
    if original is None:
        return {
            "reverted": False,
            "reason": f"No snapshot found for {category}/{filename}. Was install run?",
        }

    target = vaultspec_dir / "rules" / category / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(original, encoding="utf-8")
    logger.info("Reverted %s/%s to snapshot original.", category, filename)
    return {"reverted": True, "reason": "Restored to install snapshot."}


def list_modified_builtins(vaultspec_dir: Path) -> list[dict]:
    """List builtin resources that differ from their snapshots.

    Returns list of dicts with keys: category, filename,
    status ("modified", "missing", "ok").
    """
    snapshot_dir = vaultspec_dir / _SNAPSHOT_DIR
    rules_dir = vaultspec_dir / "rules"
    results = []

    if not snapshot_dir.exists():
        return results

    for snapshot in snapshot_dir.rglob(f"*{_BUILTIN_SUFFIX}"):
        rel = snapshot.relative_to(snapshot_dir)
        category = rel.parts[0] if len(rel.parts) > 1 else ""
        current = rules_dir / rel

        if not current.exists():
            status = "missing"
        else:
            try:
                snap_content = snapshot.read_text(encoding="utf-8")
                curr_content = current.read_text(encoding="utf-8")
                status = "modified" if snap_content != curr_content else "ok"
            except (OSError, UnicodeDecodeError):
                status = "modified"

        results.append(
            {
                "category": category,
                "filename": rel.name,
                "path": str(rel),
                "status": status,
            }
        )

    return results
