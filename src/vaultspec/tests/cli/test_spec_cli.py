"""Tests for the spec_cli.py CLI entry point.

Covers: help text for all 11 resource groups, argument parsing via direct
parser access, functional subprocess tests (doctor, readiness, init, rules
list, hooks list), and direct handler dispatch routing.
"""

import json
import subprocess
import sys
from typing import ClassVar

import pytest

from tests.constants import TEST_PROJECT

from .conftest import make_ns, setup_rules_dir

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Helper: run spec_cli as subprocess
# ---------------------------------------------------------------------------


def run_spec(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run vaultspec.spec_cli as subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "vaultspec.spec_cli", *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


# ===================================================================
# Help text (subprocess-based)
# ===================================================================


class TestSpecCliHelp:
    """Verify --help text for all 11 resource groups."""

    def test_main_help(self):
        result = run_spec("--help")
        assert result.returncode == 0
        for resource in [
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
        ]:
            assert resource in result.stdout, f"Missing '{resource}' in help output"

    def test_rules_help(self):
        result = run_spec("rules", "--help")
        assert result.returncode == 0
        for cmd in ["list", "add", "show", "edit", "remove", "rename", "sync"]:
            assert cmd in result.stdout, f"Missing '{cmd}' in rules help"

    def test_agents_help(self):
        result = run_spec("agents", "--help")
        assert result.returncode == 0
        assert "set-tier" in result.stdout

    def test_skills_help(self):
        result = run_spec("skills", "--help")
        assert result.returncode == 0

    def test_config_help(self):
        result = run_spec("config", "--help")
        assert result.returncode == 0
        for cmd in ["show", "sync"]:
            assert cmd in result.stdout, f"Missing '{cmd}' in config help"

    def test_system_help(self):
        result = run_spec("system", "--help")
        assert result.returncode == 0
        for cmd in ["show", "sync"]:
            assert cmd in result.stdout, f"Missing '{cmd}' in system help"

    def test_test_help(self):
        result = run_spec("test", "--help")
        assert result.returncode == 0
        assert "category" in result.stdout

    def test_hooks_help(self):
        result = run_spec("hooks", "--help")
        assert result.returncode == 0
        for cmd in ["list", "run"]:
            assert cmd in result.stdout, f"Missing '{cmd}' in hooks help"

    def test_readiness_help(self):
        result = run_spec("readiness", "--help")
        assert result.returncode == 0
        assert "--json" in result.stdout

    def test_init_help(self):
        result = run_spec("init", "--help")
        assert result.returncode == 0
        assert "--force" in result.stdout


# ===================================================================
# Argument parsing (direct parser access)
# ===================================================================


class TestSpecCliArgParsing:
    """Test argparse configuration by parsing args directly."""

    @pytest.fixture()
    def parser(self):
        """Return the real spec_cli argument parser."""
        from ... import spec_cli

        return spec_cli._make_parser()

    def test_rules_list_parse(self, parser):
        args = parser.parse_args(["rules", "list"])
        assert args.resource == "rules"
        assert args.command == "list"

    def test_rules_add_requires_name(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["rules", "add"])

    def test_rules_add_with_name(self, parser):
        args = parser.parse_args(["rules", "add", "--name", "my-rule"])
        assert args.command == "add"
        assert args.name == "my-rule"

    def test_agents_set_tier_requires_tier(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["agents", "set-tier", "my-agent"])

    def test_agents_set_tier_valid(self, parser):
        args = parser.parse_args(["agents", "set-tier", "my-agent", "--tier", "HIGH"])
        assert args.tier == "HIGH"
        assert args.name == "my-agent"

    def test_agents_add_tier_choices(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["agents", "add", "--name", "x", "--tier", "INVALID"])

    def test_sync_all_flags(self, parser):
        args = parser.parse_args(["sync-all", "--prune", "--dry-run"])
        assert args.prune is True
        assert args.dry_run is True

    def test_test_category_default(self, parser):
        args = parser.parse_args(["test"])
        assert args.category == "all"

    def test_test_category_unit(self, parser):
        args = parser.parse_args(["test", "unit"])
        assert args.category == "unit"

    def test_test_module_flag(self, parser):
        args = parser.parse_args(["test", "--module", "cli"])
        assert args.module == "cli"

    def test_test_invalid_category(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["test", "invalid"])

    def test_readiness_json_flag(self, parser):
        args = parser.parse_args(["readiness", "--json"])
        assert args.json is True

    def test_hooks_run_event(self, parser):
        args = parser.parse_args(["hooks", "run", "post-sync", "--path", "/x"])
        assert args.event == "post-sync"
        assert args.path == "/x"

    def test_init_force_flag(self, parser):
        args = parser.parse_args(["init", "--force"])
        assert args.force is True

    def test_no_resource_defaults_none(self, parser):
        args = parser.parse_args([])
        assert args.resource is None

    def test_root_flag_accepts_path(self, parser, tmp_path):
        args = parser.parse_args(["--root", str(tmp_path), "rules", "list"])
        assert args.root == tmp_path

    def test_rules_show_requires_name(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["rules", "show"])

    def test_rules_rename_requires_both_names(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["rules", "rename", "old-name"])

    def test_rules_rename_valid(self, parser):
        args = parser.parse_args(["rules", "rename", "old-name", "new-name"])
        assert args.old_name == "old-name"
        assert args.new_name == "new-name"


# ===================================================================
# Functional tests (subprocess + test-project / tmp_path)
# ===================================================================


class TestSpecCliFunctional:
    """Functional tests exercising real CLI commands."""

    pytestmark: ClassVar = [pytest.mark.integration]

    def test_doctor_output(self):
        result = run_spec("doctor")
        assert result.returncode == 0
        assert "Python:" in result.stdout

    def test_readiness_text(self):
        result = run_spec("--root", str(TEST_PROJECT), "readiness")
        assert result.returncode == 0
        assert "Readiness Assessment" in result.stdout
        for dimension in ["Documentation", "Framework"]:
            assert dimension in result.stdout

    def test_readiness_json(self):
        result = run_spec("--root", str(TEST_PROJECT), "readiness", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "dimensions" in data
        assert "overall" in data
        assert "recommendations" in data

    def test_init_creates_structure(self, tmp_path):
        # Pre-create minimal .vaultspec so resolve_args_workspace passes validation
        (tmp_path / ".vaultspec").mkdir()
        result = run_spec("--root", str(tmp_path), "init", "--force")
        assert result.returncode == 0
        assert (tmp_path / ".vaultspec" / "rules" / "rules").is_dir()
        assert (tmp_path / ".vaultspec" / "rules" / "agents").is_dir()
        assert (tmp_path / ".vault" / "adr").is_dir()
        assert (tmp_path / ".vault" / "plan").is_dir()

    def test_rules_list_output(self):
        result = run_spec("--root", str(TEST_PROJECT), "rules", "list")
        assert result.returncode == 0

    def test_hooks_list_empty(self, tmp_path):
        # Pre-create minimal .vaultspec so resolve_args_workspace passes validation
        (tmp_path / ".vaultspec").mkdir()
        result = run_spec("--root", str(tmp_path), "hooks", "list")
        assert result.returncode == 0


# ===================================================================
# Direct handler dispatch routing
# ===================================================================


class TestSpecCliDispatchRouting:
    """Test that handlers can be called directly with real Namespace objects."""

    def test_rules_list_handler(self):
        from ...core import rules_list

        ns = make_ns(root=TEST_PROJECT)
        rules_list(ns)

    def test_rules_add_handler(self, tmp_path):
        from ...core import init_paths, rules_add
        from ...core import types as _t

        setup_rules_dir(tmp_path)
        init_paths(tmp_path)

        ns = make_ns(
            root=tmp_path,
            name="test-rule",
            content="Test content for rule.",
            force=False,
        )
        rules_add(ns)

        rule_file = _t.RULES_SRC_DIR / "test-rule.md"
        assert rule_file.exists()
        content = rule_file.read_text(encoding="utf-8")
        assert "test-rule" in content

    def test_config_show_handler(self, capsys):
        from ...core import config_show, init_paths

        init_paths(TEST_PROJECT)
        ns = make_ns(root=TEST_PROJECT)
        config_show(ns)
