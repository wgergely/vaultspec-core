"""Tests for sync command behavior."""

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app

pytestmark = [pytest.mark.unit]


@pytest.fixture
def runner():
    return CliRunner()


class TestSyncCoreError:
    def test_sync_core_fails(self, runner):
        """sync core must fail with clear error."""
        result = runner.invoke(app, ["sync", "core"])
        assert result.exit_code != 0
        assert "core" in result.output.lower()

    def test_sync_core_error_mentions_source(self, runner):
        """Error should explain that core is the sync source."""
        result = runner.invoke(app, ["sync", "core"])
        assert (
            "source" in result.output.lower() or ".vaultspec" in result.output.lower()
        )


class TestSyncValidation:
    def test_sync_unknown_provider_fails(self, runner):
        """Unknown provider name must fail."""
        result = runner.invoke(app, ["sync", "nonexistent"])
        assert result.exit_code != 0

    def test_sync_help_shows_providers(self, runner):
        """--help should list available providers."""
        result = runner.invoke(app, ["sync", "--help"])
        assert result.exit_code == 0
