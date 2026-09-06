"""Symlink containment for the legacy-index relocation migration.

The migration scans the docs tree for ``*.index.md`` files and relocates
each into ``.vault/index/``. ``rglob`` will not descend *through* a symlinked
directory, but the ``is_file()`` filter that follows it does follow a
symlinked *file*, so a link planted in the docs tree was adopted as a legacy
index and its target's bytes were carried into the index directory.

That directory is not an ordinary output. It is regenerated summary material
that agents read, so content copied into it is content pulled into a model's
context. A migration is a poor place to acquire a new read of a file the
workspace never authored, which is why a symlinked candidate is skipped
rather than adopted.

Symlink creation needs developer mode or elevation on Windows. On a host
that refuses it the scenario cannot be staged at all, so the refusal itself
is asserted and the test ends; on every capable host the link is real and
the full scenario runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.migrations.m_0_1_17_index_subfolder import migrate

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

pytestmark = [pytest.mark.unit]

_SECRET = "outside content the vault never authored\n"


@pytest.fixture(autouse=True)
def reset_cfg() -> Generator[None]:
    reset_config()
    yield
    reset_config()


def _index_text(feature: str) -> str:
    return (
        f"---\ntags:\n  - '#index'\n  - '#{feature}'\n"
        f"date: '2026-01-01'\n---\n\n# `{feature}` index\n"
    )


class TestSymlinkedLegacyIndexIsNotAdopted:
    """A link planted in the docs tree may not import its target."""

    def test_a_symlinked_legacy_index_is_skipped_and_left_alone(
        self, tmp_path: Path
    ) -> None:
        """The target's bytes must not appear under ``.vault/index/``.

        The planted link is a *file* link, which is the case ``rglob``'s
        directory discipline does not cover: ``is_file()`` follows it and
        reports a perfectly ordinary index file.
        """
        docs = tmp_path / ".vault"
        docs.mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.index.md"
        secret.write_text(_SECRET, encoding="utf-8")

        link = docs / "planted.index.md"
        try:
            link.symlink_to(secret)
        except (OSError, NotImplementedError):
            assert not link.exists(), "refused symlink left an artifact behind"
            return

        result = migrate(tmp_path)

        index_dir = docs / "index"
        relocated = sorted(index_dir.iterdir()) if index_dir.is_dir() else []
        assert relocated == []
        assert result.counts["moved"] == 0
        # The source is untouched: skipping is not deleting.
        assert link.is_symlink()
        assert secret.read_text(encoding="utf-8") == _SECRET

    def test_a_real_legacy_index_beside_the_link_still_migrates(
        self, tmp_path: Path
    ) -> None:
        """Skipping the link must not cost the migration its actual job.

        A guard that made the whole migration bail out would leave the
        workspace on the old layout forever, which is a worse outcome than
        the one being prevented.
        """
        docs = tmp_path / ".vault"
        docs.mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.index.md"
        secret.write_text(_SECRET, encoding="utf-8")
        genuine = docs / "genuine.index.md"
        genuine.write_text(_index_text("genuine"), encoding="utf-8")

        link = docs / "planted.index.md"
        try:
            link.symlink_to(secret)
        except (OSError, NotImplementedError):
            assert not link.exists(), "refused symlink left an artifact behind"
            return

        result = migrate(tmp_path)

        moved = docs / "index" / "genuine.index.md"
        assert moved.is_file()
        assert not genuine.exists()
        assert result.counts["moved"] == 1
        assert _SECRET not in moved.read_text(encoding="utf-8")
        assert not (docs / "index" / "planted.index.md").exists()
