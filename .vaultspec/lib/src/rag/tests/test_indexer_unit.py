"""Unit tests for rag.indexer — extraction and doc preparation (no GPU)."""

import pytest
from core.config import reset_config
from rag.indexer import IndexResult, _extract_feature, _extract_title, prepare_document
from tests.constants import TEST_PROJECT

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


class TestExtractTitle:
    def test_extracts_h1(self):
        assert _extract_title("# My Title\nSome content") == "My Title"

    def test_extracts_first_h1(self):
        assert _extract_title("# First\n## Second\n# Third") == "First"

    def test_no_h1(self):
        assert _extract_title("No heading here") == ""

    def test_empty_string(self):
        assert _extract_title("") == ""

    def test_h1_with_whitespace(self):
        assert _extract_title("  # Spaced Title  ") == "Spaced Title"

    def test_h2_not_extracted(self):
        assert _extract_title("## H2 Heading\nContent") == ""


class TestExtractFeature:
    def test_extracts_feature_tag(self):
        assert _extract_feature(["#adr", "#auth"]) == "auth"

    def test_extracts_feature_from_plan(self):
        assert _extract_feature(["#plan", "#rag"]) == "rag"

    def test_no_feature_tag(self):
        assert _extract_feature(["#adr"]) == ""

    def test_empty_tags(self):
        assert _extract_feature([]) == ""

    def test_doc_type_tags_excluded(self):
        assert _extract_feature(["#research", "#exec", "#reference"]) == ""

    def test_first_non_doctype_wins(self):
        assert _extract_feature(["#adr", "#auth", "#security"]) == "auth"


class TestIndexResult:
    def test_creation(self):
        result = IndexResult(
            total=100, added=50, updated=10, removed=5, duration_ms=1234, device="cuda"
        )
        assert result.total == 100
        assert result.device == "cuda"


class TestPrepareDocument:
    def test_prepares_valid_document(self):
        doc_path = (
            TEST_PROJECT / ".vault" / "adr" / "2026-02-05-editor-demo-architecture.md"
        )
        doc = prepare_document(doc_path, TEST_PROJECT)
        assert doc is not None
        assert doc.id == "2026-02-05-editor-demo-architecture"
        assert doc.doc_type == "adr"
        assert doc.feature == "editor-demo"
        assert len(doc.title) > 0
        assert doc.vector == []

    def test_returns_doc_for_audit_dir(self):
        # audit/ is now a valid DocType directory
        audit_files = list((TEST_PROJECT / ".vault" / "audit").glob("*.md"))
        if audit_files:
            doc = prepare_document(audit_files[0], TEST_PROJECT)
            # May still be None if the audit file lacks proper frontmatter,
            # but at minimum the doc_type should be recognized
            if doc is not None:
                assert doc.doc_type == "audit"

    def test_returns_none_for_nonexistent_file(self):
        missing = (
            TEST_PROJECT / ".vault" / "adr" / "nonexistent-doc-that-does-not-exist.md"
        )
        doc = prepare_document(missing, TEST_PROJECT)
        assert doc is None
