"""Tests for the unified __main__.py CLI router.

Covers: --help / -h / no-args help text, --version / -V flags,
        namespace routing (vault, team, subagent), and spec_cli
        fallthrough for resource commands (rules, agents, skills,
        doctor, unknown commands).
"""

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.unit]


def run_vaultspec(*args: str) -> subprocess.CompletedProcess[str]:
    """Run ``python -m vaultspec`` as a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "vaultspec", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestMainHelp:
    """Verify that help output is printed for --help, -h, and no-args."""

    def test_help_flag(self):
        """--help exits 0 and lists all SPEC_COMMANDS and NAMESPACES keys."""
        result = run_vaultspec("--help")
        assert result.returncode == 0
        assert "vaultspec" in result.stdout
        # SPEC_COMMANDS keys
        for cmd in (
            "rules",
            "agents",
            "skills",
            "config",
            "system",
            "sync-all",
            "test",
            "doctor",
            "init",
            "readiness",
            "hooks",
        ):
            assert cmd in result.stdout, f"missing SPEC_COMMANDS key: {cmd}"
        # NAMESPACES keys
        for ns in ("vault", "team", "subagent", "mcp"):
            assert ns in result.stdout, f"missing NAMESPACES key: {ns}"

    def test_help_no_args(self):
        """No arguments exits 0 and prints the same help text as --help."""
        result = run_vaultspec()
        assert result.returncode == 0
        assert "vaultspec" in result.stdout
        assert "rules" in result.stdout
        assert "vault" in result.stdout

    def test_help_h_flag(self):
        """-h flag exits 0."""
        result = run_vaultspec("-h")
        assert result.returncode == 0
        assert "vaultspec" in result.stdout


class TestMainVersion:
    """Verify --version and -V print the version string."""

    def test_version_long(self):
        """--version exits 0 and output contains the version string."""
        from ...cli_common import get_version

        expected_version = get_version()
        result = run_vaultspec("--version")
        assert result.returncode == 0
        assert expected_version in result.stdout

    def test_version_short(self):
        """-V exits 0 and prints the same version."""
        from ...cli_common import get_version

        expected_version = get_version()
        result = run_vaultspec("-V")
        assert result.returncode == 0
        assert expected_version in result.stdout


class TestNamespaceRouting:
    """Verify that namespace commands route to the correct sub-CLI."""

    def test_vault_namespace_help(self):
        """``vaultspec vault --help`` exits 0 and shows vault_cli subcommands."""
        result = run_vaultspec("vault", "--help")
        assert result.returncode == 0
        assert "audit" in result.stdout
        assert "create" in result.stdout

    def test_team_namespace_help(self):
        """``vaultspec team --help`` exits 0 and shows team_cli subcommands."""
        result = run_vaultspec("team", "--help")
        assert result.returncode == 0
        assert "create" in result.stdout
        assert "dissolve" in result.stdout

    def test_subagent_namespace_help(self):
        """``vaultspec subagent --help`` exits 0 and shows subagent_cli subcommands."""
        result = run_vaultspec("subagent", "--help")
        assert result.returncode == 0
        assert "run" in result.stdout
        assert "list" in result.stdout

    def test_vault_namespace_version(self):
        """``vaultspec vault -V`` exits 0."""
        result = run_vaultspec("vault", "-V")
        assert result.returncode == 0

    def test_subagent_namespace_version(self):
        """``vaultspec subagent -V`` exits 0."""
        result = run_vaultspec("subagent", "-V")
        assert result.returncode == 0


class TestSpecCliFallthrough:
    """Verify commands that fall through to spec_cli are routed correctly."""

    def test_rules_help(self):
        """``vaultspec rules --help`` exits 0 and shows rules subcommands."""
        result = run_vaultspec("rules", "--help")
        assert result.returncode == 0
        for subcmd in ("list", "add", "show", "sync"):
            assert subcmd in result.stdout, f"missing rules subcmd: {subcmd}"

    def test_agents_help(self):
        """``vaultspec agents --help`` exits 0."""
        result = run_vaultspec("agents", "--help")
        assert result.returncode == 0

    def test_skills_help(self):
        """``vaultspec skills --help`` exits 0."""
        result = run_vaultspec("skills", "--help")
        assert result.returncode == 0

    def test_doctor_runs(self):
        """``vaultspec doctor`` exits 0 and output contains 'Python:'."""
        result = run_vaultspec("doctor")
        assert result.returncode == 0
        assert "Python:" in result.stdout

    def test_unknown_command_prints_help(self):
        """``vaultspec nonexistent`` falls through to spec_cli which rejects it."""
        result = run_vaultspec("nonexistent")
        # argparse rejects the invalid choice with exit code 2 and usage text
        assert result.returncode == 2
        assert "invalid choice" in result.stderr
