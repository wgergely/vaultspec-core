"""Guard against drift between the CLI command surface and `.vaultspec/CLI.md`.

Walks the Typer app tree, invokes ``--help`` on every visible leaf command, and
asserts that every command name and every non-global option name appears in
the handbook. Prevents silent regressions where a new command, subcommand, or
flag lands without a documentation update.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app

if TYPE_CHECKING:
    import typer

pytestmark = [pytest.mark.integration]


_REPO_ROOT = Path(__file__).resolve().parents[4]
_HANDBOOK = _REPO_ROOT / ".vaultspec" / "CLI.md"

# Options carried through the global options table or otherwise inherited on
# essentially every subcommand. Documenting them once at the top of CLI.md is
# sufficient; per-command tables do not need to repeat them.
_GLOBAL_FLAGS: frozenset[str] = frozenset(
    {"--help", "--target", "-t", "--debug", "-d", "--version", "-V"}
)

# Matches long (``--flag``) or short (``-f``) option tokens as they appear in
# Typer's help output tables.
_OPTION_TOKEN = re.compile(r"(?<![A-Za-z0-9_])(-{1,2}[A-Za-z][A-Za-z0-9_-]*)")


def _collect_leaf_command_paths(typer_app: typer.Typer) -> list[tuple[str, ...]]:
    """Return the full command path for every visible leaf command."""

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
            if group.typer_instance is not None:
                _walk(group.typer_instance, group_path)

    _walk(typer_app, ())
    return paths


def _collect_group_paths(typer_app: typer.Typer) -> list[tuple[str, ...]]:
    """Return the path of every visible Typer sub-group (needed for coverage)."""

    paths: list[tuple[str, ...]] = []

    def _walk(current: typer.Typer, prefix: tuple[str, ...]) -> None:
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


def _help_output(cli: CliRunner, path: tuple[str, ...]) -> str:
    result = cli.invoke(app, [*path, "--help"])
    assert result.exit_code == 0, (
        f"`--help` for {' '.join(path) or '<root>'} exited {result.exit_code}:\n"
        f"{result.output}"
    )
    return result.output


def _extract_options(help_text: str) -> set[str]:
    """Extract every option token from a Typer ``--help`` block."""

    options: set[str] = set()
    in_options_block = False
    for raw in help_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("+- Options") or line.startswith("Options:"):
            in_options_block = True
            continue
        if in_options_block and line.startswith("+-"):
            # End of a Typer option box.
            in_options_block = False
            continue
        if not in_options_block:
            continue
        if not line.startswith("|"):
            continue
        # Only the leading option tokens on each row.
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        for cell in cells:
            if not cell.startswith("-"):
                continue
            for match in _OPTION_TOKEN.finditer(cell):
                options.add(match.group(1))
    return options


def test_handbook_exists() -> None:
    assert _HANDBOOK.is_file(), f"Missing handbook at {_HANDBOOK}"


def test_every_cli_command_is_documented() -> None:
    handbook_text = _HANDBOOK.read_text(encoding="utf-8")
    leaf_paths = _collect_leaf_command_paths(app)
    group_paths = _collect_group_paths(app)
    assert leaf_paths, "CLI tree is empty; Typer app failed to register commands"

    missing: list[str] = []
    for path in leaf_paths + group_paths:
        leaf = path[-1]
        full = " ".join(path)
        if leaf in handbook_text or full in handbook_text:
            continue
        missing.append(full)

    assert not missing, (
        "The following CLI commands are registered in code but not mentioned in "
        f"{_HANDBOOK.relative_to(_REPO_ROOT)}:\n  - " + "\n  - ".join(sorted(missing))
    )


def test_every_cli_option_is_documented() -> None:
    handbook_text = _HANDBOOK.read_text(encoding="utf-8")
    cli = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

    missing: list[str] = []
    for path in _collect_leaf_command_paths(app):
        help_text = _help_output(cli, path)
        for option in sorted(_extract_options(help_text)):
            if option in _GLOBAL_FLAGS:
                continue
            if option in handbook_text:
                continue
            missing.append(f"{' '.join(path)}  {option}")

    assert not missing, (
        "The following CLI options appear in `--help` but are not mentioned "
        f"anywhere in {_HANDBOOK.relative_to(_REPO_ROOT)}:\n  - "
        + "\n  - ".join(sorted(missing))
    )
