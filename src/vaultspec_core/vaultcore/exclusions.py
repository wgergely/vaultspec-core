"""The one definition of which ``.vault/`` subtrees are not vault content.

Three directories under the docs root hold files that are shaped like vault
documents but are not part of the corpus:

- ``.obsidian/`` - editor state, owned by Obsidian.
- ``_archive/`` - documents deliberately retired from the live corpus.
- ``.trash/`` - pre-deletion snapshots written by
  :mod:`vaultspec_core.vaultcore.trash`.

Every walker over ``.vault/**/*.md`` shares this predicate so a file that one
consumer treats as corpus cannot be treated as non-corpus by the next. Before
this module the exclusion was an inlined ``".obsidian" in path.parts or
"_archive" in path.parts`` repeated at six sites, none of which named
``.trash`` - harmless only while nothing wrote there. A snapshot of a removed
document would otherwise re-enter the corpus as a duplicate of the document
it is the backup of, and the checks would report the backup as damage.

The mutating walkers (the rename cascade, the rename transaction snapshot)
already exclude every dot-prefixed directory by a wider rule of their own and
are left alone; this predicate is for the readers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["EXCLUDED_VAULT_DIR_NAMES", "is_excluded_vault_path"]

#: Directory names whose subtrees are never vault corpus.
EXCLUDED_VAULT_DIR_NAMES = frozenset({".obsidian", ".trash", "_archive"})


def is_excluded_vault_path(path: Path) -> bool:
    """Report whether *path* sits inside a non-corpus ``.vault/`` subtree.

    Args:
        path: Any path; matched by directory name anywhere in its parts, so
            it works on absolute and vault-relative paths alike.

    Returns:
        ``True`` when the path is editor state, archived, or a snapshot.
    """
    return any(part in EXCLUDED_VAULT_DIR_NAMES for part in path.parts)
