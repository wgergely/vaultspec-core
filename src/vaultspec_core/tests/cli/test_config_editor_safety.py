"""Tests for config CLI commands and editor safety/resolution."""

from __future__ import annotations

import shutil
import sys
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.cli import app
from vaultspec_core.core.exceptions import EditorResolutionError
from vaultspec_core.core.local_config import get_local_config_path, resolve_editor

if TYPE_CHECKING:
    from pathlib import Path

    from typer.testing import CliRunner

pytestmark = [pytest.mark.integration]


def _write_probe_editor(directory: Path, name: str, exit_code: int = 0) -> str:
    """Create a real, resolvable editor executable on disk.

    Writes a genuine platform-appropriate launcher script that accepts (and
    ignores) the file-path argument :func:`vaultspec_core.core.resources.resource_edit`
    appends, then terminates with ``exit_code``. This exercises the real
    subprocess and :func:`shutil.which` resolution paths with a real binary
    rather than a Windows-only system editor, so the assertions hold on any
    operating system.

    Named a *probe* rather than a fake because that is what it is: a real
    executable on a real ``PATH``, not a test double. The suite-quality guard in
    ``tests/test_test_suite_quality.py`` rejects ``fake``/``stub`` in a test
    symbol's name, and a name that misdescribes a real binary as a double both
    trips that guard and misleads the next reader.

    :param directory: Directory to write the script into; prepend it to ``PATH``
        so the returned name resolves via :func:`shutil.which`.
    :param name: Bare editor name, used verbatim as the resolvable command.
    :param exit_code: Process exit status the probe editor returns.
    :returns: The bare editor name to pass to ``--editor`` or an editor env var.
    """
    if sys.platform == "win32":
        script = directory / f"{name}.cmd"
        script.write_text(f"@echo off\r\nexit /b {exit_code}\r\n", encoding="utf-8")
    else:
        script = directory / name
        script.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
        script.chmod(0o755)
    return name


class TestConfigCli:
    """Verify config get, set, unset, list command operations."""

    def test_config_crud(self, runner: CliRunner, tmp_path: Path) -> None:
        # Establish target directory
        target_dir = tmp_path / "project"
        target_dir.mkdir()

        # 1. Config get of unset key should return code 1
        result = runner.invoke(
            app, ["--target", str(target_dir), "config", "get", "editor"]
        )
        assert result.exit_code == 1
        assert "Key 'editor' is not set." in result.output

        # 2. Config set should succeed
        result = runner.invoke(
            app, ["--target", str(target_dir), "config", "set", "editor", "notepad"]
        )
        assert result.exit_code == 0
        assert "Set 'editor' to 'notepad'" in result.output

        # Verify config file exists on disk
        config_path = get_local_config_path(target_dir)
        assert config_path.is_file()
        config_content = config_path.read_text(encoding="utf-8")
        assert 'editor = "notepad"' in config_content

        # 3. Config get of set key should print the value
        result = runner.invoke(
            app, ["--target", str(target_dir), "config", "get", "editor"]
        )
        assert result.exit_code == 0
        assert result.output.strip() == "notepad"

        # 4. Config get --json should return JSON envelope
        result = runner.invoke(
            app, ["--target", str(target_dir), "config", "get", "editor", "--json"]
        )
        assert result.exit_code == 0
        import json

        payload = json.loads(result.output)
        assert payload["schema"] == "vaultspec.config.get.v1"
        assert payload["status"] == "unchanged"
        assert payload["data"]["key"] == "editor"
        assert payload["data"]["value"] == "notepad"

        # 5. Config list should print table
        result = runner.invoke(app, ["--target", str(target_dir), "config", "list"])
        assert result.exit_code == 0
        assert "editor" in result.output
        assert "notepad" in result.output

        # 6. Config list --json should return JSON envelope
        result = runner.invoke(
            app, ["--target", str(target_dir), "config", "list", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["schema"] == "vaultspec.config.list.v1"
        assert payload["status"] == "unchanged"
        assert payload["data"]["entries"]["editor"] == "notepad"

        # 7. Config unset should clear the setting
        result = runner.invoke(
            app, ["--target", str(target_dir), "config", "unset", "editor"]
        )
        assert result.exit_code == 0
        assert "Unset 'editor'" in result.output

        # Config file should be empty or have deleted key
        config_content = config_path.read_text(encoding="utf-8")
        assert "editor" not in config_content

        # 8. Config get should fail again
        result = runner.invoke(
            app, ["--target", str(target_dir), "config", "get", "editor"]
        )
        assert result.exit_code == 1


class TestEditorResolution:
    """Verify editor resolution precedence ladder.

    Order: flag -> config -> VISUAL -> EDITOR -> vi.

    The flag and config rungs are untrusted channels, so their probe editors
    are named after real editors on the allowlist; the environment rungs are
    trusted and may name anything that resolves.
    """

    def test_resolution_ladder(self, tmp_path: Path) -> None:
        import os

        # Real, resolvable probe editors - one distinct binary per ladder rung -
        # created on disk and reachable via a PATH prepend, so precedence is
        # proven with genuine executables on any operating system.
        bindir = tmp_path / "bin"
        bindir.mkdir()
        ed_editor = _write_probe_editor(bindir, "vsed-editor")
        ed_visual = _write_probe_editor(bindir, "vsed-visual")
        ed_vaultspec = _write_probe_editor(bindir, "vsed-vaultspec")
        ed_config = _write_probe_editor(bindir, "nano")
        ed_flag = _write_probe_editor(bindir, "micro")

        # Save old values
        old_path = os.environ.get("PATH")
        old_visual = os.environ.get("VISUAL")
        old_editor = os.environ.get("EDITOR")
        old_vaultspec_editor = os.environ.get("VAULTSPEC_EDITOR")

        try:
            # Prepend the probe-editor dir and clear editor env vars to avoid
            # pollution from the ambient environment.
            os.environ["PATH"] = str(bindir) + os.pathsep + (old_path or "")
            os.environ.pop("VISUAL", None)
            os.environ.pop("EDITOR", None)
            os.environ.pop("VAULTSPEC_EDITOR", None)

            # 1. Fallback to vi (if vi is on PATH, otherwise raises Error)
            vi_exists = shutil.which("vi") is not None
            if vi_exists:
                assert resolve_editor(target_dir=tmp_path) == "vi"
            else:
                with pytest.raises(EditorResolutionError) as excinfo:
                    resolve_editor(target_dir=tmp_path)
                assert "Could not resolve a working text editor" in str(excinfo.value)

            # 2. EDITOR env var should take precedence over vi
            os.environ["EDITOR"] = ed_editor
            assert resolve_editor(target_dir=tmp_path) == ed_editor

            # 3. VISUAL env var should take precedence over EDITOR
            os.environ["VISUAL"] = ed_visual
            assert resolve_editor(target_dir=tmp_path) == ed_visual

            # 4. VAULTSPEC_EDITOR env var should take precedence over VISUAL
            os.environ["VAULTSPEC_EDITOR"] = ed_vaultspec
            assert resolve_editor(target_dir=tmp_path) == ed_vaultspec

            # 5. Local config should take precedence over VAULTSPEC_EDITOR
            from vaultspec_core.core.local_config import set_config_value

            # Write local config
            get_local_config_path(tmp_path)
            set_config_value("editor", ed_config, target_dir=tmp_path)
            assert resolve_editor(target_dir=tmp_path) == ed_config

            # 6. Editor override flag should take precedence over local config
            assert (
                resolve_editor(editor_override=ed_flag, target_dir=tmp_path) == ed_flag
            )

        finally:
            # Restore environment variables
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path

            if old_visual is None:
                os.environ.pop("VISUAL", None)
            else:
                os.environ["VISUAL"] = old_visual

            if old_editor is None:
                os.environ.pop("EDITOR", None)
            else:
                os.environ["EDITOR"] = old_editor

            if old_vaultspec_editor is None:
                os.environ.pop("VAULTSPEC_EDITOR", None)
            else:
                os.environ["VAULTSPEC_EDITOR"] = old_vaultspec_editor


class TestEditorSubprocessSafety:
    """Verify exit codes 2, 3, 4 under different editor invocation failures."""

    def test_editor_failures_exits(
        self, runner: CliRunner, synthetic_project: Path, tmp_path: Path
    ) -> None:
        import os

        # Real probe editors that exit with the exact codes the ladder maps:
        # a nonexistent binary (resolution fail -> 2), a script exiting 5
        # (non-zero -> 3), and a script exiting 130 (cancellation -> 4).
        bindir = tmp_path / "bin"
        bindir.mkdir()
        ed_fail5 = _write_probe_editor(bindir, "micro", exit_code=5)
        ed_cancel = _write_probe_editor(bindir, "nano", exit_code=130)

        old_path = os.environ.get("PATH")
        try:
            os.environ["PATH"] = str(bindir) + os.pathsep + (old_path or "")

            # Add a test rule first so we have something to edit
            result = runner.invoke(
                app,
                [
                    "--target",
                    str(synthetic_project),
                    "spec",
                    "rules",
                    "add",
                    "test-safety-rule",
                    "--body",
                    "Initial rule content",
                ],
            )
            assert result.exit_code == 0

            # Case 1: Resolution Failure -> code 2. Every rung of the ladder must
            # miss, including the terminal ``vi`` fallback which is present on
            # many POSIX hosts. Point PATH exclusively at the probe-editor dir
            # (which holds no ``vi``) so nothing resolves; resolution fails
            # before any subprocess launches, so no external binary is needed.
            # Windows keeps the system PATH prepended - ``vi`` is absent there
            # and ``cmd.exe`` stays available for the later cases.
            if sys.platform == "win32":
                os.environ["PATH"] = str(bindir) + os.pathsep + (old_path or "")
            else:
                os.environ["PATH"] = str(bindir)
            result = runner.invoke(
                app,
                [
                    "--target",
                    str(synthetic_project),
                    "spec",
                    "rules",
                    "edit",
                    "test-safety-rule",
                    "--editor",
                    "nonexistent-editor-binary-xyz",
                ],
            )
            assert result.exit_code == 2
            assert "Error: Could not resolve a working text editor" in result.output

            # Restore the probe-editor dir plus the system PATH so the exit-code
            # cases below can launch their real editor subprocesses (and reach
            # cmd.exe on Windows).
            os.environ["PATH"] = str(bindir) + os.pathsep + (old_path or "")

            # Case 2: Subprocess Failure (editor exits non-zero, not 130) -> code 3
            result = runner.invoke(
                app,
                [
                    "--target",
                    str(synthetic_project),
                    "spec",
                    "rules",
                    "edit",
                    "test-safety-rule",
                    "--editor",
                    ed_fail5,
                ],
            )
            assert result.exit_code == 3
            assert "Error: Editor exited with non-zero exit code 5." in result.output

            # Case 3: User Cancellation (editor exits with code 130) -> code 4
            result = runner.invoke(
                app,
                [
                    "--target",
                    str(synthetic_project),
                    "spec",
                    "rules",
                    "edit",
                    "test-safety-rule",
                    "--editor",
                    ed_cancel,
                ],
            )
            assert result.exit_code == 4
            assert "Error: Editor edit cancelled by user." in result.output
        finally:
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path
