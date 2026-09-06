"""The safety net under the destructive migrations.

Three properties, each asserted against a real workspace on disk:

- **Backed up.** Every document a migration removes exists in
  ``.vault/.trash/`` first, byte for byte. The comparison is against bytes
  captured before the run, so a copy that lost a CRLF or an accent fails.
- **Refusal.** A snapshot that cannot be written aborts the migration with
  *nothing* deleted. Deleting because the backup failed is the one outcome
  worse than not deleting.
- **Faithful preview.** The set ``migrations run --dry-run`` enumerates is
  exactly the set a real run goes on to remove. Asserted as list equality
  between the preview and the observed difference on disk, because a
  preview computed differently from the run it precedes is worse than no
  preview - it is trusted.

Real temporary workspaces and real filesystem failures throughout. No
mocks, no patches, no skips.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.migrations import MigrationError, preview_deletions
from vaultspec_core.migrations.m_0_1_74_exec_ledger_only import migrate, preview
from vaultspec_core.vaultcore.trash import RESTORE_FILENAME, trash_root

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

pytestmark = [pytest.mark.unit]

_FOLDER = "2026-05-17-demo"
_PLAN_STEM = "2026-05-17-demo-plan"

#: Deliberately not plain ASCII with LF: a copy that normalises newlines or
#: re-encodes would still "look" restored while failing byte equality.
_PROSE = "Prose no consumer reads — café, naïve, déjà vu.\r\n"


@pytest.fixture(autouse=True)
def reset_cfg() -> Generator[None]:
    reset_config()
    yield
    reset_config()


def _skeleton(root: Path) -> Path:
    """Install the ledger template and a parent plan; return the exec folder."""
    from pathlib import Path as _Path

    folder = root / ".vault" / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (root / ".vaultspec" / "templates").mkdir(parents=True, exist_ok=True)
    src = (
        _Path(__file__).resolve().parents[2]
        / "builtins"
        / "templates"
        / "exec-ledger.md"
    )
    (root / ".vaultspec" / "templates" / "exec-ledger.md").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    plan_dir = root / ".vault" / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / f"{_PLAN_STEM}.md").write_text(
        "---\ntags:\n  - '#plan'\n  - '#demo'\ndate: '2026-05-17'\n"
        "modified: '2026-05-17'\ntier: L2\nrelated: []\n---\n\n"
        "# `demo` plan\n\n## Description\n\nProse.\n\n"
        "### Phase `P01` - one\n\n"
        "- [x] `P01.S01` - first; `src/foo.py`.\n"
        "- [x] `P01.S02` - second; `src/bar.py`.\n\n"
        "## Parallelization\n\nProse.\n\n## Verification\n\nProse.\n",
        encoding="utf-8",
    )
    return folder


def _record(root: Path, name: str, *, step_id: str) -> Path:
    folder = root / ".vault" / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_bytes(
        (
            "---\ntags:\n  - '#exec'\n  - '#demo'\ndate: '2026-05-17'\n"
            f"body_schema: 'body-v1'\nstep_id: '{step_id}'\nrelated:\n"
            f"  - '[[{_PLAN_STEM}]]'\n---\n\n# did a thing\n\n"
            "## Scope\n\n- `src/foo.py`\n\n"
            f"## Description\n\n{_PROSE}"
        ).encode()
    )
    return path


def _corpus(root: Path, count: int = 3) -> dict[Path, bytes]:
    """Plant *count* foldable records; return each path's original bytes."""
    _skeleton(root)
    return {
        record: record.read_bytes()
        for record in (
            _record(root, f"{_FOLDER}-P01-S{index:02d}", step_id=f"S{index:02d}")
            for index in range(1, count + 1)
        )
    }


def _sole_snapshot(root: Path) -> Path:
    """Return the one snapshot directory the run created."""
    snapshots = sorted(item for item in trash_root(root).iterdir() if item.is_dir())
    assert len(snapshots) == 1, f"expected exactly one snapshot, found {snapshots}"
    return snapshots[0]


class TestSnapshotBeforeDestruction:
    def test_every_removed_record_is_copied_byte_for_byte(self, tmp_path: Path) -> None:
        originals = _corpus(tmp_path)

        result = migrate(tmp_path)

        assert result.counts["folded"] == len(originals)
        assert all(not record.exists() for record in originals), (
            "the migration must still remove the records it folded"
        )
        snapshot = _sole_snapshot(tmp_path)
        for record, payload in originals.items():
            copy = snapshot / "exec" / _FOLDER / record.name
            assert copy.is_file(), f"{record.name} was deleted without a backup"
            assert copy.read_bytes() == payload, (
                f"{record.name}'s backup is not byte-identical to the original"
            )

    def test_the_result_names_the_snapshot_and_its_size(self, tmp_path: Path) -> None:
        originals = _corpus(tmp_path)

        result = migrate(tmp_path)

        assert result.snapshot == str(_sole_snapshot(tmp_path))
        assert result.counts["snapshot_bytes"] == sum(
            len(payload) for payload in originals.values()
        )
        assert ".trash/" in result.summary

    def test_the_snapshot_carries_a_restore_index(self, tmp_path: Path) -> None:
        originals = _corpus(tmp_path, count=2)

        migrate(tmp_path)

        index = (_sole_snapshot(tmp_path) / RESTORE_FILENAME).read_text(
            encoding="utf-8"
        )
        for record in originals:
            assert f".vault/exec/{_FOLDER}/{record.name}" in index

    def test_a_restored_copy_is_the_document_that_was_removed(
        self, tmp_path: Path
    ) -> None:
        """The whole promise: copy it back and you have your document.

        Asserted by performing the documented recovery - a plain file copy
        from the snapshot to the original path - and comparing bytes.
        """
        originals = _corpus(tmp_path, count=1)
        record, payload = next(iter(originals.items()))

        migrate(tmp_path)
        copy = _sole_snapshot(tmp_path) / "exec" / _FOLDER / record.name
        record.write_bytes(copy.read_bytes())

        assert record.read_bytes() == payload

    def test_the_snapshot_is_not_vault_content(self, tmp_path: Path) -> None:
        """A backup that re-enters the corpus is a duplicate, not a backup."""
        from vaultspec_core.vaultcore.scanner import scan_vault

        _corpus(tmp_path)
        migrate(tmp_path)
        snapshot = _sole_snapshot(tmp_path)

        scanned = list(scan_vault(tmp_path))

        assert scanned, "the workspace still has documents to scan"
        assert not any(snapshot in path.parents for path in scanned), (
            "snapshot copies must not be scanned as vault documents"
        )


class TestFailedSnapshotAborts:
    def test_unwritable_trash_stops_the_migration_with_nothing_deleted(
        self, tmp_path: Path
    ) -> None:
        """A `.trash` that is a file makes the snapshot impossible.

        A real, portable filesystem failure of the same class as a full
        disk: the directory cannot be created. Every record must survive.
        """
        originals = _corpus(tmp_path)
        trash_root(tmp_path).write_text("not a directory", encoding="utf-8")

        with pytest.raises(MigrationError, match="without a backup"):
            migrate(tmp_path)

        for record, payload in originals.items():
            assert record.is_file(), f"{record.name} was deleted without a backup"
            assert record.read_bytes() == payload

    def test_the_manifest_is_not_bumped_when_the_snapshot_fails(
        self, tmp_path: Path
    ) -> None:
        """The driver's contract: a raising migration leaves the version alone.

        So the next invocation re-attempts the fold once the operator has
        cleared whatever made the snapshot impossible.
        """
        from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data
        from vaultspec_core.migrations import run_pending_migrations

        originals = _corpus(tmp_path)
        (tmp_path / ".vaultspec").mkdir(parents=True, exist_ok=True)
        manifest = read_manifest_data(tmp_path)
        manifest.vaultspec_version = "0.1.57"
        write_manifest_data(tmp_path, manifest)
        trash_root(tmp_path).write_text("not a directory", encoding="utf-8")

        with pytest.raises(MigrationError):
            run_pending_migrations(tmp_path)

        assert read_manifest_data(tmp_path).vaultspec_version == "0.1.57"
        assert all(record.is_file() for record in originals)


class TestPreviewMatchesTheRun:
    def test_the_preview_equals_what_the_run_removes(self, tmp_path: Path) -> None:
        """The test that makes the preview trustworthy.

        The enumeration is captured before the run and compared against the
        difference the run actually made on disk. Any divergence - a path
        previewed but kept, or removed but unpreviewed - fails here.
        """
        _corpus(tmp_path, count=4)
        before = {
            path for path in (tmp_path / ".vault").rglob("*.md") if path.is_file()
        }
        previewed = sorted(preview(tmp_path))

        migrate(tmp_path)

        after = {path for path in (tmp_path / ".vault").rglob("*.md") if path.is_file()}
        removed = sorted(before - after)
        assert previewed, "the fixture must give the migration something to remove"
        assert previewed == removed

    def test_the_preview_removes_nothing_itself(self, tmp_path: Path) -> None:
        originals = _corpus(tmp_path)

        assert preview(tmp_path)

        for record, payload in originals.items():
            assert record.read_bytes() == payload
        assert not trash_root(tmp_path).exists()

    def test_the_registry_preview_covers_the_pending_entries(
        self, tmp_path: Path
    ) -> None:
        from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data

        _corpus(tmp_path)
        (tmp_path / ".vaultspec").mkdir(parents=True, exist_ok=True)
        manifest = read_manifest_data(tmp_path)
        manifest.vaultspec_version = "0.1.57"
        write_manifest_data(tmp_path, manifest)

        previews = preview_deletions(tmp_path)

        by_name = {entry.name: entry for entry in previews}
        assert "exec_ledger_only" in by_name
        assert by_name["exec_ledger_only"].previewable
        assert by_name["exec_ledger_only"].paths
        assert all(entry.previewable for entry in previews), (
            "every pending entry must be able to say what it deletes"
        )

    def test_an_already_folded_workspace_previews_no_deletions(
        self, tmp_path: Path
    ) -> None:
        _corpus(tmp_path)
        migrate(tmp_path)

        assert preview(tmp_path) == []


class TestIdempotenceSurvivesTheNet:
    def test_a_second_run_neither_folds_nor_snapshots(self, tmp_path: Path) -> None:
        _corpus(tmp_path)
        migrate(tmp_path)
        first = _sole_snapshot(tmp_path)
        contents = sorted(path.name for path in first.rglob("*"))

        second = migrate(tmp_path)

        assert second.counts["folded"] == 0
        assert second.snapshot is None
        assert _sole_snapshot(tmp_path) == first
        assert sorted(path.name for path in first.rglob("*")) == contents
