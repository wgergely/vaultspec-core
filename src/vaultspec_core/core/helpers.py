"""Shared filesystem, YAML, and process helpers for vaultspec runtime code.

The functions here support multiple implementation layers rather than a single
feature area. They provide the low-level operations used by resource
management, config generation, syncing, and hook execution.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _yaml_load(text: str) -> dict[str, Any]:
    """Parse a YAML string and return a dict, defaulting to empty dict on empty input.

    Args:
        text: A YAML-formatted string to parse.

    Returns:
        Parsed key-value mapping, or an empty dict if *text* is empty or null.
    """
    return yaml.safe_load(text) or {}


class _LiteralStr(str):
    """Marker type for strings that should use YAML literal block scalar."""


def _literal_representer(dumper: yaml.Dumper, data: _LiteralStr) -> yaml.ScalarNode:
    """Represent a _LiteralStr value using YAML literal block scalar style (``|``).

    Args:
        dumper: The PyYAML Dumper instance performing serialization.
        data: The string value to represent with literal block style.

    Returns:
        A YAML ScalarNode configured with ``|`` block scalar style.
    """
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(_LiteralStr, _literal_representer)


def _yaml_dump(data: dict[str, Any]) -> str:
    """Serialize a dict to YAML, using literal block style for multi-line values.

    Args:
        data: Key-value mapping to serialize.

    Returns:
        YAML string representation with multi-line string values rendered as
        literal block scalars (``|``).
    """
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
    fm_str = _yaml_dump(frontmatter)
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


def _rmtree_robust(path: Path) -> None:
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

    def _on_error(
        func: Callable[..., object],
        fpath: str,
        exc_info: tuple[type, BaseException, object],
    ) -> None:
        if os.name == "nt":
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        else:
            raise exc_info[1]

    shutil.rmtree(path, onerror=_on_error)


def atomic_write(path: Path, content: str) -> None:
    """Write content to file atomically via tmp + rename.

    Args:
        path: Destination file path to write.
        content: Text content to write, encoded as UTF-8.
    """
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    try:
        tmp.write_bytes(content.encode("utf-8"))
        try:
            tmp.replace(path)
        except PermissionError as exc:
            if os.name != "nt":
                raise
            logger.warning(
                "atomic_write falling back to copy+unlink for %s "
                "after replace failed: %s",
                path,
                exc,
            )
            try:
                shutil.copyfile(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
    except Exception as exc:
        logger.error("atomic_write failed for %s: %s", path, exc)
        raise


def _launch_editor(editor: str, file_path: str) -> None:
    """Launch editor, handling Windows .cmd/.bat wrappers.

    Args:
        editor: Editor command string (may include flags, e.g. ``"code --wait"``).
        file_path: Absolute path to the file to open in the editor.
    """
    parts = editor.split()
    resolved = shutil.which(parts[0]) or parts[0]
    if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat")):
        result = subprocess.run(["cmd.exe", "/c", resolved, *parts[1:], file_path])
    else:
        result = subprocess.run([resolved, *parts[1:], file_path])
    if result.returncode != 0:
        logger.warning("Editor exited with code %d", result.returncode)


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
    for f in sorted(src_dir.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            sources[f.name] = (f, meta, body)
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
