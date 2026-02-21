"""Unit tests for the hooks engine."""

from __future__ import annotations

import pytest

from vaultspec.hooks import (
    SUPPORTED_EVENTS,
    Hook,
    HookAction,
    load_hooks,
    trigger,
)
from vaultspec.hooks.engine import (
    _interpolate,
    _parse_action,
    _parse_hook,
)

pytestmark = [pytest.mark.unit]


class TestSupportedEvents:
    """Verify the set of supported events."""

    def test_events_is_frozenset(self):
        assert isinstance(SUPPORTED_EVENTS, frozenset)

    def test_expected_events(self):
        expected = {
            "vault.document.created",
            "vault.document.modified",
            "vault.index.updated",
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

    def test_agent_action(self):
        raw = {
            "type": "agent",
            "name": "vaultspec-reviewer",
            "task": "Review {path}",
        }
        action = _parse_action(raw)
        assert action is not None
        assert action.action_type == "agent"
        assert action.agent_name == "vaultspec-reviewer"
        assert action.task == "Review {path}"

    def test_shell_missing_command(self):
        assert _parse_action({"type": "shell"}) is None

    def test_agent_missing_name(self):
        raw = {"type": "agent", "task": "do something"}
        assert _parse_action(raw) is None

    def test_agent_missing_task(self):
        raw = {"type": "agent", "name": "some-agent"}
        assert _parse_action(raw) is None

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
        # Invalid — missing event
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
                    command="echo hello",
                ),
            ],
        )
        results = trigger([hook], "config.synced")
        assert len(results) == 1
        assert results[0].success is True
        assert "hello" in results[0].output

    def test_context_interpolation(self):
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(
                    action_type="shell",
                    command="echo {root}",
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

    def test_failing_command(self):
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(
                    action_type="shell",
                    command="exit 1",
                ),
            ],
        )
        results = trigger([hook], "config.synced")
        assert len(results) == 1
        assert results[0].success is False
