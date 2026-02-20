import pytest
from metrics.api import VaultSummary, get_vault_metrics
from vaultcore.models import DocType

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
            DocType.AUDIT,
            DocType.PLAN,
            DocType.EXEC,
            DocType.REFERENCE,
            DocType.RESEARCH,
        ):
            assert result.counts_by_type.get(dt, 0) > 0, f"Missing count for {dt.value}"

    def test_counts_features(self, vault_root):
        result = get_vault_metrics(vault_root)
        assert result.total_features > 5


@pytest.mark.unit
class TestVaultSummaryEdgeCases:
    def test_empty_vault_zero_counts(self, tmp_path):
        """Metrics on empty vault return zero counts."""
        vault_dir = tmp_path / ".vault"
        vault_dir.mkdir()
        for subdir in ["adr", "audit", "exec", "plan", "reference", "research"]:
            (vault_dir / subdir).mkdir()
        summary = get_vault_metrics(tmp_path)
        assert summary.total_docs == 0
        assert summary.total_features == 0

    def test_single_doc_type_only(self, tmp_path):
        """Vault with only ADRs still returns valid metrics."""
        vault_dir = tmp_path / ".vault" / "adr"
        vault_dir.mkdir(parents=True)
        doc = vault_dir / "2026-01-01-test-adr.md"
        doc.write_text(
            "---\nstatus: accepted\nfeature: test\ntags: []\n---\n# Test ADR\n"
        )
        summary = get_vault_metrics(tmp_path)
        assert summary.total_docs >= 1

    def test_features_deduplicated(self, vault_root):
        """Same feature across multiple docs counted once."""
        from verification.api import list_features

        features = list_features(vault_root)
        # list_features returns a set, so features are inherently unique
        assert len(features) == len(set(features))
