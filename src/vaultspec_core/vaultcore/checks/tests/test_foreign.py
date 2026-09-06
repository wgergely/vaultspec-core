"""Real-filesystem tests for the ``foreign`` checker.

Builds real on-disk workspaces (real ``.vaultspec/`` and ``.vault/`` trees,
real bytes, no test doubles) and asserts the checker's contract: recognised
resource categories and their contents stay clean, a foreign top-level entry
under ``.vaultspec/`` and a foreign file nested inside a ``.vault/`` document
directory are each reported as a single WARNING that never raises the error
count driving the CLI exit code, and a genuine ``.vault/.trash/`` pre-deletion
snapshot (built through the real :class:`~vaultspec_core.vaultcore.trash.TrashWriter`)
alongside an ``_archive/`` document are never flagged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .._base import Severity
from ..foreign import check_foreign

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]

DATE = "2026-07-20"


def _frontmatter(doc_type: str, feature: str) -> str:
    return (
        f"---\ntags:\n  - '#{doc_type}'\n  - '#{feature}'\n"
        f"date: '{DATE}'\nmodified: '{DATE}'\nrelated: []\n---\n"
    )


def _write_vault_doc(
    root: Path, doc_type: str, feature: str, *, stem: str = ""
) -> Path:
    fm = _frontmatter(doc_type, feature)
    name = stem or f"{DATE}-{feature}-{doc_type}"
    path = root / ".vault" / doc_type / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{fm}\n# {feature} {doc_type}\n\nBody.\n", encoding="utf-8")
    return path


def _seed_recognised_vaultspec_tree(root: Path) -> None:
    """Populate every real builtins resource category, plus runtime artifacts.

    Uses the real bundled ``builtins`` tree (no stand-in list) so the fixture
    can never drift from what an actual install seeds.
    """
    from vaultspec_core.builtins import builtins_root

    fw_dir = root / ".vaultspec"
    for category in builtins_root().iterdir():
        if not category.is_dir() or category.name == "__pycache__":
            continue
        dest = fw_dir / category.name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "placeholder.md").write_text("seeded\n", encoding="utf-8")

    (fw_dir / "_snapshots").mkdir(parents=True, exist_ok=True)
    (fw_dir / "workspace.json").write_text("{}\n", encoding="utf-8")
    (fw_dir / "providers.json").write_text("{}\n", encoding="utf-8")
    (fw_dir / "mcp-ownership.json").write_text("{}\n", encoding="utf-8")
    (fw_dir / "providers.json.lock").write_text("", encoding="utf-8")


class TestCheckForeignVaultspecTree:
    def test_recognised_tree_has_no_warnings(self, tmp_path: Path) -> None:
        _seed_recognised_vaultspec_tree(tmp_path)

        result = check_foreign(tmp_path)

        assert result.check_name == "foreign"
        assert result.is_clean
        assert result.error_count == 0

    def test_authored_content_inside_extension_points_is_not_flagged(
        self, tmp_path: Path
    ) -> None:
        """Adding project-authored rules/skills is expected, not foreign."""
        _seed_recognised_vaultspec_tree(tmp_path)
        (tmp_path / ".vaultspec" / "rules" / "my-project-rule.md").write_text(
            "authored\n", encoding="utf-8"
        )
        skill_dir = tmp_path / ".vaultspec" / "skills" / "my-project-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("authored skill\n", encoding="utf-8")

        result = check_foreign(tmp_path)

        assert result.is_clean

    def test_foreign_directory_under_vaultspec_is_a_warning(
        self, tmp_path: Path
    ) -> None:
        """Reproduces issue #450: application tests under .vaultspec/tests/."""
        _seed_recognised_vaultspec_tree(tmp_path)
        foreign_dir = tmp_path / ".vaultspec" / "tests" / "clitui_ledger"
        foreign_dir.mkdir(parents=True)
        (foreign_dir / "test_campaign.py").write_text(
            "def test_x(): pass\n", encoding="utf-8"
        )

        result = check_foreign(tmp_path)

        assert result.error_count == 0
        assert result.warning_count == 1
        diag = result.diagnostics[0]
        assert diag.severity == Severity.WARNING
        assert diag.fixable is False
        assert diag.path is not None
        assert diag.path.as_posix() == ".vaultspec/tests"
        assert ".vaultspec/" in diag.message
        assert "tests" in diag.message

    def test_foreign_file_under_vaultspec_root_is_a_warning(
        self, tmp_path: Path
    ) -> None:
        _seed_recognised_vaultspec_tree(tmp_path)
        (tmp_path / ".vaultspec" / "scratch.txt").write_text(
            "not framework content\n", encoding="utf-8"
        )

        result = check_foreign(tmp_path)

        assert result.warning_count == 1
        assert result.error_count == 0
        diag = result.diagnostics[0]
        assert diag.path is not None
        assert diag.path.as_posix() == ".vaultspec/scratch.txt"

    def test_dot_prefixed_vaultspec_entries_are_not_flagged(
        self, tmp_path: Path
    ) -> None:
        """Editor/VCS state such as .git is not the framework's to judge."""
        _seed_recognised_vaultspec_tree(tmp_path)
        dotdir = tmp_path / ".vaultspec" / ".git"
        dotdir.mkdir(parents=True)
        (dotdir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

        result = check_foreign(tmp_path)

        assert result.is_clean

    def test_missing_vaultspec_dir_is_not_flagged(self, tmp_path: Path) -> None:
        """A bare workspace with no framework installed is not pollution."""
        result = check_foreign(tmp_path)
        assert result.is_clean


class TestCheckForeignVaultTree:
    def test_clean_vault_has_no_warnings(self, tmp_path: Path) -> None:
        _write_vault_doc(tmp_path, "adr", "clean-feature")
        _write_vault_doc(tmp_path, "research", "clean-feature")

        result = check_foreign(tmp_path)

        assert result.is_clean

    def test_non_markdown_file_inside_document_dir_is_a_warning(
        self, tmp_path: Path
    ) -> None:
        _write_vault_doc(tmp_path, "adr", "clean-feature")
        stray = tmp_path / ".vault" / "adr" / "notes.txt"
        stray.write_text("scratch notes\n", encoding="utf-8")

        result = check_foreign(tmp_path)

        assert result.error_count == 0
        assert result.warning_count == 1
        diag = result.diagnostics[0]
        assert diag.severity == Severity.WARNING
        assert diag.fixable is False
        assert diag.path is not None and diag.path.as_posix() == ".vault/adr/notes.txt"
        assert ".vault/adr/" in diag.message

    def test_nested_non_markdown_file_under_exec_feature_dir_is_a_warning(
        self, tmp_path: Path
    ) -> None:
        """Reproduces the cadrumo shape: application code nested inside exec/."""
        _write_vault_doc(tmp_path, "exec", "my-feature", stem=f"{DATE}-my-feature-s01")
        stray = (
            tmp_path / ".vault" / "exec" / f"{DATE}-my-feature" / "campaign_helpers.py"
        )
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("VALUE = 1\n", encoding="utf-8")

        result = check_foreign(tmp_path)

        assert result.warning_count == 1
        diag = result.diagnostics[0]
        assert diag.path is not None
        assert diag.path.as_posix() == (
            f".vault/exec/{DATE}-my-feature/campaign_helpers.py"
        )

    def test_auxiliary_data_and_logs_dirs_are_not_walked(self, tmp_path: Path) -> None:
        _write_vault_doc(tmp_path, "adr", "clean-feature")
        (tmp_path / ".vault" / "data").mkdir(parents=True)
        (tmp_path / ".vault" / "data" / "index.sqlite").write_bytes(b"\x00\x01")
        (tmp_path / ".vault" / "logs").mkdir(parents=True)
        (tmp_path / ".vault" / "logs" / "run.log").write_text("log\n", encoding="utf-8")

        result = check_foreign(tmp_path)

        assert result.is_clean

    def test_missing_vault_dir_is_not_flagged(self, tmp_path: Path) -> None:
        result = check_foreign(tmp_path)
        assert result.is_clean


class TestCheckForeignExclusions:
    def test_trash_snapshot_and_archive_document_are_not_flagged(
        self, tmp_path: Path
    ) -> None:
        """A real pre-deletion snapshot and an archived document must be clean.

        Builds the snapshot through the real
        :class:`~vaultspec_core.vaultcore.trash.TrashWriter` used by every
        deleting migration, rather than hand-placing files at a guessed path,
        so this exercises the same shape ``check_foreign`` will actually see
        in production - including the non-``.md`` ``RESTORE.txt`` index the
        writer places beside every copy, which would trip the "non-.md is
        foreign" rule if the ``.trash/`` subtree were not excluded.
        """
        from vaultspec_core.vaultcore.trash import TrashWriter

        adr_path = _write_vault_doc(tmp_path, "adr", "about-to-be-removed")
        writer = TrashWriter(tmp_path, label="test-migration")
        writer.capture([adr_path])
        snapshot = writer.result()
        assert snapshot is not None
        assert (snapshot.root / "RESTORE.txt").is_file()
        assert any(snapshot.root.rglob("*.md"))

        # archive_feature() preserves the per-type subdirectory under _archive/.
        archived = (
            tmp_path / ".vault" / "_archive" / "adr" / f"{DATE}-old-feature-adr.md"
        )
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_text(
            _frontmatter("adr", "old-feature") + "\n# retired\n", encoding="utf-8"
        )
        # A non-.md file living in _archive/ must be just as invisible as one
        # in .trash/: both are retired/backup content the framework must never
        # nag an operator to move.
        (tmp_path / ".vault" / "_archive" / "adr" / "notes.txt").write_text(
            "why this was archived\n", encoding="utf-8"
        )

        adr_path.unlink()  # the writer copied it; the migration would now delete it
        result = check_foreign(tmp_path)

        assert result.is_clean, result.diagnostics


class TestCheckForeignInRunAllChecks:
    def test_vault_check_all_surfaces_the_foreign_check(self, tmp_path: Path) -> None:
        from .. import run_all_checks

        _write_vault_doc(tmp_path, "adr", "clean-feature")
        stray = tmp_path / ".vault" / "research" / "scratch.py"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("VALUE = 1\n", encoding="utf-8")

        results = run_all_checks(tmp_path, fix=False)
        by_name = {r.check_name: r for r in results}

        assert "foreign" in by_name, "run_all_checks must include the foreign check"
        assert by_name["foreign"].warning_count == 1
        assert by_name["foreign"].error_count == 0
