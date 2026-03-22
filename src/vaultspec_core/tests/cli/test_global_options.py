"""Tests for global CLI options."""

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.mark.unit
class TestGlobalOptions:
    def test_no_verbose_flag(self, runner):
        """--verbose must not exist."""
        result = runner.invoke(app, ["--verbose", "sync"])
        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_target_help_text(self, runner):
        """--target help must describe target directory."""
        result = runner.invoke(app, ["--help"])
        assert "target directory" in result.output.lower()

    def test_debug_flag_exists(self, runner):
        """--debug must still exist."""
        result = runner.invoke(app, ["--help"])
        assert "--debug" in result.output

    def test_no_install_completion(self, runner):
        """--install-completion must not appear in help."""
        result = runner.invoke(app, ["--help"])
        assert "--install-completion" not in result.output

    def test_no_show_completion(self, runner):
        """--show-completion must not appear in help."""
        result = runner.invoke(app, ["--help"])
        assert "--show-completion" not in result.output
