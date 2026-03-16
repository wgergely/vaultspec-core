"""Unit tests for the vault command group.

Covers vault add, vault stats, vault doctor, etc.
"""

from __future__ import annotations

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
        assert "add" in result.output
        assert "doctor" in result.output
        assert "stats" in result.output

    def test_add_help(self, runner, test_project):
        result = run_vault(runner, "add", "--help", target=test_project)
        assert result.exit_code == 0
        assert "--feature" in result.output


class TestAddSubcommand:
    """Verify 'vault add' behavior."""

    def test_add_generates_correct_filename(self, runner, test_project):
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
            "adr",
            "--feature",
            "test-feat",
            "--title",
            "My Title",
            target=test_project,
        )
        assert result.exit_code == 0
        assert expected_path.exists()

    def test_add_strips_hash_from_feature(self, runner, test_project):
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
            "adr",
            "--feature",
            "#my-feat",
            target=test_project,
        )
        assert expected_path.exists()

    def test_add_valid_doc_types_accepted(self, runner, tmp_path: Path, test_project):
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

        for _doc_type, filename in mapping.items():
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
        # vault_app uses no_args_is_help=True, which Typer reports as exit code 0
        # but the CliRunner may return 2 depending on version; accept both.
        assert result.exit_code in (0, 2)
        assert "add" in result.output or "Usage" in result.output
