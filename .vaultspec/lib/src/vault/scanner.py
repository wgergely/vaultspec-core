from __future__ import annotations

from typing import TYPE_CHECKING

from vault.models import DocType, VaultConstants

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator


def scan_vault(root_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Yields all markdown files in the .vault/ directory."""
    docs_dir = root_dir / VaultConstants.DOCS_DIR
    if not docs_dir.exists():
        return

    for path in docs_dir.rglob("*.md"):
        # Skip internal config
        if ".obsidian" in path.parts:
            continue
        yield path


def get_doc_type(path: pathlib.Path, root_dir: pathlib.Path) -> DocType | None:
    """Determines the DocType based on the file's parent directory."""
    docs_dir = root_dir / VaultConstants.DOCS_DIR
    try:
        rel_path = path.relative_to(docs_dir)
        if len(rel_path.parts) < 2:
            return None
        return DocType(rel_path.parts[0])
    except (ValueError, KeyError):
        return None
