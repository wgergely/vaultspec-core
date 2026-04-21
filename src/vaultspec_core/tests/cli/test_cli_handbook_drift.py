"""Guard against drift between the CLI command surface and `.vaultspec/CLI.md`.

Walks the Typer app tree, collects every registered command path, and asserts
that every command name appears somewhere in the handbook. Prevents silent
regressions where a new command or subcommand lands without a documentation
update.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.cli import app

if TYPE_CHECKING:
    import typer

pytestmark = [pytest.mark.integration]


_REPO_ROOT = Path(__file__).resolve().parents[4]
_HANDBOOK = _REPO_ROOT / ".vaultspec" / "CLI.md"


def _collect_command_paths(typer_app: typer.Typer) -> list[tuple[str, ...]]:
    """Return the full command path for every leaf and group in the Typer tree.

    Each entry is a tuple of segments, e.g. ``("vault", "check", "body-links")``.
    Groups themselves are included so a section heading in the handbook can
    satisfy the drift check for them.
    """

    paths: list[tuple[str, ...]] = []

    def _walk(current: typer.Typer, prefix: tuple[str, ...]) -> None:
        for info in current.registered_commands:
            if info.hidden:
                continue
            name = info.name
            if not name and info.callback is not None:
                name = getattr(info.callback, "__name__", None)
            if name:
                paths.append((*prefix, name))
        for group in current.registered_groups:
            name = group.name
            if not name or group.hidden:
                continue
            group_path = (*prefix, name)
            paths.append(group_path)
            if group.typer_instance is not None:
                _walk(group.typer_instance, group_path)

    _walk(typer_app, ())
    return paths


def test_handbook_exists() -> None:
    assert _HANDBOOK.is_file(), f"Missing handbook at {_HANDBOOK}"


def test_every_cli_command_is_documented() -> None:
    handbook_text = _HANDBOOK.read_text(encoding="utf-8")
    paths = _collect_command_paths(app)
    assert paths, "CLI tree is empty; Typer app failed to register commands"

    missing: list[str] = []
    for path in paths:
        leaf = path[-1]
        full = " ".join(path)
        if leaf in handbook_text or full in handbook_text:
            continue
        missing.append(full)

    assert not missing, (
        "The following CLI commands are registered in code but not mentioned in "
        f"{_HANDBOOK.relative_to(_REPO_ROOT)}:\n  - " + "\n  - ".join(sorted(missing))
    )
