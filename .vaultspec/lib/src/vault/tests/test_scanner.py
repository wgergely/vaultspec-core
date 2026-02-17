import pytest
from core.config import reset_config
from tests.constants import TEST_PROJECT
from vault.models import DocType
from vault.scanner import get_doc_type, scan_vault

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


class TestScanVault:
    def test_yields_many_markdown_files(self):
        paths = list(scan_vault(TEST_PROJECT))
        assert len(paths) > 80

    def test_all_files_are_markdown(self):
        for p in scan_vault(TEST_PROJECT):
            assert p.suffix == ".md"

    def test_skips_obsidian(self):
        for p in scan_vault(TEST_PROJECT):
            assert ".obsidian" not in p.parts

    def test_includes_known_adr(self):
        names = {p.name for p in scan_vault(TEST_PROJECT)}
        assert "2026-02-05-editor-demo-architecture.md" in names

    def test_includes_known_plan(self):
        names = {p.name for p in scan_vault(TEST_PROJECT)}
        assert "2026-02-05-editor-demo-phase1-plan.md" in names


class TestGetDocType:
    def test_adr_dir(self):
        path = (
            TEST_PROJECT / ".vault" / "adr" / "2026-02-05-editor-demo-architecture.md"
        )
        assert get_doc_type(path, TEST_PROJECT) == DocType.ADR

    def test_plan_dir(self):
        path = (
            TEST_PROJECT / ".vault" / "plan" / "2026-02-05-editor-demo-phase1-plan.md"
        )
        assert get_doc_type(path, TEST_PROJECT) == DocType.PLAN

    def test_research_dir(self):
        path = (
            TEST_PROJECT / ".vault" / "research" / "2026-02-05-editor-demo-research.md"
        )
        assert get_doc_type(path, TEST_PROJECT) == DocType.RESEARCH

    def test_reference_dir(self):
        path = (
            TEST_PROJECT
            / ".vault"
            / "reference"
            / "2026-02-05-editor-demo-core-reference.md"
        )
        assert get_doc_type(path, TEST_PROJECT) == DocType.REFERENCE

    def test_unknown_dir_returns_none(self):
        # audit/ is not a valid DocType directory
        audit_files = list((TEST_PROJECT / ".vault" / "audit").glob("*.md"))
        if audit_files:
            assert get_doc_type(audit_files[0], TEST_PROJECT) is None
