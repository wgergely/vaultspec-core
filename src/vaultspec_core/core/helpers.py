"""Shared filesystem, YAML, and process helpers for vaultspec runtime code.

The functions here support multiple implementation layers rather than a single
feature area. They provide the low-level operations used by resource
management, config generation, syncing, and hook execution.
"""

from __future__ import annotations

import errno
import logging
import os
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

import yaml

logger = logging.getLogger(__name__)

__all__ = ["launch_editor", "rmtree_robust"]


_thread_locks: dict[str, threading.Lock] = {}
_thread_locks_guard = threading.Lock()


def _get_thread_lock(key: str) -> threading.Lock:
    """Return a per-path threading lock, creating one if needed."""
    with _thread_locks_guard:
        if key not in _thread_locks:
            _thread_locks[key] = threading.Lock()
        return _thread_locks[key]


# The two errno values Microsoft documents `_locking` as setting for a
# LOCKING VIOLATION under `LK_LOCK` - that is, "someone else holds the range",
# which is contention rather than a fault:
#
#   EDEADLOCK  the range could not be locked after its ten internal attempts
#              (spelled EDEADLK here: the two names are the same value on
#              every platform, and only EDEADLK resolves off Windows)
#   EACCES     locking violation (the region is already locked)
#
# Both mean "wait and try again". Only EDEADLOCK was retried here, so real
# contention that surfaced as EACCES propagated as `PermissionError(13,
# 'Permission denied')` and read like a filesystem permission fault - which is
# what made the Windows concurrency suite flaky (issue #321). Note the absence
# of a `winerror` on that exception: it comes from the CRT's errno, not from
# the Win32 error layer, which is what distinguishes it from the scanner race
# `_replace_atomic` absorbs.
_WINDOWS_LOCK_CONTENTION_ERRORS = frozenset({errno.EDEADLK, errno.EACCES})

# `LK_LOCK` blocks for about ten seconds before reporting EDEADLOCK, so that
# path needs no pause. An EACCES violation can come back immediately, so a
# short sleep keeps a contended acquire from becoming a hot spin.
_WINDOWS_LOCK_RETRY_INTERVAL_SECONDS = 0.05


def _is_windows_lock_contention(exc: OSError) -> bool:
    """Whether *exc* means the lock is held elsewhere rather than unusable.

    Kept separate from the acquire loop so the classification is testable on
    every platform: the loop itself needs a real Windows file descriptor, the
    decision it makes does not.

    Args:
        exc: The error raised by :func:`msvcrt.locking`.

    Returns:
        ``True`` when the call should be retried, ``False`` when it is a
        genuine failure - a bad descriptor, an unreadable volume - that should
        propagate rather than spin forever.
    """
    return exc.errno in _WINDOWS_LOCK_CONTENTION_ERRORS


def _acquire_windows_lock(fd: int) -> None:
    """Block until the byte-range lock on *fd* is held.

    :func:`msvcrt.locking` with ``LK_LOCK`` is not a blocking acquire despite
    the name: it retries ten times at one-second intervals and then reports a
    locking violation. Any operation holding a lock past that budget - a
    large repair, a slow or network volume, an antivirus scan mid-write -
    would make a concurrent caller fail rather than wait its turn. Retrying on
    exactly the contention errnos keeps the contract this module documents,
    matching :func:`fcntl.flock` with ``LOCK_EX`` on Unix, which blocks
    indefinitely.

    Any other ``OSError`` is a genuine failure - a bad descriptor, an
    unreadable volume - and propagates rather than spinning forever.

    Args:
        fd: Open file descriptor of the ``.lock`` sibling file.

    Raises:
        RuntimeError: If called off Windows. The sole caller reaches this
            only inside a ``sys.platform == "win32"`` branch, so the guard
            is unreachable in practice; it is what lets a type checker
            resolve the Windows-only ``msvcrt`` surface below when
            checking against a non-Windows platform.
    """
    if sys.platform != "win32":
        raise RuntimeError("_acquire_windows_lock is a Windows-only helper")

    import msvcrt

    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        except OSError as exc:
            if not _is_windows_lock_contention(exc):
                raise
            time.sleep(_WINDOWS_LOCK_RETRY_INTERVAL_SECONDS)
            continue
        return


@contextmanager
def advisory_lock(path: Path) -> Generator[None]:
    """Advisory file lock for serializing concurrent read-modify-write cycles.

    Serializes threads within the same process via a per-path
    :class:`threading.Lock`, then serializes across processes via an
    OS-level file lock (``fcntl.flock`` on Unix, ``msvcrt.locking``
    on Windows).  Both layers block until acquired.

    Args:
        path: The file being protected.  A sibling ``.lock`` file is
            created next to it and used as the lock target.
    """
    lock_path = path.with_suffix(path.suffix + ".lock")

    # Only create the lock file's parent if it already exists.  Creating
    # it unconditionally would cause side-effects (e.g. directory creation
    # during dry-run operations where the target doesn't exist yet).
    # When the parent doesn't exist, no concurrent writer can race on
    # this file, so it is safe to skip locking entirely.
    if not lock_path.parent.exists():
        yield
        return

    resolved_key = str(lock_path.resolve())
    tlock = _get_thread_lock(resolved_key)
    tlock.acquire()
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            if sys.platform == "win32":
                import msvcrt

                _acquire_windows_lock(fd)
                try:
                    yield
                finally:
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    finally:
        tlock.release()


class _LiteralStr(str):
    """Marker type for strings that should use YAML literal block scalar."""


class _ScalarRepresenter(Protocol):
    """The subset of PyYAML's untyped ``Dumper`` interface this module relies on."""

    def represent_scalar(
        self, tag: str, value: str, style: str | None = None
    ) -> yaml.ScalarNode: ...


def _literal_representer(
    dumper: _ScalarRepresenter, data: _LiteralStr
) -> yaml.ScalarNode:
    """Represent a _LiteralStr value using YAML literal block scalar style (``|``).

    Args:
        dumper: The PyYAML Dumper instance performing serialization.
        data: The string value to represent with literal block style.

    Returns:
        A YAML ScalarNode configured with ``|`` block scalar style.
    """
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


_literal_representer_registered = False
_literal_representer_lock = threading.Lock()


def _ensure_literal_representer() -> None:
    """Register :func:`_literal_representer` with PyYAML on first use.

    Performing this registration lazily (rather than at module import)
    prevents a partially broken or missing PyYAML install from taking the
    framework down during ``import vaultspec_core.core``: every CLI entry
    point and downstream package depends on that import succeeding so
    ``vaultspec-core spec doctor`` and ``vaultspec-core install --upgrade`` can
    diagnose and repair a
    degraded environment.  See GitHub issue #85.

    Uses double-checked locking so that two threads calling
    :func:`dump_yaml` concurrently for the first time both observe a
    registered representer without either of them entering the critical
    section twice.  ``yaml.add_representer`` mutates a class-level
    ``Dumper.yaml_representers`` dict, and although the GIL serialises
    each individual dict assignment in CPython, the lock is the right
    contract for non-CPython runtimes and free-threaded builds.
    """
    global _literal_representer_registered
    if _literal_representer_registered:
        return
    with _literal_representer_lock:
        if _literal_representer_registered:
            return
        yaml.add_representer(_LiteralStr, _literal_representer)
        _literal_representer_registered = True


def dump_yaml(data: dict[str, Any]) -> str:
    """Serialize a dict to YAML, using literal block style for multi-line values.

    Args:
        data: Key-value mapping to serialize.

    Returns:
        YAML string representation with multi-line string values rendered as
        literal block scalars (``|``).
    """
    _ensure_literal_representer()
    prepared = {}
    for k, v in data.items():
        if isinstance(v, str) and "\n" in v:
            prepared[k] = _LiteralStr(v)
        else:
            prepared[k] = v
    return yaml.dump(
        prepared, default_flow_style=False, allow_unicode=True, sort_keys=False
    ).rstrip("\n")


def build_file(frontmatter: dict[str, Any], body: str) -> str:
    """Assemble a Markdown file with YAML frontmatter.

    Args:
        frontmatter: Key-value pairs to serialize as the YAML front matter block.
        body: Markdown body text to place after the closing ``---`` delimiter.

    Returns:
        A string of the form ``---\\n<yaml>\\n---\\n\\n<body>``.
    """
    fm_str = dump_yaml(frontmatter)
    return f"---\n{fm_str}\n---\n\n{body}"


def ensure_dir(path: Path) -> None:
    """Create *path* and all intermediate parents if they do not already exist.

    Refuses to create directories inside symlink targets to prevent
    accidental writes through symbolic links.

    Args:
        path: Directory path to create.
    """
    if path.exists() and path.is_symlink():
        logger.warning("Refusing to create directory inside symlink target: %s", path)
        return
    path.mkdir(parents=True, exist_ok=True)


def rmtree_robust(path: Path) -> None:
    """Remove a directory tree, handling symlinks and Windows read-only files.

    Symlinks are unlinked directly rather than followed. On Windows, a
    read-only attribute on a child file is cleared before retrying the
    removal so that NTFS-protected trees can be deleted.

    Args:
        path: Directory (or symlink to directory) to remove.
    """
    if path.is_symlink():
        path.unlink()
        return

    def _on_exc(
        func: Callable[..., object],
        fpath: str,
        exc: BaseException,
    ) -> None:
        if os.name == "nt":
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        else:
            raise exc

    shutil.rmtree(path, onexc=_on_exc)


def _open_atomic_temp(path: Path) -> tuple[int, Path, tuple[int, int]]:
    """Exclusively create an unpredictable regular file beside *path*."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    for optional_flag in ("O_BINARY", "O_CLOEXEC", "O_NOFOLLOW"):
        flags |= getattr(os, optional_flag, 0)

    for _attempt in range(128):
        candidate = path.with_name(f".vs-write-{secrets.token_hex(16)}.tmp")
        try:
            fd = os.open(candidate, flags, 0o666)
        except FileExistsError:
            continue
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            os.close(fd)
            raise OSError(
                f"Atomic write temporary path is not a regular file: {candidate}"
            )
        return fd, candidate, (opened.st_dev, opened.st_ino)
    raise FileExistsError(
        f"Could not allocate an atomic write temporary file for {path}"
    )


def _unlink_owned_temp(path: Path, identity: tuple[int, int]) -> None:
    """Remove *path* only while it is still the temporary file we created.

    A temporary this function cannot delete is a temporary that outlives the
    run, so a missing write bit is cleared and the unlink retried rather than
    allowed to leak the file. The retry stays inside the identity check, so it
    can only ever widen a file this call created (issue #412).
    """
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == identity:
        try:
            path.unlink()
        except PermissionError:
            os.chmod(path, stat.S_IMODE(current.st_mode) | stat.S_IWUSR)
            path.unlink()


def _assert_owned_temp(path: Path, identity: tuple[int, int]) -> None:
    """Fail unless *path* still names the temporary regular file we opened."""
    try:
        current = path.lstat()
    except FileNotFoundError as exc:
        raise OSError(f"Atomic write temporary file disappeared: {path}") from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or (
            current.st_dev,
            current.st_ino,
        )
        != identity
    ):
        raise OSError(f"Atomic write temporary file identity changed: {path}")


def _is_read_only_file(path: Path) -> bool:
    """Report whether *path* is a regular file with no owner-write bit.

    A path that cannot be stat'ed answers ``False``: the caller's own attempt
    is then the thing that decides, rather than this check refusing on a guess.
    """
    try:
        current = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(current.st_mode) and not (
        stat.S_IMODE(current.st_mode) & stat.S_IWUSR
    )


# ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION
_WINDOWS_TRANSIENT_REPLACE_ERRORS = frozenset({5, 32})
_WINDOWS_REPLACE_RETRY_BUDGET_SECONDS = 2.0
_WINDOWS_REPLACE_RETRY_INTERVAL_SECONDS = 0.05


def _replace_atomic(tmp: Path, path: Path) -> None:
    """Call :func:`os.replace`, absorbing a transient Windows scanner race.

    A destination a writer just created or modified is briefly opened by
    antivirus real-time protection or the search indexer on Windows, which
    holds the file just long enough for a same-instant ``MoveFileEx`` to fail
    with ``ERROR_ACCESS_DENIED`` (5) or ``ERROR_SHARING_VIOLATION`` (32) even
    though no other VaultSpec writer holds the document's advisory lock
    (issue #321): the lock only serialises this project's own writers, not an
    external scanner. Retrying briefly rides out that window the same way
    :func:`_acquire_windows_lock` rides out ``msvcrt``'s own retry budget; a
    persistent lock - a genuine external handle rather than a momentary scan
    - still exhausts the budget and surfaces the original error.

    Args:
        tmp: The exclusively-created temporary file to rename from.
        path: The destination document path.
    """
    if sys.platform != "win32":
        os.replace(tmp, path)
        return

    # A read-only destination fails MoveFileEx with ERROR_ACCESS_DENIED, which
    # is indistinguishable by winerror from the scanner race below - but it is
    # permanent, so retrying only spends the budget before failing anyway, and
    # Windows names the *source* in the error it raises, so the report points
    # at a temporary file the caller never named. Refuse up front, and say
    # which file is read-only (issue #412).
    if _is_read_only_file(path):
        raise PermissionError(
            errno.EACCES,
            "Destination is read-only; refusing to replace it",
            str(path),
        )

    deadline = time.monotonic() + _WINDOWS_REPLACE_RETRY_BUDGET_SECONDS
    while True:
        try:
            os.replace(tmp, path)
        except PermissionError as exc:
            if (
                getattr(exc, "winerror", None) not in _WINDOWS_TRANSIENT_REPLACE_ERRORS
                or time.monotonic() >= deadline
            ):
                raise
            time.sleep(_WINDOWS_REPLACE_RETRY_INTERVAL_SECONDS)
            continue
        return


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Atomically replace *path* from an exclusively created sibling file."""
    destination_mode: int | None = None
    try:
        destination = path.lstat()
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISLNK(destination.st_mode):
            # The rename replaces the *link*, not its target: the link is
            # severed, the real file is left stale, and the run exits 0 with
            # no notice. Refuse instead (issue #413).
            #
            # The alternative the issue offers - resolve the destination and
            # write through the link - is rejected. It would let a managed
            # write land on any path the link names, which is exactly what
            # this project's containment guard (`_assert_within`) exists to
            # prevent, and what `_open_atomic_temp`'s ``O_NOFOLLOW`` already
            # refuses for the temporary. Following a link here would be the
            # one place the write surface does not hold that line.
            raise OSError(
                errno.ELOOP,
                "Destination is a symbolic link; refusing to replace it",
                str(path),
            )
        if stat.S_ISREG(destination.st_mode):
            destination_mode = stat.S_IMODE(destination.st_mode)

    fd, tmp, identity = _open_atomic_temp(path)
    owns_tmp = True
    try:
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written == 0:
                raise OSError(f"Atomic write made no progress for {path}")
            view = view[written:]
        if destination_mode is not None and hasattr(os, "fchmod"):
            # Copy the destination's mode onto the temporary, but never
            # withhold owner-write from it: this file still has to be renamed
            # and, if that fails, deleted. Stamping a read-only destination's
            # mode here made the cleanup unlink fail and leaked the temporary
            # (issue #412). The exact mode is restored after the replace.
            os.fchmod(fd, destination_mode | stat.S_IWUSR)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        _assert_owned_temp(tmp, identity)
        _replace_atomic(tmp, path)
        owns_tmp = False
        if destination_mode is not None and not destination_mode & stat.S_IWUSR:
            # Only reached where the write bit was added above, so the common
            # case costs no syscall.
            os.chmod(path, destination_mode)
    finally:
        if fd >= 0:
            os.close(fd)
        if owns_tmp:
            _unlink_owned_temp(tmp, identity)


def atomic_write(path: Path, content: str) -> None:
    """Write UTF-8 content through :func:`atomic_write_bytes`.

    Args:
        path: Destination file path to write.
        content: Text content to write, encoded as UTF-8.
    """
    try:
        atomic_write_bytes(path, content.encode("utf-8"))
    except Exception as exc:
        logger.error("atomic_write failed for %s: %s", path, exc)
        raise


def launch_editor(editor: str, file_path: str) -> None:
    """Open *file_path* in *editor* for the scaffold-then-edit creation flows.

    A thin wrapper over :func:`vaultspec_core.core.editor.spawn_editor`, which
    owns tokenization, validation and the spawn. This entry point differs from
    the ``edit`` verbs only in what it does with the outcome: a resource is
    being *created* here, the file already exists on disk with its scaffold,
    and a non-zero editor status is therefore worth a warning rather than a
    failure.

    Args:
        editor: Editor command string (may include flags, e.g. ``"code --wait"``).
        file_path: Absolute path to the file to open in the editor.

    Raises:
        EditorValidationError: When the command is refused, or when the
            invocation has no terminal to attach an editor to.
    """
    from .editor import spawn_editor

    returncode = spawn_editor(editor, file_path, source="the configured default editor")
    if returncode != 0:
        logger.warning("Editor exited with code %d", returncode)


def collect_md_resources(
    src_dir: Path,
    warnings: list[str] | None = None,
) -> dict[str, tuple[Path, dict[str, Any], str]]:
    """Collect all ``*.md`` resource definitions from *src_dir*.

    Reads and parses frontmatter from every Markdown file found directly in
    *src_dir*, returning a mapping of filename -> (path, metadata, body).

    Args:
        src_dir: Directory to scan for ``*.md`` files.
        warnings: Optional list to append parse-error messages to, so callers
            can propagate them into :class:`~vaultspec_core.core.types.SyncResult`.

    Returns:
        Ordered mapping of filename to ``(source_path, frontmatter_dict, body_text)``
        tuples; empty if *src_dir* does not exist.
    """
    from ..vaultcore import parse_frontmatter

    sources: dict[str, tuple[Path, dict[str, Any], str]] = {}
    if not src_dir.exists():
        return sources
    for f in sorted(src_dir.glob("**/*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            rel_path = f.relative_to(src_dir).as_posix()
            sources[rel_path] = (f, meta, body)
        except Exception as e:
            logger.error("Failed to read/parse %s: %s", f, e)
            if warnings is not None:
                warnings.append(f"Failed to read/parse {f}: {e}")
    return sources


def kill_process_tree(pid: int) -> None:
    """Forcefully terminate a process and all its children.

    On Windows, uses ``taskkill /f /t /pid``. On other platforms, uses
    ``pkill -P``.

    Args:
        pid: Root process ID to kill.
    """
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/f", "/t", "/pid", str(pid)], capture_output=True)
    else:
        # Simple fallback for Unix; in production use psutil if available
        subprocess.run(["pkill", "-9", "-P", str(pid)], capture_output=True)
        subprocess.run(["kill", "-9", str(pid)], capture_output=True)


def package_version() -> str:
    """Return the running ``vaultspec-core`` package version string.

    Wraps :func:`importlib.metadata.version` and falls back to
    ``"unknown"`` so callers still complete when running from a
    development tree without installed metadata. The fallback parses
    via :func:`parse_version_tuple` to the empty tuple, which sorts
    strictly below any real version - safe for "is the workspace below
    the running version?" comparisons.
    """
    try:
        from importlib.metadata import version

        return version("vaultspec-core")
    except Exception:
        return "unknown"


def parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse a PEP 440 version string into a comparable integer tuple.

    Strips any pre/post/dev suffixes and splits on dots. An empty string
    parses to ``()`` so the empty-manifest case sorts strictly below any
    real version.

    Args:
        version_str: Version string like ``"0.1.4"`` or ``"1.2.3rc1"``.

    Returns:
        Tuple of integer version segments.

    Raises:
        ValueError: If the cleaned string contains a non-integer segment
            (e.g. ``"1.x"``).
    """
    import re

    if not version_str:
        return ()
    clean = re.split(r"[^0-9.]", version_str)[0].rstrip(".")
    if not clean:
        return ()
    return tuple(int(x) for x in clean.split("."))
