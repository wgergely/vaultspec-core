"""Tests for verification conformance and repair behavior.

Exercises structural verification, per-file checks, feature extraction,
vertical integrity, and repair flows over the bundled vaultcore fixtures.
"""

import pytest

from .. import (
    FixResult,
    VerificationError,
    fix_violations,
    get_malformed,
    list_features,
    verify_file,
    verify_vault_structure,
    verify_vertical_integrity,
)

pytestmark = [pytest.mark.unit]


class TestVerificationError:
    def test_init(self):
        from pathlib import Path

        err = VerificationError(Path("test.md"), "bad file")
        assert err.path == Path("test.md")
        assert err.message == "bad file"

    def test_str(self):
        from pathlib import Path

        err = VerificationError(Path("test.md"), "bad file")
        assert str(err) == "test.md: bad file"


class TestVerifyVaultStructure:
    def test_valid_known_dirs(self, vault_root):
        errors = verify_vault_structure(vault_root)
        # test-project has some non-standard dirs (audit, stories)
        # so we just verify the function returns a list
        assert isinstance(errors, list)

    def test_detects_nonstandard_dirs(self, vault_root):
        errors = verify_vault_structure(vault_root)
        # test-project has "stories" which is not a valid DocType dir
        error_strs = [str(e) for e in errors]
        assert any("stories" in s for s in error_strs)


class TestVerifyFile:
    def test_valid_file(self, vault_root):
        # Pick a known well-formed ADR that follows naming conventions
        path = (
            vault_root
            / ".vault"
            / "adr"
            / "2026-02-06-incremental-layout-engine-design-adr.md"
        )
        errors = verify_file(path, vault_root)
        assert len(errors) == 0


class TestGetMalformed:
    def test_returns_list(self, vault_root):
        errors = get_malformed(vault_root)
        assert isinstance(errors, list)


class TestListFeatures:
    def test_extracts_features(self, vault_root):
        features = list_features(vault_root)
        assert "editor-demo" in features

    def test_excludes_directory_tags(self, vault_root):
        features = list_features(vault_root)
        assert "adr" not in features
        assert "plan" not in features
        assert "research" not in features

    def test_returns_many_features(self, vault_root):
        features = list_features(vault_root)
        assert len(features) > 5


class TestVerifyVerticalIntegrity:
    def test_returns_list(self, vault_root):
        errors = verify_vertical_integrity(vault_root)
        assert isinstance(errors, list)

    def test_covered_feature_not_flagged(self, vault_root):
        errors = verify_vertical_integrity(vault_root)
        # editor-demo has both ADR and plan docs
        error_msgs = [e.message for e in errors]
        assert not any("editor-demo" in m for m in error_msgs)


class TestFixResult:
    def test_init(self):
        from pathlib import Path

        result = FixResult(Path("test.md"), "add_tags", "Added tags: [#adr]")
        assert result.path == Path("test.md")
        assert result.action == "add_tags"
        assert result.detail == "Added tags: [#adr]"

    def test_str(self):
        from pathlib import Path

        result = FixResult(Path("test.md"), "add_tags", "Added tags: [#adr]")
        assert str(result) == "test.md: add_tags - Added tags: [#adr]"


class TestFixViolations:
    def test_fixes_missing_tags(self, tmp_path):
        """Test that missing tags are added based on directory."""
        vault_dir = tmp_path / ".vault" / "adr"
        vault_dir.mkdir(parents=True)

        test_file = vault_dir / "2026-02-18-test-feature-adr.md"
        test_file.write_text(
            "---\ndate: 2026-02-18\n---\n\n# Test\n",
            encoding="utf-8",
        )

        fixes = fix_violations(tmp_path)

        assert len(fixes) > 0
        assert any(f.action == "add_doc_type_tag" for f in fixes)

        # Verify the file was updated
        content = test_file.read_text(encoding="utf-8")
        assert "#adr" in content

    def test_fixes_missing_date_prefix(self, tmp_path):
        """Test that missing date prefix is added."""
        vault_dir = tmp_path / ".vault" / "research"
        vault_dir.mkdir(parents=True)

        test_file = vault_dir / "no-date.md"
        test_file.write_text(
            '---\ntags: ["#research", "#test"]\ndate: 2026-02-18\n---\n\n# Test\n',
            encoding="utf-8",
        )

        fixes = fix_violations(tmp_path)

        assert len(fixes) > 0
        assert any(f.action == "add_date_prefix" for f in fixes)

        # Verify file was renamed
        assert not test_file.exists()
        renamed_files = list(vault_dir.glob("2026-*-no-date.md"))
        assert len(renamed_files) == 1

    def test_fixes_wrong_suffix(self, tmp_path):
        """Test that wrong filename suffix is corrected."""
        vault_dir = tmp_path / ".vault" / "plan"
        vault_dir.mkdir(parents=True)

        test_file = vault_dir / "2026-02-18-test-feature.md"
        test_file.write_text(
            '---\ntags: ["#plan", "#test"]\ndate: 2026-02-18\n---\n\n# Test\n',
            encoding="utf-8",
        )

        fixes = fix_violations(tmp_path)

        assert len(fixes) > 0
        assert any(f.action == "rename_suffix" for f in fixes)

        # Verify file was renamed with correct suffix
        assert not test_file.exists()
        correct_file = vault_dir / "2026-02-18-test-feature-plan.md"
        assert correct_file.exists()

    def test_handles_bom(self, tmp_path):
        """Test that BOM is handled correctly."""
        vault_dir = tmp_path / ".vault" / "reference"
        vault_dir.mkdir(parents=True)

        test_file = vault_dir / "2026-02-18-test-bom-reference.md"
        # Write with BOM
        test_file.write_text(
            "\ufeff---\ndate: 2026-02-18\n---\n\n# Test\n",
            encoding="utf-8",
        )

        fixes = fix_violations(tmp_path)

        # Should add tags despite BOM
        assert len(fixes) > 0
        assert any(f.action == "add_doc_type_tag" for f in fixes)

        # Verify file was updated without BOM
        content = test_file.read_text(encoding="utf-8")
        assert not content.startswith("\ufeff")
        assert "#reference" in content

    def test_no_fixes_for_valid_file(self, tmp_path):
        """Test that valid files are not modified."""
        vault_dir = tmp_path / ".vault" / "adr"
        vault_dir.mkdir(parents=True)

        valid_file = vault_dir / "2026-02-18-test-valid-adr.md"
        valid_file.write_text(
            '---\ntags: ["#adr", "#test"]\ndate: 2026-02-18\n---\n\n# Test Valid\n',
            encoding="utf-8",
        )

        fixes = fix_violations(tmp_path)
        assert isinstance(fixes, list)
        assert len(fixes) == 0
