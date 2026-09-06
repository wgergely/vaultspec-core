"""Unit tests for platform-aware editor command tokenization.

These cover :func:`vaultspec_core.core.editor.validate_editor_command` and the
ladder helper that consumes it, which must not mangle a Windows editor path
(backslash separators, and quotes around a directory containing spaces) before
the :func:`shutil.which` lookup.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.editor import validate_editor_command
from vaultspec_core.core.local_config import _accept_editor_candidate

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]

_TRUSTED_SOURCE = "the $EDITOR environment variable"


def test_native_absolute_path_resolves(tmp_path: Path) -> None:
    """A real editor referenced by its native absolute path resolves.

    On Windows the absolute path uses backslash separators; tokenizing it with
    POSIX quoting rules would consume the backslashes and break the lookup.
    Tokenization disables POSIX mode on Windows so the path reaches
    :func:`shutil.which` intact.
    """
    editor = tmp_path / "myeditor.bat"
    editor.write_text("@echo off\n", encoding="utf-8")
    editor.chmod(0o755)

    assert _accept_editor_candidate(str(editor), _TRUSTED_SOURCE, "trusted") is True


def test_quoted_path_with_spaces_survives_tokenization(tmp_path: Path) -> None:
    """A quoted path containing spaces is one token, quotes consumed.

    Windows tokenization keeps the quotes it split on, so they are stripped
    explicitly; without that the structural rules would reject every editor
    installed under ``Program Files``.
    """
    directory = tmp_path / "my editor dir"
    directory.mkdir()
    editor = directory / "myeditor.bat"
    editor.write_text("@echo off\n", encoding="utf-8")
    editor.chmod(0o755)

    tokens = validate_editor_command(
        f'"{editor}" --wait', source=_TRUSTED_SOURCE, trust="trusted"
    )
    assert tokens == [str(editor), "--wait"]
    assert (
        _accept_editor_candidate(f'"{editor}" --wait', _TRUSTED_SOURCE, "trusted")
        is True
    )


def test_missing_command_falls_through_to_the_next_rung() -> None:
    """A first token that is not on ``PATH`` is a rung that does not apply.

    An editor that is simply not installed on this machine must not become a
    hard failure: the ladder moves on. Only a value that resolves and is then
    refused raises.
    """
    assert (
        _accept_editor_candidate(
            "vaultspec-not-a-real-editor-xyz", _TRUSTED_SOURCE, "trusted"
        )
        is False
    )


def test_blank_command_is_rejected() -> None:
    """A whitespace-only command names nothing and is refused as malformed."""
    from vaultspec_core.core.editor import EditorValidationError

    with pytest.raises(EditorValidationError):
        _accept_editor_candidate("   ", _TRUSTED_SOURCE, "trusted")


def test_windows_extension_is_ignored_when_naming_the_program() -> None:
    """``Code.exe`` and ``code`` are the same program to the allowlist."""
    from vaultspec_core.core.editor import editor_program_name

    name = editor_program_name("Code.exe")
    assert name == ("code" if sys.platform == "win32" else "code.exe")
