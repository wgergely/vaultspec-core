"""Unit tests for the vault command group.

Covers vault add, vault stats, vault check, etc.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.cli import app

from ...vaultcore import DocType

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


class TestGetVersion:
    """Verify version information is correctly retrieved."""

    def test_reads_version_from_pyproject(self, synthetic_project):
        from importlib.metadata import version

        from vaultspec_core.cli_common import get_version

        v = get_version()
        expected = version("vaultspec-core")
        assert v == expected

    def test_get_version_returns_string(self, synthetic_project):
        from vaultspec_core.cli_common import get_version

        assert isinstance(get_version(), str)


class TestHelpText:
    """Verify that --help output contains expected strings."""

    def test_main_help(self, runner, synthetic_project):
        result = runner.invoke(
            app, ["--target", str(synthetic_project), "vault", "--help"]
        )
        assert result.exit_code == 0
        assert "add" in result.output
        assert "check" in result.output
        assert "stats" in result.output

    def test_add_help(self, runner, synthetic_project):
        result = runner.invoke(
            app, ["--target", str(synthetic_project), "vault", "add", "--help"]
        )
        assert result.exit_code == 0
        assert "--feature" in result.output


class TestAddSubcommand:
    """Verify 'vault add' behavior."""

    def test_add_generates_correct_filename(self, runner, synthetic_project):
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Cleanup potential leftover from previous failed tests
        expected_path = (
            synthetic_project / ".vault" / "adr" / f"{date_str}-test-feat-adr.md"
        )
        if expected_path.exists():
            expected_path.unlink()

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "adr",
                "--feature",
                "test-feat",
                "--title",
                "My Title",
            ],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"
        assert expected_path.exists()

    def test_add_strips_hash_from_feature(self, runner, synthetic_project):
        """Creating with #feature should strip the hash."""
        date_str = datetime.now().strftime("%Y-%m-%d")

        expected_path = (
            synthetic_project / ".vault" / "adr" / f"{date_str}-my-feat-adr.md"
        )
        if expected_path.exists():
            expected_path.unlink()

        runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "adr",
                "--feature",
                "#my-feat",
            ],
        )
        assert expected_path.exists()

    def test_add_valid_doc_types_accepted(
        self, runner, tmp_path: Path, synthetic_project
    ):
        """Test all valid DocType choices are accepted.

        Uses real templates via seed_builtins - never shadow template files.
        """
        from vaultspec_core.builtins import seed_builtins
        from vaultspec_core.core.types import init_paths

        # Seed real templates from the repo into the tmp workspace
        rules_dir = tmp_path / ".vaultspec" / "rules"
        rules_dir.mkdir(parents=True)
        seed_builtins(rules_dir, force=True)

        # Create vault type directories
        for dt in DocType:
            (tmp_path / ".vault" / dt.value).mkdir(parents=True, exist_ok=True)

        # Create prerequisite docs for feature 'f' so exec validation passes.
        # Exec requires research + ADR + plan to exist for the feature.
        for prereq in ("research", "adr", "plan"):
            d = tmp_path / ".vault" / prereq
            (d / f"2026-01-01-f-{prereq}.md").write_text(
                f"---\ntags:\n  - '#{prereq}'\n  - '#f'\n"
                f"date: '2026-01-01'\nrelated: []\n---\n# Stub\n",
                encoding="utf-8",
            )

        init_paths(tmp_path)

        for dt in DocType:
            result = runner.invoke(
                app,
                [
                    "--target",
                    str(tmp_path),
                    "vault",
                    "add",
                    dt.value,
                    "--feature",
                    "f",
                ],
            )
            assert result.exit_code == 0, (
                f"DocType {dt.value} rejected (output: {result.output})"
            )

    def test_add_created_doc_passes_validation(self, runner, synthetic_project):
        """Created documents must pass the project's own frontmatter validation."""
        from vaultspec_core.vaultcore.parser import parse_vault_metadata

        date_str = datetime.now().strftime("%Y-%m-%d")
        expected_path = (
            synthetic_project
            / ".vault"
            / "research"
            / f"{date_str}-valid-doc-research.md"
        )
        if expected_path.exists():
            expected_path.unlink()

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "vault",
                "add",
                "research",
                "--feature",
                "valid-doc",
                "--title",
                "Validation Test",
            ],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"
        assert expected_path.exists()

        # The created document must pass our own validation
        content = expected_path.read_text(encoding="utf-8")
        metadata, _ = parse_vault_metadata(content)
        errors = metadata.validate()
        assert not errors, f"Created document fails validation: {errors}"


class TestNoCommand:
    def test_no_command_prints_help(self, runner, synthetic_project):
        result = runner.invoke(app, ["--target", str(synthetic_project), "vault"])
        # vault_app uses no_args_is_help=True, which Typer reports as exit code 0
        # but the CliRunner may return 2 depending on version; accept both.
        assert result.exit_code in (0, 2)
        assert "add" in result.output or "Usage" in result.output
