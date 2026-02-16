import pytest
from metrics.api import VaultSummary, get_vault_metrics
from vault.models import DocType

pytestmark = [pytest.mark.unit]


class TestVaultSummary:
    def test_dataclass_creation(self):
        summary = VaultSummary(
            total_docs=10,
            counts_by_type={DocType.ADR: 3, DocType.PLAN: 2},
            total_features=5,
        )
        assert summary.total_docs == 10
        assert summary.counts_by_type[DocType.ADR] == 3
        assert summary.total_features == 5


class TestGetVaultMetrics:
    def test_counts_documents(self, vault_root):
        result = get_vault_metrics(vault_root)
        assert result.total_docs > 80

    def test_has_all_doc_types(self, vault_root):
        result = get_vault_metrics(vault_root)
        for dt in (
            DocType.ADR,
            DocType.PLAN,
            DocType.EXEC,
            DocType.REFERENCE,
            DocType.RESEARCH,
        ):
            assert result.counts_by_type.get(dt, 0) > 0, f"Missing count for {dt.value}"

    def test_counts_features(self, vault_root):
        result = get_vault_metrics(vault_root)
        assert result.total_features > 5
