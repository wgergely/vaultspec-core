"""Tests for vault query engine."""

from pathlib import Path

import pytest

from ...config import reset_config
from ..query import (
    VaultDocument,
    get_stats,
    list_documents,
    list_feature_details,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
TEST_PROJECT = _REPO_ROOT / "test-project"

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


class TestListDocuments:
    def test_list_all(self):
        docs = list_documents(TEST_PROJECT)
        assert len(docs) > 0
        assert all(isinstance(d, VaultDocument) for d in docs)

    def test_filter_by_type(self):
        docs = list_documents(TEST_PROJECT, doc_type="adr")
        assert len(docs) > 0
        assert all(d.doc_type == "adr" for d in docs)

    def test_filter_by_feature(self):
        docs = list_documents(TEST_PROJECT)
        # Find a real feature from the test data
        features = {d.feature for d in docs if d.feature}
        if features:
            feature = next(iter(features))
            filtered = list_documents(TEST_PROJECT, feature=feature)
            assert len(filtered) > 0
            assert all(d.feature == feature for d in filtered)

    def test_filter_by_date(self):
        docs = list_documents(TEST_PROJECT)
        dates = {d.date for d in docs if d.date}
        if dates:
            date = next(iter(dates))
            filtered = list_documents(TEST_PROJECT, date=date)
            assert len(filtered) > 0
            assert all(d.date == date for d in filtered)

    def test_list_orphaned(self):
        docs = list_documents(TEST_PROJECT, doc_type="orphaned")
        assert isinstance(docs, list)

    def test_list_invalid(self):
        docs = list_documents(TEST_PROJECT, doc_type="invalid")
        assert isinstance(docs, list)

    def test_document_has_all_fields(self):
        docs = list_documents(TEST_PROJECT)
        if docs:
            d = docs[0]
            assert hasattr(d, "path")
            assert hasattr(d, "name")
            assert hasattr(d, "doc_type")
            assert hasattr(d, "feature")
            assert hasattr(d, "date")
            assert hasattr(d, "tags")


class TestGetStats:
    def test_basic_stats(self):
        stats = get_stats(TEST_PROJECT)
        assert "total_docs" in stats
        assert "total_features" in stats
        assert "counts_by_type" in stats

    def test_stats_with_feature_filter(self):
        docs = list_documents(TEST_PROJECT)
        features = {d.feature for d in docs if d.feature}
        if features:
            feature = next(iter(features))
            stats = get_stats(TEST_PROJECT, feature=feature)
            assert "total_docs" in stats

    def test_stats_includes_orphan_count(self):
        stats = get_stats(TEST_PROJECT)
        assert "orphaned_count" in stats

    def test_stats_includes_invalid_count(self):
        stats = get_stats(TEST_PROJECT)
        assert "invalid_link_count" in stats


class TestListFeatureDetails:
    def test_returns_feature_info(self):
        features = list_feature_details(TEST_PROJECT)
        assert isinstance(features, list)
        if features:
            f = features[0]
            assert "name" in f
            assert "doc_count" in f
            assert "types" in f


class TestArchiveFeature:
    def test_archive_moves_docs(self, tmp_path):
        """Archiving moves all docs for a feature into .vault/_archive/."""
        from ..query import archive_feature

        # Set up a mini vault with a doc
        vault_dir = tmp_path / ".vault" / "adr"
        vault_dir.mkdir(parents=True)
        doc = vault_dir / "2026-03-16-test-feature-adr.md"
        doc.write_text(
            "---\ntags:\n  - adr\n  - test-feature\ndate: 2026-03-16\n---\nContent.\n",
            encoding="utf-8",
        )

        result = archive_feature(tmp_path, "test-feature")
        assert result["archived_count"] == 1
        assert not doc.exists()  # Original moved
        archive_dir = tmp_path / ".vault" / "_archive"
        assert archive_dir.exists()
        # File should be under _archive/adr/
        assert (archive_dir / "adr" / doc.name).exists()

    def test_archive_nonexistent_feature(self, tmp_path):
        """Archiving a feature with no docs returns zero count."""
        from ..query import archive_feature

        # Set up an empty vault
        vault_dir = tmp_path / ".vault" / "adr"
        vault_dir.mkdir(parents=True)

        result = archive_feature(tmp_path, "nonexistent-feature-xyz")
        assert result["archived_count"] == 0
        assert result["paths"] == []

    def test_archive_preserves_subdir_structure(self, tmp_path):
        """Archived docs maintain their type subdirectory."""
        from ..query import archive_feature

        # Create docs in different type dirs
        for dtype in ("adr", "plan"):
            d = tmp_path / ".vault" / dtype
            d.mkdir(parents=True)
            f = d / f"2026-03-16-my-feat-{dtype}.md"
            content = (
                f"---\ntags:\n  - {dtype}\n  - my-feat\n"
                f"date: 2026-03-16\n---\nContent.\n"
            )
            f.write_text(content, encoding="utf-8")

        result = archive_feature(tmp_path, "my-feat")
        assert result["archived_count"] == 2
        archive = tmp_path / ".vault" / "_archive"
        assert (archive / "adr" / "2026-03-16-my-feat-adr.md").exists()
        assert (archive / "plan" / "2026-03-16-my-feat-plan.md").exists()
