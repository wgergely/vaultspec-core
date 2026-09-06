"""Surface exec-folder feature drift left behind by a partial rename.

The framework names every execution-record folder after the feature it
belongs to: ``.vault/exec/{plan_date}-{feature}/``. A feature rename
(``vaultspec-core vault feature rename``) renames that folder and rewrites
every record's ``#feature`` tag together, so a fully-converged vault always
agrees on the feature between an exec folder's name and the tags of the
records inside it. A partial or hand-edited rename breaks that agreement - the
records carry one ``#feature`` tag while the folder still spells another -
which silently strands the records: a feature listing, index, or subsequent
rename keys off the tag and no longer reaches the misnamed folder.

This checker walks the exec tree directly (mirroring ``scan_vault``'s
exclusions: ``.obsidian``/``_archive`` subtrees and symlinks are skipped) and
reports each exec folder whose feature segment disagrees with the ``#feature``
tag of the records it contains, as an ``ERROR`` carrying the observed-vs-
expected names and a descriptive remediation hint (reconcile the folder name
and the records' tag so they agree). The hint is deliberately not a runnable
``vault feature rename`` command: on this drift class that command errors in
both directions (the folder feature has zero matching tagged docs, and the tag
feature's docs do not all live under a single folder of that shape). It is
read-only: reconciling the drift is a feature rename, not a frontmatter
rewrite, and which side is canonical (folder vs tag) is a deliberate operator
decision the cli-rename-integrity ADR defers.

Scope - what this checker deliberately does NOT do:

- It does NOT check authored-document (adr/audit/plan/reference/research)
  filename feature-segment against the ``#feature`` tag. Authored filenames in
  a real vault legitimately use a narrative topic segment distinct from the
  feature tag (e.g. an ADR whose filename carries a narrative topic
  segment such as an environment-variable slug while it is tagged
  ``#framework``), so ``filename-segment == tag`` is not an invariant. A
  genuinely rename-drifted authored doc is structurally indistinguishable from
  a legitimately narrative-named one without rename history, so flagging it
  would be a false positive on a clean vault. The same reasoning excludes exec
  *record* filenames: a record may be narratively named while still correctly
  tagged, so only the folder-vs-tag agreement is checked here.
- It does NOT check feature-index existence or staleness - that is
  :func:`~vaultspec_core.vaultcore.checks.features.check_features`' domain.
- It does NOT check filename or directory grammar - that is
  :func:`~vaultspec_core.vaultcore.checks.structure.check_structure`' domain.

Records with no parseable feature tag (or the ``uncategorized`` placeholder)
are skipped, mirroring ``check_features``: they carry no feature to reconcile
against the folder. A clean, fully-consistent vault yields zero findings.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity, extract_feature_tags

if TYPE_CHECKING:
    from pathlib import Path

    from ._base import VaultSnapshot

logger = logging.getLogger(__name__)

__all__ = ["check_feature_rename_integrity"]

# Exec folders are named ``{plan_date}-{feature}`` (see
# vaultspec_core.vaultcore.hydration): the feature segment is everything after
# the ``YYYY-MM-DD`` plan-date prefix. A folder that does not match this shape
# is a grammar problem owned by ``check_structure`` and is skipped here.
_EXEC_FOLDER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")


def check_feature_rename_integrity(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot | None = None,
) -> CheckResult:
    """Report exec folders whose feature disagrees with their records' tag.

    When *snapshot* is supplied (the combined ``run_all_checks`` pass), the
    folder-vs-tag comparison runs entirely from the snapshot: an exec
    record's containing folder is its path's parent, and its feature tag is
    already parsed - no corpus re-read. Standalone, it walks
    ``<root>/<docs_dir>/exec/*`` directly. For every exec folder named
    ``{plan_date}-{feature}``, each contained record's feature tag must equal
    that ``{feature}`` segment; a record carrying a different feature tag is
    the post-rename drift signal and the folder is reported once as an
    ``ERROR``.

    Records that are symlinks (disk path only), unreadable, non-UTF-8
    (surfaced by ``check_encoding``), or tagged only ``#uncategorized`` /
    untagged are skipped. Folders whose name lacks the
    ``{plan_date}-{feature}`` shape are skipped as a grammar concern owned by
    ``check_structure``.

    The check is vault-wide and takes no ``feature`` filter: drift is defined
    by the folder-vs-tag disagreement itself, not by any single feature scope.

    Args:
        root_dir: Project root directory.
        snapshot: Pre-built snapshot mapping document paths to parsed
            ``(metadata, body)`` tuples.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with check
        name ``"feature-rename-integrity"``. Does not support ``--fix``.
    """
    from ...config import get_config
    from ..models import DocType

    result = CheckResult(check_name="feature-rename-integrity", supports_fix=False)

    exec_dir = root_dir / get_config().docs_dir / DocType.EXEC.value

    if snapshot is not None:
        conflicts_by_folder = _conflicts_from_snapshot(snapshot, exec_dir)
    else:
        if not exec_dir.exists():
            return result
        conflicts_by_folder = _conflicts_from_disk(exec_dir)

    for folder, folder_feature, conflicting in conflicts_by_folder:
        rel_folder = folder.relative_to(root_dir) if folder.is_absolute() else folder
        conflicting_tags = sorted(conflicting)
        tag_display = ", ".join(f"#{t}" for t in conflicting_tags)
        example = conflicting[conflicting_tags[0]]
        result.diagnostics.append(
            CheckDiagnostic(
                path=rel_folder,
                message=(
                    f"Exec folder feature segment '{folder_feature}' disagrees "
                    f"with the {tag_display} feature tag of the records it "
                    f"contains (e.g. {example.name}). This is post-rename drift "
                    "between the exec folder name and its records' feature tag."
                ),
                severity=Severity.ERROR,
                fix_description=(
                    "Reconcile the exec folder name and its records' #feature "
                    f"tag so they agree (the records are tagged "
                    f"'#{conflicting_tags[0]}' but live under a "
                    f"'{folder_feature}' folder)."
                ),
            )
        )

    return result


def _record_feature(tags: list[str]) -> str | None:
    """Return a record's comparable feature tag, or ``None`` to skip it."""
    feats = extract_feature_tags(tags)
    feature = feats[0] if feats else None
    if not feature or feature == "uncategorized":
        return None
    return feature


def _conflicts_from_snapshot(
    snapshot: VaultSnapshot,
    exec_dir: Path,
) -> list[tuple[Path, str, dict[str, Path]]]:
    """Derive per-folder tag conflicts from the parsed snapshot.

    Exec records are the snapshot documents whose parent directory sits
    directly under *exec_dir*; the folder name the disk walk would read is
    the path's parent name, so no filesystem access is needed.
    """
    by_folder: dict[Path, list[Path]] = {}
    for doc_path in snapshot:
        parent = doc_path.parent
        if parent.parent == exec_dir:
            by_folder.setdefault(parent, []).append(doc_path)

    conflicts: list[tuple[Path, str, dict[str, Path]]] = []
    for folder in sorted(by_folder):
        match = _EXEC_FOLDER_RE.match(folder.name)
        if match is None:
            continue
        folder_feature = match.group(1)
        conflicting: dict[str, Path] = {}
        for record in sorted(by_folder[folder]):
            metadata, _body = snapshot[record]
            feature = _record_feature(metadata.tags)
            if feature is not None and feature != folder_feature:
                conflicting.setdefault(feature, record)
        if conflicting:
            conflicts.append((folder, folder_feature, conflicting))
    return conflicts


def _conflicts_from_disk(
    exec_dir: Path,
) -> list[tuple[Path, str, dict[str, Path]]]:
    """Derive per-folder tag conflicts by walking the exec tree directly."""
    from ..exclusions import is_excluded_vault_path
    from ..parser import parse_frontmatter

    conflicts: list[tuple[Path, str, dict[str, Path]]] = []
    for folder in sorted(exec_dir.iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            continue
        if is_excluded_vault_path(folder):
            continue
        match = _EXEC_FOLDER_RE.match(folder.name)
        if match is None:
            continue
        folder_feature = match.group(1)

        # Map each conflicting feature tag to a representative record so the
        # diagnostic can name a concrete file without emitting one error per
        # record in a large folder.
        conflicting: dict[str, Path] = {}
        for record in sorted(folder.glob("*.md")):
            if record.is_symlink() or not record.is_file():
                continue
            try:
                content = record.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # Unreadable / non-UTF-8 records are surfaced by check_encoding;
                # they carry no parseable tag to compare here.
                continue
            meta, _ = parse_frontmatter(content)
            tags = meta.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            feature = _record_feature(tags)
            if feature is not None and feature != folder_feature:
                conflicting.setdefault(feature, record)
        if conflicting:
            conflicts.append((folder, folder_feature, conflicting))
    return conflicts
