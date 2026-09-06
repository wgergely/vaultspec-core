"""Security regression tests for the editor command surface.

The editor setting is the one place where this package takes a command string
from the user and hands it to the operating system, and it used to hand over
whatever it was given. Anything the user could name got run: the setting was an
"open my file" control by intent and an "execute this" control in fact.

Three channels carried that value, and all three are exercised here: the
per-invocation ``--editor`` flag, the project-local ``.vaultspec/config.toml``
``editor`` key that persists it, and the environment variables that back the
ordinary terminal workflow. The tests assert the closure *and* the workflow -
a user with ``EDITOR=vim`` or ``--editor "code --wait"`` must be no worse off
than before, and a legitimately unusable value must still fail the way it
always did rather than in some new way.

Everything here runs the real CLI over the real filesystem with real
executables on a real ``PATH``. The probe programs are inert: each one writes a
marker file and exits. There is no test double anywhere in this file, and the
environment is configured through the CLI runner's own ``env=`` argument
rather than by patching the interpreter's view of it.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.cli import app
from vaultspec_core.core.editor import (
    EDITOR_PROGRAM_ALLOWLIST,
    GATEWAY_ENV_MARKER,
    EditorValidationError,
    editor_program_name,
    validate_editor_command,
)
from vaultspec_core.core.local_config import get_local_config_path

if TYPE_CHECKING:
    from pathlib import Path

    from typer.testing import CliRunner

pytestmark = [pytest.mark.integration]

#: A program that certainly exists on ``PATH`` and is certainly not an editor.
#: The running interpreter satisfies both: naming it proves the refusal turns
#: on *what the program is* rather than on whether it could be found.
_NON_EDITOR_PROGRAM = "python"


def _write_marker_probe(directory: Path, name: str, marker: Path) -> str:
    """Create a real executable that records that it ran, then exits zero.

    Inert by construction: it writes one file inside the test's own temporary
    directory and does nothing else. Called a *probe* rather than a double
    because it is a genuine program on a genuine ``PATH`` - the suite-quality
    guard rejects ``fake``/``stub`` in a test symbol's name, and here the name
    would be wrong as well as banned.

    Args:
        directory: Directory to write the program into. Prepend it to ``PATH``
            so *name* resolves.
        name: Bare program name, used verbatim as the editor command.
        marker: File the program writes when it runs.

    Returns:
        The bare program name, ready to pass as an editor command.
    """
    if sys.platform == "win32":
        script = directory / f"{name}.cmd"
        script.write_text(
            f'@echo off\r\necho ran> "{marker}"\r\nexit /b 0\r\n',
            encoding="utf-8",
        )
    else:
        script = directory / name
        script.write_text(
            f'#!/bin/sh\necho ran > "{marker}"\nexit 0\n', encoding="utf-8"
        )
        script.chmod(0o755)
    return name


def _clean_env(bindir: Path) -> dict[str, str]:
    """Build a CLI environment with *bindir* as the whole of ``PATH``.

    Every editor environment variable is cleared, so a test asserting on one
    rung of the resolution ladder is not answered by the developer's own
    ambient settings. On Windows the system ``PATH`` is kept alongside
    *bindir*, because ``cmd.exe`` has to stay reachable for a ``.cmd`` launcher
    to run at all.

    Args:
        bindir: Directory holding this test's probe programs.

    Returns:
        The environment mapping to hand to the CLI runner's ``env=``.
    """
    import os

    path = str(bindir)
    if sys.platform == "win32":
        path = path + os.pathsep + os.environ.get("PATH", "")
    env = {"PATH": path}
    for name in ("EDITOR", "VISUAL", "VAULTSPEC_EDITOR", GATEWAY_ENV_MARKER):
        env[name] = ""
    return env


def _add_rule(runner: CliRunner, project: Path, name: str) -> None:
    """Create a rule to edit, failing the test if the scaffold did not land.

    Args:
        runner: The CLI runner.
        project: The installed workspace root.
        name: Rule name to create.
    """
    result = runner.invoke(
        app,
        ["--target", str(project), "spec", "rules", "add", name, "--body", "content"],
    )
    assert result.exit_code == 0, result.output


class TestEditorCommandRules:
    """The validation rules themselves, stated directly."""

    def test_a_program_that_is_not_an_editor_is_refused(self) -> None:
        """An untrusted channel may not nominate an arbitrary program.

        This is the whole of the vulnerability class: the editor setting was
        an execution primitive because nothing ever asked what it named.
        """
        with pytest.raises(EditorValidationError) as excinfo:
            validate_editor_command(
                _NON_EDITOR_PROGRAM, source="the --editor flag", trust="untrusted"
            )
        message = str(excinfo.value)
        assert _NON_EDITOR_PROGRAM in message
        assert "not a known text editor" in message

    def test_the_refusal_states_the_rule_and_the_way_out(self) -> None:
        """A refused user is told what is allowed and how to widen it."""
        with pytest.raises(EditorValidationError) as excinfo:
            validate_editor_command(
                _NON_EDITOR_PROGRAM, source="the --editor flag", trust="untrusted"
            )
        assert "vim" in str(excinfo.value)
        assert "code --wait" in str(excinfo.value)
        assert "VAULTSPEC_EDITOR" in excinfo.value.hint

    @pytest.mark.parametrize(
        "command",
        [
            "vim",
            "code --wait",
            "subl -n -w",
            "nvim -f",
            "emacsclient -c",
        ],
    )
    def test_ordinary_editor_settings_are_accepted(self, command: str) -> None:
        """Editors that carry arguments pass: the allowlist screens the program.

        A "no spaces" rule would have been the easy way to stop an argument
        string, and it would have rejected the settings most people actually
        use.
        """
        assert validate_editor_command(
            command, source="the --editor flag", trust="untrusted"
        )

    @pytest.mark.parametrize(
        "command",
        [
            "vim; touch marker",
            "vim && touch marker",
            "vim | tee marker",
            "vim $(touch marker)",
            "vim `touch marker`",
            "vim %USERPROFILE%",
            'vim "argument\nwith-newline"',
            "vim argument\x00with-nul",
        ],
    )
    def test_command_processor_syntax_is_refused(self, command: str) -> None:
        """Metacharacters are refused even behind an allowlisted program.

        The editor is spawned as an argv list, so these could not inject on
        their own - but the Windows batch launcher path necessarily re-parses
        its arguments, and no real editor setting contains them. The last two
        cases are control characters *inside* a token, which tokenization
        preserves rather than splitting on.
        """
        with pytest.raises(EditorValidationError):
            validate_editor_command(
                command, source="the --editor flag", trust="untrusted"
            )

    def test_the_environment_may_name_an_unlisted_editor(self) -> None:
        """The trusted tier is the escape hatch for an editor nobody listed.

        Setting an environment variable for this process already requires the
        ability to run code as this process, so screening it against the
        allowlist would protect nothing and would strand anyone whose editor
        the list has never heard of.
        """
        assert validate_editor_command(
            "/opt/some-obscure-editor --wait",
            source="the $EDITOR environment variable",
            trust="trusted",
        ) == ["/opt/some-obscure-editor", "--wait"]

    def test_a_path_qualified_editor_is_recognized_by_its_program_name(self) -> None:
        """A full path to an allowlisted editor is still that editor."""
        if sys.platform == "win32":
            command = r'"C:\Program Files\Microsoft VS Code\Code.exe" --wait'
        else:
            command = "/usr/local/bin/code --wait"
        assert validate_editor_command(
            command, source="the --editor flag", trust="untrusted"
        )

    def test_program_name_normalization_ignores_directory_and_case(self) -> None:
        """The allowlist is keyed by a normalized bare program name."""
        assert editor_program_name("/usr/bin/VIM") == "vim"
        assert "vim" in EDITOR_PROGRAM_ALLOWLIST

    def test_an_empty_command_is_refused(self) -> None:
        """A whitespace-only setting names nothing and is rejected as such."""
        with pytest.raises(EditorValidationError):
            validate_editor_command(
                "   ", source="the --editor flag", trust="untrusted"
            )


class TestEditorFlagVariant:
    """The per-invocation ``--editor`` value, end to end through the CLI."""

    def test_the_flag_cannot_run_a_program_that_is_not_an_editor(
        self, runner: CliRunner, synthetic_project: Path, tmp_path: Path
    ) -> None:
        """``spec rules edit --editor <program>`` refuses a non-editor.

        The probe is a real, resolvable executable that records having run, so
        an absent marker is positive evidence that nothing was spawned rather
        than evidence that the command merely failed somewhere.
        """
        bindir = tmp_path / "bin"
        bindir.mkdir()
        marker = tmp_path / "flag-probe-ran.txt"
        probe = _write_marker_probe(bindir, "vsprobe-runner", marker)
        _add_rule(runner, synthetic_project, "flag-variant-rule")

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "spec",
                "rules",
                "edit",
                "flag-variant-rule",
                "--editor",
                probe,
            ],
            env=_clean_env(bindir),
        )

        assert result.exit_code == 2, result.output
        assert "not a known text editor" in result.output
        assert not marker.exists(), "the refused editor command was executed anyway"

    def test_an_allowlisted_editor_with_arguments_still_runs(
        self, runner: CliRunner, synthetic_project: Path, tmp_path: Path
    ) -> None:
        """The legitimate workflow is untouched: ``--editor "micro -q"`` works."""
        bindir = tmp_path / "bin"
        bindir.mkdir()
        marker = tmp_path / "editor-ran.txt"
        _write_marker_probe(bindir, "micro", marker)
        _add_rule(runner, synthetic_project, "flag-happy-rule")

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "spec",
                "rules",
                "edit",
                "flag-happy-rule",
                "--editor",
                "micro -q",
            ],
            env=_clean_env(bindir),
        )

        assert result.exit_code == 0, result.output
        assert marker.exists(), "the allowlisted editor was not launched"


class TestPersistedConfigVariant:
    """The ``.vaultspec/config.toml`` ``editor`` key - the same value, delayed."""

    def test_config_set_refuses_to_persist_a_non_editor(
        self, runner: CliRunner, synthetic_project: Path
    ) -> None:
        """``config set editor`` will not write a value it would not run."""
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "config",
                "set",
                "editor",
                _NON_EDITOR_PROGRAM,
            ],
        )

        assert result.exit_code != 0, result.output
        config_path = get_local_config_path(synthetic_project)
        persisted = (
            config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        )
        assert _NON_EDITOR_PROGRAM not in persisted

    def test_a_hand_written_config_is_refused_on_read(
        self, runner: CliRunner, synthetic_project: Path, tmp_path: Path
    ) -> None:
        """Validating only on write would be no defence at all.

        The config file is committed with the workspace, so its value can
        arrive by cloning a repository or by an editor's own hand - neither of
        which goes through ``config set``. The read path has to hold on its
        own, so this test writes the file directly.
        """
        bindir = tmp_path / "bin"
        bindir.mkdir()
        marker = tmp_path / "config-probe-ran.txt"
        probe = _write_marker_probe(bindir, "vsprobe-persisted", marker)
        _add_rule(runner, synthetic_project, "config-variant-rule")

        config_path = get_local_config_path(synthetic_project)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(f'editor = "{probe}"\n', encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "spec",
                "rules",
                "edit",
                "config-variant-rule",
            ],
            env=_clean_env(bindir),
        )

        assert result.exit_code == 2, result.output
        assert "not a known text editor" in result.output
        assert not marker.exists(), "the persisted editor command was executed anyway"

    def test_a_refused_config_value_can_still_be_cleared(
        self, runner: CliRunner, synthetic_project: Path
    ) -> None:
        """A workspace poisoned by a bad value is not bricked by the fix.

        ``config get``, ``config list`` and ``config unset`` keep working on a
        value the edit path refuses, so the person who inherited it can see it
        and remove it.
        """
        config_path = get_local_config_path(synthetic_project)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(f'editor = "{_NON_EDITOR_PROGRAM}"\n', encoding="utf-8")

        shown = runner.invoke(
            app, ["--target", str(synthetic_project), "config", "get", "editor"]
        )
        assert shown.exit_code == 0, shown.output
        assert _NON_EDITOR_PROGRAM in shown.output

        cleared = runner.invoke(
            app, ["--target", str(synthetic_project), "config", "unset", "editor"]
        )
        assert cleared.exit_code == 0, cleared.output
        assert _NON_EDITOR_PROGRAM not in config_path.read_text(encoding="utf-8")


class TestEnvironmentWorkflow:
    """The ordinary terminal workflow, which must not have moved."""

    def test_editor_environment_variable_still_opens_the_editor(
        self, runner: CliRunner, synthetic_project: Path, tmp_path: Path
    ) -> None:
        """``EDITOR=vim`` is the common case and keeps working."""
        bindir = tmp_path / "bin"
        bindir.mkdir()
        marker = tmp_path / "env-editor-ran.txt"
        _write_marker_probe(bindir, "vim", marker)
        _add_rule(runner, synthetic_project, "env-variant-rule")

        env = _clean_env(bindir)
        env["EDITOR"] = "vim"
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "spec",
                "rules",
                "edit",
                "env-variant-rule",
            ],
            env=env,
        )

        assert result.exit_code == 0, result.output
        assert marker.exists(), "the environment-configured editor was not launched"

    def test_an_unlisted_editor_works_through_the_environment(
        self, runner: CliRunner, synthetic_project: Path, tmp_path: Path
    ) -> None:
        """The documented escape hatch is real, not just described.

        Someone whose editor the allowlist has never heard of has to be able
        to keep working; the environment is where they do it.
        """
        bindir = tmp_path / "bin"
        bindir.mkdir()
        marker = tmp_path / "unlisted-editor-ran.txt"
        probe = _write_marker_probe(bindir, "vsprobe-obscure-editor", marker)
        _add_rule(runner, synthetic_project, "unlisted-editor-rule")

        env = _clean_env(bindir)
        env["VAULTSPEC_EDITOR"] = probe
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "spec",
                "rules",
                "edit",
                "unlisted-editor-rule",
            ],
            env=env,
        )

        assert result.exit_code == 0, result.output
        assert marker.exists(), "the environment escape hatch did not launch"


class TestNonInteractiveInvocation:
    """The marker the MCP gateway stamps on every child it spawns."""

    def test_a_marked_invocation_opens_no_editor_from_any_source(
        self, runner: CliRunner, synthetic_project: Path, tmp_path: Path
    ) -> None:
        """A tool-originated call has no terminal, so nothing is launched.

        The editor here is allowlisted and reachable and would run in a
        terminal. The refusal turns on the invocation, not on the value, which
        is what makes it hold even if some other path were to let an editor
        command through the gateway's flag screening.
        """
        bindir = tmp_path / "bin"
        bindir.mkdir()
        marker = tmp_path / "gateway-editor-ran.txt"
        _write_marker_probe(bindir, "nano", marker)
        _add_rule(runner, synthetic_project, "gateway-marked-rule")

        env = _clean_env(bindir)
        env["EDITOR"] = "nano"
        env[GATEWAY_ENV_MARKER] = "1"
        result = runner.invoke(
            app,
            [
                "--target",
                str(synthetic_project),
                "spec",
                "rules",
                "edit",
                "gateway-marked-rule",
            ],
            env=env,
        )

        assert result.exit_code == 2, result.output
        assert "no terminal" in result.output
        assert not marker.exists(), "an editor was launched for a marked invocation"
