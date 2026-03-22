"""Tests for vault document path resolution and feature dependency validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from vaultspec_core.vaultcore.hydration import create_vault_doc, hydrate_template
from vaultspec_core.vaultcore.models import DocType
from vaultspec_core.vaultcore.resolve import (
    RelatedResolutionError,
    resolve_related_inputs,
    validate_feature_dependencies,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture()
def vault_project(tmp_path: Path) -> Path:
    """Scaffold a vault with real templates and some existing documents.

    Uses seed_builtins to copy real templates - never shadows them.
    """
    from vaultspec_core.builtins import seed_builtins

    rules_dir = tmp_path / ".vaultspec" / "rules"
    rules_dir.mkdir(parents=True)
    seed_builtins(rules_dir, force=True)

    # Create vault directories
    for dt in DocType:
        (tmp_path / ".vault" / dt.value).mkdir(parents=True)

    # Create some existing documents for resolution tests
    (tmp_path / ".vault" / "research" / "2026-03-01-my-feat-research.md").write_text(
        "---\ntags:\n  - '#research'\n  - '#my-feat'\n"
        "date: '2026-03-01'\nrelated: []\n---\n# Research\n",
        encoding="utf-8",
    )
    (tmp_path / ".vault" / "adr" / "2026-03-05-my-feat-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#my-feat'\n"
        "date: '2026-03-05'\nrelated:\n  - '[[2026-03-01-my-feat-research]]'\n"
        "---\n# ADR\n",
        encoding="utf-8",
    )
    (tmp_path / ".vault" / "plan" / "2026-03-10-my-feat-plan.md").write_text(
        "---\ntags:\n  - '#plan'\n  - '#my-feat'\n"
        "date: '2026-03-10'\nrelated:\n  - '[[2026-03-05-my-feat-adr]]'\n"
        "---\n# Plan\n",
        encoding="utf-8",
    )

    return tmp_path


# ---- resolve_related_inputs tests -------------------------------------------


class TestResolveRelatedInputs:
    """Test path resolution from various input formats to [[wiki-link]]."""

    def test_resolve_by_stem(self, vault_project: Path) -> None:
        result = resolve_related_inputs(["2026-03-01-my-feat-research"], vault_project)
        assert result == ["[[2026-03-01-my-feat-research]]"]

    def test_resolve_by_filename(self, vault_project: Path) -> None:
        result = resolve_related_inputs(
            ["2026-03-01-my-feat-research.md"], vault_project
        )
        assert result == ["[[2026-03-01-my-feat-research]]"]

    def test_resolve_by_wikilink(self, vault_project: Path) -> None:
        result = resolve_related_inputs(
            ["[[2026-03-01-my-feat-research]]"], vault_project
        )
        assert result == ["[[2026-03-01-my-feat-research]]"]

    def test_resolve_by_relative_path(self, vault_project: Path) -> None:
        result = resolve_related_inputs(
            [".vault/research/2026-03-01-my-feat-research.md"], vault_project
        )
        assert result == ["[[2026-03-01-my-feat-research]]"]

    def test_resolve_by_absolute_path(self, vault_project: Path) -> None:
        abspath = str(
            vault_project / ".vault" / "research" / "2026-03-01-my-feat-research.md"
        )
        result = resolve_related_inputs([abspath], vault_project)
        assert result == ["[[2026-03-01-my-feat-research]]"]

    def test_resolve_multiple(self, vault_project: Path) -> None:
        result = resolve_related_inputs(
            ["2026-03-01-my-feat-research", "2026-03-05-my-feat-adr"],
            vault_project,
        )
        assert len(result) == 2
        assert "[[2026-03-01-my-feat-research]]" in result
        assert "[[2026-03-05-my-feat-adr]]" in result

    def test_resolve_deduplicates(self, vault_project: Path) -> None:
        result = resolve_related_inputs(
            [
                "2026-03-01-my-feat-research",
                "2026-03-01-my-feat-research.md",
                "[[2026-03-01-my-feat-research]]",
            ],
            vault_project,
        )
        assert result == ["[[2026-03-01-my-feat-research]]"]

    def test_resolve_unknown_raises(self, vault_project: Path) -> None:
        with pytest.raises(RelatedResolutionError) as exc_info:
            resolve_related_inputs(["nonexistent-doc"], vault_project)
        assert "nonexistent-doc" in exc_info.value.failures

    def test_resolve_multiple_failures(self, vault_project: Path) -> None:
        with pytest.raises(RelatedResolutionError) as exc_info:
            resolve_related_inputs(
                ["missing-a", "2026-03-01-my-feat-research", "missing-b"],
                vault_project,
            )
        assert len(exc_info.value.failures) == 2
        assert "missing-a" in exc_info.value.failures
        assert "missing-b" in exc_info.value.failures

    def test_resolve_empty_input(self, vault_project: Path) -> None:
        result = resolve_related_inputs([], vault_project)
        assert result == []

    def test_resolve_wikilink_with_display_text(self, vault_project: Path) -> None:
        result = resolve_related_inputs(
            ["[[2026-03-01-my-feat-research|Research Doc]]"], vault_project
        )
        assert result == ["[[2026-03-01-my-feat-research]]"]


# ---- validate_feature_dependencies tests ------------------------------------


class TestValidateFeatureDependencies:
    """Test lifecycle dependency validation at create time."""

    def test_research_no_dependencies(self, vault_project: Path) -> None:
        diags = validate_feature_dependencies(
            vault_project,
            DocType.RESEARCH,
            "new-feat",
        )
        assert not diags

    def test_adr_warns_no_research(self, vault_project: Path) -> None:
        diags = validate_feature_dependencies(vault_project, DocType.ADR, "new-feat")
        assert any("WARNING:" in d and "research" in d.lower() for d in diags)

    def test_adr_no_warning_when_research_exists(self, vault_project: Path) -> None:
        diags = validate_feature_dependencies(vault_project, DocType.ADR, "my-feat")
        assert not any("research" in d.lower() for d in diags)

    def test_plan_warns_no_adr(self, vault_project: Path) -> None:
        # Create a feature with research but no ADR
        research_path = (
            vault_project / ".vault" / "research" / "2026-03-01-plan-only-research.md"
        )
        research_path.write_text(
            "---\ntags:\n  - '#research'\n  - '#plan-only'\n"
            "date: '2026-03-01'\nrelated: []\n---\n# R\n",
            encoding="utf-8",
        )
        diags = validate_feature_dependencies(vault_project, DocType.PLAN, "plan-only")
        assert any("WARNING:" in d and "adr" in d.lower() for d in diags)

    def test_plan_no_warning_when_adr_exists(self, vault_project: Path) -> None:
        diags = validate_feature_dependencies(vault_project, DocType.PLAN, "my-feat")
        # my-feat has research + adr, so no warnings
        assert not any("ERROR:" in d for d in diags)

    def test_exec_fails_no_plan(self, vault_project: Path) -> None:
        # Create a feature with only research
        research_path = (
            vault_project / ".vault" / "research" / "2026-03-01-exec-only-research.md"
        )
        research_path.write_text(
            "---\ntags:\n  - '#research'\n  - '#exec-only'\n"
            "date: '2026-03-01'\nrelated: []\n---\n# R\n",
            encoding="utf-8",
        )
        diags = validate_feature_dependencies(vault_project, DocType.EXEC, "exec-only")
        errors = [d for d in diags if d.startswith("ERROR:")]
        assert len(errors) >= 1
        assert any("plan" in e.lower() for e in errors)

    def test_exec_fails_no_adr(self, vault_project: Path) -> None:
        # Create a feature with plan but no ADR
        (vault_project / ".vault" / "plan" / "2026-03-01-no-adr-plan.md").write_text(
            "---\ntags:\n  - '#plan'\n  - '#no-adr'\n"
            "date: '2026-03-01'\nrelated: []\n---\n# P\n",
            encoding="utf-8",
        )
        diags = validate_feature_dependencies(vault_project, DocType.EXEC, "no-adr")
        errors = [d for d in diags if d.startswith("ERROR:")]
        assert any("adr" in e.lower() for e in errors)

    def test_exec_passes_full_chain(self, vault_project: Path) -> None:
        # my-feat has research + adr + plan
        diags = validate_feature_dependencies(vault_project, DocType.EXEC, "my-feat")
        errors = [d for d in diags if d.startswith("ERROR:")]
        assert not errors


# ---- hydrate_template with related/tags tests -------------------------------


class TestHydrateWithRelatedAndTags:
    """Test template hydration with related links and extra tags."""

    def test_inject_related_replaces_placeholder(self) -> None:
        template = (
            "---\ntags:\n  - '#adr'\n  - '#feat'\n"
            "date: '2026-03-01'\n"
            'related:\n  - "[[{yyyy-mm-dd-*}]]"\n---\n# Title\n'
        )
        result = hydrate_template(
            template,
            "feat",
            "2026-03-01",
            related=["[[2026-03-01-feat-research]]"],
        )
        assert "[[2026-03-01-feat-research]]" in result
        assert "{yyyy-mm-dd-*}" not in result

    def test_inject_empty_related(self) -> None:
        template = (
            "---\ntags:\n  - '#adr'\n  - '#feat'\n"
            "date: '2026-03-01'\n"
            'related:\n  - "[[{yyyy-mm-dd-*}]]"\n---\n# Title\n'
        )
        result = hydrate_template(template, "feat", "2026-03-01", related=[])
        assert "related: []" in result
        assert "{yyyy-mm-dd-*}" not in result

    def test_inject_multiple_related(self) -> None:
        template = (
            "---\ntags:\n  - '#plan'\n  - '#feat'\n"
            "date: '2026-03-01'\n"
            'related:\n  - "[[{yyyy-mm-dd-*}]]"\n---\n# Title\n'
        )
        result = hydrate_template(
            template,
            "feat",
            "2026-03-01",
            related=["[[doc-a]]", "[[doc-b]]", "[[doc-c]]"],
        )
        assert "[[doc-a]]" in result
        assert "[[doc-b]]" in result
        assert "[[doc-c]]" in result

    def test_inject_extra_tags(self) -> None:
        template = (
            "---\ntags:\n  - '#adr'\n  - '#feat'\n"
            "date: '2026-03-01'\nrelated: []\n---\n# Title\n"
        )
        result = hydrate_template(
            template,
            "feat",
            "2026-03-01",
            extra_tags=["#scope-backend", "#priority-high"],
        )
        assert "#scope-backend" in result
        assert "#priority-high" in result
        # Original tags still present
        assert "#adr" in result
        assert "#feat" in result

    def test_no_related_preserves_placeholder(self) -> None:
        template = (
            "---\ntags:\n  - '#adr'\n  - '#feat'\n"
            "date: '2026-03-01'\n"
            'related:\n  - "[[{yyyy-mm-dd-*}]]"\n---\n# Title\n'
        )
        result = hydrate_template(template, "feat", "2026-03-01")
        # When related=None (default), placeholder should be preserved
        assert "{yyyy-mm-dd-*}" in result


# ---- create_vault_doc integration tests ------------------------------------


class TestCreateVaultDocWithRelated:
    """Test document creation with related and tags parameters."""

    @pytest.fixture()
    def vault_env(self, tmp_path: Path) -> Path:
        """Scaffold vault with real templates and an existing research doc.

        Uses seed_builtins - never shadows template files.
        """
        from vaultspec_core.builtins import seed_builtins

        rules_dir = tmp_path / ".vaultspec" / "rules"
        rules_dir.mkdir(parents=True)
        seed_builtins(rules_dir, force=True)

        for dt in DocType:
            (tmp_path / ".vault" / dt.value).mkdir(parents=True)

        # Create a research doc to reference
        research_path = (
            tmp_path / ".vault" / "research" / "2026-03-01-test-feat-research.md"
        )
        research_path.write_text(
            "---\ntags:\n  - '#research'\n  - '#test-feat'\n"
            "date: '2026-03-01'\nrelated: []\n---\n# Research\n",
            encoding="utf-8",
        )

        return tmp_path

    def test_create_with_resolved_related(self, vault_env: Path) -> None:
        path = create_vault_doc(
            vault_env,
            DocType.ADR,
            "test-feat",
            "2026-03-15",
            title="Decision",
            related=["[[2026-03-01-test-feat-research]]"],
        )
        content = path.read_text(encoding="utf-8")
        assert "[[2026-03-01-test-feat-research]]" in content
        assert "{yyyy-mm-dd-*}" not in content

    def test_create_with_extra_tags(self, vault_env: Path) -> None:
        path = create_vault_doc(
            vault_env,
            DocType.ADR,
            "tag-feat",
            "2026-03-15",
            title="Tags Test",
            extra_tags=["#scope-api"],
        )
        content = path.read_text(encoding="utf-8")
        assert "#scope-api" in content
        assert "#adr" in content
        assert "#tag-feat" in content

    def test_create_without_related_defaults_to_empty(self, vault_env: Path) -> None:
        path = create_vault_doc(
            vault_env,
            DocType.ADR,
            "no-rel-feat",
            "2026-03-15",
            title="No Related",
        )
        content = path.read_text(encoding="utf-8")
        # Placeholder must be replaced - created docs must pass validation
        assert "{yyyy-mm-dd-*}" not in content
        assert "related: []" in content
