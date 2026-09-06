"""Atomic archival of an explicit set of live vault documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import get_config
from ..core.exceptions import VaultSpecError
from .checks.exec_mapping import link_stem
from .exclusions import is_excluded_vault_path
from .parser import parse_vault_metadata
from .rename_engine import RenameTransaction, assert_within, docs_lock_target

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "ArchiveDocumentsError",
    "ArchiveDocumentsResult",
    "RestoreDocumentsError",
    "RestoreDocumentsResult",
    "archive_documents",
    "restore_documents",
]


class ArchiveDocumentsError(VaultSpecError):
    """Raised when an explicit batch archive cannot safely proceed."""


class RestoreDocumentsError(VaultSpecError):
    """Raised when an explicit batch restoration cannot safely proceed."""


@dataclass(frozen=True)
class ArchiveDocumentsResult:
    """The paths archived, or validated for archival by a dry run."""

    status: str
    archived_paths: tuple[Path, ...]
    cross_link_paths: tuple[Path, ...]
    dry_run: bool

    @property
    def archived_count(self) -> int:
        """Return the number of documents in the explicit archive batch."""
        return len(self.archived_paths)

    @property
    def paths(self) -> tuple[Path, ...]:
        """Compatibility name for the destination paths."""
        return self.archived_paths

    def to_dict(self) -> dict[str, object]:
        """Return a portable, JSON-ready representation."""
        return {
            "status": self.status,
            "archived_count": self.archived_count,
            "paths": [path.as_posix() for path in self.archived_paths],
            "cross_link_paths": [path.as_posix() for path in self.cross_link_paths],
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True)
class RestoreDocumentsResult:
    """The paths restored, or validated for restoration by a dry run."""

    status: str
    restored_paths: tuple[Path, ...]
    deduplicated_paths: tuple[Path, ...]
    cross_link_paths: tuple[Path, ...]
    dry_run: bool

    @property
    def restored_count(self) -> int:
        """Return the number of documents in the explicit restore batch."""
        return len(self.restored_paths)

    @property
    def deduplicated_count(self) -> int:
        """Return the archived duplicates removed during the restore batch."""
        return len(self.deduplicated_paths)

    @property
    def paths(self) -> tuple[Path, ...]:
        """Compatibility name for the destination paths."""
        return self.restored_paths

    def to_dict(self) -> dict[str, object]:
        """Return a portable, JSON-ready representation."""
        return {
            "status": self.status,
            "restored_count": self.restored_count,
            "paths": [path.as_posix() for path in self.restored_paths],
            "deduplicated_count": self.deduplicated_count,
            "deduplicated_paths": [path.as_posix() for path in self.deduplicated_paths],
            "cross_link_paths": [path.as_posix() for path in self.cross_link_paths],
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True)
class _ArchiveMove:
    source: Path
    destination: Path
    source_relative: Path


@dataclass(frozen=True)
class _RestoreMove:
    source: Path
    destination: Path
    destination_relative: Path
    deduplicate: bool


def archive_documents(
    root_dir: Path,
    relative_paths: Iterable[str | Path],
    *,
    dry_run: bool = False,
) -> ArchiveDocumentsResult:
    """Archive explicit project-relative ``.vault`` document paths as one batch.

    Every input must be a relative path beginning within the configured vault
    directory. Each document moves to ``.vault/_archive/<vault-relative-path>``.
    Preflight rejects every unsafe source or destination before the first move;
    an apply runs under the normal docs-domain lock and rolls back on failure.

    A ``dry_run`` evaluates the identical :func:`_preflight` the apply runs -
    every deterministic precondition, including the runtime-directory one - and
    writes nothing. Its verdict is point-in-time rather than a reservation: the
    preview holds no lock, so the apply re-runs the whole preflight under
    :func:`~vaultspec_core.vaultcore.rename_engine.docs_lock_target` and fails
    the batch closed if anything moved in between.
    """
    root = root_dir.resolve()
    docs_dir = root / get_config().docs_dir
    _assert_docs_dir(root, docs_dir)
    _assert_runtime_dir(docs_dir)

    supplied = tuple(relative_paths)
    if dry_run:
        moves = _preflight(root, docs_dir, supplied)
        cross_links = _cross_link_paths(root, docs_dir, moves)
        return _result(root, moves, cross_links, dry_run=True)

    _create_runtime_dir(docs_dir)

    with RenameTransaction(docs_dir, lock_target=docs_lock_target(docs_dir)) as tx:
        # Re-run the whole preflight while holding the common docs lock. This
        # closes the gap between validation and the first destructive rename.
        moves = _preflight(root, docs_dir, supplied)
        cross_links = _cross_link_paths(root, docs_dir, moves)
        tx.snapshot(move.source for move in moves)
        for move in moves:
            _create_destination_parent(tx, docs_dir, move.destination.parent)
            _require_regular_document(move.source)
            try:
                moved = tx.rename(move.source, move.destination)
            except OSError as exc:
                raise ArchiveDocumentsError(
                    f"Archive move failed: {move.source} -> {move.destination}: {exc}"
                ) from exc
            if not moved:
                raise ArchiveDocumentsError(
                    "Archive move was refused without replacing a destination: "
                    f"{move.source} -> {move.destination}"
                )

    return _result(root, moves, cross_links, dry_run=False)


def restore_documents(
    root_dir: Path,
    relative_paths: Iterable[str | Path],
    *,
    dry_run: bool = False,
    deduplicate_identical: bool = False,
) -> RestoreDocumentsResult:
    """Restore explicit project-relative archived documents as one batch.

    Every input must name a Markdown document under ``.vault/_archive``. Each
    document moves back to the exact vault-relative path encoded after that
    prefix. Preflight rejects every unsafe source or destination before the
    first move; an apply uses the common docs lock and rolls back on failure.

    A ``dry_run`` carries the same contract as :func:`archive_documents`: it
    evaluates every deterministic precondition the apply enforces, writes
    nothing, and is a point-in-time preview rather than a reservation.
    """
    root = root_dir.resolve()
    docs_dir = root / get_config().docs_dir
    _assert_docs_dir(root, docs_dir, error_type=RestoreDocumentsError)
    _assert_runtime_dir(docs_dir, error_type=RestoreDocumentsError)

    supplied = tuple(relative_paths)
    if dry_run:
        moves = _restore_preflight(
            root, docs_dir, supplied, deduplicate_identical=deduplicate_identical
        )
        cross_links = _restore_cross_link_paths(root, docs_dir, moves)
        return _restore_result(root, moves, cross_links, dry_run=True)

    _create_runtime_dir(docs_dir, error_type=RestoreDocumentsError)

    with RenameTransaction(docs_dir, lock_target=docs_lock_target(docs_dir)) as tx:
        # Match archive's locked preflight so no path can change after the
        # initial validation and before the first destructive rename.
        moves = _restore_preflight(
            root, docs_dir, supplied, deduplicate_identical=deduplicate_identical
        )
        cross_links = _restore_cross_link_paths(root, docs_dir, moves)
        tx.snapshot(move.source for move in moves)
        for move in moves:
            if move.deduplicate:
                _require_identical_restore_duplicate(move.source, move.destination)
                try:
                    move.source.unlink()
                except OSError as exc:
                    raise RestoreDocumentsError(
                        f"Cannot remove archived duplicate {move.source}: {exc}"
                    ) from exc
                continue
            _create_destination_parent(
                tx,
                docs_dir,
                move.destination.parent,
                error_type=RestoreDocumentsError,
                operation="restore",
            )
            _require_regular_document(
                move.source, error_type=RestoreDocumentsError, operation="restore"
            )
            try:
                moved = tx.rename(move.source, move.destination)
            except OSError as exc:
                raise RestoreDocumentsError(
                    f"Restore move failed: {move.source} -> {move.destination}: {exc}"
                ) from exc
            if not moved:
                raise RestoreDocumentsError(
                    "Restore move was refused without replacing a destination: "
                    f"{move.source} -> {move.destination}"
                )

    return _restore_result(root, moves, cross_links, dry_run=False)


def _assert_docs_dir(
    root: Path,
    docs_dir: Path,
    *,
    error_type: type[ArchiveDocumentsError | RestoreDocumentsError] = (
        ArchiveDocumentsError
    ),
) -> None:
    if docs_dir.is_symlink() or not docs_dir.is_dir():
        raise error_type(
            f"Vault document directory must be a real directory: {docs_dir}"
        )
    try:
        docs_dir.relative_to(root)
        docs_dir.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise error_type(
            f"Configured vault directory escapes the project root: {docs_dir}"
        ) from exc


def _assert_runtime_dir(
    docs_dir: Path,
    *,
    error_type: type[ArchiveDocumentsError | RestoreDocumentsError] = (
        ArchiveDocumentsError
    ),
) -> None:
    """Check the runtime directory without creating it.

    This is the deterministic half of the runtime-directory precondition, split
    out so a ``dry_run`` can evaluate it too. Creating the directory is the
    mutating half and stays on the apply path in :func:`_create_runtime_dir`;
    a preview must leave the filesystem untouched.

    Args:
        docs_dir: The configured vault document directory.
        error_type: Exception raised on failure, so the restore path reports
            its own error type.

    Raises:
        ArchiveDocumentsError: If the runtime path is a symlink, or exists as
            something other than a directory. ``error_type`` selects the
            concrete class.
    """
    runtime_dir = docs_dir / "data"
    if runtime_dir.is_symlink():
        raise error_type(
            f"Vault runtime directory must not be a symlink: {runtime_dir}"
        )
    if runtime_dir.exists() and not runtime_dir.is_dir():
        raise error_type(f"Vault runtime path is not a directory: {runtime_dir}")


def _create_runtime_dir(
    docs_dir: Path,
    *,
    error_type: type[ArchiveDocumentsError | RestoreDocumentsError] = (
        ArchiveDocumentsError
    ),
) -> None:
    """Create the runtime directory after re-checking its preconditions.

    Args:
        docs_dir: The configured vault document directory.
        error_type: Exception raised on failure, so the restore path reports
            its own error type.

    Raises:
        ArchiveDocumentsError: If the deterministic checks in
            :func:`_assert_runtime_dir` fail, or the path is still not a
            directory after creation. ``error_type`` selects the concrete class.
    """
    _assert_runtime_dir(docs_dir, error_type=error_type)
    runtime_dir = docs_dir / "data"
    runtime_dir.mkdir(exist_ok=True)
    if not runtime_dir.is_dir():
        raise error_type(f"Vault runtime path is not a directory: {runtime_dir}")


def _preflight(
    root: Path, docs_dir: Path, relative_paths: tuple[str | Path, ...]
) -> tuple[_ArchiveMove, ...]:
    if not relative_paths:
        raise ArchiveDocumentsError("Archive requires at least one document path.")

    moves: list[_ArchiveMove] = []
    seen_sources: set[Path] = set()
    seen_destinations: set[Path] = set()
    for value in relative_paths:
        source, source_relative = _resolve_source(root, docs_dir, value)
        destination = docs_dir / "_archive" / source_relative
        assert_within(docs_dir, destination)
        if source in seen_sources:
            raise ArchiveDocumentsError(f"Duplicate archive source: {source}")
        if destination in seen_destinations:
            raise ArchiveDocumentsError(f"Archive destination collision: {destination}")
        if destination.exists() or destination.is_symlink():
            raise ArchiveDocumentsError(
                f"Archive destination already exists: {destination}"
            )
        _require_safe_destination_parent(docs_dir, destination.parent)
        seen_sources.add(source)
        seen_destinations.add(destination)
        moves.append(_ArchiveMove(source, destination, source_relative))
    return tuple(moves)


def _restore_preflight(
    root: Path,
    docs_dir: Path,
    relative_paths: tuple[str | Path, ...],
    *,
    deduplicate_identical: bool,
) -> tuple[_RestoreMove, ...]:
    if not relative_paths:
        raise RestoreDocumentsError("Restore requires at least one document path.")

    moves: list[_RestoreMove] = []
    seen_sources: set[Path] = set()
    seen_destinations: set[Path] = set()
    for value in relative_paths:
        source, destination_relative = _resolve_restore_source(root, docs_dir, value)
        destination = docs_dir / destination_relative
        try:
            assert_within(docs_dir, destination)
        except VaultSpecError as exc:
            raise RestoreDocumentsError(
                f"Restore destination escapes vault: {destination}"
            ) from exc
        if source in seen_sources:
            raise RestoreDocumentsError(f"Duplicate restore source: {source}")
        if destination in seen_destinations:
            raise RestoreDocumentsError(f"Restore destination collision: {destination}")
        deduplicate = False
        if destination.exists() or destination.is_symlink():
            if not deduplicate_identical:
                raise RestoreDocumentsError(
                    f"Restore destination already exists: {destination}"
                )
            _require_identical_restore_duplicate(source, destination)
            deduplicate = True
        else:
            _require_safe_destination_parent(
                docs_dir,
                destination.parent,
                error_type=RestoreDocumentsError,
                operation="restore",
            )
        seen_sources.add(source)
        seen_destinations.add(destination)
        moves.append(
            _RestoreMove(source, destination, destination_relative, deduplicate)
        )
    return tuple(moves)


def _resolve_source(root: Path, docs_dir: Path, value: str | Path) -> tuple[Path, Path]:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ArchiveDocumentsError(
            f"Archive path must be project-relative and confined to .vault: {value}"
        )
    raw_source = root / relative
    try:
        vault_relative = raw_source.relative_to(docs_dir)
    except ValueError as exc:
        raise ArchiveDocumentsError(
            f"Archive path must be under {docs_dir}: {relative}"
        ) from exc
    if not vault_relative.parts or vault_relative.parts[0] == "_archive":
        raise ArchiveDocumentsError(
            f"Archive source must be live and outside _archive: {relative}"
        )
    if raw_source.suffix.lower() != ".md":
        raise ArchiveDocumentsError(
            f"Archive source must be a vault Markdown document: {relative}"
        )
    _require_no_symlink_components(docs_dir, raw_source)
    source = raw_source.resolve(strict=False)
    assert_within(docs_dir, source)
    _require_regular_document(source)
    return source, vault_relative


def _resolve_restore_source(
    root: Path, docs_dir: Path, value: str | Path
) -> tuple[Path, Path]:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RestoreDocumentsError(
            f"Restore path must be project-relative and confined to .vault: {value}"
        )
    raw_source = root / relative
    try:
        vault_relative = raw_source.relative_to(docs_dir)
    except ValueError as exc:
        raise RestoreDocumentsError(
            f"Restore path must be under {docs_dir}: {relative}"
        ) from exc
    if len(vault_relative.parts) < 2 or vault_relative.parts[0] != "_archive":
        raise RestoreDocumentsError(
            f"Restore source must be under _archive: {relative}"
        )
    if raw_source.suffix.lower() != ".md":
        raise RestoreDocumentsError(
            f"Restore source must be a vault Markdown document: {relative}"
        )
    _require_no_symlink_components(
        docs_dir, raw_source, error_type=RestoreDocumentsError, operation="restore"
    )
    source = raw_source.resolve(strict=False)
    try:
        assert_within(docs_dir, source)
    except VaultSpecError as exc:
        raise RestoreDocumentsError(f"Restore source escapes vault: {source}") from exc
    _require_regular_document(
        source, error_type=RestoreDocumentsError, operation="restore"
    )
    return source, Path(*vault_relative.parts[1:])


def _require_regular_document(
    path: Path,
    *,
    error_type: type[ArchiveDocumentsError | RestoreDocumentsError] = (
        ArchiveDocumentsError
    ),
    operation: str = "archive",
) -> None:
    if path.is_symlink() or not path.is_file():
        raise error_type(
            f"{operation.capitalize()} source is not a regular file: {path}"
        )
    try:
        path.read_bytes()
    except OSError as exc:
        raise error_type(f"Cannot read {operation} source {path}: {exc}") from exc


def _require_identical_restore_duplicate(source: Path, destination: Path) -> None:
    """Refuse a restore deduplication unless both files have exactly the same bytes."""
    _require_regular_document(
        source, error_type=RestoreDocumentsError, operation="restore"
    )
    if destination.is_symlink() or not destination.is_file():
        raise RestoreDocumentsError(
            f"Restore deduplication destination is not a regular file: {destination}"
        )
    try:
        identical = source.read_bytes() == destination.read_bytes()
    except OSError as exc:
        raise RestoreDocumentsError(
            f"Cannot compare restore duplicate {source} with {destination}: {exc}"
        ) from exc
    if not identical:
        raise RestoreDocumentsError(
            f"Restore destination is not byte-identical: {destination}"
        )


def _require_no_symlink_components(
    docs_dir: Path,
    path: Path,
    *,
    error_type: type[ArchiveDocumentsError | RestoreDocumentsError] = (
        ArchiveDocumentsError
    ),
    operation: str = "archive",
) -> None:
    try:
        relative = path.relative_to(docs_dir)
    except ValueError as exc:
        raise error_type(
            f"{operation.capitalize()} source escapes vault: {path}"
        ) from exc
    current = docs_dir
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise error_type(
                f"{operation.capitalize()} source contains a symlink component: "
                f"{current}"
            )


def _require_safe_destination_parent(
    docs_dir: Path,
    parent: Path,
    *,
    error_type: type[ArchiveDocumentsError | RestoreDocumentsError] = (
        ArchiveDocumentsError
    ),
    operation: str = "archive",
) -> None:
    try:
        assert_within(docs_dir, parent)
    except VaultSpecError as exc:
        raise error_type(
            f"{operation.capitalize()} destination parent escapes vault: {parent}"
        ) from exc
    current = docs_dir
    relative = parent.relative_to(docs_dir)
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise error_type(
                f"{operation.capitalize()} destination parent must not be a "
                f"symlink: {current}"
            )
        if current.exists() and not current.is_dir():
            raise error_type(
                f"{operation.capitalize()} destination parent is not a "
                f"directory: {current}"
            )


def _create_destination_parent(
    transaction: RenameTransaction,
    docs_dir: Path,
    parent: Path,
    *,
    error_type: type[ArchiveDocumentsError | RestoreDocumentsError] = (
        ArchiveDocumentsError
    ),
    operation: str = "archive",
) -> None:
    _require_safe_destination_parent(
        docs_dir, parent, error_type=error_type, operation=operation
    )
    missing: list[Path] = []
    current = parent
    while current != docs_dir and not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir()
        transaction.record_created_dir(directory)


def _cross_link_paths(
    root: Path, docs_dir: Path, moves: tuple[_ArchiveMove, ...]
) -> tuple[Path, ...]:
    archived_stems = {move.source.stem for move in moves}
    source_paths = {move.source for move in moves}
    linked: list[Path] = []
    for path in docs_dir.rglob("*.md"):
        try:
            relative = path.relative_to(docs_dir)
        except ValueError:
            continue
        if path in source_paths or is_excluded_vault_path(relative):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        try:
            metadata, _body = parse_vault_metadata(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if any(link_stem(link) in archived_stems for link in metadata.related):
            linked.append(path.relative_to(root))
    return tuple(sorted(linked))


def _result(
    root: Path,
    moves: tuple[_ArchiveMove, ...],
    cross_links: tuple[Path, ...],
    *,
    dry_run: bool,
) -> ArchiveDocumentsResult:
    return ArchiveDocumentsResult(
        status="unchanged" if dry_run else "updated",
        archived_paths=tuple(move.destination.relative_to(root) for move in moves),
        cross_link_paths=cross_links,
        dry_run=dry_run,
    )


def _restore_cross_link_paths(
    root: Path, docs_dir: Path, moves: tuple[_RestoreMove, ...]
) -> tuple[Path, ...]:
    restored_stems = {move.source.stem for move in moves}
    linked: list[Path] = []
    for path in docs_dir.rglob("*.md"):
        try:
            relative = path.relative_to(docs_dir)
        except ValueError:
            continue
        if is_excluded_vault_path(relative) or path.is_symlink() or not path.is_file():
            continue
        try:
            metadata, _body = parse_vault_metadata(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if any(link_stem(link) in restored_stems for link in metadata.related):
            linked.append(path.relative_to(root))
    return tuple(sorted(linked))


def _restore_result(
    root: Path,
    moves: tuple[_RestoreMove, ...],
    cross_links: tuple[Path, ...],
    *,
    dry_run: bool,
) -> RestoreDocumentsResult:
    return RestoreDocumentsResult(
        status="unchanged" if dry_run else "updated",
        restored_paths=tuple(
            move.destination.relative_to(root) for move in moves if not move.deduplicate
        ),
        deduplicated_paths=tuple(
            move.source.relative_to(root) for move in moves if move.deduplicate
        ),
        cross_link_paths=cross_links,
        dry_run=dry_run,
    )
