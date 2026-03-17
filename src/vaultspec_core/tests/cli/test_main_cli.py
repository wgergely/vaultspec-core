"""Tests for the unified __main__.py CLI router."""

from __future__ import annotations

import pytest

from .conftest import run_vaultspec

pytestmark = [pytest.mark.unit]


class TestMainHelp:
    """Verify that help output is printed for --help, -h, and no-args."""

    def test_help_flag(self, runner, test_project):
        """--help exits 0."""
        result = run_vaultspec(runner, "--help", target=test_project)
        assert result.exit_code == 0
        assert "vaultspec-core" in result.output

    def test_help_no_args(self, runner, test_project):
        """No arguments exits 0 and prints help text."""
        result = run_vaultspec(runner, target=test_project)
        assert result.exit_code == 0
        assert "vaultspec-core" in result.output

    def test_help_h_flag(self, runner, test_project):
        """-h is rejected because the CLI only exposes --help."""
        result = run_vaultspec(runner, "-h", target=test_project)
        assert result.exit_code != 0
        assert "No such option: -h" in result.output


class TestMainVersion:
    """Verify --version and -V print the version string."""

    def test_version_long(self, runner, test_project):
        """--version exits 0 and output contains the version string."""
        from vaultspec_core.cli_common import get_version

        expected_version = get_version()
        result = run_vaultspec(runner, "--version", target=test_project)
        assert result.exit_code == 0
        assert expected_version in result.output

    def test_version_short(self, runner, test_project):
        """-V exits 0 and prints the same version."""
        from vaultspec_core.cli_common import get_version

        expected_version = get_version()
        result = run_vaultspec(runner, "-V", target=test_project)
        assert result.exit_code == 0
        assert expected_version in result.output


class TestNamespaceRouting:
    """Verify that namespace commands route to the correct sub-CLI."""

    def test_vault_namespace_help(self, runner, test_project):
        """``vaultspec vault --help`` exits 0 and shows subcommands."""
        result = run_vaultspec(runner, "vault", "--help", target=test_project)
        assert result.exit_code == 0
        assert "add" in result.output
        assert "check" in result.output

    def test_spec_namespace_help(self, runner, test_project):
        """``vaultspec spec --help`` exits 0 and shows subcommands."""
        result = run_vaultspec(runner, "spec", "--help", target=test_project)
        assert result.exit_code == 0
        assert "rules" in result.output
        assert "skills" in result.output


class TestSpecCliFallthrough:
    """Verify commands under the spec group are routed correctly."""

    def test_rules_help(self, runner, test_project):
        """``vaultspec spec rules --help`` exits 0 and shows rules subcommands."""
        result = run_vaultspec(runner, "spec", "rules", "--help", target=test_project)
        assert result.exit_code == 0
        assert "list" in result.output

    def test_skills_help(self, runner, test_project):
        """``vaultspec spec skills --help`` exits 0."""
        result = run_vaultspec(runner, "spec", "skills", "--help", target=test_project)
        assert result.exit_code == 0

    def test_vault_check_all_runs(self, runner, test_project):
        """``vaultspec vault check all`` exits 0 and shows check results."""
        result = run_vaultspec(runner, "vault", "check", "all", target=test_project)
        # check all may find real issues in test-project, accept 0 or 1
        assert result.exit_code in (0, 1)
        assert "Vault Check" in result.output

    def test_unknown_command_fails(self, runner, test_project):
        """``vaultspec nonexistent`` fails."""
        result = run_vaultspec(runner, "nonexistent", target=test_project)
        assert result.exit_code != 0

    def test_root_mcp_subcommand_is_unknown(self, runner, test_project):
        """``vaultspec-core mcp`` is rejected because MCP ships separately."""
        result = run_vaultspec(runner, "mcp", target=test_project)
        assert result.exit_code != 0
        assert "No such command" in result.output
