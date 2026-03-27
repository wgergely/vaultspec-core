"""Tests for the ``vaultspec-core doctor`` CLI command."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from vaultspec_core.cli import app
from vaultspec_core.core.diagnosis.diagnosis import (
    ProviderDiagnosis,
    WorkspaceDiagnosis,
)
from vaultspec_core.core.diagnosis.signals import (
    BuiltinVersionSignal,
    ConfigSignal,
    ContentSignal,
    FrameworkSignal,
    GitignoreSignal,
    ManifestEntrySignal,
    ProviderDirSignal,
)
from vaultspec_core.core.enums import Tool

runner = CliRunner(env={"NO_COLOR": "1"})


def _healthy_diagnosis() -> WorkspaceDiagnosis:
    """Build a fully healthy WorkspaceDiagnosis."""
    return WorkspaceDiagnosis(
        framework=FrameworkSignal.PRESENT,
        providers={
            Tool.CLAUDE: ProviderDiagnosis(
                tool=Tool.CLAUDE,
                dir_state=ProviderDirSignal.COMPLETE,
                manifest_entry=ManifestEntrySignal.COHERENT,
                content={},
                config=ConfigSignal.OK,
            ),
        },
        builtin_version=BuiltinVersionSignal.CURRENT,
        gitignore=GitignoreSignal.COMPLETE,
    )


def _unhealthy_diagnosis() -> WorkspaceDiagnosis:
    """Build a diagnosis with errors and warnings."""
    return WorkspaceDiagnosis(
        framework=FrameworkSignal.PRESENT,
        providers={
            Tool.CLAUDE: ProviderDiagnosis(
                tool=Tool.CLAUDE,
                dir_state=ProviderDirSignal.PARTIAL,
                manifest_entry=ManifestEntrySignal.COHERENT,
                content={"rule.md": ContentSignal.DIVERGED},
                config=ConfigSignal.OK,
            ),
            Tool.GEMINI: ProviderDiagnosis(
                tool=Tool.GEMINI,
                dir_state=ProviderDirSignal.MISSING,
                manifest_entry=ManifestEntrySignal.ORPHANED,
                content={},
                config=ConfigSignal.MISSING,
            ),
        },
        builtin_version=BuiltinVersionSignal.MODIFIED,
        gitignore=GitignoreSignal.CORRUPTED,
    )


class TestDoctorCommand:
    """Tests for the doctor CLI command output and exit codes."""

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_healthy_exit_zero(self, mock_diagnose):
        mock_diagnose.return_value = _healthy_diagnosis()
        result = runner.invoke(app, ["doctor", "--target", "."])
        assert result.exit_code == 0

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_healthy_output_contains_framework(self, mock_diagnose):
        mock_diagnose.return_value = _healthy_diagnosis()
        result = runner.invoke(app, ["doctor", "--target", "."])
        assert "framework" in result.output.lower()

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_warnings_exit_one(self, mock_diagnose):
        diag = _healthy_diagnosis()
        diag.builtin_version = BuiltinVersionSignal.MODIFIED
        mock_diagnose.return_value = diag
        result = runner.invoke(app, ["doctor", "--target", "."])
        assert result.exit_code == 1

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_errors_exit_two(self, mock_diagnose):
        mock_diagnose.return_value = _unhealthy_diagnosis()
        result = runner.invoke(app, ["doctor", "--target", "."])
        assert result.exit_code == 2

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_json_output_valid(self, mock_diagnose):
        mock_diagnose.return_value = _healthy_diagnosis()
        result = runner.invoke(app, ["doctor", "--target", ".", "--json"])
        data = json.loads(result.output)
        assert "framework" in data
        assert "providers" in data
        assert "builtin_version" in data
        assert "gitignore" in data

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_json_exit_code_reflects_state(self, mock_diagnose):
        mock_diagnose.return_value = _unhealthy_diagnosis()
        result = runner.invoke(app, ["doctor", "--target", ".", "--json"])
        assert result.exit_code == 2
        data = json.loads(result.output)
        assert data["framework"] == "present"

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_missing_framework_exit_two(self, mock_diagnose):
        diag = WorkspaceDiagnosis(framework=FrameworkSignal.MISSING)
        mock_diagnose.return_value = diag
        result = runner.invoke(app, ["doctor", "--target", "."])
        assert result.exit_code == 2

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_output_contains_provider_names(self, mock_diagnose):
        mock_diagnose.return_value = _unhealthy_diagnosis()
        result = runner.invoke(app, ["doctor", "--target", "."])
        assert "claude" in result.output.lower()
        assert "gemini" in result.output.lower()

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_output_contains_builtins_row(self, mock_diagnose):
        mock_diagnose.return_value = _healthy_diagnosis()
        result = runner.invoke(app, ["doctor", "--target", "."])
        assert "builtins" in result.output.lower()

    @patch("vaultspec_core.core.diagnosis.diagnose")
    def test_output_contains_gitignore_row(self, mock_diagnose):
        mock_diagnose.return_value = _healthy_diagnosis()
        result = runner.invoke(app, ["doctor", "--target", "."])
        assert "gitignore" in result.output.lower()
