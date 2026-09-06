"""Validation and the single spawn site for the interactive text editor.

Opening a document in the user's editor is the one place where this package
hands a *user-supplied command string* to the operating system. Three separate
call sites used to tokenize that string and call :func:`subprocess.run`
themselves, each with slightly different tokenization, and none of them looked
at what the string actually named. This module replaces all three: it owns the
tokenizer, the validation rules, and the spawn.

Trust tiers
-----------

An editor command can arrive from several places, and they are not equally
trustworthy. The distinction this module draws is between channels that a
*remote* or *repository-borne* actor can influence and channels that already
imply local code execution:

``untrusted``
    The per-invocation ``--editor`` value and the project-local
    ``.vaultspec/config.toml`` ``editor`` key. Both travel: the flag is one
    argument on a command line that automation may compose, and the config
    file is committed alongside the workspace, so cloning a repository is
    enough to inherit its value. These must name a *known editor program*
    (:data:`EDITOR_PROGRAM_ALLOWLIST`) in addition to passing the structural
    rules.

``trusted``
    The process environment - ``VAULTSPEC_EDITOR``, ``VISUAL``, ``EDITOR`` -
    and the built-in fallback. Anyone who can set an environment variable for
    this process can already run code as this process, so an allowlist there
    buys nothing and would only stop people from using an editor this module
    has never heard of. These are validated structurally but not against the
    allowlist, which makes the environment the documented escape hatch for an
    editor outside the list.

Editors that carry arguments
----------------------------

``code --wait`` and ``subl -n -w`` are ordinary, correct editor settings, so a
"no spaces" rule is not available. Instead the command is tokenized once, with
platform-appropriate quoting, and the two halves are judged separately: the
*program* token is what the allowlist screens, and *every* token - program and
arguments alike - is screened structurally. A quoted path with spaces
(``"C:\\Program Files\\Microsoft VS Code\\Code.exe" --wait``) survives that
intact, because tokenization happens before either check.

Non-interactive callers
-----------------------

Launching an editor presupposes a terminal in front of a human. When the MCP
gateway spawns the CLI it marks the child process through
:data:`GATEWAY_ENV_MARKER`, and :func:`spawn_editor` refuses outright: no
editor value from any source is honoured for such a call. The marker travels
in the child's environment, which is composed by the gateway itself, so a
caller supplying tool arguments has no channel through which to clear it.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Literal

from .exceptions import EditorResolutionError

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "EDITOR_PROGRAM_ALLOWLIST",
    "GATEWAY_ENV_MARKER",
    "EditorTrust",
    "EditorValidationError",
    "assert_interactive_editing_allowed",
    "editor_program_name",
    "spawn_editor",
    "validate_editor_command",
]

#: Trust tier of the channel an editor command arrived through. See the module
#: docstring: ``"untrusted"`` values are additionally screened against
#: :data:`EDITOR_PROGRAM_ALLOWLIST`.
EditorTrust = Literal["trusted", "untrusted"]

#: Environment variable the MCP gateway sets on every CLI subprocess it spawns,
#: so the child can tell a tool-call invocation from a terminal one. Presence
#: with any non-empty value means "not a terminal"; the value itself carries no
#: meaning. The gateway composes the child environment, so a caller passing
#: tool arguments cannot set, clear, or forge this.
GATEWAY_ENV_MARKER = "VAULTSPEC_MCP_GATEWAY_INVOCATION"

#: Characters no legitimate editor command contains and that a command
#: processor would give meaning to. The editor is always spawned as an argv
#: list rather than through a shell, so these cannot inject on their own - but
#: the Windows ``.cmd`` / ``.bat`` path necessarily routes through
#: ``cmd.exe /c``, which re-parses its arguments, and rejecting the characters
#: outright is cheaper than reasoning about that re-parse.
_FORBIDDEN_CHARACTERS = frozenset(";&|<>`$()!^%*?\"'\n\r\t\x00")

#: File extensions stripped from a program token before the allowlist lookup,
#: so ``Code.exe``, ``code.cmd`` and ``code`` are the same program. Applied on
#: Windows only: on POSIX a file named ``vim.sh`` is not ``vim``.
_WINDOWS_PROGRAM_SUFFIXES = (".exe", ".cmd", ".bat", ".com")

#: Programs an ``--editor`` flag or a project-local config value may name.
#:
#: This is a *known-editor* list, not an integrity check: it stops an untrusted
#: channel from nominating an arbitrary interpreter, archiver, or downloader as
#: "the editor", which is the whole of the privilege the editor setting used to
#: confer. It deliberately does not try to verify that the binary found on
#: ``PATH`` under one of these names really is that editor - a caller who can
#: place a program on your ``PATH`` has already won by a shorter route.
#:
#: Entries are lower-cased program names without a Windows extension. Add to
#: this list rather than widening the rules; an editor that is missing here is
#: still usable through ``VAULTSPEC_EDITOR`` / ``VISUAL`` / ``EDITOR``.
EDITOR_PROGRAM_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Terminal editors
        "amp",
        "dte",
        "e3",
        "ed",
        "editor",
        "elvis",
        "emacs",
        "emacs-nox",
        "emacsclient",
        "gvim",
        "helix",
        "hx",
        "jed",
        "joe",
        "jstar",
        "kak",
        "mcedit",
        "mg",
        "micro",
        "mvim",
        "ne",
        "nvi",
        "nvim",
        "nvim-qt",
        "neovide",
        "nano",
        "pico",
        "sensible-editor",
        "textadept",
        "tilde",
        "vi",
        "view",
        "vim",
        "vim.basic",
        "vim.tiny",
        "vimdiff",
        "vimx",
        # Graphical editors
        "atom",
        "bbedit",
        "brackets",
        "code",
        "code-insiders",
        "code-oss",
        "codium",
        "cursor",
        "geany",
        "gedit",
        "gnome-text-editor",
        "kate",
        "kwrite",
        "lapce",
        "leafpad",
        "mate",
        "mousepad",
        "nedit",
        "notepad",
        "notepad++",
        "notepad2",
        "pluma",
        "positron",
        "scite",
        "subl",
        "sublime",
        "sublime_text",
        "textmate",
        "vscodium",
        "windsurf",
        "xed",
        "zed",
        "zeditor",
        # JetBrains launchers
        "appcode",
        "clion",
        "datagrip",
        "fleet",
        "goland",
        "idea",
        "idea64",
        "phpstorm",
        "pycharm",
        "pycharm64",
        "rider",
        "rubymine",
        "rustrover",
        "studio",
        "webstorm",
    }
)


class EditorValidationError(EditorResolutionError):
    """An editor command was refused before any process was spawned.

    Subclasses :class:`~vaultspec_core.core.exceptions.EditorResolutionError`
    so that every caller which already maps a resolution failure onto its exit
    code keeps working, while a caller that wants to tell "no editor could be
    found" apart from "this editor is not allowed" still can.
    """


def _allowed_programs_hint() -> str:
    """Render the allowlist as a comma-separated line for an error message.

    Returns:
        Every allowed program name, sorted, joined with ``", "``.
    """
    return ", ".join(sorted(EDITOR_PROGRAM_ALLOWLIST))


def _tokenize(command: str, source: str) -> list[str]:
    """Split *command* into argv tokens with platform-appropriate quoting.

    POSIX mode is disabled on Windows exactly as
    :mod:`vaultspec_core.hooks.engine` does it, so a Windows path containing
    backslashes (``C:\\tools\\ed.exe``) is not mangled by POSIX escape
    handling.

    Args:
        command: The raw editor command string.
        source: Human-readable description of where *command* came from, used
            in the error message.

    Returns:
        The tokenized command, program first.

    Raises:
        EditorValidationError: When the command is empty, or when quoting is
            unbalanced so it cannot be tokenized at all.
    """
    try:
        tokens = shlex.split(command, posix=(os.name != "nt"))
    except ValueError as exc:
        msg = (
            f"The editor command from {source} could not be parsed: {exc}. "
            "Check that quotes in the command are balanced."
        )
        raise EditorValidationError(msg) from exc
    if os.name == "nt":
        # ``posix=False`` preserves the quotes it split on, so a Windows path
        # with spaces arrives as ``'"C:\Program Files\...\Code.exe"'``.
        # Strip one balanced pair per token before anything inspects the text,
        # or the structural rules below would reject every quoted path.
        tokens = [
            token[1:-1]
            if len(token) >= 2 and token[0] == '"' and token[-1] == '"'
            else token
            for token in tokens
        ]
    tokens = [token for token in tokens if token]
    if not tokens:
        msg = (
            f"The editor command from {source} is empty. It must name an "
            "editor program, optionally followed by arguments."
        )
        raise EditorValidationError(msg)
    return tokens


def editor_program_name(program_token: str) -> str:
    """Reduce a program token to the bare name the allowlist is keyed by.

    Strips any directory component, lower-cases, and on Windows strips a
    trailing executable extension, so ``C:\\Program Files\\Microsoft VS
    Code\\Code.exe``, ``code.cmd`` and ``code`` all reduce to ``code``.

    Args:
        program_token: The first token of a tokenized editor command.

    Returns:
        The normalized program name.
    """
    name = os.path.basename(program_token).lower()
    if sys.platform == "win32":
        for suffix in _WINDOWS_PROGRAM_SUFFIXES:
            if name.endswith(suffix):
                return name[: -len(suffix)]
    return name


def validate_editor_command(
    command: str,
    *,
    source: str,
    trust: EditorTrust,
) -> list[str]:
    """Validate an editor command and return its argv tokens.

    Applies the structural rules to every token, and - for an ``"untrusted"``
    channel - additionally requires the program token to name a known editor.
    See the module docstring for why the two tiers exist and why arguments are
    screened separately from the program.

    Args:
        command: The raw editor command string, which may carry arguments.
        source: Human-readable description of where *command* came from (for
            example ``"the --editor flag"``), quoted back in error messages so
            a rejected user knows which setting to change.
        trust: The trust tier of that channel.

    Returns:
        The validated argv tokens, program first. The caller appends the file
        path and spawns; no further parsing is needed or permitted.

    Raises:
        EditorValidationError: When the command is empty or unparseable, when
            any token carries a forbidden character, or when an untrusted
            channel names a program outside :data:`EDITOR_PROGRAM_ALLOWLIST`.
            The message always states the rule that was broken.
    """
    tokens = _tokenize(command, source)

    for token in tokens:
        offending = sorted(_FORBIDDEN_CHARACTERS.intersection(token))
        if offending:
            shown = ", ".join(repr(char) for char in offending)
            msg = (
                f"The editor command from {source} contains "
                f"{shown} in {token!r}. An editor command may contain only a "
                "program name or path followed by plain arguments; shell "
                "metacharacters, environment-variable syntax, and control "
                "characters are not allowed, because the editor is launched "
                "directly rather than through a shell."
            )
            raise EditorValidationError(msg)

    if trust == "untrusted":
        program = editor_program_name(tokens[0])
        if program not in EDITOR_PROGRAM_ALLOWLIST:
            msg = (
                f"The editor command from {source} names {program!r}, which "
                "is not a known text editor. Arguments are fine - "
                "'code --wait' and 'subl -n -w' are accepted - but the "
                "program itself must be one of: "
                f"{_allowed_programs_hint()}."
            )
            raise EditorValidationError(
                msg,
                hint=(
                    "To use an editor that is not on that list, set it in the "
                    "environment instead - VAULTSPEC_EDITOR, VISUAL, or "
                    "EDITOR - which is trusted because setting it already "
                    "requires the ability to run code as you."
                ),
            )

    return tokens


def assert_interactive_editing_allowed() -> None:
    """Refuse to open an editor for a non-interactive, tool-originated call.

    The MCP gateway marks every CLI subprocess it spawns (see
    :data:`GATEWAY_ENV_MARKER`). Such a call has no terminal, so an interactive
    edit could never complete anyway; refusing here means that even if some
    future path let an editor value through the gateway's own flag screening,
    the value would still never reach :func:`subprocess.run`.

    Raises:
        EditorValidationError: When the gateway marker is present in the
            environment.
    """
    if os.environ.get(GATEWAY_ENV_MARKER):
        msg = (
            "Interactive editing is not available for this invocation. The "
            "command was started by the MCP gateway, which has no terminal "
            "attached, so no editor can be opened."
        )
        raise EditorValidationError(
            msg,
            hint=(
                "Read or write the file through the dedicated document tools, "
                "or run the edit command yourself in a terminal."
            ),
        )


def spawn_editor(
    command: str,
    file_path: str | Path,
    *,
    source: str = "the resolved editor setting",
) -> int:
    """Validate *command*, then open *file_path* with it and wait.

    This is the only place in the package that spawns an editor. It re-runs the
    structural validation on the already-resolved command even though the
    resolver validated each candidate, because the resolver's guarantee is
    about the *sources* it walked and this function is reachable from callers
    that never went through it.

    The editor is spawned as an argv list, never through a shell. A Windows
    ``.cmd`` / ``.bat`` launcher is the exception the platform forces - those
    are batch scripts and only ``cmd.exe`` can run them - which is why
    :func:`validate_editor_command` rejects the characters ``cmd.exe`` would
    re-interpret.

    Args:
        command: The resolved editor command, which may carry arguments.
        file_path: The file to open. Appended as the final argument.
        source: Human-readable description of where *command* came from, for
            error messages.

    Returns:
        The editor's exit status.

    Raises:
        EditorValidationError: When editing is not available for this
            invocation, or when *command* breaks a structural rule.
        OSError: When the editor process cannot be started.
        subprocess.SubprocessError: When the editor process fails to run.
    """
    assert_interactive_editing_allowed()
    tokens = validate_editor_command(command, source=source, trust="trusted")

    resolved = shutil.which(tokens[0]) or tokens[0]
    argv = [resolved, *tokens[1:], str(file_path)]
    if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat")):
        argv = ["cmd.exe", "/c", *argv]

    completed = subprocess.run(argv, shell=False, check=False)
    return completed.returncode
