"""Unit tests for the vault_cli.py CLI entry point."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from ...vaultcore import DocType
from .conftest import run_vault

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


class TestGetVersion:
    """Verify version information is correctly retrieved."""

    def test_reads_version_from_pyproject(self, test_project):
        from vaultspec_core.cli_common import get_version

        v = get_version()
        assert v == "0.1.0"

    def test_get_version_returns_string(self, test_project):
        from vaultspec_core.cli_common import get_version

        assert isinstance(get_version(), str)


class TestHelpText:
    """Verify that --help output contains expected strings."""

    def test_main_help(self, runner, test_project):
        result = run_vault(runner, "--help", target=test_project)
        assert result.exit_code == 0
        assert "audit" in result.output
        assert "add" in result.output

    def test_audit_help(self, runner, test_project):
        result = run_vault(runner, "audit", "--help", target=test_project)
        assert result.exit_code == 0
        assert "--summary" in result.output
        assert "--verify" in result.output

    def test_add_help(self, runner, test_project):
        result = run_vault(runner, "add", "--help", target=test_project)
        assert result.exit_code == 0
        assert "--type" in result.output
        assert "--feature" in result.output


class TestAuditSummary:
    """Verify 'vault audit --summary' output."""

    def test_audit_summary_text(self, runner, test_project):
        result = run_vault(runner, "audit", "--summary", target=test_project)
        assert result.exit_code == 0
        assert "Vault Summary" in result.output
        assert "Total Documents:" in result.output

    def test_audit_summary_json(self, runner, test_project):
        result = run_vault(runner, "audit", "--summary", "--json", target=test_project)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "summary" in data
        assert "total_docs" in data["summary"]


class TestAuditFeatures:
    """Verify 'vault audit --features' output."""

    def test_audit_features_text(self, runner, test_project):
        # Create a doc with feature tag
        (test_project / ".vault" / "adr").mkdir(parents=True, exist_ok=True)
        (test_project / ".vault" / "adr" / "f1.md").write_text(
            '---\ntags: ["#adr", "#my-feature"]\n---\n', encoding="utf-8"
        )
        result = run_vault(runner, "audit", "--features", target=test_project)
        assert result.exit_code == 0
        assert "my-feature" in result.output


class TestAuditVerify:
    """Verify 'vault audit --verify' output."""

    def test_audit_verify_text(self, runner, test_project):
        result = run_vault(runner, "audit", "--verify", target=test_project)
        assert result.exit_code == 0
        assert (
            "Verification Passed." in result.output
            or "Verification Failed" in result.output
        )

    def test_audit_verify_json(self, runner, test_project):
        result = run_vault(runner, "audit", "--verify", "--json", target=test_project)
        assert result.exit_code == 0
        # Find the JSON part if there are warnings
        output = result.output
        if "{" in output:
            output = output[output.index("{") :]
        data = json.loads(output)
        assert "verification" in data
        assert "passed" in data["verification"]


class TestCreateSubcommand:
    """Verify 'vault create' behavior."""

    def test_create_generates_correct_filename(self, runner, test_project):
        date_str = datetime.now().strftime("%Y-%m-%d")
        tmpl_dir = test_project / ".vaultspec" / "rules" / "templates"
        tmpl_dir.mkdir(parents=True, exist_ok=True)
        (tmpl_dir / "adr.md").write_text("# ADR Template", encoding="utf-8")

        # Cleanup potential leftover from previous failed tests
        expected_path = test_project / ".vault" / "adr" / f"{date_str}-test-feat-adr.md"
        if expected_path.exists():
            expected_path.unlink()

        result = run_vault(
            runner,
            "add",
            "--type",
            "adr",
            "--feature",
            "test-feat",
            "--title",
            "My Title",
            target=test_project,
        )
        assert result.exit_code == 0
        assert expected_path.exists()

    def test_create_strips_hash_from_feature(self, runner, test_project):
        """Creating with #feature should strip the hash."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        tmpl_dir = test_project / ".vaultspec" / "rules" / "templates"
        tmpl_dir.mkdir(parents=True, exist_ok=True)
        (tmpl_dir / "adr.md").write_text("# Template", encoding="utf-8")

        expected_path = test_project / ".vault" / "adr" / f"{date_str}-my-feat-adr.md"
        if expected_path.exists():
            expected_path.unlink()

        run_vault(
            runner,
            "add",
            "--type",
            "adr",
            "--feature",
            "#my-feat",
            target=test_project,
        )
        assert expected_path.exists()

    def test_create_valid_doc_types_accepted(
        self, runner, tmp_path: Path, test_project
    ):
        """Test all valid DocType choices are accepted."""
        # Setup isolated env
        tmpl_dir = tmp_path / ".vaultspec" / "rules" / "templates"
        tmpl_dir.mkdir(parents=True)
        (tmp_path / ".vault").mkdir()

        # Manually follow hydration.py mapping
        mapping = {
            DocType.ADR: "adr.md",
            DocType.AUDIT: "audit.md",
            DocType.PLAN: "plan.md",
            DocType.RESEARCH: "research.md",
            DocType.REFERENCE: "ref-audit.md",
            DocType.EXEC: "exec-step.md",
        }

        for dt, filename in mapping.items():
            tmpl_file = tmpl_dir / filename
            tmpl_file.write_text("T", encoding="utf-8")

        from vaultspec_core.core.types import init_paths

        init_paths(tmp_path)

        for dt in DocType:
            result = run_vault(
                runner,
                "--target",
                str(tmp_path),
                "add",
                "--type",
                dt.value,
                "--feature",
                "f",
            )
            assert result.exit_code == 0, (
                f"DocType {dt.value} rejected (output: {result.output})"
            )


class TestNoCommand:
    def test_no_command_prints_help(self, runner, test_project):
        result = run_vault(runner, target=test_project)
        assert result.exit_code == 0
