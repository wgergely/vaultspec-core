"""Tests for the ``vaultspec-core doctor`` CLI command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


class TestDoctorCommand:
    """Tests for the doctor CLI command output and exit codes."""

    def test_installed_workspace_does_not_error(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()
        result = factory.run("doctor")
        assert result.exit_code in (0, 1)

    def test_output_contains_framework(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()
        result = factory.run("doctor")
        assert "framework" in result.output.lower()

    def test_corrupted_manifest_exit_two(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install().corrupt_manifest()
        result = factory.run("doctor")
        assert result.exit_code == 2

    def test_json_output_valid(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()
        result = factory.run("doctor", "--json")
        data = json.loads(result.output)
        assert "framework" in data
        assert "providers" in data
        assert "builtin_version" in data
        assert "gitignore" in data

    def test_json_exit_code_reflects_corrupted_state(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install().corrupt_manifest()
        result = factory.run("doctor", "--json")
        assert result.exit_code == 2
        # The output may contain log warnings before the JSON payload.
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert data["framework"] == "corrupted"

    def test_missing_framework_exit_two(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        result = factory.run("doctor")
        assert result.exit_code == 2

    def test_output_contains_provider_names(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()
        result = factory.run("doctor")
        assert "claude" in result.output.lower()

    def test_output_contains_builtins_row(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()
        result = factory.run("doctor")
        assert "builtins" in result.output.lower()

    def test_output_contains_gitignore_row(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()
        result = factory.run("doctor")
        assert "gitignore" in result.output.lower()

    def test_deleted_vaultspec_dir_exit_two(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install().delete_vaultspec_dir()
        result = factory.run("doctor")
        assert result.exit_code == 2

    def test_json_healthy_framework_present(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()
        result = factory.run("doctor", "--json")
        data = json.loads(result.output)
        assert data["framework"] == "present"
