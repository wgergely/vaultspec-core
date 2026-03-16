"""Tests for the spec command group (spec rules, spec skills, etc.).

Covers: help text for resource groups, functional tests (rules list, hooks list),
and direct handler dispatch routing.
"""

from typing import ClassVar

import pytest

from .conftest import run_spec, setup_rules_dir

pytestmark = [pytest.mark.unit]


class TestSpecCliHelp:
    """Verify --help text for resource groups under the spec namespace."""

    def test_main_help(self, runner, test_project):
        result = run_spec(runner, "spec", "--help", target=test_project)
        assert result.exit_code == 0
        for resource in [
            "rules",
            "skills",
            "system",
            "hooks",
        ]:
            assert resource in result.output, f"Missing '{resource}' in help output"

    def test_rules_help(self, runner, test_project):
        result = run_spec(runner, "spec", "rules", "--help", target=test_project)
        assert result.exit_code == 0
        for cmd in ["list", "add", "show", "edit", "remove", "rename", "sync"]:
            assert cmd in result.output, f"Missing '{cmd}' in rules help"

    def test_skills_help(self, runner, test_project):
        result = run_spec(runner, "spec", "skills", "--help", target=test_project)
        assert result.exit_code == 0

    def test_system_help(self, runner, test_project):
        result = run_spec(runner, "spec", "system", "--help", target=test_project)
        assert result.exit_code == 0
        for cmd in ["show", "sync"]:
            assert cmd in result.output, f"Missing '{cmd}' in system help"

    def test_hooks_help(self, runner, test_project):
        result = run_spec(runner, "spec", "hooks", "--help", target=test_project)
        assert result.exit_code == 0
        for cmd in ["list", "run"]:
            assert cmd in result.output, f"Missing '{cmd}' in hooks help"


class TestSpecCliFunctional:
    """Functional tests exercising real CLI commands under spec namespace."""

    pytestmark: ClassVar = [pytest.mark.integration]

    def test_rules_list_output(self, runner, test_project):
        result = run_spec(runner, "spec", "rules", "list", target=test_project)
        assert result.exit_code == 0

    def test_hooks_list_empty(self, runner, tmp_path):
        (tmp_path / ".vaultspec").mkdir()
        result = run_spec(runner, "--target", str(tmp_path), "spec", "hooks", "list")
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
