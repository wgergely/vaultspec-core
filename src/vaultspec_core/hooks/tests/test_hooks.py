"""Unit tests for the hooks engine."""

from __future__ import annotations

import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

from ...hooks import (
    SUPPORTED_EVENTS,
    Hook,
    HookAction,
    HookResult,
    fire_hooks,
    load_hooks,
    trigger,
)

if TYPE_CHECKING:
    from pathlib import Path

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
    """Test action parsing, exercised through load_hooks() (the public entry
    point that drives the private action/hook parsers)."""

    @staticmethod
    def _load_single_hook(tmp_path: Path, actions_yaml: str) -> Hook:
        (tmp_path / "test.yaml").write_text(
            f"event: config.synced\nactions:\n{actions_yaml}",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        return hooks[0]

    def test_shell_action(self, tmp_path: Path) -> None:
        hook = self._load_single_hook(
            tmp_path, "  - type: shell\n    command: echo hello\n"
        )
        assert len(hook.actions) == 1
        action = hook.actions[0]
        assert action.action_type == "shell"
        assert action.command == "echo hello"

    def test_shell_missing_command(self, tmp_path: Path) -> None:
        hook = self._load_single_hook(tmp_path, "  - type: shell\n")
        assert hook.actions == []

    def test_unknown_type(self, tmp_path: Path) -> None:
        hook = self._load_single_hook(tmp_path, "  - type: webhook\n")
        assert hook.actions == []

    def test_empty_dict(self, tmp_path: Path) -> None:
        hook = self._load_single_hook(tmp_path, "  - {}\n")
        assert hook.actions == []


class TestParseHook:
    """Test hook parsing from YAML files via load_hooks()."""

    def test_valid_hook(self, tmp_path: Path) -> None:
        (tmp_path / "test.yaml").write_text(
            "event: config.synced\nactions:\n  - type: shell\n    command: echo done\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        hook = hooks[0]
        assert hook.name == "test"
        assert hook.event == "config.synced"
        assert len(hook.actions) == 1
        assert hook.enabled is True

    def test_missing_event(self, tmp_path: Path) -> None:
        (tmp_path / "test.yaml").write_text("enabled: true\n", encoding="utf-8")
        assert load_hooks(tmp_path) == []

    def test_unsupported_event(self, tmp_path: Path) -> None:
        (tmp_path / "test.yaml").write_text("event: unknown.event\n", encoding="utf-8")
        assert load_hooks(tmp_path) == []

    def test_disabled_hook(self, tmp_path: Path) -> None:
        (tmp_path / "test.yaml").write_text(
            "event: config.synced\nenabled: false\n"
            "actions:\n  - type: shell\n    command: echo x\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        assert hooks[0].enabled is False

    def test_multiple_actions(self, tmp_path: Path) -> None:
        (tmp_path / "test.yaml").write_text(
            "event: vault.document.created\nactions:\n"
            "  - type: shell\n    command: echo 1\n"
            "  - type: shell\n    command: echo 2\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        assert len(hooks[0].actions) == 2


class TestLoadHooks:
    """Test loading hooks from a directory."""

    def test_empty_dir(self, tmp_path: Path) -> None:
        hooks = load_hooks(tmp_path)
        assert hooks == []

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        hooks = load_hooks(tmp_path / "nonexistent")
        assert hooks == []

    def test_loads_yaml(self, tmp_path: Path) -> None:
        hook_file = tmp_path / "my-hook.yaml"
        hook_file.write_text(
            "event: config.synced\nactions:\n  - type: shell\n    command: echo done\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1
        assert hooks[0].name == "my-hook"

    def test_loads_yml(self, tmp_path: Path) -> None:
        hook_file = tmp_path / "my-hook.yml"
        hook_file.write_text(
            "event: config.synced\nactions:\n  - type: shell\n    command: echo done\n",
            encoding="utf-8",
        )
        hooks = load_hooks(tmp_path)
        assert len(hooks) == 1

    def test_skips_invalid(self, tmp_path: Path) -> None:
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
    """Test template variable interpolation, exercised through trigger()
    (the public entry point that drives the private interpolation step)."""

    @staticmethod
    def _interpolated_output(tmp_path: Path, template: str, ctx: dict[str, str]) -> str:
        script = tmp_path / "echo_arg.py"
        script.write_text("import sys; print(sys.argv[1])", encoding="utf-8")
        exe = sys.executable.replace("\\", "/")
        script_path = str(script).replace("\\", "/")
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[
                HookAction(
                    action_type="shell",
                    command=f"{exe} {script_path} {template}",
                ),
            ],
        )
        results = trigger([hook], "config.synced", ctx)
        assert len(results) == 1
        assert results[0].success is True
        return results[0].output

    def test_basic(self, tmp_path: Path) -> None:
        assert self._interpolated_output(
            tmp_path, "hello_{name}", {"name": "world"}
        ) == ("hello_world")

    def test_multiple_vars(self, tmp_path: Path) -> None:
        result = self._interpolated_output(
            tmp_path, "{a}_and_{b}", {"a": "X", "b": "Y"}
        )
        assert result == "X_and_Y"

    def test_missing_var_unchanged(self, tmp_path: Path) -> None:
        assert self._interpolated_output(tmp_path, "{missing}", {}) == "{missing}"

    def test_empty_context(self, tmp_path: Path) -> None:
        assert self._interpolated_output(tmp_path, "no_vars", {}) == "no_vars"


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

    def test_context_interpolation(self, tmp_path: Path) -> None:
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

    def test_failing_command(self, tmp_path: Path) -> None:
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

    def test_yaml_takes_precedence_over_yml(self, tmp_path: Path) -> None:
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

    def test_unique_stems_load_all(self, tmp_path: Path) -> None:
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
    """Test that a concurrent trigger() of an in-flight event is blocked, and
    that the guard is released once the in-flight call completes.

    These exercise the real guard through the public trigger() entry point: a
    background thread is given a genuinely slow shell action so a second,
    concurrent trigger() call for the same event observes the guard while the
    first is still running.
    """

    def test_reentrant_trigger_returns_empty(self, tmp_path: Path) -> None:
        marker = tmp_path / "started"
        script = tmp_path / "slow.py"
        script.write_text(
            "import pathlib, time\n"
            f"pathlib.Path({str(marker)!r}).touch()\n"
            "time.sleep(1)\n",
            encoding="utf-8",
        )
        exe = sys.executable.replace("\\", "/")
        script_path = str(script).replace("\\", "/")
        hook = Hook(
            name="test",
            event="config.synced",
            actions=[HookAction(action_type="shell", command=f"{exe} {script_path}")],
        )

        outer_results: list[HookResult] = []

        def run_outer() -> None:
            outer_results.extend(trigger([hook], "config.synced"))

        outer_thread = threading.Thread(target=run_outer)
        outer_thread.start()
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert marker.exists(), "outer trigger's shell action never started"

            inner_results = trigger([hook], "config.synced")
            assert inner_results == []
        finally:
            outer_thread.join(timeout=5)

        assert len(outer_results) == 1
        assert outer_results[0].success is True

    def test_non_reentrant_trigger_works(self):
        # A normal, non-concurrent call is never affected by the guard.
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

    def test_guard_released_after_execution(self):
        # If the guard were not released, this second call would be blocked
        # and return [] just like the reentrant case above.
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
        first = trigger([hook], "audit.completed")
        assert len(first) == 1
        assert first[0].success is True

        second = trigger([hook], "audit.completed")
        assert len(second) == 1
        assert second[0].success is True


class TestFireHooksIntegration:
    """Integration tests for the load_hooks + trigger combination.

    fire_hooks() internally uses _t.HOOKS_DIR which requires workspace
    initialisation. These tests exercise the same real code path by calling
    load_hooks(tmp_path) + trigger() directly.
    """

    def test_shell_hook_side_effect(self, tmp_path: Path) -> None:
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

    def test_no_hooks_returns_empty(self, tmp_path: Path) -> None:
        hooks = load_hooks(tmp_path)
        results = trigger(hooks, "vault.document.created")
        assert results == []


class TestFireHooksExplicitDirectory:
    """``fire_hooks(hooks_dir=...)`` must load from that directory, not the
    ambient workspace context.

    Regression coverage for the sync ``--target`` bug where the hook
    definitions loaded came from whichever workspace happened to be
    ambient rather than the one a caller explicitly names. Passing
    ``hooks_dir`` also means a caller can exercise ``fire_hooks`` without
    workspace initialisation at all.
    """

    def test_loads_from_the_explicit_directory_not_the_ambient_context(
        self, tmp_path: Path
    ) -> None:
        explicit_dir = tmp_path / "explicit-hooks"
        explicit_dir.mkdir()
        marker = tmp_path / "fired.txt"
        script = tmp_path / "create_marker.py"
        script.write_text(
            f"import pathlib; pathlib.Path({str(marker)!r}).touch()",
            encoding="utf-8",
        )
        (explicit_dir / "marker.yaml").write_text(
            "event: config.synced\nenabled: true\nactions:\n"
            f"  - type: shell\n    command: {sys.executable} {script}\n",
            encoding="utf-8",
        )

        # Deliberately do not initialise any workspace context: the whole
        # point of the explicit hooks_dir parameter is that fire_hooks does
        # not need one when it is given.
        fire_hooks("config.synced", hooks_dir=explicit_dir)

        assert marker.exists(), (
            "fire_hooks(hooks_dir=...) must load hooks from the directory it was given"
        )
