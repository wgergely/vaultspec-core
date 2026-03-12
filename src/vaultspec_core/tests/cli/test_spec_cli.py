"""Tests for the spec_cli.py CLI entry point.

Covers: help text for all resource groups, functional tests (doctor, readiness,
init, rules list, hooks list), and direct handler dispatch routing.
"""

import json
from typing import ClassVar

import pytest

from .conftest import run_spec, setup_rules_dir

pytestmark = [pytest.mark.unit]


class TestSpecCliHelp:
    """Verify --help text for resource groups."""

    def test_main_help(self, runner, test_project):
        result = run_spec(runner, "--help", target=test_project)
        assert result.exit_code == 0
        for resource in [
            "rules",
            "skills",
            "config",
            "system",
            "sync-all",
            "test",
            "doctor",
            "init",
            "readiness",
            "hooks",
        ]:
            assert resource in result.output, f"Missing '{resource}' in help output"

    def test_rules_help(self, runner, test_project):
        result = run_spec(runner, "rules", "--help", target=test_project)
        assert result.exit_code == 0
        for cmd in ["list", "add", "show", "edit", "remove", "rename", "sync"]:
            assert cmd in result.output, f"Missing '{cmd}' in rules help"

    def test_skills_help(self, runner, test_project):
        result = run_spec(runner, "skills", "--help", target=test_project)
        assert result.exit_code == 0

    def test_config_help(self, runner, test_project):
        result = run_spec(runner, "config", "--help", target=test_project)
        assert result.exit_code == 0
        for cmd in ["show", "sync"]:
            assert cmd in result.output, f"Missing '{cmd}' in config help"

    def test_system_help(self, runner, test_project):
        result = run_spec(runner, "system", "--help", target=test_project)
        assert result.exit_code == 0
        for cmd in ["show", "sync"]:
            assert cmd in result.output, f"Missing '{cmd}' in system help"

    def test_test_help(self, runner, test_project):
        result = run_spec(runner, "test", "--help", target=test_project)
        assert result.exit_code == 0
        assert "category" in result.output

    def test_hooks_help(self, runner, test_project):
        result = run_spec(runner, "hooks", "--help", target=test_project)
        assert result.exit_code == 0
        for cmd in ["list", "run"]:
            assert cmd in result.output, f"Missing '{cmd}' in hooks help"

    def test_readiness_help(self, runner, test_project):
        result = run_spec(runner, "readiness", "--help", target=test_project)
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_init_help(self, runner, test_project):
        result = run_spec(runner, "init", "--help", target=test_project)
        assert result.exit_code == 0
        assert "--force" in result.output


class TestSpecCliFunctional:
    """Functional tests exercising real CLI commands."""

    pytestmark: ClassVar = [pytest.mark.integration]

    def test_doctor_output(self, runner, test_project):
        result = run_spec(runner, "doctor", target=test_project)
        assert result.exit_code == 0
        assert "Python" in result.output

    def test_readiness_text(self, runner, test_project):
        result = run_spec(runner, "readiness", target=test_project)
        assert result.exit_code == 0
        assert "Readiness Assessment" in result.output
        for dimension in ["Documentation", "Framework"]:
            assert dimension in result.output

    def test_readiness_json(self, runner, test_project):
        result = run_spec(runner, "readiness", "--json", target=test_project)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "dimensions" in data
        assert "overall" in data
        assert "recommendations" in data

    def test_init_creates_structure(self, runner, tmp_path):
        (tmp_path / ".vaultspec").mkdir()
        result = run_spec(runner, "--target", str(tmp_path), "init", "--force")
        assert result.exit_code == 0
        assert (tmp_path / ".vaultspec" / "rules" / "rules").is_dir()
        assert (tmp_path / ".vault" / "adr").is_dir()
        assert (tmp_path / ".vault" / "plan").is_dir()
        assert (tmp_path / ".codex" / "config.toml").is_file()

    def test_rules_list_output(self, runner, test_project):
        result = run_spec(runner, "rules", "list", target=test_project)
        assert result.exit_code == 0

    def test_hooks_list_empty(self, runner, tmp_path):
        (tmp_path / ".vaultspec").mkdir()
        result = run_spec(runner, "--target", str(tmp_path), "hooks", "list")
        assert result.exit_code == 0


class TestSpecCliDispatchRouting:
    """Test that core handlers can be called directly."""

    def test_rules_list_handler(self, test_project):
        from ...core import rules_list

        rules_list()

    def test_rules_add_handler(self, tmp_path):
        from ...core import init_paths, rules_add
        from ...core import types as _t

        setup_rules_dir(tmp_path)
        init_paths(tmp_path)

        rules_add(
            name="test-rule",
            content="Test content for rule.",
            force=False,
        )

        rule_file = _t.RULES_SRC_DIR / "test-rule.md"
        assert rule_file.exists()
        content = rule_file.read_text(encoding="utf-8")
        assert "test-rule" in content

    def test_config_show_handler(self, test_project):
        from ...core import config_show

        config_show()
