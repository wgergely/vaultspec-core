"""Tests for vault scanning and document type classification.

Covers :func:`~vaultspec_core.vaultcore.scanner.scan_vault` (file discovery,
``.obsidian`` exclusion) and :func:`~vaultspec_core.vaultcore.scanner.get_doc_type`
(directory-based classification) against a synthetic vault fixture.
"""

import pytest

from ...config import reset_config
from ...testing.synthetic import CorpusManifest, build_synthetic_vault
from .. import DocType, get_doc_type, scan_vault

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def vault_project(tmp_path) -> CorpusManifest:
    return build_synthetic_vault(
        tmp_path,
        n_docs=24,
        seed=42,
        named_docs={
            "editor_demo_adr": "2026-02-05-editor-demo-architecture-adr",
            "editor_demo_plan": "2026-02-05-editor-demo-phase1-plan",
            "editor_demo_research": "2026-02-05-editor-demo-research",
            "editor_demo_reference": "2026-02-05-editor-demo-core-reference",
        },
    )


class TestScanVault:
    def test_yields_many_markdown_files(self, vault_project: CorpusManifest):
        paths = list(scan_vault(vault_project.root))
        # Anchor the lower bound to the generated corpus size: at least
        # one doc per requested doc count, so a regression that emits
        # only a handful of files would still trip this assertion.
        assert len(paths) >= len(vault_project.docs)

    def test_all_files_are_markdown(self, vault_project: CorpusManifest):
        for p in scan_vault(vault_project.root):
            assert p.suffix == ".md"

    def test_skips_obsidian(self, vault_project: CorpusManifest):
        # Create a .obsidian directory to verify it is excluded
        obsidian_dir = vault_project.root / ".vault" / ".obsidian"
        obsidian_dir.mkdir(parents=True)
        (obsidian_dir / "config.md").write_text("obsidian config", encoding="utf-8")
        for p in scan_vault(vault_project.root):
            assert ".obsidian" not in p.parts

    def test_includes_known_adr(self, vault_project: CorpusManifest):
        names = {p.name for p in scan_vault(vault_project.root)}
        assert "2026-02-05-editor-demo-architecture-adr.md" in names

    def test_includes_known_plan(self, vault_project: CorpusManifest):
        names = {p.name for p in scan_vault(vault_project.root)}
        assert "2026-02-05-editor-demo-phase1-plan.md" in names


class TestGetDocType:
    def test_adr_dir(self, vault_project: CorpusManifest):
        path = vault_project.named_docs["editor_demo_adr"].path
        assert get_doc_type(path, vault_project.root) == DocType.ADR

    def test_plan_dir(self, vault_project: CorpusManifest):
        path = vault_project.named_docs["editor_demo_plan"].path
        assert get_doc_type(path, vault_project.root) == DocType.PLAN

    def test_research_dir(self, vault_project: CorpusManifest):
        path = vault_project.named_docs["editor_demo_research"].path
        assert get_doc_type(path, vault_project.root) == DocType.RESEARCH

    def test_reference_dir(self, vault_project: CorpusManifest):
        path = vault_project.named_docs["editor_demo_reference"].path
        assert get_doc_type(path, vault_project.root) == DocType.REFERENCE

    def test_audit_dir_returns_audit(self, vault_project: CorpusManifest):
        audit_files = list((vault_project.root / ".vault" / "audit").glob("*.md"))
        assert audit_files, "Synthetic vault must produce at least one audit doc"
        assert get_doc_type(audit_files[0], vault_project.root) == DocType.AUDIT
