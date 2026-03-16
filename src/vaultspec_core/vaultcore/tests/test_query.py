"""Tests for vault query engine."""

import pytest

from tests.constants import TEST_PROJECT

from ...config import reset_config
from ..query import (
    VaultDocument,
    get_stats,
    list_documents,
    list_feature_details,
)

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
