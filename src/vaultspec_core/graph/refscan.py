"""Read a vault corpus from the git object database at an arbitrary ref.

Issue #160 asks core to make its declared-edge graph ref-addressable:
``vault graph --json --ref <branch|sha>`` resolving documents from blobs at the
ref, read-only, with no working-tree mutation. This module is the read seam for
that path. It enumerates the vault blobs at a ref and reads each blob's bytes
through subprocess ``git`` - the only git access pattern the project already
trusts (it ships no git library) - yielding ``(tree_path, content)`` pairs that
mirror what ``scan_vault`` plus ``read_text`` yield for the working tree.

The feature is git-only by nature: a non-repository workspace or an
unresolvable ref raises :class:`RefScanError` rather than falling back to a
working-tree read that would silently answer for the wrong corpus (the
``ref-scoped-reads-bypass-worktree-cache`` codification candidate). The same
exclusions ``scan_vault`` applies (``.obsidian`` config trees, ``_archive``
documents) are applied here so a ref build sees the same document set a
working-tree build of that corpus would.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ..core.exceptions import VaultSpecError
from ..vaultcore.exclusions import EXCLUDED_VAULT_DIR_NAMES

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["RefScanError", "read_vault_at_ref"]


class RefScanError(VaultSpecError):
    """Raised when a ref-scoped vault read cannot resolve the repo or ref.

    Distinct from an :class:`OSError`: it signals a clean, typed failure (not a
    git repository, ``git`` not installed, or a ref that does not resolve) so
    the caller can report it and exit non-zero without ever falling back to a
    working-tree read.
    """


def _run_git(root_dir: Path, args: list[str]) -> bytes:
    """Run ``git -C <root_dir> <args>`` and return raw stdout bytes.

    Args:
        root_dir: Repository working directory passed via ``git -C``.
        args: Git arguments after the ``-C <root_dir>`` prefix.

    Returns:
        The command's raw stdout bytes (not decoded, so blob content can be
        decoded explicitly as UTF-8 by the caller).

    Raises:
        RefScanError: When ``git`` is not installed or the command fails.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root_dir), *args],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RefScanError(
            "git executable not found; ref-scoped reads require git on PATH.",
            hint="Install git or run without --ref.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace").strip()
        raise RefScanError(
            f"git {' '.join(args)} failed: {stderr or exc}",
        ) from exc
    return result.stdout


def _resolve_commit(root_dir: Path, ref: str) -> str:
    """Resolve *ref* to a commit SHA, or raise :class:`RefScanError`.

    Verifies the workspace is a git repository and that *ref* names a commit.
    A non-repository workspace and an unresolvable ref both raise a typed
    error rather than degrading to a working-tree read.

    Args:
        root_dir: Repository working directory.
        ref: A branch name, tag, or commit-ish to resolve.

    Returns:
        The resolved commit SHA (40-hex string).

    Raises:
        RefScanError: When *root_dir* is not a git repository or *ref* does
            not resolve to a commit.
    """
    # ``rev-parse --git-dir`` succeeds inside any repository (work tree or
    # bare) and fails cleanly outside one.
    try:
        _run_git(root_dir, ["rev-parse", "--git-dir"])
    except RefScanError as exc:
        raise RefScanError(
            f"not a git repository: {root_dir}",
            hint="--ref reads from the git object database and needs a repo.",
        ) from exc

    try:
        out = _run_git(
            root_dir, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]
        )
    except RefScanError as exc:
        raise RefScanError(
            f"ref does not resolve to a commit: {ref!r}",
            hint="Pass an existing branch, tag, or commit sha.",
        ) from exc
    return out.decode("utf-8", errors="replace").strip()


def read_vault_at_ref(root_dir: Path, ref: str, docs_dir: str) -> list[tuple[str, str]]:
    """Return ``(tree_path, content)`` pairs for the vault corpus at *ref*.

    Enumerates the ``.md`` blobs under *docs_dir* at *ref* and reads each
    blob's UTF-8 text, mirroring the document set and exclusions
    ``scan_vault`` applies to the working tree (``.obsidian`` and ``_archive``
    are skipped). The corpus read is read-only: no working-tree state is
    written and no migration runs.

    Args:
        root_dir: Repository working directory.
        ref: A branch name, tag, or commit-ish to read the corpus from.
        docs_dir: The configured docs directory name (e.g. ``.vault``),
            used both to scope the tree enumeration and as the virtual
            tree-path prefix.

    Returns:
        A list of ``(tree_path, content)`` pairs in deterministic
        (lexicographic tree-path) order. ``tree_path`` is the repo-relative
        POSIX path (e.g. ``.vault/adr/foo.md``).

    Raises:
        RefScanError: When the workspace is not a git repository or *ref*
            does not resolve.
    """
    commit = _resolve_commit(root_dir, ref)

    # ``-z`` makes ls-tree NUL-separate the names and never quote non-ASCII
    # paths, so the split is unambiguous regardless of path content.
    raw = _run_git(
        root_dir,
        ["ls-tree", "-r", "-z", "--name-only", commit, "--", docs_dir],
    )
    names = [
        chunk for chunk in raw.decode("utf-8", errors="replace").split("\0") if chunk
    ]

    corpus: list[tuple[str, str]] = []
    for tree_path in sorted(names):
        if not tree_path.endswith(".md"):
            continue
        parts = PurePosixPath(tree_path).parts
        if EXCLUDED_VAULT_DIR_NAMES.intersection(parts):
            continue
        blob = _run_git(root_dir, ["cat-file", "blob", f"{commit}:{tree_path}"])
        try:
            content = blob.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                "Skipping non-UTF-8 vault blob at %s in ref %s", tree_path, ref
            )
            continue
        corpus.append((tree_path, content))

    logger.info(
        "Read %d vault documents from ref %s (%s)", len(corpus), ref, commit[:12]
    )
    return corpus
