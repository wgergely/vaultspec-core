import pytest

from tests.constants import PROJECT_ROOT, TEST_PROJECT

from .. import (
    SecurityError,
    find_project_root,
    safe_read_text,
)

pytestmark = [pytest.mark.unit]


class TestSecurityError:
    def test_is_exception(self):
        assert issubclass(SecurityError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(SecurityError, match="test message"):
            raise SecurityError("test message")


class TestSafeReadText:
    def test_reads_file_within_workspace(self):
        # test-project has a .vault/ with real markdown files
        adr_dir = TEST_PROJECT / ".vault" / "adr"
        md_files = list(adr_dir.glob("*.md"))
        assert len(md_files) > 0
        result = safe_read_text(md_files[0], TEST_PROJECT)
        assert len(result) > 0

    def test_reads_nested_file(self):
        path = (
            TEST_PROJECT
            / ".vault"
            / "adr"
            / "2026-02-05-editor-demo-architecture-adr.md"
        )
        result = safe_read_text(path, TEST_PROJECT)
        assert "editor" in result.lower()

    def test_raises_file_not_found(self):
        missing = TEST_PROJECT / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            safe_read_text(missing, TEST_PROJECT)

    def test_raises_security_error_for_path_outside_workspace(self):
        # Try to read a file outside test-project via the parent
        outside_file = PROJECT_ROOT / "pyproject.toml"
        with pytest.raises(SecurityError):
            safe_read_text(outside_file, TEST_PROJECT)


class TestFindProjectRoot:
    def test_finds_git_root(self):
        # test-project is inside a git repo, so walking up should find .git
        result = find_project_root(start_dir=TEST_PROJECT)
        assert (result / ".git").exists()
