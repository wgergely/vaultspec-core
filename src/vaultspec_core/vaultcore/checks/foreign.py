"""Warn about foreign files inside the framework-managed roots.

``.vaultspec/`` and ``.vault/`` are the two trees the framework itself
populates and reads back. Nothing stops a project from dropping unrelated
files or whole subtrees inside either one - a repository once grew an
application-specific test suite five files and roughly 6,400 lines deep under
``.vaultspec/tests/`` with no warning from any framework command (issue
#450). This checker makes that pollution visible without touching it: it is
detection-only, never deletes or moves anything, and reports every finding as
a ``WARNING`` rather than an ``ERROR`` because "foreign" is a structural
inference, not a certainty - a false positive here trains operators to ignore
the warning, which is worse than not having it.

Two independent, narrow rules keep the false-positive rate low:

- Under ``.vaultspec/``, only the *top-level* entry name is checked against
  the set the framework itself is known to place there (every builtins
  resource category, derived from :func:`~vaultspec_core.builtins.builtins_root`
  the same way :func:`~vaultspec_core.core.scaffold.scaffold_core` derives it,
  plus the per-machine runtime artifacts documented in
  :mod:`~vaultspec_core.core.gitignore`). Nothing beneath a recognised
  directory is inspected: ``rules/``, ``skills/``, ``templates/``, ``system/``,
  ``agents/``, ``hooks/``, ``mcps/``, ``reference/``, and any future builtins
  category are explicit, user-editable or team-shared extension points, and a
  project is expected to add its own content there.
- Under ``.vault/``, only files that sit inside a document-type directory
  (:attr:`~vaultspec_core.vaultcore.models.VaultConstants.SUPPORTED_DIRECTORIES`)
  and do not end in ``.md`` are flagged - a vault document directory holds
  markdown documents and nothing else. The auxiliary ``data/`` and ``logs/``
  subtrees are never walked, and the shared
  :func:`~vaultspec_core.vaultcore.exclusions.is_excluded_vault_path` predicate
  keeps ``.trash/`` snapshots, ``.obsidian/`` editor state, and ``_archive/``
  documents out of scope, exactly as every other vault walker does.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..exclusions import is_excluded_vault_path
from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["check_foreign"]

#: Root-level ``.vaultspec/`` files the framework itself writes, never
#: authored content. Mirrors the runtime entries
#: :func:`~vaultspec_core.core.gitignore.get_recommended_entries` recommends
#: ignoring, minus the ``*.lock`` sentinels (matched separately below because
#: their basenames vary) and ``_snapshots/`` (a directory, handled by
#: :data:`_VAULTSPEC_EXTRA_DIRS`).
_VAULTSPEC_ALLOWED_FILES = frozenset(
    {
        "workspace.json",  # per-project install declaration
        "providers.json",  # installed-provider manifest
        "mcp-ownership.json",  # per-machine MCP ownership ledger
    }
)

#: Directory names the framework places under ``.vaultspec/`` that are not
#: mirrored under ``builtins/`` (so :func:`_vaultspec_allowed_dir_names`
#: cannot derive them from the bundled resource tree).
_VAULTSPEC_EXTRA_DIRS = frozenset({"_snapshots"})


def _vaultspec_allowed_dir_names() -> frozenset[str]:
    """Return every directory name the framework itself places under ``.vaultspec/``.

    Derived from the bundled builtins package tree - the same source
    :func:`~vaultspec_core.core.scaffold.scaffold_core` reads when it
    provisions a fresh ``.vaultspec/`` - so a new resource category (a future
    ``workflows/``, say) is recognised automatically without a second,
    hand-maintained list that could drift from the one install actually uses.
    """
    from ...builtins import builtins_root

    root = builtins_root()
    return (
        frozenset(
            d.name for d in root.iterdir() if d.is_dir() and d.name != "__pycache__"
        )
        | _VAULTSPEC_EXTRA_DIRS
    )


def _check_vaultspec_tree(root_dir: Path, result: CheckResult) -> None:
    """Flag top-level ``.vaultspec/`` entries the framework did not place."""
    from ...config import get_config

    cfg = get_config()
    fw_dir = root_dir / cfg.framework_dir
    if not fw_dir.is_dir():
        return

    allowed_dirs = _vaultspec_allowed_dir_names()

    for item in sorted(fw_dir.iterdir()):
        if item.name.startswith("."):
            # Editor/VCS state (.git, .obsidian, ...) - never framework content
            # and never authored through a vault verb either; not ours to judge.
            continue

        if item.is_dir():
            if item.name in allowed_dirs:
                continue
            result.diagnostics.append(
                CheckDiagnostic(
                    path=item.relative_to(root_dir),
                    message=(
                        f"Unrecognized directory '{item.name}' inside "
                        f"{cfg.framework_dir}/. The framework does not place "
                        "or read content here; move project code and tests "
                        "outside the managed tree."
                    ),
                    severity=Severity.WARNING,
                )
            )
        elif item.is_file():
            if item.name in _VAULTSPEC_ALLOWED_FILES or item.name.endswith(".lock"):
                continue
            result.diagnostics.append(
                CheckDiagnostic(
                    path=item.relative_to(root_dir),
                    message=(
                        f"Unrecognized file '{item.name}' inside "
                        f"{cfg.framework_dir}/. The framework does not place "
                        "or read this file; move project content outside the "
                        "managed tree."
                    ),
                    severity=Severity.WARNING,
                )
            )


def _check_vault_tree(root_dir: Path, result: CheckResult) -> None:
    """Flag non-``.md`` files nested inside a ``.vault/`` document directory."""
    from ...config import get_config
    from ..models import VaultConstants

    cfg = get_config()
    docs_dir = root_dir / cfg.docs_dir
    if not docs_dir.is_dir():
        return

    for dirname in sorted(VaultConstants.SUPPORTED_DIRECTORIES):
        type_dir = docs_dir / dirname
        if not type_dir.is_dir():
            continue
        for path in sorted(type_dir.rglob("*")):
            if path.is_dir():
                continue
            # Shared with every other .vault/ walker: keeps .trash/ snapshots,
            # .obsidian/ editor state, and _archive/ documents out of scope.
            if is_excluded_vault_path(path):
                continue
            if path.suffix.lower() == ".md":
                continue
            result.diagnostics.append(
                CheckDiagnostic(
                    path=path.relative_to(root_dir),
                    message=(
                        f"Foreign file '{path.name}' inside "
                        f"{cfg.docs_dir}/{dirname}/: a vault document "
                        "directory holds only .md documents."
                    ),
                    severity=Severity.WARNING,
                )
            )


def check_foreign(root_dir: Path) -> CheckResult:
    """Warn about files the framework did not place inside its managed roots.

    Detection-only: never renames, moves, or deletes anything, and offers no
    ``--fix`` - a file the checker cannot identify is exactly the file it must
    not act on. Runs vault-wide with no ``feature`` filter, since a foreign
    file has no vault frontmatter to carry a feature tag in the first place
    (mirrors :func:`~vaultspec_core.vaultcore.checks.encoding.check_encoding` and
    :func:`~vaultspec_core.vaultcore.checks.rename_integrity.check_rename_integrity`,
    which are scope-free for the same reason).

    Args:
        root_dir: Project root directory.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with check
        name ``"foreign"``.
    """
    result = CheckResult(check_name="foreign", supports_fix=False)
    _check_vaultspec_tree(root_dir, result)
    _check_vault_tree(root_dir, result)
    return result
