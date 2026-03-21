"""Unit tests for the hooks engine."""

from __future__ import annotations

import sys

import pytest

from ...hooks import (
    SUPPORTED_EVENTS,
    Hook,
    HookAction,
    load_hooks,
    trigger,
)
from ...hooks.engine import (
    _interpolate,
    _parse_action,
    _parse_hook,
    _triggering,
)

pytestmark = [pytest.mark.unit]


class TestSupportedEvents:
    """Verify the set of supported events."""

    def test_events_is_frozenset(self):
        assert isinstance(SUPPORTED_EVENTS, frozenset)

    def test_expected_events(self):
        expected = {
            "vault.document.created",
            "config.synced",
            "audit.completed",
        }
        assert expected == SUPPORTED_EVENTS


class TestParseAction:
    """Test action parsing from dicts."""

    def test_shell_action(self):
        raw = {"type": "shell", "command": "echo hello"}
        action = _parse_action(raw)
        assert action is not None
        assert action.action_type == "shell"
        assert action.command == "echo hello"

    def test_shell_missing_command(self):
        assert _parse_action({"type": "shell"}) is None

    def test_unknown_type(self):
        assert _parse_action({"type": "webhook"}) is None

    def test_empty_dict(self):
        assert _parse_action({}) is None


class TestParseHook:
    """Test hook parsing from YAML dicts."""

    def test_valid_hook(self, tmp_path):
        path = tmp_path / "test.yaml"
        data = {
            "event": "config.synced",
            "actions": [
                {"type": "shell", "command": "echo done"},
            ],
        }
        hook = _parse_hook(path, data)
        assert hook is not None
        assert hook.name == "test"
        assert hook.event == "config.synced"
        assert len(hook.actions) == 1
        assert hook.enabled is True

    def test_missing_event(self, tmp_path):
        path = tmp_path / "test.yaml"
        assert _parse_hook(path, {}) is None

    def test_unsupported_event(self, tmp_path):
        path = tmp_path / "test.yaml"
        data = {"event": "unknown.event"}
        assert _parse_hook(path, data) is None

    def test_disabled_hook(self, tmp_path):
        path = tmp_path / "test.yaml"
        data = {
            "event": "config.synced",
            "enabled": False,
            "actions": [
                {"type": "shell", "command": "echo x"},
            ],
        }
        hook = _parse_hook(path, data)
        assert hook is not None
        assert hook.enabled is False

    def test_multiple_actions(self, tmp_path):
        path = tmp_path / "test.yaml"
        data = {
            "event": "vault.document.created",
            "actions": [
                {"type": "shell", "command": "echo 1"},
                {"type": "shell", "command": "echo 2"},
            ],
        }
        hook = _parse_hook(path, data)
        assert hook is not None
        assert len(hook.actions) == 2


class TestLoadHooks:
    """Test loading hooks from a directory."""

    def test_empty_dir(self, tmp_path):
        hooks = load_hooks(tmp_path)
        assert hooks == []

    def test_nonexistent_dir(self, tmp_path):
        hooks = load_hooks(tmp_path / "nonexistent")
        assert hooks == []

    def test_loads_yaml(self, tmp_path):
        hook_file = tmp_path / "my-hook.yaml"
        hook_file.write_text(
            "event: config.synced\nactions:\n  - type: shell\n    command: echo done\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        assert hooks[0].name == "my-hook"

    def test_loads_yml(self, tmp_path):
        hook_file = tmp_path / "my-hook.yml"
        hook_file.write_text(
            "event: config.synced\nactions:\n  - type: shell\n    command: echo done\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1

    def test_skips_invalid(self, tmp_path):
        # Valid hook
        (tmp_path / "good.yaml").write_text(
            "event: config.synced\nactions:\n  - type: shell\n    command: echo ok\n",
            encoding="utf-8",
        )
        # Invalid  - missing event
        (tmp_path / "bad.yaml").write_text(
            "actions:\n  - type: shell\n    command: echo bad\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        assert hooks[0].name == "good"


class TestInterpolate:
    """Test template variable interpolation."""

    def test_basic(self):
        assert _interpolate("hello {name}", {"name": "world"}) == ("hello world")

    def test_multiple_vars(self):
        result = _interpolate(
            "{a} and {b}",
            {"a": "X", "b": "Y"},
        )
        assert result == "X and Y"

    def test_missing_var_unchanged(self):
        assert _interpolate("{missing}", {}) == "{missing}"

    def test_empty_context(self):
        assert _interpolate("no vars", {}) == "no vars"


class TestTrigger:
    """Test hook triggering."""

    def test_no_matching_hooks(self):
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(action_type="shell", command="echo x"),
            ],
        )
        results = trigger([hook], "vault.index.updated")
        assert results == []

    def test_disabled_hooks_skipped(self):
        hook = Hook(
            name="test",
            event="config.synced",
            enabled=False,
            actions=[
                HookAction(action_type="shell", command="echo x"),
            ],
        )
        results = trigger([hook], "config.synced")
        assert results == []

    def test_shell_execution(self):
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(
                    action_type="shell",
                    command=f"{sys.executable.replace('\\', '/')} -V",
                ),
            ],
        )
        results = trigger([hook], "config.synced")
        assert len(results) == 1
        assert results[0].success is True
        assert "Python" in results[0].output

    def test_context_interpolation(self, tmp_path):
        script = tmp_path / "print_arg.py"
        script.write_text("import sys\nprint(sys.argv[1])", encoding="utf-8")
        exe = sys.executable.replace("\\", "/")
        script_path = str(script).replace("\\", "/")
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(
                    action_type="shell",
                    command=f"{exe} {script_path} {{root}}",
                ),
            ],
        )
        results = trigger(
            [hook],
            "config.synced",
            {"root": "/tmp/test"},
        )
        assert len(results) == 1
        assert results[0].success is True

    def test_failing_command(self, tmp_path):
        # Write the script to a file to avoid shell quoting issues on Windows.
        script = tmp_path / "fail.py"
        script.write_text("import sys; sys.exit(1)", encoding="utf-8")
        exe = sys.executable.replace("\\", "/")
        script_path = str(script).replace("\\", "/")
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(
                    action_type="shell",
                    command=f"{exe} {script_path}",
                ),
            ],
        )
        results = trigger([hook], "config.synced")
        assert len(results) == 1
        assert results[0].success is False


class TestDeduplication:
    """Test that duplicate yaml/yml stems load only one hook."""

    def test_yaml_takes_precedence_over_yml(self, tmp_path):
        yaml_content = (
            "event: config.synced\nactions:\n  - type: shell\n    command: echo yaml\n"
        )
        yml_content = (
            "event: config.synced\nactions:\n  - type: shell\n    command: echo yml\n"
        )
        (tmp_path / "hook.yaml").write_text(yaml_content, encoding="utf-8")
        (tmp_path / "hook.yml").write_text(yml_content, encoding="utf-8")
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        assert hooks[0].source_path is not None
        assert hooks[0].source_path.suffix == ".yaml"

    def test_unique_stems_load_all(self, tmp_path):
        (tmp_path / "hook-a.yaml").write_text(
            "event: config.synced\nactions:\n  - type: shell\n    command: echo a\n",
            encoding="utf-8",
        )
        (tmp_path / "hook-b.yml").write_text(
            "event: audit.completed\nactions:\n  - type: shell\n    command: echo b\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 2


class TestReentrantGuard:
    """Test that recursive trigger of the same event is blocked."""

    def test_reentrant_trigger_returns_empty(self):
        # Directly mutate the module-level _triggering set to simulate a
        # re-entrant call (as if trigger() is already running for this event).
        # This avoids mocking  - we exercise the real guard path in trigger().
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(
                    action_type="shell",
                    command=f"{sys.executable.replace('\\', '/')} -V",
                )
            ],
        )
        _triggering.add("config.synced")
        try:
            results = trigger([hook], "config.synced")
            assert results == []
        finally:
            _triggering.discard("config.synced")

    def test_non_reentrant_trigger_works(self):
        # Ensure the guard does not affect a different event or a clean state.
        _triggering.discard("config.synced")
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(
                    action_type="shell",
                    command=f"{sys.executable.replace('\\', '/')} -V",
                )
            ],
        )
        results = trigger([hook], "config.synced")
        assert len(results) == 1
        assert results[0].success is True

    def test_triggering_set_cleaned_up_after_execution(self):
        hook = Hook(
            name="test",
            event="audit.completed",
            actions=[
                HookAction(
                    action_type="shell",
                    command=f"{sys.executable.replace('\\', '/')} -V",
                )
            ],
        )
        trigger([hook], "audit.completed")
        assert "audit.completed" not in _triggering


class TestFireHooksIntegration:
    """Integration tests for the load_hooks + trigger combination.

    fire_hooks() internally uses _t.HOOKS_DIR which requires workspace
    initialisation. These tests exercise the same real code path by calling
    load_hooks(tmp_path) + trigger() directly.
    """

    def test_shell_hook_side_effect(self, tmp_path):
        marker = tmp_path / "hook-fired.txt"
        # Write a helper script to a file to avoid backslash escaping issues
        # with Windows paths embedded inside YAML command strings.
        script = tmp_path / "create_marker.py"
        script.write_text(
            f"import pathlib; pathlib.Path({str(marker)!r}).touch()",
            encoding="utf-8",
        )
        hook_content = (
            "event: vault.document.created\n"
            "actions:\n"
            f"  - type: shell\n"
            f"    command: {sys.executable} {script}\n"
        )
        (tmp_path / "marker-hook.yaml").write_text(hook_content, encoding="utf-8")

        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1

        results = trigger(
            hooks,
            "vault.document.created",
            {"root": str(tmp_path), "event": "vault.document.created"},
        )
        assert len(results) == 1
        assert results[0].success is True
        assert marker.exists(), "Shell hook should have created the marker file"

    def test_no_hooks_returns_empty(self, tmp_path):
        hooks = load_hooks(tmp_path)
        results = trigger(hooks, "vault.document.created")
        assert results == []
