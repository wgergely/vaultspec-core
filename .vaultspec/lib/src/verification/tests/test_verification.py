import pytest
from verification.api import (
    VerificationError,
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
        # test-project has "audit" and "stories" which are not valid DocType dirs
        error_strs = [str(e) for e in errors]
        assert any("audit" in s or "stories" in s for s in error_strs)


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
