"""Tests for builtin resource revert mechanism."""

import pytest

from vaultspec_core.core.revert import (
    get_snapshot_content,
    is_builtin,
    list_modified_builtins,
    revert_resource,
    snapshot_builtins,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture
def vaultspec_dir(tmp_path):
    """Create a minimal .vaultspec structure with builtin files."""
    vs = tmp_path / ".vaultspec"
    rules_rules = vs / "rules" / "rules"
    rules_rules.mkdir(parents=True)

    # Create a builtin rule
    builtin = rules_rules / "governance.builtin.md"
    builtin.write_text(
        "---\nname: governance\n---\nOriginal content.\n", encoding="utf-8"
    )

    # Create a custom rule (not builtin)
    custom = rules_rules / "my-rule.md"
    custom.write_text("Custom rule content.", encoding="utf-8")

    # Create a builtin in skills category
    rules_skills = vs / "rules" / "skills"
    rules_skills.mkdir(parents=True)
    skill_builtin = rules_skills / "code-review.builtin.md"
    skill_builtin.write_text(
        "---\nname: code-review\n---\nOriginal skill.\n", encoding="utf-8"
    )

    return vs


class TestIsBuiltin:
    def test_detects_builtin_suffix(self):
        assert is_builtin("governance.builtin.md") is True

    def test_rejects_custom(self):
        assert is_builtin("my-custom-rule.md") is False

    def test_rejects_partial_match(self):
        assert is_builtin("builtin.md") is False


class TestSnapshotBuiltins:
    def test_snapshots_all_builtins(self, vaultspec_dir):
        count = snapshot_builtins(vaultspec_dir)
        assert count == 2  # governance.builtin.md + code-review.builtin.md

        # Check snapshots exist
        snap = vaultspec_dir / "_snapshots"
        assert (snap / "rules" / "governance.builtin.md").exists()
        assert (snap / "skills" / "code-review.builtin.md").exists()

        # Custom rule should NOT be snapshotted
        assert not (snap / "rules" / "my-rule.md").exists()

    def test_snapshot_preserves_content(self, vaultspec_dir):
        snapshot_builtins(vaultspec_dir)
        snap_content = (
            vaultspec_dir / "_snapshots" / "rules" / "governance.builtin.md"
        ).read_text(encoding="utf-8")
        assert "Original content." in snap_content

    def test_snapshot_overwrites_existing(self, vaultspec_dir):
        snapshot_builtins(vaultspec_dir)
        # Modify the source
        (vaultspec_dir / "rules" / "rules" / "governance.builtin.md").write_text(
            "Modified.", encoding="utf-8"
        )
        # Re-snapshot
        snapshot_builtins(vaultspec_dir)
        snap_content = (
            vaultspec_dir / "_snapshots" / "rules" / "governance.builtin.md"
        ).read_text(encoding="utf-8")
        assert snap_content == "Modified."

    def test_no_rules_dir_returns_zero(self, tmp_path):
        vs = tmp_path / ".vaultspec"
        vs.mkdir()
        assert snapshot_builtins(vs) == 0


class TestGetSnapshotContent:
    def test_returns_content(self, vaultspec_dir):
        snapshot_builtins(vaultspec_dir)
        content = get_snapshot_content(vaultspec_dir, "rules", "governance.builtin.md")
        assert content is not None
        assert "Original content." in content

    def test_returns_none_when_missing(self, vaultspec_dir):
        content = get_snapshot_content(vaultspec_dir, "rules", "nonexistent.builtin.md")
        assert content is None


class TestRevertResource:
    def test_reverts_modified_builtin(self, vaultspec_dir):
        snapshot_builtins(vaultspec_dir)
        # Modify the file
        target = vaultspec_dir / "rules" / "rules" / "governance.builtin.md"
        target.write_text("USER MODIFIED THIS.", encoding="utf-8")

        result = revert_resource(vaultspec_dir, "rules", "governance.builtin.md")
        assert result["reverted"] is True

        # Content should be restored
        restored = target.read_text(encoding="utf-8")
        assert "Original content." in restored

    def test_revert_custom_fails(self, vaultspec_dir):
        result = revert_resource(vaultspec_dir, "rules", "my-rule.md")
        assert result["reverted"] is False
        assert "not a builtin" in result["reason"].lower()

    def test_revert_without_snapshot_fails(self, vaultspec_dir):
        # No snapshot taken
        result = revert_resource(vaultspec_dir, "rules", "governance.builtin.md")
        assert result["reverted"] is False
        assert "no snapshot" in result["reason"].lower()


class TestListModifiedBuiltins:
    def test_detects_modified(self, vaultspec_dir):
        snapshot_builtins(vaultspec_dir)
        # Modify one
        (vaultspec_dir / "rules" / "rules" / "governance.builtin.md").write_text(
            "CHANGED.", encoding="utf-8"
        )

        modified = list_modified_builtins(vaultspec_dir)
        statuses = {m["filename"]: m["status"] for m in modified}
        assert statuses["governance.builtin.md"] == "modified"
        assert statuses["code-review.builtin.md"] == "ok"

    def test_detects_missing(self, vaultspec_dir):
        snapshot_builtins(vaultspec_dir)
        # Delete one
        (vaultspec_dir / "rules" / "rules" / "governance.builtin.md").unlink()

        modified = list_modified_builtins(vaultspec_dir)
        statuses = {m["filename"]: m["status"] for m in modified}
        assert statuses["governance.builtin.md"] == "missing"

    def test_no_snapshots_returns_empty(self, vaultspec_dir):
        assert list_modified_builtins(vaultspec_dir) == []
